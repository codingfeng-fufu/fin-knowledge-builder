"""
规则发现型多智能体系统 API。
"""

import os
import tempfile
import threading
import traceback
from flask import jsonify, request

from . import discovery_bp
from ..config import Config
from ..models.rule_discovery import (
    DiscoveryMode,
    DiscoveryTaskStatus,
    DocumentStoreManager,
    RuleDiscoveryTaskManager,
    RuleSetManager,
)
from ..services.rule_discovery_engine import RuleDiscoveryEngine
from ..services.rule_discovery_retriever import (
    RuleDiscoveryRetriever,
    build_document_chunks,
)
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger


logger = get_logger('mirofish.api.discovery')


def allowed_file(filename: str) -> bool:
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


@discovery_bp.route('/rule-sets/import', methods=['POST'])
def import_rule_set():
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        raw_rules = data.get('rules') or []

        if not name:
            return jsonify({"success": False, "error": "请提供规则库名称 name"}), 400
        if not isinstance(raw_rules, list) or not raw_rules:
            return jsonify({"success": False, "error": "请提供非空 rules 数组"}), 400

        rules = RuleDiscoveryRetriever.ensure_rule_records(raw_rules)
        rule_set = RuleSetManager.create_rule_set(
            name=name,
            description=description,
            rules=rules,
            metadata=data.get('metadata', {}) or {},
        )

        return jsonify({
            "success": True,
            "data": rule_set.to_dict(),
        })
    except Exception as exc:
        logger.error("导入规则库失败: %s", exc)
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }), 500


@discovery_bp.route('/rule-sets', methods=['GET'])
def list_rule_sets():
    limit = request.args.get('limit', 50, type=int)
    rule_sets = RuleSetManager.list_rule_sets(limit=limit)
    return jsonify({
        "success": True,
        "data": [item.to_dict() for item in rule_sets],
        "count": len(rule_sets),
    })


@discovery_bp.route('/rule-sets/<rule_set_id>', methods=['GET'])
def get_rule_set(rule_set_id: str):
    rule_set = RuleSetManager.get_rule_set(rule_set_id)
    if not rule_set:
        return jsonify({"success": False, "error": f"规则库不存在: {rule_set_id}"}), 404

    return jsonify({
        "success": True,
        "data": rule_set.to_dict(),
    })


@discovery_bp.route('/documents/import', methods=['POST'])
def import_documents():
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            return _import_documents_from_upload()
        return _import_documents_from_json()
    except Exception as exc:
        logger.error("导入文档失败: %s", exc)
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }), 500


def _import_documents_from_json():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    raw_documents = data.get('documents') or []
    chunk_size = data.get('chunk_size', 800)
    overlap = data.get('overlap', 120)

    if not name:
        return jsonify({"success": False, "error": "请提供文档集名称 name"}), 400
    if not isinstance(raw_documents, list) or not raw_documents:
        return jsonify({"success": False, "error": "请提供 documents 数组"}), 400

    document_set = DocumentStoreManager.create_document_set(
        name=name,
        description=description,
        metadata=data.get('metadata', {}) or {},
    )

    imported_documents = []
    for item in raw_documents:
        title = (item.get('title') or 'document').strip()
        content = item.get('content', '')
        if not content.strip():
            continue
        cleaned = TextProcessor.preprocess_text(content)
        chunks = build_document_chunks(
            cleaned,
            source_name=title,
            chunk_size=int(chunk_size),
            overlap=int(overlap),
        )
        document = DocumentStoreManager.add_text_document(
            document_set.document_set_id,
            title=title,
            raw_text=cleaned,
            chunks=chunks,
            metadata=item.get('metadata', {}) or {},
        )
        imported_documents.append({
            "document_id": document.document_id,
            "title": title,
            "chunk_count": len(document.chunk_ids),
            "size": document.size,
        })

    if not imported_documents:
        return jsonify({"success": False, "error": "没有成功导入任何文本内容"}), 400

    stored = DocumentStoreManager.get_document_set(document_set.document_set_id)
    return jsonify({
        "success": True,
        "data": {
            "document_set": stored.to_dict() if stored else document_set.to_dict(),
            "imported_documents": imported_documents,
        },
    })


