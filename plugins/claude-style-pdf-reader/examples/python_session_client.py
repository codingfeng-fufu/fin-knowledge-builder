from __future__ import annotations

import json
import urllib.request


BASE_URL = "http://127.0.0.1:8787"


def post_json(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    load_result = post_json(
        "/sessions/load-pdf",
        {
            "pdf_path": r"D:\fincode\claude-code-source-code-main\claude-code-source-code-main\docs\zh\2109.02809v1.pdf",
            "auto_pages": True,
        },
    )
    print("LOAD:")
    print(json.dumps(load_result, ensure_ascii=False, indent=2))

    session_id = load_result["session"]["sessionId"]

    ask_result = post_json(
        "/sessions/ask",
        {
            "session_id": session_id,
            "question": "请用中文回答：这篇论文的核心方法和主要实验结果是什么？",
            "output_mode": "summary-json",
        },
    )
    print("\nASK:")
    print(json.dumps(ask_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
