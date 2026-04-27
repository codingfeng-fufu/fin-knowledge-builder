from __future__ import annotations

from typing import Any


CONTRACT_VERSION = "v0.4"
CURRENT_SUPPORTED_EXTENSIONS = ["txt", "md", "json", "csv", "log", "html", "htm", "pdf", "docx", "xlsx"]
TARGET_SUPPORTED_EXTENSIONS = ["pdf", "docx", "xlsx", "html", "htm", "msg", "txt", "md", "json", "csv", "log"]


def get_document_parser_contract() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "document_parser_mvp_connected",
        "summary": "当前 /workspace 已经接入 document parser MVP：txt/html/pdf/docx/xlsx 等上传材料会先被转换成 document preview / question packet / signal-based fact_sheet / evidence_packets，再进入 retrieval、TaskContext、RuleBinding 和 runtime 主链。PDF 当前优先走本地文本抽取，抽不到文本时再回退到 plugin/Kimi。",
        "current_mode": {
            "mode_id": "document_parser_mvp_connected",
            "label": "文档解析 MVP 模式",
            "description": "当前后端已支持文本和真实二进制文档上传，先解析出统一文本层、document preview、signal-based fact_sheet 与 evidence_packets，再进入工作台主链。",
        },
        "future_mode": {
            "mode_id": "structured_document_parser_enhanced",
            "label": "增强结构化文档解析模式",
            "description": "后续目标是补齐更细粒度的 blocks/tables/typed evidence locators，并把 signal-based fact_sheet 继续升级到值级 fact extraction。",
        },
        "workspace_role": {
            "entry_path": "/workspace",
            "entry_role": "expert_workbench",
            "entry_summary": "专家工作台负责接收问题与材料，输出处理建议，并把结果继续送往规则资产闭环。",
        },
        "input_contract": {
            "question_text": {
                "required": True,
                "description": "用户要解决的问题，后续会进入 Question Parser。",
            },
            "materials": {
                "required": False,
                "current_supported_extensions": CURRENT_SUPPORTED_EXTENSIONS,
                "target_supported_extensions": TARGET_SUPPORTED_EXTENSIONS,
                "item_schema": {
                    "name": "string",
                    "content": "string",
                    "content_base64": "string | null",
                    "media_type": "string | null",
                    "size": "integer | null",
                },
            },
        },
        "target_output_contract": {
            "document_set": {
                "description": "当前 document preview 供工作台展示、trace 和后续上下文桥接使用。",
                "fields": ["doc_id", "title", "doc_type", "source_type", "parse_status", "char_count", "line_count", "warnings"],
            },
            "question_packet": {
                "description": "问题结构化结果，连接问题文本、场景提示和 retrieval/runtime。",
                "fields": ["question_text", "question_types", "intents", "document_types", "extracted_inputs", "question_type", "scenario_hint", "target_object"],
            },
            "fact_sheet": {
                "description": "当前是 signal-based fact sheet：表示 required inputs 是否已在材料中被 grounded，而不是最终值级 facts。",
                "fields": ["fact_id", "fact_type", "value", "status", "source", "evidence_refs"],
            },
            "evidence_packets": {
                "description": "可直接出现在答案与 trace 中的证据片段。",
                "fields": ["doc_id", "snippet_id", "text", "locator", "chunk_type"],
            },
        },
        "runtime_bridge": {
            "consumes": ["question_packet", "fact_sheet", "evidence_packets", "document_chunks"],
            "current_bridge": "当前 /workspace 已把 parser 输出接到 retrieval、TaskContext、RuleBinding 和 runtime。retrieval 会消费 grounded fact keys，runtime 仍在执行阶段解析最终值。",
        },
        "todo_items": [
            "统一 blocks / tables / richer evidence locator 输出",
            "把 signal-based fact_sheet 进一步升级到值级 fact extraction",
            "让 parser 产出的 evidence refs 与 runtime/trace 引用完全对齐",
            "继续加强扫描版 PDF 与外部抽取回退链路的稳定性",
        ],
    }
