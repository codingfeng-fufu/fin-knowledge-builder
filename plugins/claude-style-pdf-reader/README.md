# Claude-Style PDF Reader

Repo-local Codex plugin for reading PDFs with a Claude Code-like routing
strategy while using `kimi-k2.5` as the analysis backend.

## What it does

- Mirrors Claude Code's page-routing behavior for PDFs.
- Refuses whole-document reads for PDFs over 10 pages unless you explicitly
  provide `--pages` or choose automatic batching.
- Supports automatic page batching and final aggregation for long PDFs.
- Uses the validated pure Python pipeline in
  `reconstructions/pdf_reader_python/`.

## Main entrypoint

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/file.pdf
```

Useful options:

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/file.pdf --pages 1-3
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/file.pdf --auto-pages
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/file.pdf --force-file-extract
```

## Stable JSON mode

The wrapper defaults to a stable plugin-oriented JSON envelope:

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/file.pdf --output-mode plugin-json --pretty
```

Use a compact structured summary schema:

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/file.pdf --output-mode summary-json --pretty
```

This mode performs one additional lightweight structuring pass on the generated
answer so the final output has fixed summary fields.

Use raw underlying output only when you need the lower-level transport result:

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/file.pdf --output-mode raw --pretty
```

## HTTP Service

Start the local HTTP wrapper:

```bash
python plugins/claude-style-pdf-reader/scripts/http_service.py
```

Routes:

- `GET /healthz`
- `POST /inspect-route`
- `POST /analyze`
- `POST /sessions/load-pdf`
- `POST /sessions/ask`
- `POST /sessions/inspect`

Example request body:

```json
{
  "pdf_path": "D:/docs/paper.pdf",
  "output_mode": "summary-json"
}
```

### Session-style flow

Load once:

```json
{
  "pdf_path": "D:/docs/paper.pdf",
  "auto_pages": true
}
```

Then ask repeatedly:

```json
{
  "session_id": "your-session-id",
  "question": "What is the core method?",
  "output_mode": "summary-json"
}
```

## Python Client Example

Example client is provided at:

```bash
python plugins/claude-style-pdf-reader/examples/python_client.py
python plugins/claude-style-pdf-reader/examples/python_session_client.py
```
