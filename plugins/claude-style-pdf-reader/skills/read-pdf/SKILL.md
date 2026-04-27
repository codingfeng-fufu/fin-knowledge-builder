# Claude-Style PDF Reader

Use this plugin when the user wants to read, summarize, inspect, or analyze a
PDF in a way that stays close to Claude Code's routing behavior.

## Default workflow

Run the plugin wrapper instead of the lower-level scripts directly:

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py <pdf-path>
```

The wrapper applies Claude-style routing automatically:

- If the PDF is short enough, it keeps the whole-document path.
- If the PDF is longer than Claude Code would inline, it automatically switches
  to `--auto-pages`.
- If the user asks for explicit page ranges, pass `--pages`.

## Examples

Summarize a whole paper with automatic batching when needed:

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/paper.pdf --pretty
```

Read only selected pages:

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/paper.pdf --pages 1-3 --pretty
```

Force the Moonshot file-extract shim only when the user explicitly wants to
bypass Claude-style page routing:

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/paper.pdf --force-file-extract --pretty
```

Inspect the route decision without sending the PDF:

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/paper.pdf --inspect-route
```

Ask for a compact structured summary schema:

```bash
python plugins/claude-style-pdf-reader/scripts/read_pdf.py path/to/paper.pdf --output-mode summary-json --pretty
```

Run the local HTTP wrapper:

```bash
python plugins/claude-style-pdf-reader/scripts/http_service.py
```

Then call:

- `POST /inspect-route`
- `POST /analyze`
- `POST /sessions/load-pdf`
- `POST /sessions/ask`

## Notes

- Backend model: `kimi-k2.5`
- The underlying implementation lives in `reconstructions/pdf_reader_python/`
- Prefer `--auto-pages` for long PDFs when the user wants a full-paper summary
- Prefer `--pages` when the user wants a targeted section or tighter token
  control
- `summary-json` adds one extra structuring request after the main analysis
- `examples/python_client.py` shows a minimal stdlib Python caller
- `examples/python_session_client.py` shows the Claude-style load-then-ask flow
