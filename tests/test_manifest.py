"""Unit tests for loading and discovering arrangement manifests."""
import pytest

from flip_folder_tool import find_default_manifest, load_manifest


def test_load_manifest_csv(temp_dir, sample_csv_content):
    csv_file = temp_dir / "arrangements.csv"
    csv_file.write_text(sample_csv_content, encoding="utf-8")

    catalog = load_manifest(str(csv_file))
    assert len(catalog) == 4

    # Check first song (0-indexed internally: page 1 -> 0)
    assert catalog[0]["title"] == "Song_One"
    assert catalog[0]["pages"] == [(0, "top")]

    # Check second song
    assert catalog[1]["title"] == "Song_Two"
    assert catalog[1]["pages"] == [(0, "bottom")]

    # Check multi-part song
    assert catalog[2]["title"] == "Multi_Part"
    assert catalog[2]["pages"] == [(1, "top"), (1, "bottom")]

    # Check final song
    assert catalog[3]["title"] == "Final_Song"
    assert catalog[3]["pages"] == [(2, "top")]


def test_load_manifest_json(temp_dir, sample_json_content):
    json_file = temp_dir / "arrangements.json"
    json_file.write_text(sample_json_content, encoding="utf-8")

    catalog = load_manifest(str(json_file))
    assert len(catalog) == 2

    assert catalog[0]["title"] == "Song_Alpha"
    assert catalog[0]["pages"] == [(0, "top")]

    assert catalog[1]["title"] == "Song_Beta"
    assert catalog[1]["pages"] == [(1, "top"), (2, "top")]


def test_load_manifest_full_page_section(temp_dir):
    csv_file = temp_dir / "arrangements.csv"
    csv_file.write_text(
        "title,page,section\nFull_Chart,1,full\nSingle_Chart,2,single\nAll_Chart,3,all\n",
        encoding="utf-8",
    )
    catalog = load_manifest(str(csv_file))
    assert len(catalog) == 3
    assert catalog[0]["pages"] == [(0, "full")]
    assert catalog[1]["pages"] == [(1, "single")]
    assert catalog[2]["pages"] == [(2, "all")]

    json_file = temp_dir / "arrangements.json"
    json_file.write_text(
        '[{"title": "Full_Song", "pages": [{"page": 4, "section": "full"}]}]',
        encoding="utf-8",
    )
    catalog_json = load_manifest(str(json_file))
    assert len(catalog_json) == 1
    assert catalog_json[0]["pages"] == [(3, "full")]


def test_load_manifest_file_not_found(temp_dir):
    missing_path = temp_dir / "nonexistent.csv"
    with pytest.raises(FileNotFoundError):
        load_manifest(str(missing_path))


def test_load_manifest_unsupported_format(temp_dir):
    bad_file = temp_dir / "arrangements.txt"
    bad_file.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported manifest format"):
        load_manifest(str(bad_file))


def test_find_default_manifest(temp_dir):
    pdf_path = temp_dir / "Clarinet_1.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")

    # Specific manifest matching stem
    specific_manifest = temp_dir / "Clarinet_1_arrangements.csv"
    specific_manifest.write_text("title,page,section\n", encoding="utf-8")

    found = find_default_manifest(str(pdf_path))
    assert found == str(specific_manifest)
