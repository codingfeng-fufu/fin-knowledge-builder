from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .api_service import handle_request


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8010
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
HOME_CONSOLE_PATHS = {"/", "/home", "/overview", "/home-console.html"}
REGISTRY_CONSOLE_PATHS = {"/console", "/registry-console.html"}
PROTOTYPE_CONSOLE_PATHS = {"/prototype", "/prototype-console.html"}
PRODUCT_CONSOLE_PATHS = {"/workspace", "/product", "/product-console.html"}
DEMO_CONSOLE_PATHS = {"/demo", "/demo-console.html"}
WORKFLOW_CONSOLE_PATHS = {"/workflow", "/workspace-flow", "/workflow-console.html"}
OPS_CONSOLE_PATHS = {"/ops", "/factory", "/ops-console.html"}
DISCOVERY_FRONTEND_BASE = "http://127.0.0.1:3000"
DISCOVERY_BACKEND_BASE = "http://127.0.0.1:5001"
DISCOVERY_FRONTEND_PREFIXES = (
    "/discovery",
    "/@vite",
    "/@id/",
    "/src/",
    "/node_modules/",
    "/vite.svg",
    "/icon.svg",
)
DISCOVERY_API_PREFIX = "/api/discovery"


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _status_for_response(response: dict[str, Any]) -> int:
    if response.get("ok", False):
        return HTTPStatus.OK

    error = response.get("error", {})
    code = error.get("code")
    if code in {"bad_request", "unsupported_action", "invalid_dataset"}:
        return HTTPStatus.BAD_REQUEST
    if code == "not_found":
        return HTTPStatus.NOT_FOUND
    return HTTPStatus.INTERNAL_SERVER_ERROR


def _content_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _proxy_request(
    *,
    base_url: str,
    path_with_query: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    target = f"{base_url}{path_with_query}"
    request = Request(target, data=body, method=method)
    for key, value in (headers or {}).items():
        if key.lower() in {"host", "content-length", "connection"}:
            continue
        request.add_header(key, value)
    try:
        with urlopen(request, timeout=30) as response:
            return (
                response.status,
                {key: value for key, value in response.headers.items()},
                response.read(),
            )
    except HTTPError as exc:
        return (
            exc.code,
            {key: value for key, value in exc.headers.items()},
            exc.read(),
        )
    except URLError as exc:
        message = json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "proxy_unavailable",
                    "message": str(exc.reason),
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        return (
            HTTPStatus.BAD_GATEWAY,
            {"Content-Type": "application/json; charset=utf-8"},
            message,
        )


class Phase1ApiHandler(BaseHTTPRequestHandler):
    server_version = "Phase1ApiHTTP/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith(DISCOVERY_API_PREFIX):
            self._proxy_response(
                *_proxy_request(
                    base_url=DISCOVERY_BACKEND_BASE,
                    path_with_query=self.path,
                    method="GET",
                    headers={key: value for key, value in self.headers.items()},
                )
            )
            return

        if any(
            parsed.path == prefix or parsed.path.startswith(prefix)
            for prefix in DISCOVERY_FRONTEND_PREFIXES
        ):
            self._proxy_response(
                *_proxy_request(
                    base_url=DISCOVERY_FRONTEND_BASE,
                    path_with_query=self.path,
                    method="GET",
                    headers={key: value for key, value in self.headers.items()},
                )
            )
            return

        if parsed.path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "phase1_runtime_http",
                    "status": "healthy",
                    "path": "/health",
                },
            )
            return

        if parsed.path in REGISTRY_CONSOLE_PATHS:
            self._send_file(STATIC_DIR / "registry-console.html", "text/html; charset=utf-8")
            return

        if parsed.path in HOME_CONSOLE_PATHS:
            self._send_file(STATIC_DIR / "home-console.html", "text/html; charset=utf-8")
            return

        if parsed.path in PROTOTYPE_CONSOLE_PATHS:
            self._send_file(STATIC_DIR / "prototype-console.html", "text/html; charset=utf-8")
            return

        if parsed.path in PRODUCT_CONSOLE_PATHS:
            self._send_file(STATIC_DIR / "product-console.html", "text/html; charset=utf-8")
            return

        if parsed.path in DEMO_CONSOLE_PATHS:
            self._send_file(STATIC_DIR / "demo-console.html", "text/html; charset=utf-8")
            return

        if parsed.path in WORKFLOW_CONSOLE_PATHS:
            self._send_file(STATIC_DIR / "workflow-console.html", "text/html; charset=utf-8")
            return

        if parsed.path in OPS_CONSOLE_PATHS:
            self._send_file(STATIC_DIR / "ops-console.html", "text/html; charset=utf-8")
            return

        if parsed.path.startswith("/static/"):
            relative = parsed.path.removeprefix("/static/").lstrip("/")
            target = (STATIC_DIR / relative).resolve()
            try:
                target.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {
                        "ok": False,
                        "error": {
                            "code": "not_found",
                            "message": f"unknown path: {parsed.path}",
                        },
                    },
                )
                return
            self._send_file(target, _content_type_for(target))
            return

        if parsed.path == "/api/phase1":
            self._send_json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {
                    "ok": False,
                    "error": {
                        "code": "method_not_allowed",
                        "message": "use POST /api/phase1 with a JSON payload",
                    },
                },
            )
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            {
                "ok": False,
                "error": {
                    "code": "not_found",
                    "message": f"unknown path: {parsed.path}",
                },
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith(DISCOVERY_API_PREFIX):
            content_length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(content_length) if content_length > 0 else None
            self._proxy_response(
                *_proxy_request(
                    base_url=DISCOVERY_BACKEND_BASE,
                    path_with_query=self.path,
                    method="POST",
                    body=raw_body,
                    headers={key: value for key, value in self.headers.items()},
                )
            )
            return

        if parsed.path != "/api/phase1":
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": {
                        "code": "not_found",
                        "message": f"unknown path: {parsed.path}",
                    },
                },
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": {
                        "code": "bad_request",
                        "message": "invalid Content-Length header",
                    },
                },
            )
            return

        raw_body = self.rfile.read(content_length) if content_length > 0 else b""
        if not raw_body:
            payload: dict[str, Any] = {"action": "workflow.full"}
        else:
            try:
                parsed_body = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "ok": False,
                        "error": {
                            "code": "bad_request",
                            "message": f"invalid JSON body: {exc.msg}",
                        },
                    },
                )
                return
            if not isinstance(parsed_body, dict):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "ok": False,
                        "error": {
                            "code": "bad_request",
                            "message": "request body must be a JSON object",
                        },
                    },
                )
                return
            payload = parsed_body

        response = handle_request(payload)
        self._send_json(_status_for_response(response), response)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers("application/json; charset=utf-8", 0)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = _json_bytes(payload)
        self.send_response(status_code)
        self._send_common_headers("application/json; charset=utf-8", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": {
                        "code": "not_found",
                        "message": f"file not found: {path.name}",
                    },
                },
            )
            return

        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._send_common_headers(content_type, len(body))
        self.end_headers()
        self.wfile.write(body)

    def _proxy_response(self, status_code: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status_code)
        for key, value in headers.items():
            lower = key.lower()
            if lower in {"content-length", "connection", "transfer-encoding", "content-encoding"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _send_common_headers(self, content_type: str, content_length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")


def create_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Phase1ApiHandler)


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = create_server(host=host, port=port)
    print(json.dumps({"host": host, "port": port, "service": "phase1_runtime_http"}, ensure_ascii=False))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the minimal Phase 1 HTTP API server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind.")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Port to bind.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
