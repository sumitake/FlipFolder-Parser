"""Unit tests for string and filename sanitization."""
from flip_folder_tool import sanitize_filename


def test_sanitize_basic():
    assert sanitize_filename("Johnny B Goode") == "Johnny_B_Goode"


def test_sanitize_special_characters():
    assert sanitize_filename("Ain't Nothin' (Wrong) / With That!") == "Aint_Nothin_Wrong_With_That"


def test_sanitize_whitespace_and_hyphens():
    assert sanitize_filename("  Seven -- Nation   Army  ") == "Seven_Nation_Army"


def test_sanitize_numeric_titles():
    assert sanitize_filename("25 or 6 to 4") == "25_or_6_to_4"
