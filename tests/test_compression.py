"""Unit tests for PDF chart compression and JPEG embedding."""
import os

import cv2
import numpy as np
import pymupdf

from flip_folder_tool import _render_and_save_chart_worker


def test_chart_worker_compression_size_difference(temp_dir):
    """Verify that compress=True produces smaller PDF files than lossless PNG."""
    output_dir = temp_dir / "output"
    output_dir.mkdir()

    # Create dummy PDF with a detailed noisy/stave image
    dummy_pdf = temp_dir / "sample.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=792, height=612)

    # Draw dummy music staves with realistic scanned paper grain
    np.random.seed(42)
    img = np.random.randint(245, 255, (800, 1000, 3), dtype=np.uint8)
    for y in range(100, 700, 15):
        cv2.line(img, (50, y), (950, y), (30, 30, 30), 2)
    # Add some text/notes
    cv2.putText(img, "SAMPLE NOTATION", (100, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (20, 20, 20), 2)

    _, png_bytes = cv2.imencode(".png", img)
    page.insert_image(page.rect, stream=png_bytes.tobytes())
    doc.save(str(dummy_pdf))
    doc.close()

    # 1. Render lossless PNG
    task_lossless = {
        "pdf_path": str(dummy_pdf),
        "item": {"title": "Test_Lossless", "pages": [(0, "top")]},
        "output_dir": str(output_dir),
        "target_w_pt": 504.0,
        "target_h_pt": 360.0,
        "margin_pt": 14.0,
        "dpi": 150,
        "do_deskew": False,
        "highlight_amber": False,
        "amber_opacity": 0.2,
        "compress": False,
        "quality": 92,
        "chart_hash": "hash_lossless",
    }
    res_lossless = _render_and_save_chart_worker(task_lossless)
    assert res_lossless["success"]
    size_lossless = os.path.getsize(output_dir / "Test_Lossless_5x7.pdf")

    # 2. Render compressed JPEG
    task_compressed = {
        "pdf_path": str(dummy_pdf),
        "item": {"title": "Test_Compressed", "pages": [(0, "top")]},
        "output_dir": str(output_dir),
        "target_w_pt": 504.0,
        "target_h_pt": 360.0,
        "margin_pt": 14.0,
        "dpi": 150,
        "do_deskew": False,
        "highlight_amber": False,
        "amber_opacity": 0.2,
        "compress": True,
        "quality": 85,
        "chart_hash": "hash_compressed",
    }
    res_compressed = _render_and_save_chart_worker(task_compressed)
    assert res_compressed["success"]
    size_compressed = os.path.getsize(output_dir / "Test_Compressed_5x7.pdf")

    assert size_compressed < size_lossless
