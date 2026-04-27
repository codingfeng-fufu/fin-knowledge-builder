from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import faiss
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer


PHASE1_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_MODEL = PHASE1_ROOT / "local_models" / "BAAI__bge-base-zh-v1.5"
MODEL_NAME = os.getenv("PHASE1_DENSE_MODEL", str(DEFAULT_LOCAL_MODEL))
FALLBACK_MODEL_NAME = os.getenv("PHASE1_DENSE_FALLBACK_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _index_path(root: Path) -> Path:
    return root / "dense_faiss.index"


def _manifest_path(root: Path) -> Path:
    return root / "dense_manifest.json"


def _load_encoder():
    model_name = MODEL_NAME
    fallback_used = False
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
    except Exception:
        model_name = FALLBACK_MODEL_NAME
        fallback_used = True
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
    model.to(DEVICE)
    model.eval()
    return tokenizer, model, model_name, fallback_used


def _encode_texts(tokenizer, model, texts: list[str], batch_size: int = 16) -> np.ndarray:
    rows: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        encoded = {key: value.to(DEVICE) for key, value in encoded.items()}
        with torch.no_grad():
            outputs = model(**encoded)
        hidden = outputs.last_hidden_state
        attention_mask = encoded["attention_mask"].unsqueeze(-1)
        pooled = (hidden * attention_mask).sum(dim=1) / attention_mask.sum(dim=1).clamp(min=1)
        pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        rows.extend(pooled.detach().cpu().float().tolist())
    return np.array(rows, dtype=np.float32)


def _load_or_build_index(root: Path, passages: list[dict[str, object]], tokenizer, model, model_name: str):
    manifest_path = _manifest_path(root)
    index_path = _index_path(root)
    if manifest_path.exists() and index_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                manifest.get("model_name") == model_name
                and int(manifest.get("passage_count", 0)) == len(passages)
            ):
                cpu_index = faiss.read_index(str(index_path))
                return cpu_index
        except Exception:
            pass

    embeddings = _encode_texts(tokenizer, model, [str(item.get("text", "")) for item in passages])
    cpu_index = faiss.IndexFlatIP(int(embeddings.shape[1]))
    cpu_index.add(embeddings)
    faiss.write_index(cpu_index, str(index_path))
    manifest_path.write_text(
        json.dumps(
            {
                "model_name": model_name,
                "fallback_model_name": FALLBACK_MODEL_NAME,
                "passage_count": len(passages),
                "dimension": int(embeddings.shape[1]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return cpu_index


def _maybe_gpu_index(cpu_index):
    if faiss.get_num_gpus() <= 0 or not hasattr(faiss, "StandardGpuResources"):
        return cpu_index
    try:
        resources = faiss.StandardGpuResources()
        return faiss.index_cpu_to_gpu(resources, 0, cpu_index)
    except Exception:
        return cpu_index


def main() -> int:
    payload = json.loads(sys.stdin.read())
    artifact_root = Path(str(payload["artifact_root"]))
    artifact_root.mkdir(parents=True, exist_ok=True)
    passages = list(payload.get("passages", []))
    rewrites = list(payload.get("rewrites", []))
    top_k = int(payload.get("top_k", 10) or 10)

    tokenizer, model, model_name, fallback_used = _load_encoder()
    cpu_index = _load_or_build_index(artifact_root, passages, tokenizer, model, model_name)
    index = _maybe_gpu_index(cpu_index)
    query_vectors = _encode_texts(tokenizer, model, [str(item.get("text", "")) for item in rewrites])
    distances, indices = index.search(query_vectors, top_k)

    scored_by_rule_id: dict[str, dict[str, object]] = {}
    for rewrite, row_scores, row_indices in zip(rewrites, distances.tolist(), indices.tolist()):
        for score, item_index in zip(row_scores, row_indices):
            if item_index < 0 or item_index >= len(passages):
                continue
            passage = passages[item_index]
            rule_id = passage.get("rule_id")
            if not isinstance(rule_id, str) or not rule_id:
                continue
            slot = scored_by_rule_id.setdefault(
                rule_id,
                {
                    "score": float(score),
                    "hits": 0,
                    "top_passage_id": str(passage.get("passage_id", "")),
                    "top_passage_type": str(passage.get("passage_type", "")),
                    "matched_rewrite_ids": [],
                },
            )
            slot["hits"] = int(slot["hits"]) + 1
            slot["matched_rewrite_ids"].append(str(rewrite.get("rewrite_id", "")))
            if float(score) > float(slot["score"]):
                slot["score"] = float(score)
                slot["top_passage_id"] = str(passage.get("passage_id", ""))
                slot["top_passage_type"] = str(passage.get("passage_type", ""))

    candidates = sorted(
        [
            {
                "rule_id": rule_id,
                "score": round(float(item["score"]), 4),
                "hits": int(item["hits"]),
                "top_passage_id": str(item["top_passage_id"]),
                "top_passage_type": str(item["top_passage_type"]),
                "matched_rewrite_ids": sorted(set(str(rewrite_id) for rewrite_id in item["matched_rewrite_ids"])),
            }
            for rule_id, item in scored_by_rule_id.items()
        ],
        key=lambda item: (item["score"], item["hits"], item["rule_id"]),
        reverse=True,
    )
    metadata_by_rule_id = {
        item["rule_id"]: {
            "dense_score": item["score"],
            "dense_hits": item["hits"],
            "dense_top_passage_id": item["top_passage_id"],
            "dense_top_passage_type": item["top_passage_type"],
            "dense_rewrite_ids": list(item["matched_rewrite_ids"]),
        }
        for item in candidates
    }
    print(
        json.dumps(
            {
                "candidates": candidates,
                "metadata_by_rule_id": metadata_by_rule_id,
                "diagnostics": {
                    "model_name": model_name,
                    "fallback_model_name": FALLBACK_MODEL_NAME,
                    "fallback_used": fallback_used,
                    "device": DEVICE,
                    "top_k": top_k,
                    "passage_count": len(passages),
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