def _import_documents_from_upload():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    chunk_size = request.form.get('chunk_size', 800, type=int)
    overlap = request.form.get('overlap', 120, type=int)
    uploaded_files = request.files.getlist('files')

    if not name:
        return jsonify({"success": False, "error": "请提供文档集名称 name"}), 400
    if not uploaded_files or all(not f.filename for f in uploaded_files):
        return jsonify({"success": False, "error": "请至少上传一个文件"}), 400

    document_set = DocumentStoreManager.create_document_set(
        name=name,
        description=description,
        metadata={},
    )

    imported_documents = []
    for file in uploaded_files:
        if not file.filename:
            continue
        if not allowed_file(file.filename):
            continue

        suffix = os.path.splitext(file.filename)[1].lower()
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_path = temp_file.name
            file.save(temp_path)
            extracted = FileParser.extract_text(temp_path)
            cleaned = TextProcessor.preprocess_text(extracted)
            file.stream.seek(0)
            chunks = build_document_chunks(
                cleaned,
                source_name=file.filename,
                chunk_size=chunk_size,
                overlap=overlap,
            )
            document = DocumentStoreManager.add_uploaded_document(
                document_set.document_set_id,
                file_storage=file,
                chunks=chunks,
                metadata={"text_length": len(cleaned)},
            )
            imported_documents.append({
                "document_id": document.document_id,
                "filename": document.original_filename,
                "chunk_count": len(document.chunk_ids),
                "size": document.size,
            })
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    if not imported_documents:
        return jsonify({"success": False, "error": "没有成功导入任何受支持文件"}), 400

    stored = DocumentStoreManager.get_document_set(document_set.document_set_id)
    return jsonify({
        "success": True,
        "data": {
            "document_set": stored.to_dict() if stored else document_set.to_dict(),
            "imported_documents": imported_documents,
        },
    })


@discovery_bp.route('/document-sets', methods=['GET'])
def list_document_sets():
    limit = request.args.get('limit', 50, type=int)
    document_sets = DocumentStoreManager.list_document_sets(limit=limit)
    return jsonify({
        "success": True,
        "data": [item.to_dict() for item in document_sets],
        "count": len(document_sets),
    })


@discovery_bp.route('/document-sets/<document_set_id>', methods=['GET'])
def get_document_set(document_set_id: str):
    document_set = DocumentStoreManager.get_document_set(document_set_id)
    if not document_set:
        return jsonify({"success": False, "error": f"文档集不存在: {document_set_id}"}), 404

    return jsonify({
        "success": True,
        "data": document_set.to_dict(),
    })


@discovery_bp.route('/tasks/discover-rule', methods=['POST'])
def create_discovery_task():
    try:
        data = request.get_json() or {}
        query = data.get('query', '').strip()
        context = data.get('context', '').strip()
        rule_set_id = data.get('rule_set_id', '').strip()
        document_set_id = data.get('document_set_id')
        use_llm = bool(data.get('use_llm', False))
        discovery_mode_str = (data.get('discovery_mode') or 'grounded').strip().lower()
        deduplicate = bool(data.get('deduplicate', True))

        try:
            discovery_mode = DiscoveryMode(discovery_mode_str)
        except ValueError:
            return jsonify({"success": False, "error": f"不支持的 discovery_mode: {discovery_mode_str}"}), 400

        if not query:
            return jsonify({"success": False, "error": "请提供 query"}), 400
        if not rule_set_id:
            return jsonify({"success": False, "error": "请提供 rule_set_id"}), 400

        if not RuleSetManager.get_rule_set(rule_set_id):
            return jsonify({"success": False, "error": f"规则库不存在: {rule_set_id}"}), 404

        if document_set_id and not DocumentStoreManager.get_document_set(document_set_id):
            return jsonify({"success": False, "error": f"文档集不存在: {document_set_id}"}), 404

        metadata = data.get('metadata', {}) or {}
        metadata.setdefault('use_llm', use_llm)
        metadata.setdefault('discovery_mode', discovery_mode.value)

        if deduplicate:
            existing = RuleDiscoveryTaskManager.find_similar_active_task(
                query=query,
                context=context,
                rule_set_id=rule_set_id,
                discovery_mode=discovery_mode,
                document_set_id=document_set_id,
                use_llm=use_llm,
            )
            if existing:
                return jsonify({
                    "success": True,
                    "data": {
                        **existing.to_dict(),
                        "deduplicated": True,
                    },
                })

        task = RuleDiscoveryTaskManager.create_task(
            query=query,
            context=context,
            rule_set_id=rule_set_id,
            discovery_mode=discovery_mode,
            document_set_id=document_set_id,
            metadata=metadata,
        )

        def run_discovery():
            engine = RuleDiscoveryEngine(use_llm=use_llm)
            engine.run_task(task.task_id)

        thread = threading.Thread(target=run_discovery, daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "data": task.to_dict(),
        })
    except Exception as exc:
        logger.error("创建规则发现任务失败: %s", exc)
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }), 500


