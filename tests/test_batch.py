"""Unit tests for batch processing across directories."""
import json

import cv2
import numpy as np
import pymupdf

from flip_folder_tool import batch_process_directory


def test_batch_process_directory_empty(temp_dir):
    res = batch_process_directory(str(temp_dir))
    assert res == []


def test_batch_process_directory_multiple_instruments(temp_dir):
    # Create two instrument PDFs
    insts = ["Trumpet 1", "Trombone 1"]
    for inst in insts:
        pdf_path = temp_dir / f"{inst}.pdf"
        doc = pymupdf.open()
        p = doc.new_page(width=792, height=612)
        # Draw staves
        img = np.ones((600, 1000, 3), dtype=np.uint8) * 255
        for y in [100, 115, 130, 145, 160]:
            cv2.line(img, (100, y), (900, y), (0, 0, 0), 2)
        _, png = cv2.imencode(".png", img)
        p.insert_image(p.rect, stream=png.tobytes())
        doc.save(str(pdf_path))
        doc.close()

        # Create manifest
        manifest_path = temp_dir / f"{inst}_arrangements.json"
        cat = [{"title": "March_One", "pages": [{"page": 1, "section": "top"}]}]
        manifest_path.write_text(json.dumps(cat))

    results = batch_process_directory(
        batch_dir=str(temp_dir),
        generate_master=True,
        compress=True,
        quality=90,
    )

    assert len(results) == 2
    for r in results:
        assert r["instrument"] in insts
        assert r["charts_count"] == 1
        assert r["master_pages"] == 1
        assert (temp_dir / r["instrument"]).exists()
        assert (temp_dir / f"{r['instrument']} - ALL.pdf").exists()
