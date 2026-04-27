from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from ..datasets import DatasetImportError
from ..factory import RuleFactoryError
from .api_dispatch import SUPPORTED_ACTIONS, UnsupportedActionError, dispatch_request
from .api_request import ApiRequestError, coerce_request, load_cli_payload


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _success(action: str, request_id: str | None, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "action": action,
        "request_id": request_id,
        "timestamp": _timestamp(),
        "data": data,
        "error": None,
    }


def _error(action: str | None, request_id: str | None, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "action": action,
        "request_id": request_id,
        "timestamp": _timestamp(),
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": {} if details is None else details,
        },
    }


def handle_request(payload: dict[str, Any], kimi_client: Any | None = None) -> dict[str, Any]:
    action: str | None = None
    request_id: str | None = None
    try:
        request = coerce_request(payload)
        action = request["action"]
        request_id = request["request_id"]
        data = dispatch_request(request, kimi_client=kimi_client)
        return _success(action=action, request_id=request_id, data=data)
    except UnsupportedActionError as exc:
        return _error(
            action=action,
            request_id=request_id,
            code="unsupported_action",
            message=f"unsupported action: {exc.action}",
            details={"supported_actions": SUPPORTED_ACTIONS},
        )
    except ApiRequestError as exc:
        return _error(action=action, request_id=request_id, code="bad_request", message=str(exc))
    except DatasetImportError as exc:
        return _error(action=action, request_id=request_id, code="invalid_dataset", message=str(exc))
    except RuleFactoryError as exc:
        return _error(action=action, request_id=request_id, code="bad_request", message=str(exc))
    except FileNotFoundError as exc:
        return _error(action=action, request_id=request_id, code="not_found", message=str(exc))
    except Exception as exc:  # pragma: no cover - defensive catch for service boundaries
        return _error(action=action, request_id=request_id, code="internal_error", message=str(exc))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call the function-style Phase 1 API service.")
    parser.add_argument("--payload", help="Inline JSON payload.")
    parser.add_argument("--payload-file", help="Path to a JSON payload file.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    payload = load_cli_payload(args)
    response = handle_request(payload)
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
