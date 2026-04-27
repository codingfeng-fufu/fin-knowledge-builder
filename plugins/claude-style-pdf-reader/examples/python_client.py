from __future__ import annotations

import json
import urllib.request


SERVICE_URL = "http://127.0.0.1:8787/analyze"


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    payload = {
        "pdf_path": r"D:\fincode\claude-code-source-code-main\claude-code-source-code-main\docs\zh\2109.02809v1.pdf",
        "output_mode": "summary-json",
        "pretty": True,
    }
    result = post_json(SERVICE_URL, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
