"""Unit tests for master PDF assembly and Table of Contents generation."""
import pymupdf

from flip_folder_tool import assemble_master_pdf


def test_assemble_master_pdf_toc(temp_dir):
    output_dir = temp_dir / "charts"
    output_dir.mkdir()

    # Create dummy 5x7 charts
    chart1_path = output_dir / "Song_One_5x7.pdf"
    doc1 = pymupdf.open()
    doc1.new_page(width=504.0, height=360.0)
    doc1.save(str(chart1_path))
    doc1.close()

    chart2_path = output_dir / "Song_Two_5x7.pdf"
    doc2 = pymupdf.open()
    doc2.new_page(width=504.0, height=360.0)
    doc2.new_page(width=504.0, height=360.0)
    doc2.save(str(chart2_path))
    doc2.close()

    catalog = [
        {"title": "Song_One", "raw_title": "Song One (Opener)"},
        {"title": "Song_Two"},
    ]

    master_path = temp_dir / "Master_ALL.pdf"
    pages, size_mb = assemble_master_pdf(str(output_dir), catalog, str(master_path))

    assert pages == 3
    assert size_mb > 0
    assert master_path.exists()

    # Verify TOC outline bookmarks
    master_doc = pymupdf.open(str(master_path))
    assert len(master_doc) == 3

    toc = master_doc.get_toc()
    # Expected:
    # Level 1: Song One (Opener) on page 1
    # Level 1: Song Two on page 2
    # Level 2: Page 1 on page 2
    # Level 2: Page 2 on page 3
    assert len(toc) == 4
    assert toc[0] == [1, "Song One (Opener)", 1]
    assert toc[1] == [1, "Song Two", 2]
    assert toc[2] == [2, "Page 1", 2]
    assert toc[3] == [2, "Page 2", 3]
    master_doc.close()
