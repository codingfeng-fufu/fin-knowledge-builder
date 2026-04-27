"""
规则发现相关检索与导入辅助。
"""

import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from ..models.rule_discovery import DocumentChunk, DocumentSet, RuleRecord, RuleSet
from ..utils.file_parser import split_text_into_chunks


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for match in TOKEN_PATTERN.findall((text or "").lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", match):
            if len(match) <= 2:
                tokens.append(match)
                continue
            tokens.append(match)
            tokens.extend(match[i:i + 2] for i in range(len(match) - 1))
            tokens.extend(match[i:i + 3] for i in range(len(match) - 2))
        else:
            tokens.append(match)
    return tokens


def _score_text(query: str, text: str) -> Dict[str, Any]:
    query_tokens = Counter(_tokenize(query))
    text_tokens = Counter(_tokenize(text))
    if not query_tokens or not text_tokens:
        return {"score": 0.0, "matched_terms": []}

    overlap_terms = sorted(set(query_tokens) & set(text_tokens))
    overlap_weight = sum(min(query_tokens[token], text_tokens[token]) for token in overlap_terms)
    norm = math.sqrt(sum(query_tokens.values()) * sum(text_tokens.values()))
    score = overlap_weight / norm if norm else 0.0

    normalized_query = (query or "").strip().lower()
    normalized_text = (text or "").strip().lower()
    if normalized_query and normalized_query in normalized_text:
        score += 0.35

    return {
        "score": round(score, 4),
        "matched_terms": overlap_terms[:12],
    }


def build_document_chunks(
    raw_text: str,
    source_name: str,
    document_id: str = "",
    chunk_size: int = 800,
    overlap: int = 120,
) -> List[DocumentChunk]:
    chunks = split_text_into_chunks(raw_text, chunk_size=chunk_size, overlap=overlap)
    results: List[DocumentChunk] = []
    current_offset = 0

    for index, chunk in enumerate(chunks):
        start_offset = raw_text.find(chunk, current_offset)
        if start_offset == -1:
            start_offset = current_offset
        end_offset = start_offset + len(chunk)
        current_offset = max(end_offset - overlap, 0)
        results.append(
            DocumentChunk(
                chunk_id=f"{document_id or 'pending'}_chunk_{index}",
                document_id=document_id or "pending",
                content=chunk,
                index=index,
                source_name=source_name,
                start_offset=start_offset,
                end_offset=end_offset,
                metadata={},
            )
        )

    return results


class RuleDiscoveryRetriever:
    def __init__(self, rule_set: Optional[RuleSet] = None, document_set: Optional[DocumentSet] = None):
        self.rule_set = rule_set
        self.document_set = document_set

    def search_rules(self, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        if not self.rule_set:
            return []

        results: List[Dict[str, Any]] = []
        for rule in self.rule_set.rules:
            searchable_text = "\n".join(
                [
                    rule.title,
                    rule.content,
                    " ".join(rule.conditions),
                    " ".join(rule.exceptions),
                    " ".join(rule.tags),
                    rule.source,
                ]
            )
            scoring = _score_text(query, searchable_text)
            if scoring["score"] <= 0:
                continue
            results.append(
                {
                    "rule_id": rule.rule_id,
                    "title": rule.title,
                    "content": rule.content,
                    "conditions": rule.conditions,
                    "exceptions": rule.exceptions,
                    "priority": rule.priority,
                    "source": rule.source,
                    "tags": rule.tags,
                    "score": scoring["score"],
                    "matched_terms": scoring["matched_terms"],
                }
            )

        results.sort(key=lambda item: (item["score"], item["priority"]), reverse=True)
        return results[:top_k]

    def search_documents(self, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        if not self.document_set:
            return []

        results: List[Dict[str, Any]] = []
        for chunk in self.document_set.chunks:
            scoring = _score_text(query, chunk.content)
            if scoring["score"] <= 0:
                continue
            excerpt = chunk.content
            if len(excerpt) > 260:
                excerpt = excerpt[:260].rstrip() + "..."
            results.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "reference": chunk.reference,
                    "document_id": chunk.document_id,
                    "source_name": chunk.source_name,
                    "content": chunk.content,
                    "excerpt": excerpt,
                    "score": scoring["score"],
                    "matched_terms": scoring["matched_terms"],
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]

    def scan_related_rules(
        self,
        query: str,
        *,
        exclude_rule_ids: Optional[List[str]] = None,
        min_score: float = 0.08,
        top_k: int = 6,
    ) -> List[Dict[str, Any]]:
        exclude_rule_ids = exclude_rule_ids or []
        hits = self.search_rules(query, top_k=max(top_k + len(exclude_rule_ids), top_k))
        results: List[Dict[str, Any]] = []
        for hit in hits:
            if hit["rule_id"] in exclude_rule_ids:
                continue
            if hit["score"] < min_score:
                continue
            results.append(hit)
            if len(results) >= top_k:
                break
        return results

    @staticmethod
    def format_rule_hits(rule_hits: List[Dict[str, Any]], max_chars: int = 4000) -> str:
        parts: List[str] = []
        current_length = 0
        for index, hit in enumerate(rule_hits, 1):
            block = (
                f"[{index}] {hit['rule_id']} | {hit['title']}\n"
                f"score={hit['score']}, matched_terms={','.join(hit.get('matched_terms', []))}\n"
                f"conditions={'; '.join(hit.get('conditions', [])) or 'N/A'}\n"
                f"exceptions={'; '.join(hit.get('exceptions', [])) or 'N/A'}\n"
                f"content={hit['content']}\n"
            )
            if current_length + len(block) > max_chars:
                break
            parts.append(block)
            current_length += len(block)
        return "\n".join(parts)

    @staticmethod
    def format_document_hits(document_hits: List[Dict[str, Any]], max_chars: int = 4000) -> str:
        parts: List[str] = []
        current_length = 0
        for index, hit in enumerate(document_hits, 1):
            block = (
                f"[{index}] {hit['reference']} | {hit['source_name']}\n"
                f"score={hit['score']}, matched_terms={','.join(hit.get('matched_terms', []))}\n"
                f"excerpt={hit['excerpt']}\n"
            )
            if current_length + len(block) > max_chars:
                break
            parts.append(block)
            current_length += len(block)
        return "\n".join(parts)

    @staticmethod
    def ensure_rule_records(raw_rules: List[Dict[str, Any]]) -> List[RuleRecord]:
        records: List[RuleRecord] = []
        for index, raw_rule in enumerate(raw_rules):
            rule_id = raw_rule.get("rule_id") or f"R-{index + 1:03d}"
            records.append(
                RuleRecord(
                    rule_id=rule_id,
                    title=raw_rule.get("title", "") or rule_id,
                    content=raw_rule.get("content", ""),
                    conditions=raw_rule.get("conditions", []) or [],
                    exceptions=raw_rule.get("exceptions", []) or [],
                    priority=int(raw_rule.get("priority", 0) or 0),
                    source=raw_rule.get("source", ""),
                    tags=raw_rule.get("tags", []) or [],
                    status=raw_rule.get("status", "active"),
                    metadata=raw_rule.get("metadata", {}) or {},
                )
            )
        return records
