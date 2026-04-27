from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PDF_READER_DIR = REPO_ROOT / "reconstructions" / "pdf_reader_python"
READER_PATH = REPO_ROOT / "reconstructions" / "pdf_reader_python" / "claude_pdf_reader.py"
SENDER_PATH = REPO_ROOT / "reconstructions" / "pdf_reader_python" / "send_to_kimi.py"

if str(PDF_READER_DIR) not in sys.path:
    sys.path.insert(0, str(PDF_READER_DIR))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reader = load_module("claude_pdf_reader_plugin", READER_PATH)
sender = load_module("send_to_kimi_plugin", SENDER_PATH)
PLUGIN_NAME = "claude-style-pdf-reader"
PLUGIN_SCHEMA_VERSION = "1.0"
SUMMARY_SCHEMA_VERSION = "1.0"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Claude-style PDF reader plugin wrapper. Defaults to automatic Claude-style routing."
    )
    parser.add_argument("pdf_path", type=Path, help="Path to a PDF file")
    parser.add_argument("--pages", default=None, help='Explicit page range like "1-3"')
    parser.add_argument("--auto-pages", action="store_true", help="Force automatic page batching")
    parser.add_argument("--auto-batch-size", type=int, default=sender.AUTO_PAGES_DEFAULT_BATCH_SIZE)
    parser.add_argument("--force-file-extract", action="store_true", help="Bypass Claude-style routing")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--prompt-file", type=Path, default=None)
    parser.add_argument("--system", default=None)
    parser.add_argument("--system-file", type=Path, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-tokens", type=int, default=sender.DEFAULT_MAX_TOKENS)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--no-default-prompt", action="store_true")
    parser.add_argument("--no-image-optimize", action="store_true")
    parser.add_argument("--write-json", type=Path, default=None)
    parser.add_argument("--write-reader-json", type=Path, default=None)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument(
        "--output-mode",
        choices=["plugin-json", "summary-json", "raw"],
        default="plugin-json",
        help="Wrapper output format. summary-json performs one extra structuring pass on the generated answer.",
    )
    parser.add_argument(
        "--inspect-route",
        action="store_true",
        help="Print the Claude-style routing decision and exit without sending anything",
    )
    return parser.parse_args(argv)


def build_sender_argv(args: argparse.Namespace) -> list[str]:
    pdf_path = args.pdf_path.resolve()
    sender_argv = [str(pdf_path)]

    if args.prompt is not None:
        sender_argv += ["--prompt", args.prompt]
    if args.prompt_file is not None:
        sender_argv += ["--prompt-file", str(args.prompt_file.resolve())]
    if args.system is not None:
        sender_argv += ["--system", args.system]
    if args.system_file is not None:
        sender_argv += ["--system-file", str(args.system_file.resolve())]
    if args.model is not None:
        sender_argv += ["--model", args.model]
    if args.base_url is not None:
        sender_argv += ["--base-url", args.base_url]
    if args.api_key is not None:
        sender_argv += ["--api-key", args.api_key]
    sender_argv += ["--max-tokens", str(args.max_tokens)]
    if args.temperature is not None:
        sender_argv += ["--temperature", str(args.temperature)]
    if args.top_p is not None:
        sender_argv += ["--top-p", str(args.top_p)]
    if args.no_default_prompt:
        sender_argv += ["--no-default-prompt"]
    if args.no_image_optimize:
        sender_argv += ["--no-image-optimize"]
    if args.write_json is not None:
        sender_argv += ["--write-json", str(args.write_json.resolve())]
    if args.write_reader_json is not None:
        sender_argv += ["--write-reader-json", str(args.write_reader_json.resolve())]
    if args.pretty:
        sender_argv += ["--pretty"]
    if args.full:
        sender_argv += ["--full"]

    if args.pages:
        return [*sender_argv, "--pages", args.pages]
    if args.force_file_extract:
        return [*sender_argv, "--force-file-extract"]
    if args.auto_pages:
        return [*sender_argv, "--auto-pages", "--auto-batch-size", str(args.auto_batch_size)]

    inspection = reader.inspect_pdf(pdf_path, sender.CLAUDE_ROUTE_MODEL, None)
    if inspection["selectedMode"] == "reject_requires_pages":
        return [*sender_argv, "--auto-pages", "--auto-batch-size", str(args.auto_batch_size)]
    return sender_argv


