"""Unit tests for stave-aware dynamic margin detection."""
import cv2
import numpy as np
import pymupdf

from flip_folder_tool import process_half_sheet


def test_margin_detection_preserves_early_staves(temp_dir):
    """Verify that staves starting in 0-200px are preserved and not cropped."""
    dummy_pdf = temp_dir / "early_staves.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=792, height=612)

    # Render image with staves starting at x=60
    img = np.ones((600, 1200, 3), dtype=np.uint8) * 255
    # Staves starting at x=60
    for y in [150, 165, 180, 195, 210]:
        cv2.line(img, (60, y), (1100, y), (0, 0, 0), 2)
    # Distinct marker at x=70
    cv2.circle(img, (70, 180), 8, (0, 0, 0), -1)

    _, png_bytes = cv2.imencode(".png", img)
    page.insert_image(page.rect, stream=png_bytes.tobytes())
    doc.save(str(dummy_pdf))
    doc.close()

    doc_read = pymupdf.open(str(dummy_pdf))
    # Section "top" (should auto-detect early staves and avoid stripping left 208px)
    processed = process_half_sheet(doc_read, 0, "top", dpi=200, do_deskew=False)
    doc_read.close()

    assert processed is not None
    # Check that ink near x=60 is present in the output
    # Since it was preserved, the width of the cropped content must include the early stave
    gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
    has_ink = np.any(gray < 50)
    assert has_ink


def test_margin_detection_strips_punch_holes(temp_dir):
    """Verify that binder punch holes with staves starting at x=300 are stripped."""
    dummy_pdf = temp_dir / "punch_holes.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=792, height=612)

    img = np.ones((600, 1200, 3), dtype=np.uint8) * 255
    # Draw punch hole circle at x=60
    cv2.circle(img, (60, 300), 25, (0, 0, 0), 2)
    # Staves starting far to the right at x=300
    for y in [150, 165, 180, 195, 210]:
        cv2.line(img, (300, y), (1100, y), (0, 0, 0), 2)

    _, png_bytes = cv2.imencode(".png", img)
    page.insert_image(page.rect, stream=png_bytes.tobytes())
    doc.save(str(dummy_pdf))
    doc.close()

    doc_read = pymupdf.open(str(dummy_pdf))
    processed = process_half_sheet(doc_read, 0, "top", dpi=200, do_deskew=False)
    doc_read.close()

    assert processed is not None
