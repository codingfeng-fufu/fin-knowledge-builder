from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4


SCRIPT_DIR = Path(__file__).resolve().parent
WRAPPER_PATH = SCRIPT_DIR / "read_pdf.py"


def load_wrapper():
    module_name = "claude_style_pdf_reader_http_wrapper"
    spec = importlib.util.spec_from_file_location(module_name, WRAPPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load wrapper from {WRAPPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


wrapper = load_wrapper()
SESSIONS: dict[str, dict] = {}


def resolve_pdf_path(pdf_path: str) -> Path:
    resolved = Path(pdf_path).expanduser().resolve()
    if not resolved.exists():
        raise ValueError(f"PDF path does not exist: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"PDF path is not a file: {resolved}")
    return resolved


def request_to_argv(payload: dict) -> list[str]:
    pdf_path = payload.get("pdf_path")
    if not isinstance(pdf_path, str) or not pdf_path.strip():
        raise ValueError("Field 'pdf_path' is required and must be a non-empty string.")

    argv = [pdf_path]
    scalar_flags = {
        "pages": "--pages",
        "prompt": "--prompt",
        "system": "--system",
        "model": "--model",
        "base_url": "--base-url",
        "api_key": "--api-key",
        "max_tokens": "--max-tokens",
        "temperature": "--temperature",
        "top_p": "--top-p",
        "output_mode": "--output-mode",
        "auto_batch_size": "--auto-batch-size",
        "write_json": "--write-json",
        "write_reader_json": "--write-reader-json",
        "prompt_file": "--prompt-file",
        "system_file": "--system-file",
    }
    boolean_flags = {
        "auto_pages": "--auto-pages",
        "force_file_extract": "--force-file-extract",
        "no_default_prompt": "--no-default-prompt",
        "no_image_optimize": "--no-image-optimize",
        "pretty": "--pretty",
        "full": "--full",
    }

    for key, flag in scalar_flags.items():
        value = payload.get(key)
        if value is None:
            continue
        argv.extend([flag, str(value)])

    for key, flag in boolean_flags.items():
        if bool(payload.get(key)):
            argv.append(flag)

    return argv


def build_wrapper_args_from_payload(payload: dict) -> argparse.Namespace:
    return wrapper.parse_args(request_to_argv(payload))


def build_wrapper_args_for_session(session: dict, payload: dict | None = None) -> SimpleNamespace:
    payload = payload or {}
    return SimpleNamespace(
        pdf_path=Path(session["pdfPath"]),
        pages=session.get("pages"),
        auto_pages=session["sessionType"] == "auto_pages",
        auto_batch_size=session.get("autoBatchSize", wrapper.sender.AUTO_PAGES_DEFAULT_BATCH_SIZE),
        force_file_extract=session["sessionType"] == "forced_file_extract",
        prompt=payload.get("question"),
        prompt_file=None,
        system=payload.get("system"),
        system_file=None,
        model=session.get("model"),
        base_url=session.get("baseUrl"),
        api_key=session.get("apiKey"),
        max_tokens=int(payload.get("max_tokens", session.get("maxTokens", wrapper.sender.DEFAULT_MAX_TOKENS))),
        temperature=payload.get("temperature"),
        top_p=payload.get("top_p"),
        no_default_prompt=True,
        no_image_optimize=session.get("noImageOptimize", False),
        write_json=None,
        write_reader_json=None,
        pretty=bool(payload.get("pretty", False)),
        full=bool(payload.get("full", False)),
        output_mode=payload.get("output_mode", "plugin-json"),
        inspect_route=False,
    )


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def build_session_response(session: dict) -> dict:
    response = {
        "ok": True,
        "plugin": wrapper.PLUGIN_NAME,
        "schemaVersion": wrapper.PLUGIN_SCHEMA_VERSION,
        "session": {
            "sessionId": session["sessionId"],
            "sessionType": session["sessionType"],
            "document": session["document"],
            "routing": session["routing"],
        },
    }
    if session.get("autoPages") is not None:
        response["session"]["autoPages"] = session["autoPages"]
    if session.get("file") is not None:
        response["session"]["file"] = session["file"]
    return response


def prepare_file_extract_session(
    pdf_path: Path,
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    model: str,
    session_type: str,
) -> dict:
    inspection = wrapper.reader.inspect_pdf(pdf_path, wrapper.sender.CLAUDE_ROUTE_MODEL, None)
    upload = wrapper.sender.multipart_request(f"{base_url}/files", api_key, pdf_path, "file-extract")
    file_id = upload.get("id")
    if not file_id:
        raise RuntimeError("Kimi file upload did not return a file id.")
    raw_extracted_text = wrapper.sender.file_content_request(base_url, api_key, str(file_id))
    extracted_text, extracted_meta = wrapper.sender.normalize_extracted_text(raw_extracted_text)
    return {
        "sessionId": uuid4().hex,
        "sessionType": session_type,
        "pdfPath": str(pdf_path),
        "pages": None,
        "autoBatchSize": None,
        "noImageOptimize": args.no_image_optimize,
        "apiKey": api_key,
        "baseUrl": base_url,
        "model": model,
        "maxTokens": args.max_tokens,
        "document": {
            "pdfPath": str(pdf_path),
            "pageCount": inspection.get("pageCount"),
            "fileSizeBytes": inspection.get("fileSize"),
        },
        "routing": {
            "claudeRoute": "forced_file_extract" if session_type == "forced_file_extract" else "document_block",
            "transport": "moonshot_file_extract_shim",
            "inspection": inspection,
        },
        "file": {
            "id": file_id,
            "filename": upload.get("filename", pdf_path.name),
            "bytes": upload.get("bytes"),
        },
        "extractedText": extracted_text,
        "extractedMeta": extracted_meta,
    }


def prepare_pages_session(
    pdf_path: Path,
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    model: str,
) -> dict:
    route_plan = wrapper.sender.plan_kimi_compatible_route(
        pdf_path,
        args.pages,
        optimize_images=not args.no_image_optimize,
        force_file_extract=False,
    )
    reader_result = route_plan["readerResult"]
    return {
        "sessionId": uuid4().hex,
        "sessionType": "pages",
        "pdfPath": str(pdf_path),
        "pages": args.pages,
        "autoBatchSize": None,
        "noImageOptimize": args.no_image_optimize,
        "apiKey": api_key,
        "baseUrl": base_url,
        "model": model,
        "maxTokens": args.max_tokens,
        "document": {
            "pdfPath": str(pdf_path),
            "pageCount": (route_plan["inspection"] or {}).get("pageCount"),
            "fileSizeBytes": (route_plan["inspection"] or {}).get("fileSize"),
        },
        "routing": {
            "claudeRoute": route_plan["claudeRoute"],
            "transport": route_plan["transport"],
            "inspection": route_plan["inspection"],
        },
        "readerResult": reader_result,
    }


def prepare_auto_pages_session(
    pdf_path: Path,
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    model: str,
) -> dict:
    inspection = wrapper.reader.inspect_pdf(pdf_path, wrapper.sender.CLAUDE_ROUTE_MODEL, None)
    page_count, method = wrapper.sender.determine_page_count_for_auto_pages(pdf_path, inspection)
    inspection["pageCount"] = page_count
    inspection["pageCountDetection"] = method
    if method != "pdfinfo":
        inspection.setdefault("warnings", []).append(
            "Page count was determined via fallback rendering because pdfinfo was unavailable."
        )
    page_ranges = wrapper.sender.build_auto_page_ranges(page_count, args.auto_batch_size)
    chunks = []
    for page_range in page_ranges:
        route_plan = wrapper.sender.plan_kimi_compatible_route(
            pdf_path,
            page_range,
            optimize_images=not args.no_image_optimize,
            force_file_extract=False,
        )
        chunks.append(
            {
                "pages": page_range,
                "routePlan": route_plan,
                "readerResult": route_plan["readerResult"],
            }
        )
    return {
        "sessionId": uuid4().hex,
        "sessionType": "auto_pages",
        "pdfPath": str(pdf_path),
        "pages": None,
        "autoBatchSize": min(args.auto_batch_size, wrapper.reader.PDF_MAX_PAGES_PER_READ),
        "noImageOptimize": args.no_image_optimize,
        "apiKey": api_key,
        "baseUrl": base_url,
        "model": model,
        "maxTokens": args.max_tokens,
        "document": {
            "pdfPath": str(pdf_path),
            "pageCount": page_count,
            "fileSizeBytes": inspection.get("fileSize"),
        },
        "routing": {
            "claudeRoute": "auto_pages_aggregate",
            "transport": "moonshot_chat_completions_image_url",
            "inspection": inspection,
        },
        "autoPages": {
            "pageCount": page_count,
            "batchSize": min(args.auto_batch_size, wrapper.reader.PDF_MAX_PAGES_PER_READ),
            "pageRanges": page_ranges,
        },
        "chunks": chunks,
    }


def create_session(payload: dict) -> dict:
    args = build_wrapper_args_from_payload(payload)
    pdf_path = resolve_pdf_path(str(args.pdf_path))
    sender_args = wrapper.sender.parse_args(wrapper.build_sender_argv(args))
    api_key, base_url, model = wrapper.sender.resolve_config(sender_args)

    if args.pages:
        session = prepare_pages_session(pdf_path, args, api_key, base_url, model)
    elif args.force_file_extract:
        session = prepare_file_extract_session(pdf_path, args, api_key, base_url, model, "forced_file_extract")
    elif args.auto_pages:
        session = prepare_auto_pages_session(pdf_path, args, api_key, base_url, model)
    else:
        inspection = wrapper.reader.inspect_pdf(pdf_path, wrapper.sender.CLAUDE_ROUTE_MODEL, None)
        if inspection.get("selectedMode") == "reject_requires_pages":
            session = prepare_auto_pages_session(pdf_path, args, api_key, base_url, model)
        else:
            session = prepare_file_extract_session(pdf_path, args, api_key, base_url, model, "file_extract")

    SESSIONS[session["sessionId"]] = session
    return build_session_response(session)


def build_result_for_session(session: dict, payload: dict) -> tuple[dict, dict]:
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Field 'question' is required and must be a non-empty string.")

    args = build_wrapper_args_for_session(session, payload)
    question = question.strip()

    if session["sessionType"] in {"file_extract", "forced_file_extract"}:
        extraction_prompt = "\n".join(
            [
                "The following content was extracted from a PDF file.",
                f"Original file: {Path(session['pdfPath']).name}",
                "",
                session["extractedText"],
            ]
        )
        messages = []
        if args.system:
            messages.append({"role": "system", "content": args.system})
        messages.append({"role": "system", "content": extraction_prompt})
        messages.append({"role": "user", "content": question})
        request_payload = {
            "model": session["model"],
            "max_tokens": args.max_tokens,
            "messages": messages,
        }
        if args.temperature is not None:
            request_payload["temperature"] = args.temperature
        if args.top_p is not None:
            request_payload["top_p"] = args.top_p
        response = wrapper.sender.call_chat_completions(session["baseUrl"], session["apiKey"], request_payload)
        raw_result = {
            "mode": "file_extract",
            "claudeCompatibleRouting": session["routing"],
            "file": session.get("file"),
            "extractedMeta": session.get("extractedMeta"),
            "extractedText": session["extractedText"],
            "request": request_payload,
            "response": response,
            "text": (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or ""),
        }
    elif session["sessionType"] == "pages":
        messages = []
        if args.system:
            messages.append({"role": "system", "content": args.system})
        messages.append(
            {
                "role": "user",
                "content": wrapper.sender.reader_blocks_to_kimi_content(session["readerResult"], question),
            }
        )
        request_payload = {
            "model": session["model"],
            "max_tokens": args.max_tokens,
            "messages": messages,
        }
        if args.temperature is not None:
            request_payload["temperature"] = args.temperature
        if args.top_p is not None:
            request_payload["top_p"] = args.top_p
        response = wrapper.sender.call_chat_completions(session["baseUrl"], session["apiKey"], request_payload)
        raw_result = {
            "mode": "pages_to_images",
            "claudeCompatibleRouting": session["routing"],
            "readerResult": session["readerResult"],
            "request": request_payload,
            "response": response,
            "text": (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or ""),
        }
    else:
        chunk_outputs = []
        chunk_summaries = []
        page_ranges = session["autoPages"]["pageRanges"]
        for chunk in session["chunks"]:
            chunk_text_prompt = wrapper.sender.build_chunk_prompt(chunk["pages"], question)
            messages = []
            if args.system:
                messages.append({"role": "system", "content": args.system})
            messages.append(
                {
                    "role": "user",
                    "content": wrapper.sender.reader_blocks_to_kimi_content(chunk["readerResult"], chunk_text_prompt),
                }
            )
            chunk_request = {
                "model": session["model"],
                "max_tokens": args.max_tokens,
                "messages": messages,
            }
            if args.temperature is not None:
                chunk_request["temperature"] = args.temperature
            if args.top_p is not None:
                chunk_request["top_p"] = args.top_p
            chunk_response = wrapper.sender.call_chat_completions(session["baseUrl"], session["apiKey"], chunk_request)
            chunk_text = (((chunk_response.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
            chunk_outputs.append(
                {
                    "pages": chunk["pages"],
                    "claudeCompatibleRouting": chunk["routePlan"],
                    "readerSummary": (chunk["readerResult"] or {}).get("summary"),
                    "response": chunk_response,
                    "text": chunk_text,
                }
            )
            chunk_summaries.append({"pages": chunk["pages"], "text": chunk_text})

        aggregate_messages = []
        if args.system:
            aggregate_messages.append({"role": "system", "content": args.system})
        aggregate_messages.append(
            {
                "role": "user",
                "content": wrapper.sender.build_aggregate_prompt(
                    Path(session["pdfPath"]),
                    page_ranges,
                    chunk_summaries,
                    question,
                ),
            }
        )
        aggregate_request = {
            "model": session["model"],
            "max_tokens": args.max_tokens,
            "messages": aggregate_messages,
        }
        if args.temperature is not None:
            aggregate_request["temperature"] = args.temperature
        if args.top_p is not None:
            aggregate_request["top_p"] = args.top_p
        aggregate_response = wrapper.sender.call_chat_completions(session["baseUrl"], session["apiKey"], aggregate_request)
        raw_result = {
            "mode": "auto_pages_aggregate",
            "claudeCompatibleRouting": session["routing"],
            "autoPages": session["autoPages"],
            "chunks": chunk_outputs,
            "aggregateRequest": aggregate_request,
            "aggregateResponse": aggregate_response,
            "text": (((aggregate_response.get("choices") or [{}])[0].get("message") or {}).get("content") or ""),
        }

    if args.output_mode == "raw":
        payload_out = raw_result
    else:
        plugin_output = wrapper.build_plugin_output(args, raw_result)
        if args.output_mode == "summary-json":
            payload_out = wrapper.build_summary_json_output(
                args,
                plugin_output,
                wrapper.structure_summary_with_kimi(args, plugin_output),
            )
        else:
            payload_out = plugin_output

    if isinstance(payload_out, dict):
        payload_out["session"] = {
            "sessionId": session["sessionId"],
            "sessionType": session["sessionType"],
        }
    return payload_out, raw_result


class PDFServiceHandler(BaseHTTPRequestHandler):
    server_version = "ClaudeStylePDFReaderHTTP/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "claude-style-pdf-reader",
                    "status": "healthy",
                    "sessionCount": len(SESSIONS),
                },
            )
            return
        json_response(
            self,
            HTTPStatus.NOT_FOUND,
            {"ok": False, "error": {"message": f"Unknown path: {parsed.path}"}},
        )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")
        except Exception as exc:  # noqa: BLE001
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"message": f"Invalid JSON body: {exc}"}},
            )
            return

        try:
            if parsed.path == "/inspect-route":
                args = build_wrapper_args_from_payload(payload)
                result = wrapper.inspect_route(args)
                json_response(self, HTTPStatus.OK, result)
                return
            if parsed.path == "/analyze":
                args = build_wrapper_args_from_payload(payload)
                result, _raw = wrapper.execute_plugin(args)
                json_response(self, HTTPStatus.OK, result)
                return
            if parsed.path == "/sessions/load-pdf":
                result = create_session(payload)
                json_response(self, HTTPStatus.OK, result)
                return
            if parsed.path == "/sessions/ask":
                session_id = payload.get("session_id")
                if not isinstance(session_id, str) or not session_id.strip():
                    raise ValueError("Field 'session_id' is required and must be a non-empty string.")
                session = SESSIONS.get(session_id)
                if session is None:
                    json_response(
                        self,
                        HTTPStatus.NOT_FOUND,
                        {"ok": False, "error": {"message": f"Unknown session_id: {session_id}"}},
                    )
                    return
                result, _raw = build_result_for_session(session, payload)
                json_response(self, HTTPStatus.OK, result)
                return
            if parsed.path == "/sessions/inspect":
                session_id = payload.get("session_id")
                if not isinstance(session_id, str) or not session_id.strip():
                    raise ValueError("Field 'session_id' is required and must be a non-empty string.")
                session = SESSIONS.get(session_id)
                if session is None:
                    json_response(
                        self,
                        HTTPStatus.NOT_FOUND,
                        {"ok": False, "error": {"message": f"Unknown session_id: {session_id}"}},
                    )
                    return
                json_response(self, HTTPStatus.OK, build_session_response(session))
                return
            json_response(
                self,
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": {"message": f"Unknown path: {parsed.path}"}},
            )
        except SystemExit as exc:
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"message": f"Argument validation failed: {exc}"}},
            )
        except ValueError as exc:
            json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"message": str(exc)}},
            )
        except Exception as exc:  # noqa: BLE001
            json_response(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "ok": False,
                    "error": {
                        "message": str(exc),
                        "type": exc.__class__.__name__,
                        "traceback": traceback.format_exc(),
                    },
                },
            )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Minimal HTTP wrapper for the Claude-Style PDF Reader plugin."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), PDFServiceHandler)
    print(
        json.dumps(
            {
                "ok": True,
                "service": "claude-style-pdf-reader",
                "listen": f"http://{args.host}:{args.port}",
                "routes": [
                    "/healthz",
                    "/inspect-route",
                    "/analyze",
                    "/sessions/load-pdf",
                    "/sessions/ask",
                    "/sessions/inspect",
                ],
            },
            ensure_ascii=False,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