def inspect_route(args: argparse.Namespace) -> dict:
    pdf_path = args.pdf_path.resolve()
    inspection = reader.inspect_pdf(pdf_path, sender.CLAUDE_ROUTE_MODEL, args.pages)
    if args.pages:
        chosen = {"mode": "pages", "pages": args.pages}
    elif args.force_file_extract:
        chosen = {"mode": "force-file-extract"}
    elif args.auto_pages:
        chosen = {"mode": "auto-pages", "batchSize": args.auto_batch_size}
    elif inspection["selectedMode"] == "reject_requires_pages":
        chosen = {"mode": "auto-pages", "batchSize": args.auto_batch_size}
    else:
        chosen = {"mode": "default"}
    return {
        "plugin": PLUGIN_NAME,
        "inspection": inspection,
        "chosen": chosen,
    }


def build_plugin_output(args: argparse.Namespace, result: dict) -> dict:
    routing = result.get("claudeCompatibleRouting") or {}
    inspection = routing.get("inspection") or {}
    response = result.get("aggregateResponse") or result.get("response") or {}
    usage = response.get("usage") or {}

    output: dict = {
        "ok": True,
        "plugin": PLUGIN_NAME,
        "schemaVersion": PLUGIN_SCHEMA_VERSION,
        "outputMode": "plugin-json",
        "mode": result.get("mode"),
        "document": {
            "pdfPath": str(args.pdf_path.resolve()),
            "pageCount": inspection.get("pageCount"),
            "fileSizeBytes": inspection.get("fileSize"),
        },
        "routing": {
            "requestedPages": args.pages,
            "autoPages": args.auto_pages,
            "autoBatchSize": args.auto_batch_size if args.auto_pages else None,
            "forcedFileExtract": args.force_file_extract,
            "claudeRoute": routing.get("claudeRoute"),
            "transport": routing.get("transport"),
            "inspection": inspection,
        },
        "analysis": {
            "answer": result.get("text", ""),
            "usage": usage,
        },
    }

    if result.get("autoPages") is not None:
        output["analysis"]["autoPages"] = result["autoPages"]
        output["analysis"]["chunks"] = [
            {
                "pages": chunk.get("pages"),
                "text": chunk.get("text"),
                "usage": ((chunk.get("response") or {}).get("usage") or {}),
            }
            for chunk in result.get("chunks", [])
        ]

    if result.get("file") is not None:
        output["analysis"]["file"] = result["file"]

    if result.get("readerResult") is not None:
        reader_summary = (result["readerResult"] or {}).get("summary")
        if reader_summary is not None:
            output["analysis"]["readerSummary"] = reader_summary

    return output


def extract_json_object(text: str) -> dict | None:
    stripped = text.strip()
    candidates = [stripped]
    if "```json" in stripped:
        start = stripped.find("```json")
        end = stripped.rfind("```")
        if start != -1 and end != -1 and end > start:
            candidates.append(stripped[start + 7 : end].strip())
    if "```" in stripped:
        start = stripped.find("```")
        end = stripped.rfind("```")
        if start != -1 and end != -1 and end > start:
            fence_body = stripped[start + 3 : end].strip()
            if "\n" in fence_body:
                fence_body = fence_body.split("\n", 1)[1].strip()
            candidates.append(fence_body)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def build_summary_structuring_prompt(plugin_output: dict) -> str:
    answer = plugin_output["analysis"]["answer"]
    routing = plugin_output["routing"]
    document = plugin_output["document"]
    return "\n".join(
        [
            "Convert the following PDF analysis into strict JSON.",
            "Return JSON only. Do not wrap it in markdown fences.",
            "Use exactly this schema:",
            "{",
            '  "title": string | null,',
            '  "oneSentenceSummary": string | null,',
            '  "researchProblem": string | null,',
            '  "methods": string[],',
            '  "experiments": string[],',
            '  "results": string[],',
            '  "conclusions": string[],',
            '  "limitations": string[],',
            '  "evidenceScope": string | null',
            "}",
            "Rules:",
            "- Every field must be present.",
            "- Use null only when the answer does not support the field.",
            "- Keep each array item concise.",
            "- Do not invent details not supported by the analysis.",
            "",
            f"Document metadata: {json.dumps(document, ensure_ascii=False)}",
            f"Routing metadata: {json.dumps(routing, ensure_ascii=False)}",
            "",
            "Analysis to structure:",
            answer,
        ]
    )


