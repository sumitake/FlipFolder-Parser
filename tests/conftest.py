"""Shared fixtures and setup for FlipFolder-Parser test suite."""
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test artifacts."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def sample_csv_content():
    """Sample CSV manifest content with single-page and multi-page arrangements."""
    return """title,page,section
Song_One,1,top
Song_Two,1,bottom
Multi_Part,2,top
Multi_Part,2,bottom
Final_Song,3,top
"""


@pytest.fixture
def sample_json_content():
    """Sample JSON manifest content."""
    return """[
  {
    "title": "Song_Alpha",
    "pages": [{"page": 1, "section": "top"}]
  },
  {
    "title": "Song_Beta",
    "pages": [
      {"page": 2, "section": "top"},
      {"page": 3, "section": "top"}
    ]
  }
]"""
