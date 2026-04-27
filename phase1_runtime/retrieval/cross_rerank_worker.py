from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


PHASE1_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_MODEL = PHASE1_ROOT / "local_models" / "BAAI__bge-reranker-base"
MODEL_NAME = os.getenv("PHASE1_RERANK_MODEL", str(DEFAULT_LOCAL_MODEL))
FALLBACK_MODEL_NAME = os.getenv("PHASE1_RERANK_FALLBACK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _load_model():
    model_name = MODEL_NAME
    fallback_used = False
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
    except Exception:
        model_name = FALLBACK_MODEL_NAME
        fallback_used = True
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
    model.to(DEVICE)
    model.eval()
    return tokenizer, model, model_name, fallback_used


def main() -> int:
    payload = json.loads(sys.stdin.read())
    query_text = str(payload.get("query_text", ""))
    candidates = list(payload.get("candidates", []))
    tokenizer, model, model_name, fallback_used = _load_model()

    scored = []
    for item in candidates:
        candidate_text = str(item.get("candidate_text", ""))
        rule_id = str(item.get("rule_id", ""))
        encoded = tokenizer(
            query_text,
            candidate_text,
            padding=True,
            truncation=True,
            max_length=384,
            return_tensors="pt",
        )
        encoded = {key: value.to(DEVICE) for key, value in encoded.items()}
        with torch.no_grad():
            logits = model(**encoded).logits
        score = float(logits.view(-1)[0].detach().cpu().item())
        scored.append(
            {
                "rule_id": rule_id,
                "score": round(score, 4),
                "candidate_text": candidate_text,
            }
        )

    scored.sort(key=lambda item: (item["score"], item["rule_id"]), reverse=True)
    print(
        json.dumps(
            {
                "candidates": scored,
                "diagnostics": {
                    "model_name": model_name,
                    "fallback_model_name": FALLBACK_MODEL_NAME,
                    "fallback_used": fallback_used,
                    "device": DEVICE,
                    "candidate_count": len(candidates),
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