@discovery_bp.route('/tasks', methods=['GET'])
def list_tasks():
    limit = request.args.get('limit', 50, type=int)
    tasks = RuleDiscoveryTaskManager.list_tasks(limit=limit)
    return jsonify({
        "success": True,
        "data": [item.to_dict() for item in tasks],
        "count": len(tasks),
    })


@discovery_bp.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id: str):
    task = RuleDiscoveryTaskManager.get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404
    return jsonify({
        "success": True,
        "data": task.to_dict(),
    })


@discovery_bp.route('/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id: str):
    task = RuleDiscoveryTaskManager.get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404

    if task.status in {
        DiscoveryTaskStatus.COMPLETED,
        DiscoveryTaskStatus.FAILED,
        DiscoveryTaskStatus.CANCELLED,
        DiscoveryTaskStatus.TIMED_OUT,
        DiscoveryTaskStatus.INSUFFICIENT_EVIDENCE,
        DiscoveryTaskStatus.NEED_HUMAN_REVIEW,
    }:
        return jsonify({
            "success": False,
            "error": f"当前任务状态不支持取消: {task.status.value}",
        }), 400

    updated = RuleDiscoveryTaskManager.request_cancel(task_id)
    return jsonify({
        "success": True,
        "data": updated.to_dict() if updated else task.to_dict(),
    })


@discovery_bp.route('/tasks/<task_id>/rerun', methods=['POST'])
def rerun_task(task_id: str):
    origin = RuleDiscoveryTaskManager.get_task(task_id)
    if not origin:
        return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404

    data = request.get_json(silent=True) or {}
    use_llm = bool(data.get('use_llm', origin.metadata.get('use_llm', False)))
    discovery_mode_str = (data.get('discovery_mode') or origin.discovery_mode.value).strip().lower()
    try:
        discovery_mode = DiscoveryMode(discovery_mode_str)
    except ValueError:
        return jsonify({"success": False, "error": f"不支持的 discovery_mode: {discovery_mode_str}"}), 400
    metadata = dict(origin.metadata)
    metadata.update(data.get('metadata', {}) or {})
    metadata['use_llm'] = use_llm
    metadata['discovery_mode'] = discovery_mode.value

    task = RuleDiscoveryTaskManager.create_task(
        query=origin.query,
        context=origin.context,
        rule_set_id=origin.rule_set_id,
        discovery_mode=discovery_mode,
        document_set_id=origin.document_set_id,
        metadata=metadata,
        parent_task_id=origin.task_id,
        attempt_count=origin.attempt_count + 1,
    )

    def run_discovery():
        engine = RuleDiscoveryEngine(use_llm=use_llm)
        engine.run_task(task.task_id)

    thread = threading.Thread(target=run_discovery, daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "data": task.to_dict(),
    })


@discovery_bp.route('/tasks/<task_id>/result', methods=['GET'])
def get_task_result(task_id: str):
    task = RuleDiscoveryTaskManager.get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404

    result = RuleDiscoveryTaskManager.get_result(task_id)
    if not result:
        return jsonify({"success": False, "error": "任务结果尚未生成"}), 404

    return jsonify({
        "success": True,
        "data": {
            "task_id": task.task_id,
            "query": task.query,
            "context": task.context,
            **result.to_dict(),
        },
    })


@discovery_bp.route('/tasks/<task_id>/logs', methods=['GET'])
def get_task_logs(task_id: str):
    task = RuleDiscoveryTaskManager.get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404

    from_line = request.args.get('from_line', 0, type=int)
    logs = RuleDiscoveryTaskManager.get_logs(task_id)
    sliced = logs[from_line:] if from_line > 0 else logs

    return jsonify({
        "success": True,
        "data": {
            "task_id": task_id,
            "logs": sliced,
            "next_line": len(logs),
            "total": len(logs),
        },
    })


@discovery_bp.route('/tasks/<task_id>/stages', methods=['GET'])
def list_task_stages(task_id: str):
    task = RuleDiscoveryTaskManager.get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404

    stage_names = RuleDiscoveryTaskManager.list_stage_names(task_id)
    return jsonify({
        "success": True,
        "data": {
            "task_id": task_id,
            "stages": stage_names,
            "count": len(stage_names),
        },
    })


@discovery_bp.route('/tasks/<task_id>/stages/<stage>', methods=['GET'])
def get_task_stage(task_id: str, stage: str):
    task = RuleDiscoveryTaskManager.get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404

    payload = RuleDiscoveryTaskManager.get_stage_payload(task_id, stage)
    if payload is None:
        return jsonify({"success": False, "error": f"阶段产物不存在: {stage}"}), 404

    return jsonify({
        "success": True,
        "data": {
            "task_id": task_id,
            "stage": stage,
            "payload": payload,
        },
    })
