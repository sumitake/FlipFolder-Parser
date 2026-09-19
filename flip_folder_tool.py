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

import os
import sys
import argparse
import json
import csv
import re
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


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe filenames."""
    s = re.sub(r'[^\w\s-]', '', name).strip()
    return re.sub(r'[-\s]+', '_', s)


def load_manifest(manifest_path: str):
    """
    Load arrangement catalog from JSON or CSV file.
    Returns list of dicts: [{"title": str, "pages": [(int, str), ...]}, ...]
    Page numbers in the manifest are 1-indexed (converted internally to 0-indexed).
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    catalog = []
    if path.suffix.lower() == ".csv":
        by_title = {}
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = sanitize_filename(row.get("title", "").strip())
                page_str = row.get("page", "1").strip()
                try:
                    page_num = int(page_str) - 1
                except ValueError:
                    page_num = 0
                sec = row.get("section", "top").strip().lower()
                if sec not in ("top", "bottom"):
                    sec = "top"
                if title not in by_title:
                    item = {"title": title, "pages": []}
                    by_title[title] = item
                    catalog.append(item)
                by_title[title]["pages"].append((page_num, sec))
    elif path.suffix.lower() == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            title = sanitize_filename(item.get("title", "Untitled"))
            pages = []
            for p in item.get("pages", []):
                if isinstance(p, dict):
                    page_num = int(p.get("page", p.get("page_index", 1))) - 1
                    sec = str(p.get("section", "top")).strip().lower()
                elif isinstance(p, (list, tuple)):
                    page_num = int(p[0]) - 1
                    sec = str(p[1]).strip().lower()
                else:
                    page_num = 0
                    sec = "top"
                if sec not in ("top", "bottom"):
                    sec = "top"
                pages.append((page_num, sec))
            if pages:
                catalog.append({"title": title, "pages": pages})
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


