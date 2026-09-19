"""Unit tests for command-line arguments and configuration."""
from flip_folder_tool import build_arg_parser


def test_cli_parser_defaults():
    parser = build_arg_parser()
    args = parser.parse_args(["My_Song_Packet.pdf"])

    assert args.inputs == ["My_Song_Packet.pdf"]
    assert args.dpi == 200
    assert args.target_width == 504.0
    assert args.target_height == 360.0
    assert args.margin == 14.0
    assert args.amber_opacity == 0.20
    assert args.no_deskew is False
    assert args.no_master is False
    assert args.no_amber is False
    assert args.jobs is None
    assert args.force is False
    assert args.no_cache is False
    assert args.only is None
    assert args.pages is None


def test_cli_custom_flags():
    parser = build_arg_parser()
    args = parser.parse_args([
        "Trumpet.pdf",
        "--manifest", "my_manifest.csv",
        "--output-dir", "custom_out",
        "--master", "Trumpet_Book.pdf",
        "--instrument", "Solo Trumpet",
        "--no-amber",
        "--no-deskew",
        "--dpi", "300",
        "--margin", "18.0",
        "-j", "6",
        "--force",
        "--no-cache",
        "--only", "Dancing_Queen",
        "--pages", "34-39"
    ])

    assert args.inputs == ["Trumpet.pdf"]
    assert args.manifest == "my_manifest.csv"
    assert args.output_dir == "custom_out"
    assert args.master == "Trumpet_Book.pdf"
    assert args.instrument == "Solo Trumpet"
    assert args.no_amber is True
    assert args.no_deskew is True
    assert args.dpi == 300
    assert args.margin == 18.0
    assert args.jobs == 6
    assert args.force is True
    assert args.no_cache is True
    assert args.only == "Dancing_Queen"
    assert args.pages == "34-39"


def test_cli_empty_inputs():
    parser = build_arg_parser()
    args = parser.parse_args([])
    assert args.inputs == []
    assert args.batch is None
    assert args.compress is False
    assert args.quality == 92
    assert args.auto_catalog is False


def test_cli_batch_and_compress_flags():
    parser = build_arg_parser()
    args = parser.parse_args([
        "--batch", "/path/to/music",
        "--compress",
        "--quality", "85",
        "--auto-catalog"
    ])
    assert args.batch == "/path/to/music"
    assert args.compress is True
    assert args.quality == 85
    assert args.auto_catalog is True

