#!/usr/bin/env python3
"""
Flip-Folder Sheet Music Extraction & Standardization Tool
=========================================================
Processes marching band sheet music packets (scanned or digital half-sheets)
into standardized 5" x 7" landscape PDF charts for flip folders and tablets.

Features:
  - Auto-deskew staves using Hough line transform.
  - Cleanly trims outer binder margins, punch holes, and divider cut lines.
  - Automatically strips bottom publisher copyright fine print while preserving
    all musical notation, dynamic markings (ff, fff), and rehearsal marks.
  - Detects boxed performance cuts and highlights them in translucent amber.
  - Unifies multi-page arrangements into single multi-page PDF files.
  - Assembles a unified master flip-folder PDF collection.
  - Fully decoupled arrangement catalog (JSON or CSV) usable across any instrument part.
  - Auto-detects blank half-sheets and can generate manifest templates.

Usage Examples:
  # Process a single instrument part using default arrangements.json/csv
  python flip_folder_tool.py "Clarinet 1.pdf"

  # Process another instrument part with custom manifest
  python flip_folder_tool.py "Trumpet 1.pdf" --manifest arrangements.csv

  # Batch process multiple instruments
  python flip_folder_tool.py "Clarinet 1.pdf" "Trumpet 1.pdf" "Flute.pdf"

  # Generate a manifest template for a new/unseen PDF packet
  python flip_folder_tool.py "Trombone 1.pdf" --generate-manifest
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
import pymupdf as fitz

DEFAULT_TARGET_W_PT = 504.0   # 7.0 inches landscape (72 pt/in)
DEFAULT_TARGET_H_PT = 360.0   # 5.0 inches landscape (72 pt/in)
DEFAULT_MARGIN_PT = 14.0       # ~0.20 inch safe border margin
DEFAULT_DPI = 200

# Color for performance cut box overlay (BGR: #FFD54F amber -> B=79, G=213, R=255)
AMBER_BGR = (79, 213, 255)
CACHE_FILENAME = ".flipfolder_cache.json"


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe filenames."""
    s = re.sub(r'[^\w\s-]', '', name).strip()
    return re.sub(r'[-\s]+', '_', s)


def parse_page_ranges(page_spec: str) -> set[int]:
    """Parse page spec (e.g. '1,3,5-8') into 1-based page integer set."""
    pages = set()
    for part in page_spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            pages.update(range(int(start_s), int(end_s) + 1))
        else:
            pages.add(int(part))
    return pages


def compute_chart_hash(pdf_path: str, item: dict, params: dict) -> str:
    """
    Compute a deterministic SHA256 hash representing the source PDF state,
    chart pages/sections, and extraction hyperparameters.
    """
    source_files = set()
    if "file" in item and item["file"]:
        source_files.add(str(Path(item["file"]).resolve()))
    for p in item.get("pages", []):
        if len(p) > 2 and p[2]:
            source_files.add(str(Path(p[2]).resolve()))
    if not source_files:
        source_files.add(str(Path(pdf_path).resolve()))

    file_stats = []
    for sf in sorted(source_files):
        if os.path.exists(sf):
            st = os.stat(sf)
            file_stats.append({"path": sf, "mtime_ns": st.st_mtime_ns, "size": st.st_size})

    payload = {
        "files": file_stats,
        "title": item["title"],
        "pages": [[int(p[0]), str(p[1]), str(p[2]) if len(p) > 2 else ""] for p in item["pages"]],
        "params": {
            "target_w_pt": float(params.get("target_w_pt", DEFAULT_TARGET_W_PT)),
            "target_h_pt": float(params.get("target_h_pt", DEFAULT_TARGET_H_PT)),
            "margin_pt": float(params.get("margin_pt", DEFAULT_MARGIN_PT)),
            "dpi": int(params.get("dpi", DEFAULT_DPI)),
            "do_deskew": bool(params.get("do_deskew", True)),
            "highlight_amber": bool(params.get("highlight_amber", True)),
            "amber_opacity": float(params.get("amber_opacity", 0.20)),
        },
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cache_file_path(output_dir: str) -> Path:
    """Return path to cache manifest inside output directory."""
    return Path(output_dir) / CACHE_FILENAME


def load_cache(output_dir: str) -> dict:
    """Load cached extraction metadata from disk if available."""
    cache_path = get_cache_file_path(output_dir)
    if cache_path.exists():
        try:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(output_dir: str, cache_data: dict) -> None:
    """Safely persist cache metadata to disk via atomic write."""
    cache_path = get_cache_file_path(output_dir)
    try:
        tmp_path = cache_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)
        os.replace(tmp_path, cache_path)
    except Exception:
        pass