def is_half_sheet_blank(doc, page_idx: int, section: str, dpi: int = 100) -> bool:
    """Check if half-sheet is blank by detecting presence of staves."""
    src_page = doc[page_idx]
    p_rect = src_page.rect
    if section == "top":
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
        
    print(f"Generated manifest templates:")
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
    
    if section == "top":
        crop_box = fitz.Rect(p_rect.x0, p_rect.y0, p_rect.x1, p_rect.y0 + p_rect.height * 0.50)
    else:
        crop_box = fitz.Rect(p_rect.x0, p_rect.y0 + p_rect.height * 0.50, p_rect.x1, p_rect.y1)
        
    pix = src_page.get_pixmap(clip=crop_box, dpi=dpi)
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
            center = (w // 2, h // 2)
            rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
            img = cv2.warpAffine(img, rot_mat, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
    # Scale coordinates based on DPI
    scale = dpi / 200.0
    left_strip_bound = int(208 * scale)
    right_strip_bound = int(1680 * scale)
    
    # 2. Binary mask and trim outer cut/binder guides
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
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
    active_cols = np.where(col_ink > int(25 * scale))[0]
    x_min = max(left_strip_bound, active_cols[0] - int(12 * scale)) if len(active_cols) > 0 else left_strip_bound
    x_max = min(right_strip_bound, active_cols[-1] + int(12 * scale)) if len(active_cols) > 0 else right_strip_bound
    
    # Active content vertical boundaries
    row_ink = np.sum(thresh[:, x_min:x_max] > 0, axis=1)
    active_rows = np.where(row_ink > int(30 * scale))[0]
    y_min = max(int(5 * scale), active_rows[0] - int(10 * scale)) if len(active_rows) > 0 else int(5 * scale)
    
    # 3. Detect staves and cleanly crop above copyright text
    kernel_staff = cv2.getStructuringElement(cv2.MORPH_RECT, (int(40 * scale), 1))
    staves = cv2.morphologyEx(thresh[:, x_min:x_max], cv2.MORPH_OPEN, kernel_staff)
    staff_rows = np.where(np.sum(staves > 0, axis=1) > int(200 * scale))[0]
    
    min_staff_span = int(20 * scale)
    if len(staff_rows) > 0:
        diffs = np.diff(staff_rows)
        split_pts = np.where(diffs > int(15 * scale))[0] + 1
        clusters = np.split(staff_rows, split_pts)
        staff_clusters = [c for c in clusters if (c[-1] - c[0] >= min_staff_span)]
        if len(staff_clusters) > 0:
            y_staff_low = staff_clusters[-1][-1]
            sub = thresh[y_staff_low:min(h, y_staff_low + int(70 * scale)), x_min:x_max]
            sub_ink = np.sum(sub > 0, axis=1)
            search_range = sub_ink[int(8 * scale):min(len(sub_ink), int(25 * scale))]
            valley_offset = int(8 * scale) + int(np.argmin(search_range)) if len(search_range) > 0 else int(12 * scale)
            y_max = min(h - int(5 * scale), y_staff_low + valley_offset + int(3 * scale))
        else:
            y_max = min(h - int(5 * scale), active_rows[-1] + int(12 * scale)) if len(active_rows) > 0 else (h - int(5 * scale))
    else:
        y_max = min(h - int(5 * scale), active_rows[-1] + int(12 * scale)) if len(active_rows) > 0 else (h - int(5 * scale))
        
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


def process_packet(pdf_path: str, manifest_path: str = None, output_dir: str = None,
                   master_pdf_path: str = None, instrument_name: str = None,
                   target_w_pt: float = DEFAULT_TARGET_W_PT,
                   target_h_pt: float = DEFAULT_TARGET_H_PT,
                   margin_pt: float = DEFAULT_MARGIN_PT,
                   dpi: int = DEFAULT_DPI, do_deskew: bool = True,
                   highlight_amber: bool = True, amber_opacity: float = 0.20,
                   generate_master: bool = True):
    """
    Main extraction pipeline for a single instrument PDF packet.
    """
    pdf_path = str(Path(pdf_path).resolve())
    pdf_stem = Path(pdf_path).stem
    
    if not instrument_name:
        instrument_name = pdf_stem.replace("_", " ").strip()
    inst_safe = sanitize_filename(instrument_name)
    
    if output_dir is None:
        output_dir = f"Extracted_5x7_Charts_{inst_safe}"
    os.makedirs(output_dir, exist_ok=True)
    
    if master_pdf_path is None and generate_master:
        master_pdf_path = f"{inst_safe}_Complete_5x7_FlipFolder.pdf"
        
    # Resolve manifest
    if manifest_path is None:
        manifest_path = find_default_manifest(pdf_path)
        
    doc = fitz.open(pdf_path)
    
    if manifest_path and Path(manifest_path).exists():
        print(f"[{instrument_name}] Loading arrangement manifest: {manifest_path}")
        catalog = load_manifest(manifest_path)
    else:
        print(f"[{instrument_name}] No manifest provided or found. Running in auto-detection mode...")
        catalog = []
        chart_num = 1
        for p_idx in range(len(doc)):
            for sec in ["top", "bottom"]:
                if not is_half_sheet_blank(doc, p_idx, sec, dpi=100):
                    catalog.append({
                        "title": f"Chart_{chart_num:02d}",
                        "pages": [(p_idx, sec)]
                    })
                    chart_num += 1
        print(f"[{instrument_name}] Auto-detected {len(catalog)} active half-sheets.")
        
    master_pdf = fitz.open() if generate_master else None
    total_files = 0
    total_pages = 0
    
    print("=" * 65)
    print(f"Processing Instrument: {instrument_name}")
    print(f"Source PDF: {Path(pdf_path).name} ({len(doc)} pages)")
    print(f"Catalog: {len(catalog)} arrangements")
    print(f"Target format: 5\" x 7\" ({target_w_pt:.0f} x {target_h_pt:.0f} pt)")
    print(f"Output directory: {output_dir}")
    print("=" * 65)
    
    for idx, item in enumerate(catalog, 1):
        title = item["title"]
        pages_to_extract = item["pages"]
        out_pdf = fitz.open()
        
        for p_idx, section in pages_to_extract:
            if p_idx >= len(doc):
                print(f"  [Warning] Page {p_idx + 1} exceeds document page count ({len(doc)}). Skipping.")
                continue
                
            chart_img = process_half_sheet(
                doc, p_idx, section, dpi=dpi, do_deskew=do_deskew,
                highlight_amber=highlight_amber, amber_opacity=amber_opacity
            )
            
            # Encode image to PNG stream
            success, enc_img = cv2.imencode(".png", chart_img)
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
            
            # Add to individual title PDF
            page_individual = out_pdf.new_page(width=target_w_pt, height=target_h_pt)
            page_individual.insert_image(dest_rect, stream=img_bytes)
            
            # Add to master compiled collection
            if master_pdf is not None:
                page_master = master_pdf.new_page(width=target_w_pt, height=target_h_pt)
                page_master.insert_image(dest_rect, stream=img_bytes)
                
            total_pages += 1
            
        out_filename = f"{title}_5x7.pdf"
        out_path = os.path.join(output_dir, out_filename)
        out_pdf.save(out_path, garbage=4, deflate=True)
        out_pdf.close()
        total_files += 1
        
        page_suffix = f"({len(pages_to_extract)} page{'s' if len(pages_to_extract) > 1 else ''})"
        print(f"[{idx:02d}/{len(catalog)}] Generated {out_filename:<35} {page_suffix}")
        
    doc.close()
    
    if master_pdf is not None:
        master_pdf.save(master_pdf_path, garbage=4, deflate=True)
        master_pdf.close()
        master_size_mb = os.path.getsize(master_pdf_path) / (1024 * 1024)
        print("-" * 65)
        print(f"Master Collection: {master_pdf_path} ({total_pages} pages, {master_size_mb:.2f} MB)")
        
    print("-" * 65)
    print(f"Completed '{instrument_name}': {total_files} individual PDFs in '{output_dir}/'")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(
        description="Extract and standardize marching band sheet music packets into 5x7 flip-folder charts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a packet using default arrangements catalog:
  python flip_folder_tool.py "Clarinet 1.pdf"

  # Process with specific CSV manifest:
  python flip_folder_tool.py "Trumpet 1.pdf" --manifest arrangements.csv

  # Process multiple instrument parts in batch:
  python flip_folder_tool.py "Clarinet 1.pdf" "Trumpet 1.pdf" "Flute.pdf"

  # Scan a new packet and generate editable manifest templates:
  python flip_folder_tool.py "Mellophone.pdf" --generate-manifest
        """
    )
    parser.add_argument("inputs", nargs="*", help="Path(s) to input PDF sheet music packet(s).")
    parser.add_argument("-i", "--input", action="append", dest="opt_inputs", help="Alternative way to specify input PDF(s).")
    parser.add_argument("-m", "--manifest", help="Path to arrangement catalog (JSON or CSV). Defaults to arrangements.json/csv if present.")
    parser.add_argument("-o", "--output-dir", help="Directory for individual 5x7 PDFs (defaults to Extracted_5x7_Charts_<Instrument>).")
    parser.add_argument("--master", help="Output path for master compiled PDF (defaults to <Instrument>_Complete_5x7_FlipFolder.pdf).")
    parser.add_argument("--instrument", help="Override instrument name (otherwise derived from filename).")
    parser.add_argument("--generate-manifest", action="store_true", help="Scan PDF, detect active half-sheets, and output starter manifest templates.")
    parser.add_argument("--no-master", action="store_true", help="Do not generate the compiled master flip-folder PDF.")
    parser.add_argument("--no-amber", action="store_true", help="Disable amber highlight on performance cut boxes.")
    parser.add_argument("--amber-opacity", type=float, default=0.20, help="Opacity for cut box highlight (default: 0.20).")
    parser.add_argument("--no-deskew", action="store_true", help="Disable automatic staff line de-skewing.")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="Rendering DPI (default: 200).")
    parser.add_argument("--target-width", type=float, default=DEFAULT_TARGET_W_PT, help="Width in points (default: 504.0 pt = 7.0 in).")
    parser.add_argument("--target-height", type=float, default=DEFAULT_TARGET_H_PT, help="Height in points (default: 360.0 pt = 5.0 in).")
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN_PT, help="Safe border margin in points (default: 14.0 pt).")

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
            generate_master=not args.no_master
        )

if __name__ == "__main__":
    main()