def build_summary_json_output(args: argparse.Namespace, plugin_output: dict, structured_summary: dict) -> dict:
    output = {
        "ok": True,
        "plugin": PLUGIN_NAME,
        "schemaVersion": SUMMARY_SCHEMA_VERSION,
        "outputMode": "summary-json",
        "mode": plugin_output["mode"],
        "document": plugin_output["document"],
        "routing": plugin_output["routing"],
        "summary": {
            "title": structured_summary.get("title"),
            "oneSentenceSummary": structured_summary.get("oneSentenceSummary"),
            "researchProblem": structured_summary.get("researchProblem"),
            "methods": structured_summary.get("methods") or [],
            "experiments": structured_summary.get("experiments") or [],
            "results": structured_summary.get("results") or [],
            "conclusions": structured_summary.get("conclusions") or [],
            "limitations": structured_summary.get("limitations") or [],
            "evidenceScope": structured_summary.get("evidenceScope"),
        },
        "usage": plugin_output["analysis"]["usage"],
    }
    if structured_summary.get("_unparsedResponse") is not None:
        output["summaryParsingError"] = {
            "message": "Structured parsing failed; inspect the raw structuring response.",
            "rawResponse": structured_summary["_unparsedResponse"],
        }
    return output


def structure_summary_with_kimi(args: argparse.Namespace, plugin_output: dict) -> dict:
    sender_args = sender.parse_args(build_sender_argv(args))
    api_key, base_url, model = sender.resolve_config(sender_args)
    payload = {
        "model": model,
        "max_tokens": min(args.max_tokens, 2000),
        "messages": [
            {
                "role": "user",
                "content": build_summary_structuring_prompt(plugin_output),
            }
        ],
    }
    response = sender.call_chat_completions(base_url, api_key, payload)
    response_text = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    parsed = extract_json_object(response_text)
    if parsed is None:
        return {
            "title": None,
            "oneSentenceSummary": None,
            "researchProblem": None,
            "methods": [],
            "experiments": [],
            "results": [],
            "conclusions": [],
            "limitations": [],
            "evidenceScope": "Structured parsing failed; inspect the raw plugin-json answer instead.",
            "_unparsedResponse": response_text,
        }
    return parsed


def execute_plugin(args: argparse.Namespace) -> tuple[dict, dict]:
    sender_args = sender.parse_args(build_sender_argv(args))
    result = sender.execute(sender_args)
    if args.output_mode == "raw":
        payload = result
    else:
        plugin_output = build_plugin_output(args, result)
        if args.output_mode == "summary-json":
            payload = build_summary_json_output(
                args,
                plugin_output,
                structure_summary_with_kimi(args, plugin_output),
            )
        else:
            payload = plugin_output
    return payload, result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.inspect_route:
        print(json.dumps(inspect_route(args), ensure_ascii=False, indent=2))
        return 0

    payload, result = execute_plugin(args)

    if args.write_json is not None:
        sender.write_json_file(args.write_json.resolve(), payload, args.pretty)
    if args.write_reader_json is not None and result.get("readerResult") is not None:
        sender.write_json_file(args.write_reader_json.resolve(), result["readerResult"], args.pretty)

    stdout_payload = payload if args.full else sender.summarize_payload(payload)
    if args.write_json is not None or args.write_reader_json is not None:
        receipt = {
            "ok": True,
            "plugin": PLUGIN_NAME,
            "outputMode": args.output_mode,
            "mode": result.get("mode"),
            "wroteJson": str(args.write_json.resolve()) if args.write_json is not None else None,
            "wroteReaderJson": str(args.write_reader_json.resolve()) if args.write_reader_json is not None else None,
            "textPreview": (result.get("text") or "")[:200],
        }
        print(json.dumps(receipt, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0

    print(json.dumps(stdout_payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
