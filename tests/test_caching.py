"""Unit tests for content hashing and incremental caching subsystem."""
import time

from flip_folder_tool import (
    compute_chart_hash,
    is_chart_cached,
    load_cache,
    parse_page_ranges,
    save_cache,
)


def test_parse_page_ranges():
    assert parse_page_ranges("1,3,5-8") == {1, 3, 5, 6, 7, 8}
    assert parse_page_ranges(" 10 - 12 , 15 ") == {10, 11, 12, 15}
    assert parse_page_ranges("4") == {4}
    assert parse_page_ranges("") == set()


def test_compute_chart_hash_determinism(temp_dir):
    fake_pdf = temp_dir / "sample.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 dummy content for hash test")

    item = {"title": "Test_Song", "pages": [(0, "top")]}
    params1 = {"dpi": 200, "target_w_pt": 504.0, "do_deskew": True}
    params2 = {"dpi": 200, "target_w_pt": 504.0, "do_deskew": True}

    hash1 = compute_chart_hash(str(fake_pdf), item, params1)
    hash2 = compute_chart_hash(str(fake_pdf), item, params2)
    assert hash1 == hash2

    # Invalidate by parameter change (e.g. DPI)
    params_diff_dpi = {"dpi": 300, "target_w_pt": 504.0, "do_deskew": True}
    hash_diff_dpi = compute_chart_hash(str(fake_pdf), item, params_diff_dpi)
    assert hash1 != hash_diff_dpi

    # Invalidate by section change
    item_diff_sec = {"title": "Test_Song", "pages": [(0, "bottom")]}
    hash_diff_sec = compute_chart_hash(str(fake_pdf), item_diff_sec, params1)
    assert hash1 != hash_diff_sec


def test_cache_save_and_load(temp_dir):
    cache_data = {
        "Test_Song": {
            "hash": "abcdef123456",
            "pages": 1,
            "filename": "Test_Song_5x7.pdf",
            "updated_at": time.time(),
        }
    }
    save_cache(str(temp_dir), cache_data)
    loaded = load_cache(str(temp_dir))
    assert loaded == cache_data


def test_is_chart_cached(temp_dir):
    cache = {
        "Song_A": {"hash": "validhash123", "pages": 1}
    }

    # Case 1: PDF does not exist on disk
    assert not is_chart_cached(str(temp_dir), "Song_A", "validhash123", cache)

    # Case 2: PDF exists and hash matches
    pdf_file = temp_dir / "Song_A_5x7.pdf"
    pdf_file.write_bytes(b"%PDF-1.4")
    assert is_chart_cached(str(temp_dir), "Song_A", "validhash123", cache)

    # Case 3: Hash mismatch
    assert not is_chart_cached(str(temp_dir), "Song_A", "different_hash", cache)

    # Case 4: Title not in cache
    assert not is_chart_cached(str(temp_dir), "Song_B", "anyhash", cache)