def is_chart_cached(output_dir: str, title: str, chart_hash: str, cache: dict) -> bool:
    """Check if individual chart PDF exists and matches the computed hash."""
    out_filename = f"{title}_5x7.pdf"
    out_path = Path(output_dir) / out_filename
    if not out_path.exists():
        return False
    entry = cache.get(title)
    if not entry or not isinstance(entry, dict):
        return False
    return entry.get("hash") == chart_hash


def load_manifest(manifest_path: str):
    """
    Load arrangement catalog from JSON or CSV file.
    Returns list of dicts: [{"title": str, "pages": [(int, str), ...]}, ...]
    Page numbers in the manifest are 1-indexed (converted internally to 0-indexed).
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    VALID_SECTIONS = ("top", "bottom", "full", "single", "all", "clean_top", "clean_bottom", "halftime_top", "halftime_bottom")
    catalog = []
    if path.suffix.lower() == ".csv":
        by_title = {}
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = sanitize_filename(row.get("title", "").strip())
                page_str = row.get("page", "1").strip()
                try:
                    page_num = int(page_str) - 1
                except ValueError:
                    page_num = 0
                sec = row.get("section", "top").strip().lower()
                if sec not in VALID_SECTIONS:
                    sec = "top"
                file_opt = row.get("file", "").strip() or None
                if title not in by_title:
                    item = {"title": title, "pages": []}
                    if file_opt:
                        item["file"] = file_opt
                    by_title[title] = item
                    catalog.append(item)
                if file_opt:
                    by_title[title]["pages"].append((page_num, sec, file_opt))
                else:
                    by_title[title]["pages"].append((page_num, sec))
    elif path.suffix.lower() == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            title = sanitize_filename(item.get("title", "Untitled"))
            item_file = item.get("file", None)
            pages = []
            for p in item.get("pages", []):
                if isinstance(p, dict):
                    page_num = int(p.get("page", p.get("page_index", 1))) - 1
                    sec = str(p.get("section", "top")).strip().lower()
                    p_file = p.get("file", item_file)
                elif isinstance(p, (list, tuple)):
                    page_num = int(p[0]) - 1
                    sec = str(p[1]).strip().lower()
                    p_file = p[2] if len(p) > 2 else item_file
                else:
                    page_num = 0
                    sec = "top"
                    p_file = item_file
                if sec not in VALID_SECTIONS:
                    sec = "top"
                if p_file:
                    pages.append((page_num, sec, p_file))
                else:
                    pages.append((page_num, sec))
            if pages:
                cat_entry = {"title": title, "pages": pages}
                if item_file:
                    cat_entry["file"] = item_file
                catalog.append(cat_entry)
    else:
        raise ValueError(f"Unsupported manifest format '{path.suffix}'. Use .json or .csv.")

    return catalog


def find_default_manifest(pdf_path: str):
    """
    Search for default manifest file in order of preference:
    1. <pdf_stem>_arrangements.json / .csv
    2. <pdf_dir>/arrangements.json / .csv
    3. ./arrangements.json / .csv
    """
    p = Path(pdf_path)
    candidates = [
        p.parent / f"{p.stem}_arrangements.json",
        p.parent / f"{p.stem}_arrangements.csv",
        p.parent / "arrangements.json",
        p.parent / "arrangements.csv",
        Path("arrangements.json"),
        Path("arrangements.csv"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def calculate_deskew_angle(gray: np.ndarray) -> float:
    """Detect average stave tilt angle using Hough lines."""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120, minLineLength=150, maxLineGap=12)
    if lines is None:
        return 0.0
    angles = []
    for line in lines:
        line = np.squeeze(line)
        if len(line) == 4:
            x1, y1, x2, y2 = line
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if abs(angle) < 6.0:
                angles.append(angle)
    return float(np.median(angles)) if angles else 0.0


def deskew_image(img: np.ndarray, angle: float) -> np.ndarray:
    """Rotate image to correct skew angle using Lanczos interpolation."""
    if abs(angle) <= 0.05:
        return img
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, rot_mat, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)



def is_half_sheet_blank(doc, page_idx: int, section: str, dpi: int = 100) -> bool:
    """Check if half-sheet is blank by detecting presence of staves."""
    src_page = doc[page_idx]
    p_rect = src_page.rect
    if section in ("full", "single", "all"):
        crop_box = p_rect
    elif section == "top":
        crop_box = fitz.Rect(p_rect.x0, p_rect.y0, p_rect.x1, p_rect.y0 + p_rect.height * 0.50)
    else:
        crop_box = fitz.Rect(p_rect.x0, p_rect.y0 + p_rect.height * 0.50, p_rect.x1, p_rect.y1)
        
    pix = src_page.get_pixmap(clip=crop_box, dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.h, pix.w, pix.n))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if pix.n >= 3 else img[:, :, 0]
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    thresh[:, :int(100 * dpi / 200)] = 0
    thresh[:, int(800 * dpi / 100):] = 0
    
    kernel_staff = cv2.getStructuringElement(cv2.MORPH_RECT, (int(20 * dpi / 100), 1))
    staves = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_staff)
    staff_rows = np.where(np.sum(staves > 0, axis=1) > (100 * dpi / 100))[0]
    if len(staff_rows) == 0:
        return True
    diffs = np.diff(staff_rows)
    split_pts = np.where(diffs > 10)[0] + 1
    clusters = np.split(staff_rows, split_pts)
    valid_staves = [c for c in clusters if (c[-1] - c[0] >= int(8 * dpi / 100))]
    return len(valid_staves) == 0


def generate_manifest_template(pdf_path: str, output_path: str = None):
    """Scan PDF and generate a starter JSON and CSV manifest."""
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    catalog = []
    csv_rows = []
    
    chart_num = 1
    for p_idx in range(total_pages):
        for sec in ["top", "bottom"]:
            if is_half_sheet_blank(doc, p_idx, sec):
                continue
            title = f"Song_{chart_num:02d}"
            catalog.append({
                "title": title,
                "pages": [{"page": p_idx + 1, "section": sec}]
            })
            csv_rows.append({
                "title": title,
                "page": p_idx + 1,
                "section": sec
            })
            chart_num += 1
            
    doc.close()
    
    base = Path(output_path) if output_path else Path(pdf_path).parent / f"{Path(pdf_path).stem}_arrangements"
    json_out = base.with_suffix(".json")
    csv_out = base.with_suffix(".csv")
    
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
    with open(csv_out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "page", "section"])
        writer.writeheader()
        writer.writerows(csv_rows)
        
    print("Generated manifest templates:")
    print(f"  JSON: {json_out}")
    print(f"  CSV:  {csv_out}")
    print(f"Found {len(catalog)} active half-sheets across {total_pages} document pages.")


def process_half_sheet(doc, page_idx: int, section: str, dpi: int = DEFAULT_DPI,
                       do_deskew: bool = True, highlight_amber: bool = True,
                       amber_opacity: float = 0.20) -> np.ndarray:
    """
    Renders, deskews, crops, and highlights a single half-sheet music chart.
    """
    src_page = doc[page_idx]
    p_rect = src_page.rect
    is_full_page = section in ("full", "single", "all")
    is_clean = section in ("clean_top", "clean_bottom", "halftime_top", "halftime_bottom")

    if is_full_page:
        crop_box = p_rect
    elif section in ("top", "clean_top", "halftime_top"):
        crop_box = fitz.Rect(p_rect.x0, p_rect.y0, p_rect.x1, p_rect.y0 + p_rect.height * 0.50)
    else:
        crop_box = fitz.Rect(p_rect.x0, p_rect.y0 + p_rect.height * 0.50, p_rect.x1, p_rect.y1)

    pix = src_page.get_pixmap(clip=crop_box, dpi=72 if is_full_page else dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.h, pix.w, pix.n))
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    elif pix.n == 1:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    h, w, _ = img.shape
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1. Correct skew
    if do_deskew:
        angle = calculate_deskew_angle(gray)
        if abs(angle) > 0.05:
            img = deskew_image(img, angle)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Scale coordinates based on DPI
    scale = (h / 900.0) if (is_full_page or is_clean) else (dpi / 200.0)

    # 2. Binary mask and trim outer cut/binder guides
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    if is_full_page or is_clean:
        left_strip_bound = int(w * 0.015)
        right_strip_bound = int(w * 0.985)
        thresh[:int(h * 0.015), :] = 0
        thresh[int(h * 0.985):, :] = 0
        thresh[:, :left_strip_bound] = 0
        thresh[:, right_strip_bound:] = 0
    else:
        left_strip_bound = int(208 * scale)
        right_strip_bound = int(1680 * scale)
        thresh[:, :left_strip_bound] = 0   # Strip binder punch guides and left margin cut lines
        thresh[:, right_strip_bound:] = 0  # Strip far right outer page edge

        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (int(100 * scale), 1))

        # Remove top horizontal divider cutline if present
        top_limit = int(50 * scale)
        lines_top = cv2.morphologyEx(thresh[:top_limit, :], cv2.MORPH_OPEN, kernel_h)
        hit_top = np.where(np.sum(lines_top > 0, axis=1) > int(200 * scale))[0]
        if len(hit_top) > 0:
            thresh[:hit_top[-1] + int(3 * scale), :] = 0

        # Remove bottom horizontal divider cutline if present
        bot_limit = int(60 * scale)
        lines_bot = cv2.morphologyEx(thresh[h - bot_limit:, :], cv2.MORPH_OPEN, kernel_h)
        hit_bot = np.where(np.sum(lines_bot > 0, axis=1) > int(200 * scale))[0]
        if len(hit_bot) > 0:
            thresh[h - bot_limit + hit_bot[0] - int(2 * scale):, :] = 0

    # Active content horizontal boundaries
    col_ink = np.sum(thresh > 0, axis=0)
    active_cols = np.where(col_ink > (int(5 * scale) if (is_full_page or is_clean) else int(25 * scale)))[0]
    x_min = max(left_strip_bound, active_cols[0] - int(10 * scale)) if len(active_cols) > 0 else left_strip_bound
    x_max = min(right_strip_bound, active_cols[-1] + int(10 * scale)) if len(active_cols) > 0 else right_strip_bound

    # Active content vertical boundaries
    row_ink = np.sum(thresh[:, x_min:x_max] > 0, axis=1)
    active_rows = np.where(row_ink > (int(10 * scale) if (is_full_page or is_clean) else int(30 * scale)))[0]
    y_min = max(int(5 * scale), active_rows[0] - int(10 * scale)) if len(active_rows) > 0 else int(5 * scale)

    # 3. Detect staves and cleanly crop above copyright text
    kernel_staff = cv2.getStructuringElement(cv2.MORPH_RECT, (int(w * 0.025 if (is_full_page or is_clean) else 40 * scale), 1))
    staves = cv2.morphologyEx(thresh[:, x_min:x_max], cv2.MORPH_OPEN, kernel_staff)
    staff_rows = np.where(np.sum(staves > 0, axis=1) > int(w * 0.08 if (is_full_page or is_clean) else 200 * scale))[0]
    
    min_staff_span = int(15 * scale)
    if len(staff_rows) > 0:
        diffs = np.diff(staff_rows)
        split_pts = np.where(diffs > int(10 * scale))[0] + 1
        clusters = np.split(staff_rows, split_pts)
        staff_clusters = [c for c in clusters if (c[-1] - c[0] >= min_staff_span)]
        if len(staff_clusters) > 0:
            y_staff_low = staff_clusters[-1][-1]
            sub = thresh[y_staff_low:h, x_min:x_max]
            ink_profile = np.sum(sub > 0, axis=1)
            nz = np.where(ink_profile > int(10 * scale))[0]
            gaps = np.where(np.diff(nz) > int(5 * scale))[0]
            if len(gaps) > 0:
                y_max = min(h - int(5 * scale), y_staff_low + (nz[gaps[0]] + nz[gaps[0] + 1]) // 2)
            else:
                search_range = ink_profile[int(8 * scale):min(len(ink_profile), int(25 * scale))]
                valley_offset = int(8 * scale) + int(np.argmin(search_range)) if len(search_range) > 0 else int(12 * scale)
                y_max = min(h - int(5 * scale), y_staff_low + valley_offset + int(3 * scale))
        else:
            y_max = min(h - int(5 * scale), active_rows[-1] + int(10 * scale)) if len(active_rows) > 0 else (h - int(5 * scale))
    else:
        y_max = min(h - int(5 * scale), active_rows[-1] + int(10 * scale)) if len(active_rows) > 0 else (h - int(5 * scale))
        
    cropped_img = img[y_min:y_max, x_min:x_max].copy()
    
    # 4. Detect and highlight boxed performance cuts in translucent amber
    if highlight_amber:
        c_gray = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2GRAY)
        _, c_thresh = cv2.threshold(c_gray, 80, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(c_thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        c_h, c_w = c_gray.shape
        min_box_h = int(85 * scale)
        max_box_h = int(145 * scale)
        candidate_boxes = []
        for cnt in contours:
            x_c, y_c, w_c, h_c = cv2.boundingRect(cnt)
            if w_c > c_w * 0.18 and min_box_h <= h_c <= max_box_h:
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
                if 4 <= len(approx) <= 7:
                    candidate_boxes.append((x_c, y_c, w_c, h_c))
                    
        # Deduplicate overlapping/concentric contours
        dedup_boxes = []
        candidate_boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
        for b in candidate_boxes:
            x_c, y_c, w_c, h_c = b
            dup = False
            for dx, dy, dw, dh in dedup_boxes:
                inter_x1 = max(x_c, dx)
                inter_y1 = max(y_c, dy)
                inter_x2 = min(x_c + w_c, dx + dw)
                inter_y2 = min(y_c + h_c, dy + dh)
                if inter_x2 > inter_x1 and inter_y2 > inter_y1:
                    inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
                    box_area = w_c * h_c
                    if inter_area / box_area > 0.50:
                        dup = True
                        break
            if not dup:
                dedup_boxes.append(b)
                
        if dedup_boxes:
            overlay = cropped_img.copy()
            for x_c, y_c, w_c, h_c in dedup_boxes:
                cv2.rectangle(overlay, (x_c, y_c), (x_c + w_c, y_c + h_c), AMBER_BGR, -1)
            cropped_img = cv2.addWeighted(overlay, amber_opacity, cropped_img, 1.0 - amber_opacity, 0)
            
    return cropped_img


def _render_and_save_chart_worker(task: dict) -> dict:
    """
    Worker function executed in parallel worker processes to extract,
    process, and save an individual 5x7 chart PDF.
    """
    pdf_path = task["pdf_path"]
    item = task["item"]
    title = item["title"]
    pages_to_extract = item["pages"]
    output_dir = task["output_dir"]
    dpi = task["dpi"]
    do_deskew = task["do_deskew"]
    highlight_amber = task["highlight_amber"]
    amber_opacity = task["amber_opacity"]
    target_w_pt = task["target_w_pt"]
    target_h_pt = task["target_h_pt"]
    margin_pt = task["margin_pt"]
    chart_hash = task["chart_hash"]

    out_filename = f"{title}_5x7.pdf"
    out_path = os.path.join(output_dir, out_filename)
    tmp_out_path = out_path + ".tmp"

    try:
        opened_docs = {}
        out_pdf = fitz.open()

        for p_entry in pages_to_extract:
            p_idx = p_entry[0]
            section = p_entry[1]
            p_file = p_entry[2] if (len(p_entry) > 2 and p_entry[2]) else item.get("file", pdf_path)
            
            if p_file not in opened_docs:
                opened_docs[p_file] = fitz.open(p_file)
            doc = opened_docs[p_file]

            if p_idx >= len(doc):
                continue

            chart_img = process_half_sheet(
                doc, p_idx, section, dpi=dpi, do_deskew=do_deskew,
                highlight_amber=highlight_amber, amber_opacity=amber_opacity
            )

            # Encode image to PNG stream
            success, enc_img = cv2.imencode(".png", chart_img)
            if not success:
                raise RuntimeError(f"Failed to encode image for {title} (page {p_idx + 1})")
            img_bytes = enc_img.tobytes()

            # Dimension calculations for 5x7 canvas
            avail_w = target_w_pt - (2 * margin_pt)
            avail_h = target_h_pt - (2 * margin_pt)
            img_h, img_w, _ = chart_img.shape
            img_aspect = img_w / img_h
            avail_aspect = avail_w / avail_h

            if img_aspect > avail_aspect:
                draw_w = avail_w
                draw_h = avail_w / img_aspect
            else:
                draw_h = avail_h
                draw_w = avail_h * img_aspect

            x_offset = margin_pt + (avail_w - draw_w) / 2.0
            y_offset = margin_pt + (avail_h - draw_h) / 2.0
            dest_rect = fitz.Rect(x_offset, y_offset, x_offset + draw_w, y_offset + draw_h)

            page_individual = out_pdf.new_page(width=target_w_pt, height=target_h_pt)
            page_individual.insert_image(dest_rect, stream=img_bytes)

        out_pdf.save(tmp_out_path, garbage=4, deflate=True)
        out_pdf.close()
        for d in opened_docs.values():
            d.close()
        os.replace(tmp_out_path, out_path)

        return {
            "title": title,
            "filename": out_filename,
            "pages": len(pages_to_extract),
            "chart_hash": chart_hash,
            "success": True,
            "error": None
        }
    except Exception as e:
        if os.path.exists(tmp_out_path):
            try:
                os.remove(tmp_out_path)
            except OSError:
                pass
        for d in opened_docs.values():
            try:
                d.close()
            except Exception:
                pass
        return {
            "title": title,
            "filename": out_filename,
            "pages": 0,
            "chart_hash": chart_hash,
            "success": False,
            "error": str(e)
        }


def assemble_master_pdf(output_dir: str, catalog: list, master_pdf_path: str) -> tuple[int, float]:
    """
    Fast zero-reencode master PDF assembly by splicing individual chart PDFs.
    Returns (total_pages, file_size_mb).
    """
    master_pdf = fitz.open()
    total_pages = 0
    for item in catalog:
        out_filename = f"{item['title']}_5x7.pdf"
        chart_path = os.path.join(output_dir, out_filename)
        if os.path.exists(chart_path):
            chart_doc = fitz.open(chart_path)
            master_pdf.insert_pdf(chart_doc)
            total_pages += len(chart_doc)
            chart_doc.close()
        else:
            print(f"  [Warning] Missing chart PDF for master collection: {out_filename}")

    tmp_master_path = master_pdf_path + ".tmp"
    master_pdf.save(tmp_master_path, garbage=4, deflate=True)
    master_pdf.close()
    os.replace(tmp_master_path, master_pdf_path)

    size_mb = os.path.getsize(master_pdf_path) / (1024 * 1024)
    return total_pages, size_mb


def process_packet(pdf_path: str, manifest_path: str = None, output_dir: str = None,
                   master_pdf_path: str = None, instrument_name: str = None,
                   target_w_pt: float = DEFAULT_TARGET_W_PT,
                   target_h_pt: float = DEFAULT_TARGET_H_PT,
                   margin_pt: float = DEFAULT_MARGIN_PT,
                   dpi: int = DEFAULT_DPI, do_deskew: bool = True,
                   highlight_amber: bool = True, amber_opacity: float = 0.20,
                   generate_master: bool = True,
                   jobs: int = None, force: bool = False, no_cache: bool = False,
                   only: str = None, pages: str = None):
    """
    Main extraction pipeline for a single instrument PDF packet.
    Supports incremental caching, parallel processing, and selective filtering.
    """
    t_start = time.time()
    pdf_path = str(Path(pdf_path).resolve())
    pdf_stem = Path(pdf_path).stem
    pdf_dir = Path(pdf_path).parent

    if not instrument_name:
        instrument_name = pdf_stem.strip()
    inst_name = instrument_name

    if output_dir is None:
        output_dir = str(pdf_dir / inst_name)
    else:
        output_dir = str(Path(output_dir).resolve())
    os.makedirs(output_dir, exist_ok=True)

    if master_pdf_path is None and generate_master:
        master_pdf_path = str(pdf_dir / f"{inst_name} - ALL.pdf")

    # Resolve manifest
    if manifest_path is None:
        manifest_path = find_default_manifest(pdf_path)

    doc = fitz.open(pdf_path)
    num_doc_pages = len(doc)

    if manifest_path and Path(manifest_path).exists():
        print(f"[{instrument_name}] Loading arrangement manifest: {manifest_path}")
        catalog = load_manifest(manifest_path)
    else:
        print(f"[{instrument_name}] No manifest provided or found. Running in auto-detection mode...")
        catalog = []
        chart_num = 1
        for p_idx in range(num_doc_pages):
            for sec in ["top", "bottom"]:
                if not is_half_sheet_blank(doc, p_idx, sec, dpi=100):
                    catalog.append({
                        "title": f"Chart_{chart_num:02d}",
                        "pages": [(p_idx, sec)]
                    })
                    chart_num += 1
        print(f"[{instrument_name}] Auto-detected {len(catalog)} active half-sheets.")
    doc.close()

    raw_catalog_count = len(catalog)

    # Selective filtering
    if only:
        try:
            pattern = re.compile(only, re.IGNORECASE)
            catalog = [item for item in catalog if pattern.search(item["title"])]
        except re.error:
            catalog = [item for item in catalog if only.lower() in item["title"].lower()]

    if pages:
        try:
            allowed_pages = parse_page_ranges(pages)
            catalog = [
                item for item in catalog
                if any((p_idx + 1) in allowed_pages for p_idx, _ in item["pages"])
            ]
        except ValueError as e:
            print(f"  [Warning] Invalid --pages format '{pages}': {e}. Processing all catalog pages.")

    if not catalog:
        print(f"[{instrument_name}] No arrangements matched filtering criteria (out of {raw_catalog_count}).")
        return

    # Worker count
    if jobs is None or jobs <= 0:
        cpu_cnt = os.cpu_count() or 4
        jobs = min(cpu_cnt, 8)

    cache = {} if no_cache else load_cache(output_dir)
    params = {
        "target_w_pt": target_w_pt,
        "target_h_pt": target_h_pt,
        "margin_pt": margin_pt,
        "dpi": dpi,
        "do_deskew": do_deskew,
        "highlight_amber": highlight_amber,
        "amber_opacity": amber_opacity,
    }

    filter_info = f" (filtered from {raw_catalog_count})" if len(catalog) != raw_catalog_count else ""
    cache_status = "Disabled" if no_cache else ("Bypassed (--force)" if force else "Enabled")

    print("=" * 65)
    print(f"Processing Instrument: {instrument_name}")
    print(f"Source PDF: {Path(pdf_path).name} ({num_doc_pages} pages)")
    print(f"Catalog: {len(catalog)} arrangements{filter_info}")
    print(f"Execution: {jobs} worker{'s' if jobs > 1 else ''} | Caching: {cache_status}")
    print(f"Target format: 5\" x 7\" ({target_w_pt:.0f} x {target_h_pt:.0f} pt)")
    print(f"Output directory: {output_dir}")
    print("=" * 65)

    results = {}
    pending_tasks = []

    for idx, item in enumerate(catalog, 1):
        title = item["title"]
        chart_hash = compute_chart_hash(pdf_path, item, params)
        out_filename = f"{title}_5x7.pdf"

        if not force and not no_cache and is_chart_cached(output_dir, title, chart_hash, cache):
            p_cnt = len(item["pages"])
            p_sfx = f"({p_cnt} page{'s' if p_cnt > 1 else ''})"
            print(f"[{idx:02d}/{len(catalog)}] [Cached]    {out_filename:<35} {p_sfx}")
            results[idx] = {
                "title": title,
                "filename": out_filename,
                "pages": p_cnt,
                "chart_hash": chart_hash,
                "cached": True,
                "success": True,
                "error": None,
            }
        else:
            task_payload = {
                "pdf_path": pdf_path,
                "item": item,
                "output_dir": output_dir,
                "target_w_pt": target_w_pt,
                "target_h_pt": target_h_pt,
                "margin_pt": margin_pt,
                "dpi": dpi,
                "do_deskew": do_deskew,
                "highlight_amber": highlight_amber,
                "amber_opacity": amber_opacity,
                "chart_hash": chart_hash,
            }
            pending_tasks.append((idx, task_payload))

    # Execute pending tasks
    if pending_tasks:
        effective_workers = min(jobs, len(pending_tasks))
        if effective_workers > 1:
            with ProcessPoolExecutor(max_workers=effective_workers) as executor:
                future_to_idx = {
                    executor.submit(_render_and_save_chart_worker, task): idx
                    for idx, task in pending_tasks
                }
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    res = future.result()
                    results[idx] = res
                    p_sfx = f"({res['pages']} page{'s' if res['pages'] > 1 else ''})"
                    if res["success"]:
                        print(f"[{idx:02d}/{len(catalog)}] Generated   {res['filename']:<35} {p_sfx}")
                    else:
                        print(f"[{idx:02d}/{len(catalog)}] [Error]     {res['filename']:<35} - {res['error']}")
        else:
            for idx, task in pending_tasks:
                res = _render_and_save_chart_worker(task)
                results[idx] = res
                p_sfx = f"({res['pages']} page{'s' if res['pages'] > 1 else ''})"
                if res["success"]:
                    print(f"[{idx:02d}/{len(catalog)}] Generated   {res['filename']:<35} {p_sfx}")
                else:
                    print(f"[{idx:02d}/{len(catalog)}] [Error]     {res['filename']:<35} - {res['error']}")

    # Save cache
    if not no_cache:
        for res in results.values():
            if res.get("success"):
                cache[res["title"]] = {
                    "hash": res["chart_hash"],
                    "pages": res["pages"],
                    "filename": res["filename"],
                    "updated_at": time.time(),
                }
        save_cache(output_dir, cache)

    # Assemble master PDF
    if generate_master and master_pdf_path:
        t_master_start = time.time()
        total_master_pages, master_size_mb = assemble_master_pdf(output_dir, catalog, master_pdf_path)
        t_master_elapsed = time.time() - t_master_start
        print("-" * 65)
        print(f"Master Collection: {master_pdf_path} ({total_master_pages} pages, {master_size_mb:.2f} MB) [Assembled in {t_master_elapsed:.2f}s]")

    t_elapsed = time.time() - t_start
    cached_count = sum(1 for r in results.values() if r.get("cached"))
    rendered_count = sum(1 for r in results.values() if not r.get("cached") and r.get("success"))
    print("-" * 65)
    print(f"Completed '{instrument_name}': {len(results)} charts ({cached_count} cached, {rendered_count} rendered) in {t_elapsed:.2f}s")
    print("=" * 65)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build and configure the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Extract and standardize marching band sheet music packets into 5x7 flip-folder charts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fast incremental run (skips unchanged charts automatically):
  python flip_folder_tool.py "Clarinet 1.pdf"

  # Force re-rendering all charts using 4 parallel workers:
  python flip_folder_tool.py "Clarinet 1.pdf" --force -j 4

  # Extract only a specific song:
  python flip_folder_tool.py "Clarinet 1.pdf" --only "Dancing_Queen"

  # Process arrangements spanning specific pages:
  python flip_folder_tool.py "Clarinet 1.pdf" --pages 34-39

  # Process multiple instrument parts in batch:
  python flip_folder_tool.py "Clarinet 1.pdf" "Trumpet 1.pdf" "Flute.pdf"

  # Scan a new packet and generate editable manifest templates:
  python flip_folder_tool.py "Mellophone.pdf" --generate-manifest
        """
    )
    parser.add_argument("inputs", nargs="*", help="Path(s) to input PDF sheet music packet(s).")
    parser.add_argument("-i", "--input", action="append", dest="opt_inputs", help="Alternative way to specify input PDF(s).")
    parser.add_argument("-m", "--manifest", help="Path to arrangement catalog (JSON or CSV). Defaults to arrangements.json/csv if present.")
    parser.add_argument("-o", "--output-dir", help="Directory for individual 5x7 PDFs (defaults to '<Instrument>').")
    parser.add_argument("--master", help="Output path for master compiled PDF (defaults to '<Instrument> - ALL.pdf').")
    parser.add_argument("--instrument", help="Override instrument name (otherwise derived from filename).")
    parser.add_argument("--generate-manifest", action="store_true", help="Scan PDF, detect active half-sheets, and output starter manifest templates.")
    parser.add_argument("--no-master", action="store_true", help="Do not generate the compiled master flip-folder PDF.")
    parser.add_argument("-j", "--jobs", type=int, default=None, help="Number of parallel worker processes (default: up to 8 CPU cores).")
    parser.add_argument("-f", "--force", action="store_true", help="Force re-generation of all charts, bypassing the incremental cache.")
    parser.add_argument("--no-cache", action="store_true", help="Disable reading and writing the .flipfolder_cache.json file.")
    parser.add_argument("--only", "--filter", dest="only", help="Filter arrangements by title substring or regex (e.g. --only Dancing_Queen).")
    parser.add_argument("--pages", help="Filter arrangements by 1-based page numbers (e.g. --pages 34-39 or --pages 1,2,5).")
    parser.add_argument("--no-amber", action="store_true", help="Disable amber highlight on performance cut boxes.")
    parser.add_argument("--amber-opacity", type=float, default=0.20, help="Opacity for cut box highlight (default: 0.20).")
    parser.add_argument("--no-deskew", action="store_true", help="Disable automatic staff line de-skewing.")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="Rendering DPI (default: 200).")
    parser.add_argument("--target-width", type=float, default=DEFAULT_TARGET_W_PT, help="Width in points (default: 504.0 pt = 7.0 in).")
    parser.add_argument("--target-height", type=float, default=DEFAULT_TARGET_H_PT, help="Height in points (default: 360.0 pt = 5.0 in).")
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN_PT, help="Safe border margin in points (default: 14.0 pt).")
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    all_inputs = []
    if args.inputs:
        all_inputs.extend(args.inputs)
    if args.opt_inputs:
        all_inputs.extend(args.opt_inputs)

    if not all_inputs:
        parser.print_help()
        sys.exit(1)

    for pdf_file in all_inputs:
        if not os.path.exists(pdf_file):
            print(f"Error: Input file '{pdf_file}' not found.")
            continue

        if args.generate_manifest:
            generate_manifest_template(pdf_file, args.manifest)
            continue

        process_packet(
            pdf_path=pdf_file,
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            master_pdf_path=args.master,
            instrument_name=args.instrument,
            target_w_pt=args.target_width,
            target_h_pt=args.target_height,
            margin_pt=args.margin,
            dpi=args.dpi,
            do_deskew=not args.no_deskew,
            highlight_amber=not args.no_amber,
            amber_opacity=args.amber_opacity,
            generate_master=not args.no_master,
            jobs=args.jobs,
            force=args.force,
            no_cache=args.no_cache,
            only=args.only,
            pages=args.pages
        )

if __name__ == "__main__":
    main()
