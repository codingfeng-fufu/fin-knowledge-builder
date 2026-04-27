"""
Quick test script for Kimi API connectivity.
Usage: python3 test_kimi.py
"""
import json
from pathlib import Path
from urllib import error, request

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return cfg


def test_kimi(model: str):
    cfg = load_config()
    api_key = cfg.get("moonshot_api_key", "")
    base_url = cfg.get("moonshot_base_url", "https://api.moonshot.ai/v1")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "你好，请回复 OK"}],
        "max_tokens": 20,
        "temperature": 0.1,
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            print(f"✓ 模型 {model} 调用成功")
            print(f"  回复: {content}")
    except error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        print(f"✗ HTTP {e.code}: {detail[:200]}")
    except error.URLError as e:
        print(f"✗ 连接失败: {e}")


if __name__ == "__main__":
    print(f"配置文件: {CONFIG_PATH}")
    cfg = load_config()
    key = cfg.get("moonshot_api_key", "")
    print(f"API Key: {key[:8]}...{key[-4:]} (长度 {len(key)})")
    print()
    test_kimi("kimi-k2-0905-preview")
