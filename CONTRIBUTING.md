# Contributing

Thanks for helping improve FlipFolder-Parser.

## Development Setup

Install development tools:

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-dev.txt
```

Run the local checks:

```bash
ruff check .
python3 -m py_compile flip_folder_tool.py build_flip_folder_pack.py
pytest -q
```

## Pull Requests

- Keep runtime dependencies minimal. The tool relies on standard library Python, `pymupdf`, `opencv-python`, and `numpy`.
- Never commit copyrighted sheet music, scanned band packets, or personal documents. Use synthetic or redacted pages for tests.
- Update documentation for user-facing changes.
- Add or update unit tests in `tests/` for behavior changes.

## Security Reports

Report suspected vulnerabilities through GitHub private vulnerability reporting. Do not open a public issue for security-sensitive reports.
