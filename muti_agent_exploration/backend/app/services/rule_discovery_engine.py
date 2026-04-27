"""
规则发现型多智能体编排服务。
"""

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Config
from ..models.rule_discovery import (
    CandidateRule,
    CandidateType,
    DiscoveryDecision,
    DiscoveryMode,
    DiscoveryTask,
    DiscoveryTaskStatus,
    ResolutionType,
    RuleDiscoveryTaskManager,
    RuleSetManager,
    DocumentStoreManager,
    ValidationStatus,
)
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .rule_discovery_retriever import RuleDiscoveryRetriever


logger = get_logger('mirofish.rule_discovery')

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
STOPWORDS = {
    "的", "了", "和", "与", "及", "或", "并", "且", "对", "就", "是", "在", "将", "要",
    "是否", "什么", "如何", "哪些", "这个", "那个", "需要", "根据", "结合", "针对",
    "query", "context", "rule", "rules", "document", "documents",
}

RELATION_PRIORITY = {
    "conflict": 4,
    "duplicate": 3,
    "tighten": 2,
    "supplement": 1,
    "analogous": 0,
}

TEMPLATE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'rule_discovery_templates.json')


def _load_template_library() -> Dict[str, Any]:
    try:
        with open(TEMPLATE_CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("templates"), dict):
            return data
    except Exception as exc:
        logger.warning("加载规则模板配置失败，回退到内置模板: %s", exc)

    return {
        "default_template": "generic_control",
        "templates": {
            "ai_external_communication": {
                "title": "AI外发内容审核规则",
                "description": "适用于 AI 生成或辅助生成的拟对外发送文本。",
                "match_all": ["ai_generated", "external_communication"],
                "match_any": [],
                "required_controls": [
                    "完成人工复核",
                    "核实涉及事实、时间、范围和承诺的内容",
                ],
                "required_review_roles": [
                    "发送责任人",
                    "业务负责人",
                ],
                "required_confirmation_targets": [
                    "合作范围",
                    "交付时间",
                    "承诺措辞",
                ],
            },
            "ambiguous_disclosure": {
                "title": "对外披露澄清规则",
                "description": "适用于表述模糊、可能引发误解的披露或说明场景。",
                "match_all": ["external_communication", "misleading_expression"],
                "match_any": [],
                "required_controls": [
                    "修正可能造成误解的表述",
                ],
                "required_review_roles": [
                    "业务负责人",
                ],
                "required_confirmation_targets": [
                    "表述准确性",
                ],
            },
            "data_external_sharing": {
                "title": "外发数据审查规则",
                "description": "适用于包含数据、隐私或敏感信息的外部共享场景。",
                "match_all": ["external_communication", "sensitive_data"],
                "match_any": [],
                "required_controls": [
                    "确认数据共享范围",
                    "核验外发授权与脱敏状态",
                ],
                "required_review_roles": [
                    "业务负责人",
                    "数据或合规责任人",
                ],
                "required_confirmation_targets": [
                    "数据授权范围",
                    "脱敏状态",
                ],
            },
            "external_commitment_review": {
                "title": "对外承诺审核规则",
                "description": "适用于涉及对外承诺、交付时间、合作结论确认的外部沟通场景。",
                "match_all": ["external_communication", "unverified_commitment"],
                "match_any": [],
                "required_controls": [
                    "核实涉及事实、时间、范围和承诺的内容",
                ],
                "required_review_roles": [
                    "业务负责人",
                ],
                "required_confirmation_targets": [
                    "合作范围",
                    "交付时间",
                    "承诺措辞",
                ],
            },
            "human_review_gate": {
                "title": "人工复核门槛规则",
                "description": "适用于自动生成、高风险或责任不清的内容在执行前必须经过人工复核的场景。",
                "match_all": [],
                "match_any": ["ai_generated", "misleading_expression", "unverified_commitment"],
                "required_controls": [
                    "完成人工复核",
                ],
                "required_review_roles": [
                    "业务负责人",
                ],
                "required_confirmation_targets": [],
            },
            "generic_control": {
                "title": "风险控制规则",
                "description": "适用于无法归入具体模板时的一般性治理约束。",
                "match_all": [],
                "match_any": [],
                "required_controls": [],
                "required_review_roles": [],
                "required_confirmation_targets": [],
            },
            "financial_analysis_method": {
                "title": "金融分析求解方法",
                "description": "适用于研报、财务或经营分析类问题，要求系统优先围绕指标、趋势、证据和结论组织回答。",
                "match_all": [],
                "match_any": [],
                "required_controls": [],
                "required_review_roles": [],
                "required_confirmation_targets": [],
            },
        },
    }


RULE_TEMPLATE_LIBRARY: Dict[str, Any] = _load_template_library()


class RuleDiscoveryEngine:
    def __init__(self, llm_client: Optional[LLMClient] = None, use_llm: bool = True):
        self.llm_client: Optional[LLMClient] = None
        if not use_llm:
            return
        if llm_client:
            self.llm_client = llm_client
        elif Config.LLM_API_KEY:
            try:
                self.llm_client = LLMClient()
            except Exception as exc:
                logger.warning("规则发现服务初始化 LLMClient 失败，将使用启发式回退: %s", exc)

    def run_task(self, task_id: str) -> DiscoveryDecision:
        task = RuleDiscoveryTaskManager.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        rule_set = RuleSetManager.get_rule_set(task.rule_set_id)
        if not rule_set:
            raise ValueError(f"规则库不存在: {task.rule_set_id}")

        document_set = None
        if task.document_set_id:
            document_set = DocumentStoreManager.get_document_set(task.document_set_id)
            if not document_set:
                raise ValueError(f"文档集不存在: {task.document_set_id}")

        retriever = RuleDiscoveryRetriever(rule_set=rule_set, document_set=document_set)
        RuleDiscoveryTaskManager.append_log(task_id, "start", "规则发现任务开始", {
            "rule_set_id": task.rule_set_id,
            "document_set_id": task.document_set_id,
            "llm_enabled": bool(self.llm_client),
        })
        RuleDiscoveryTaskManager.update_task(task_id, started_at=datetime.now().isoformat())

        try:
            self._update_progress(task, DiscoveryTaskStatus.RECEIVED, 5, "received")
            self._check_task_control(task_id)

            problem_frame = self._build_problem_frame(task)
            problem_frame = self._decorate_stage_payload(task, "problem_frame", problem_frame)
            RuleDiscoveryTaskManager.save_stage_payload(task_id, "problem_frame", problem_frame)
            RuleDiscoveryTaskManager.append_log(task_id, "problem_frame", "问题建模完成", problem_frame)
            self._update_progress(task, DiscoveryTaskStatus.FRAMED, 18, "problem_frame")
            self._check_task_control(task_id)

            analogies = self._find_analogies(task, retriever, problem_frame)
            analogies = self._decorate_stage_payload(task, "analogies", analogies)
            RuleDiscoveryTaskManager.save_stage_payload(task_id, "analogies", analogies)
            RuleDiscoveryTaskManager.append_log(task_id, "analogies", "类比规则分析完成", {
                "reuse_candidates": analogies.get("reuse_candidates", []),
                "adaptation_candidates": analogies.get("adaptation_candidates", []),
                "gaps": analogies.get("gaps", []),
            })
            self._update_progress(task, DiscoveryTaskStatus.ANALOGIES_FOUND, 35, "analogies")
            self._check_task_control(task_id)

            evidence = self._collect_evidence(task, retriever, problem_frame, analogies)
            evidence = self._decorate_stage_payload(task, "evidence", evidence)
            RuleDiscoveryTaskManager.save_stage_payload(task_id, "evidence", evidence)
            RuleDiscoveryTaskManager.append_log(task_id, "evidence", "证据检索完成", {
                "evidence_count": len(evidence.get("evidence_items", [])),
                "open_questions": evidence.get("open_questions", []),
            })
            self._update_progress(task, DiscoveryTaskStatus.EVIDENCE_COLLECTED, 52, "evidence")
            self._check_task_control(task_id)

            candidates = self._propose_candidates(task, problem_frame, analogies, evidence, rule_set)
            candidate_payload = self._decorate_stage_payload(task, "candidates", {
                "candidates": [item.to_dict() for item in candidates]
            })
            RuleDiscoveryTaskManager.save_stage_payload(task_id, "candidates", candidate_payload)
            RuleDiscoveryTaskManager.append_log(task_id, "candidates", "候选规则生成完成", {
                "candidate_count": len(candidates),
                "candidate_types": [item.candidate_type.value for item in candidates],
            })
            self._update_progress(task, DiscoveryTaskStatus.CANDIDATES_PROPOSED, 70, "candidates")
            self._check_task_control(task_id)

            validated = self._validate_candidates(task, retriever, problem_frame, analogies, evidence, candidates)
            validated = self._decorate_stage_payload(task, "validation", validated)
            RuleDiscoveryTaskManager.save_stage_payload(task_id, "validation", validated)
            RuleDiscoveryTaskManager.append_log(task_id, "validation", "候选规则验证完成", {
                "rejected_candidates": validated.get("rejected_candidates", []),
                "open_questions": validated.get("open_questions", []),
            })
            self._update_progress(task, DiscoveryTaskStatus.CANDIDATES_VALIDATED, 86, "validation")
            self._check_task_control(task_id)

            decision = self._finalize_decision(task, candidates, validated)
            RuleDiscoveryTaskManager.save_result(task_id, decision)
            RuleDiscoveryTaskManager.append_log(task_id, "decision", "规则发现结果已生成", decision.to_dict())

            final_status = DiscoveryTaskStatus.COMPLETED
            if decision.need_human_review:
                final_status = DiscoveryTaskStatus.NEED_HUMAN_REVIEW
            elif decision.resolution_type == ResolutionType.INSUFFICIENT_EVIDENCE:
                final_status = DiscoveryTaskStatus.INSUFFICIENT_EVIDENCE

            self._update_progress(task, final_status, 100, "completed")
            RuleDiscoveryTaskManager.update_task(task_id, completed_at=datetime.now().isoformat())
            return decision
        except DiscoveryCancelledError as exc:
            RuleDiscoveryTaskManager.append_log(task_id, "cancelled", "规则发现任务已取消", {
                "reason": str(exc),
            }, level="warning")
            RuleDiscoveryTaskManager.update_task(
                task_id,
                status=DiscoveryTaskStatus.CANCELLED,
                progress=100,
                current_stage="cancelled",
                error=str(exc),
                completed_at=datetime.now().isoformat(),
            )
            raise
        except DiscoveryTimedOutError as exc:
            RuleDiscoveryTaskManager.append_log(task_id, "timed_out", "规则发现任务超时", {
                "reason": str(exc),
            }, level="error")
            RuleDiscoveryTaskManager.update_task(
                task_id,
                status=DiscoveryTaskStatus.TIMED_OUT,
                progress=100,
                current_stage="timed_out",
                error=str(exc),
                completed_at=datetime.now().isoformat(),
            )
            raise
        except Exception as exc:
            logger.exception("规则发现任务失败: %s", task_id)
            RuleDiscoveryTaskManager.append_log(task_id, "failed", "规则发现任务失败", {
                "error": str(exc),
            }, level="error")
            RuleDiscoveryTaskManager.update_task(
                task_id,
                status=DiscoveryTaskStatus.FAILED,
                progress=100,
                current_stage="failed",
                error=str(exc),
                completed_at=datetime.now().isoformat(),
            )
            raise

    def _update_progress(
        self,
        task: DiscoveryTask,
        status: DiscoveryTaskStatus,
        progress: int,
        stage: str,
    ) -> None:
        RuleDiscoveryTaskManager.update_task(
            task.task_id,
            status=status,
            progress=progress,
            current_stage=stage,
        )

    def _check_task_control(self, task_id: str) -> None:
        task = RuleDiscoveryTaskManager.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        if task.cancel_requested:
            raise DiscoveryCancelledError("任务被用户取消")
        timeout_seconds = int(task.metadata.get("timeout_seconds", 0) or 0)
        if timeout_seconds <= 0 or not task.created_at:
            return
        started = datetime.fromisoformat(task.created_at)
        elapsed = (datetime.now() - started).total_seconds()
        if elapsed > timeout_seconds:
            raise DiscoveryTimedOutError(f"任务执行超过 {timeout_seconds} 秒")

    def _decorate_stage_payload(self, task: DiscoveryTask, stage: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        enriched = dict(payload)
        enriched["agent_runs"] = self._build_stage_agent_runs(task, stage, payload)
        return enriched

    def _build_stage_agent_runs(self, task: DiscoveryTask, stage: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        builders = {
            "problem_frame": self._build_problem_frame_agent_runs,
            "analogies": self._build_analogy_agent_runs,
            "evidence": self._build_evidence_agent_runs,
            "candidates": self._build_candidate_agent_runs,
            "validation": self._build_validation_agent_runs,
        }
        builder = builders.get(stage)
        if not builder:
            return []
        return builder(task, payload)

    def _agent_run(
        self,
        *,
        agent_name: str,
        role: str,
        tone: str,
        headline: str,
        points: List[str],
        raw: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "agent_name": agent_name,
            "role": role,
            "tone": tone,
            "headline": headline,
            "points": [item for item in points if item],
            "raw": raw,
        }

    def _build_problem_frame_agent_runs(self, task: DiscoveryTask, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            self._agent_run(
                agent_name="Intent Mapper",
                role="Problem Framer",
                tone="blue",
                headline="先定义这个任务到底是在找旧规则、改造旧规则，还是在探索新规则。",
                points=[
                    f"Intent: {payload.get('intent', 'discover_rule')}",
                    f"Action: {payload.get('action', 'N/A')}",
                ],
                raw={
                    "intent": payload.get("intent"),
                    "action": payload.get("action"),
                },
            ),
            self._agent_run(
                agent_name="Constraint Extractor",
                role="Problem Framer",
                tone="teal",
                headline="把 Query 和 Context 里的约束条件单独拉出来，后面所有 agent 都围绕这些条件工作。",
                points=[
                    f"Entities: {', '.join(payload.get('entities', [])) or 'N/A'}",
                    f"Constraints: {'；'.join(payload.get('constraints', [])) or 'N/A'}",
                ],
                raw={
                    "entities": payload.get("entities", []),
                    "constraints": payload.get("constraints", []),
                },
            ),
            self._agent_run(
                agent_name="Ambiguity Mapper",
                role="Problem Framer",
                tone="orange",
                headline="提前标出模糊项和待查证问题，防止后续 agent 误把假设当结论。",
                points=[
                    f"Ambiguities: {'；'.join(payload.get('ambiguities', [])) or '无'}",
                    f"Search Queries: {' / '.join(payload.get('search_queries', [])) or '无'}",
                ],
                raw={
                    "ambiguities": payload.get("ambiguities", []),
                    "search_queries": payload.get("search_queries", []),
                },
            ),
        ]

    def _build_analogy_agent_runs(self, task: DiscoveryTask, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            self._agent_run(
                agent_name="Exact Match Scout",
                role="Analogy Miner",
                tone="green",
                headline="优先尝试在规则库里找能直接复用的旧规则。",
                points=[
                    f"Reuse Candidates: {', '.join(payload.get('reuse_candidates', [])) or '无'}",
                ],
                raw={
                    "reuse_candidates": payload.get("reuse_candidates", []),
                    "rule_hits": payload.get("rule_hits", [])[:3],
                },
            ),
            self._agent_run(
                agent_name="Adaptation Scout",
                role="Analogy Miner",
                tone="purple",
                headline="如果没有现成规则，就找最接近的旧规则结构，看看能不能改造。",
                points=[
                    f"Adaptation Candidates: {', '.join(payload.get('adaptation_candidates', [])) or '无'}",
                    f"Gaps: {'；'.join(payload.get('gaps', [])) or '无'}",
                ],
                raw={
                    "adaptation_candidates": payload.get("adaptation_candidates", []),
                    "gaps": payload.get("gaps", []),
                },
            ),
            self._agent_run(
                agent_name="Negative Miner",
                role="Analogy Miner",
                tone="red",
                headline="主动找‘不相干’和‘不完全同构’的证据，避免错误类比。",
                points=[
                    f"Top Mismatch: {payload.get('analogies', [])[0].get('mismatch_points', ['无'])[0] if payload.get('analogies') else '无'}",
                    f"Total Analogy Hits: {len(payload.get('analogies', []))}",
                ],
                raw={
                    "analogies": payload.get("analogies", []),
                },
            ),
        ]

    def _build_evidence_agent_runs(self, task: DiscoveryTask, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        evidence_items = payload.get("evidence_items", [])
        return [
            self._agent_run(
                agent_name="Support Finder",
                role="Evidence Explorer",
                tone="green",
                headline="先把最能支持候选规则的文档片段找出来。",
                points=[
                    *(f"{item.get('reference') or 'evidence'}: {item.get('excerpt') or item.get('why_relevant')}" for item in evidence_items[:2]),
                ] or ["暂无支持性证据"],
                raw={"evidence_items": evidence_items[:2]},
            ),
            self._agent_run(
                agent_name="Risk Finder",
                role="Evidence Explorer",
                tone="orange",
                headline="单独看风险点和误导因素，避免只挑支持证据。",
                points=[
                    *(f"Risk Signal: {item.get('why_relevant') or item.get('excerpt')}" for item in evidence_items[2:4]),
                ] or ["暂无额外风险证据"],
                raw={"evidence_items": evidence_items[2:4]},
            ),
            self._agent_run(
                agent_name="Gap Finder",
                role="Evidence Explorer",
                tone="red",
                headline="把当前证据还不足以说明的问题单独列出来。",
                points=[
                    f"Open Questions: {'；'.join(payload.get('open_questions', [])) or '无'}",
                ],
                raw={"open_questions": payload.get("open_questions", [])},
            ),
        ]

    def _build_candidate_agent_runs(self, task: DiscoveryTask, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates = payload.get("candidates", [])
        if not candidates:
            return []

        by_type = {}
        for candidate in candidates:
            candidate_type = candidate.get("candidate_type", "unknown")
            by_type.setdefault(candidate_type, candidate)

        runs: List[Dict[str, Any]] = []
        mapping = {
            "exact_reuse": ("Reuse Drafter", "blue", "优先尝试直接复用旧规则。"),
            "adapted_rule": ("Adaptation Drafter", "teal", "在旧规则框架上补条件、补边界。"),
            "novel_rule": ("Novel Rule Drafter", "wine", "在旧规则无法覆盖时提出全新候选规则。"),
        }
        for candidate_type, candidate in by_type.items():
            name, tone, headline = mapping.get(candidate_type, ("Rule Drafter", "purple", "提出候选规则。"))
            runs.append(
                self._agent_run(
                    agent_name=name,
                    role="Rule Hypothesizer",
                    tone=tone,
                    headline=headline,
                    points=[
                        f"Title: {candidate.get('rule_title', 'N/A')}",
                        f"Sources: {' / '.join(candidate.get('knowledge_sources', [])) or 'N/A'}",
                        f"Ground / Spec: {candidate.get('grounding_score', '--')} / {candidate.get('speculation_score', '--')}",
                    ],
                    raw=candidate,
                )
            )
        return runs

    def _build_validation_agent_runs(self, task: DiscoveryTask, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidate = (payload.get("candidates") or [{}])[0]
        critic = candidate.get("critic_report", {})
        relation_line = " / ".join(
            f"{item.get('rule_id')}:{item.get('relation_type')}"
            for item in critic.get("related_rules", [])
        ) or "无"
        return [
            self._agent_run(
                agent_name="Conflict Critic",
                role="Rule Critic",
                tone="red",
                headline="先看候选规则和现有规则体系是否打架。",
                points=[
                    f"Relations: {relation_line}",
                    f"Adjudication: {critic.get('adjudication', {}).get('reason', '无')}",
                ],
                raw={"related_rules": critic.get("related_rules", []), "adjudication": critic.get("adjudication", {})},
            ),
            self._agent_run(
                agent_name="Counterexample Critic",
                role="Rule Critic",
                tone="orange",
                headline="尝试用反例和边界条件把候选规则推翻。",
                points=[
                    *(critic.get("counterexamples", [])[:3]),
                ] or ["未发现明显反例"],
                raw={"counterexamples": critic.get("counterexamples", [])},
            ),
            self._agent_run(
                agent_name="Provenance Critic",
                role="Rule Critic",
                tone="purple",
                headline="检查这条规则的来源、缺口和可追溯性是否足够。",
                points=[
                    f"Validation: {candidate.get('validation_status', 'N/A')}",
                    f"Missing Elements: {'；'.join(critic.get('missing_elements', [])) or '无'}",
                    f"Reason: {candidate.get('validation_reason', 'N/A')}",
                ],
                raw=candidate,
            ),
        ]

    def _stage_system_prompt(self, base_prompt: str, mode: DiscoveryMode, stage: str) -> str:
        if mode == DiscoveryMode.EMERGENT:
            return (
                base_prompt
                + " 你可以引入通用知识、行业常识和跨法域经验进行规则探究，"
                + "但必须显式区分哪些内容来自输入材料，哪些来自通用知识，哪些只是推断。"
            )
        return (
            base_prompt
            + " 你必须尽量闭卷，只能基于当前任务提供的规则库、文档证据和中间产物推理。"
            + " 不得引入输入中未出现的外部制度、法域、监管机构或通用知识结论。"
        )

    def _build_source_provenance(
        self,
        mode: DiscoveryMode,
        evidence_refs: List[str],
        *,
        allow_general: bool,
        derived_from: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        derived_from = derived_from or []
        knowledge_sources = ["rule_library", "document_evidence"]
        grounding_score = 0.78 if evidence_refs else 0.52
        speculation_score = 0.22 if evidence_refs else 0.48
        if allow_general and mode == DiscoveryMode.EMERGENT:
            knowledge_sources.append("general_knowledge")
            grounding_score = min(grounding_score, 0.66)
            speculation_score = max(speculation_score, 0.34)

        if derived_from:
            grounding_score = min(max(grounding_score + 0.08, 0.0), 0.95)
            speculation_score = max(speculation_score - 0.08, 0.05)

        return {
            "mode": mode.value,
            "rule_refs": derived_from,
            "evidence_refs": evidence_refs,
            "general_knowledge_used": "general_knowledge" in knowledge_sources,
            "knowledge_sources": knowledge_sources,
            "grounding_score": round(grounding_score, 3),
            "speculation_score": round(speculation_score, 3),
        }

    def _build_problem_frame(self, task: DiscoveryTask) -> Dict[str, Any]:
        fallback = self._build_problem_frame_fallback(task)
        if not self.llm_client:
            return fallback

        system_prompt = self._stage_system_prompt(
            (
            "你是 Problem Framer。你的任务是把用户问题建模成结构化问题，不要输出规则。"
            "只输出 JSON，对象字段固定为：intent, entities, action, constraints, exceptions, ambiguities, search_queries。"
            ),
            task.discovery_mode,
            "problem_frame",
        )
        user_payload = {
            "query": task.query,
            "context": task.context,
            "fallback_reference": fallback,
        }
        llm_result = self._call_json_with_fallback(
            stage="problem_frame",
            payload=user_payload,
            system_prompt=system_prompt,
            fallback=fallback,
        )
        return self._normalize_problem_frame_result(llm_result, fallback)

    def _build_problem_frame_fallback(self, task: DiscoveryTask) -> Dict[str, Any]:
        combined = "\n".join(part for part in [task.query, task.context] if part)
        keywords = self._extract_keywords(combined, limit=8)
        constraints = self._split_sentences(task.context, limit=3)
        if not constraints and task.query:
            constraints = self._split_sentences(task.query, limit=2)

        search_queries = [task.query.strip()]
        for sentence in constraints[:2]:
            query = sentence.strip()
            if query and query not in search_queries:
                search_queries.append(query)
        if task.context:
            mixed = f"{task.query.strip()} {task.context[:80].strip()}".strip()
            if mixed and mixed not in search_queries:
                search_queries.append(mixed)

        return {
            "intent": "discover_rule",
            "entities": keywords[:4],
            "action": task.query[:160].strip(),
            "constraints": constraints,
            "exceptions": [],
            "ambiguities": [],
            "search_queries": search_queries[:4],
        }

    def _find_analogies(
        self,
        task: DiscoveryTask,
        retriever: RuleDiscoveryRetriever,
        problem_frame: Dict[str, Any],
    ) -> Dict[str, Any]:
        query = self._compose_search_query(task, problem_frame)
        rule_hits = retriever.search_rules(query, top_k=8)
        fallback = self._find_analogies_fallback(rule_hits)
        fallback["rule_hits"] = rule_hits

        if not self.llm_client or not rule_hits:
            return fallback

        system_prompt = self._stage_system_prompt(
            (
            "你是 Analogy Miner。你的任务不是强行命中旧规则，而是判断哪些旧规则可直接复用、"
            "哪些只能作为改造起点，以及当前问题相对旧规则还缺什么。"
            "只输出 JSON，字段固定为：analogies, reuse_candidates, adaptation_candidates, gaps。"
            ),
            task.discovery_mode,
            "analogies",
        )
        user_payload = {
            "problem_frame": problem_frame,
            "rule_hits": rule_hits,
        }
        llm_result = self._call_json_with_fallback(
            stage="analogies",
            payload=user_payload,
            system_prompt=system_prompt,
            fallback=fallback,
        )
        normalized = self._normalize_analogy_result(llm_result, rule_hits, fallback)
        normalized["rule_hits"] = rule_hits
        return normalized

    def _find_analogies_fallback(self, rule_hits: List[Dict[str, Any]]) -> Dict[str, Any]:
        analogies: List[Dict[str, Any]] = []
        reuse_candidates: List[str] = []
        adaptation_candidates: List[str] = []
        gaps: List[str] = []

        for hit in rule_hits[:5]:
            reusable = hit["score"] >= 0.8
            adaptable = hit["score"] >= 0.18
            if reusable:
                reuse_candidates.append(hit["rule_id"])
            elif adaptable:
                adaptation_candidates.append(hit["rule_id"])

            analogies.append(
                {
                    "rule_id": hit["rule_id"],
                    "title": hit["title"],
                    "score": hit["score"],
                    "reusable": reusable,
                    "adaptable": adaptable,
                    "match_points": hit.get("matched_terms", []),
                    "mismatch_points": [] if reusable else ["当前问题与已有规则并非完全同构"],
                }
            )

        if not reuse_candidates and not adaptation_candidates:
            if rule_hits:
                adaptation_candidates.append(rule_hits[0]["rule_id"])
                gaps.append("未找到可直接复用规则，但存在可作为改造起点的近似规则")
            else:
                gaps.append("现有规则库中未找到可直接迁移的规则结构")
        elif not reuse_candidates:
            gaps.append("存在相似规则，但仍需补充条件或新增约束")

        return {
            "analogies": analogies,
            "reuse_candidates": reuse_candidates,
            "adaptation_candidates": adaptation_candidates,
            "gaps": gaps,
        }

    def _normalize_analogy_result(
        self,
        llm_result: Dict[str, Any],
        rule_hits: List[Dict[str, Any]],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        rule_id_set = {item["rule_id"] for item in rule_hits if item.get("rule_id")}

        def normalize_rule_refs(value: Any) -> List[str]:
            items = value if isinstance(value, list) else [value] if value else []
            results: List[str] = []
            for item in items:
                if isinstance(item, str):
                    if item in rule_id_set:
                        results.append(item)
                elif isinstance(item, dict):
                    rule_id = item.get("rule_id") or item.get("id") or item.get("name")
                    if isinstance(rule_id, str) and rule_id in rule_id_set:
                        results.append(rule_id)
            return list(dict.fromkeys(results))

        def normalize_gap_items(value: Any) -> List[str]:
            items = value if isinstance(value, list) else [value] if value else []
            results: List[str] = []
            for item in items:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        results.append(text)
                    continue
                if isinstance(item, dict):
                    text = str(
                        item.get("summary")
                        or item.get("reason")
                        or item.get("gap")
                        or item.get("description")
                        or ""
                    ).strip()
                    if text:
                        results.append(text)
            return results

        analogies = llm_result.get("analogies", fallback.get("analogies", []))
        if not isinstance(analogies, list):
            analogies = fallback.get("analogies", [])

        gaps = normalize_gap_items(llm_result.get("gaps", fallback.get("gaps", [])))
        if not gaps:
            gaps = normalize_gap_items(fallback.get("gaps", []))

        reuse_candidates = normalize_rule_refs(llm_result.get("reuse_candidates", []))
        adaptation_candidates = normalize_rule_refs(llm_result.get("adaptation_candidates", []))

        if not reuse_candidates and not adaptation_candidates:
            reuse_candidates = fallback.get("reuse_candidates", [])
            adaptation_candidates = fallback.get("adaptation_candidates", [])

        return {
            "analogies": analogies,
            "reuse_candidates": reuse_candidates,
            "adaptation_candidates": adaptation_candidates,
            "gaps": gaps,
        }

    def _collect_evidence(
        self,
        task: DiscoveryTask,
        retriever: RuleDiscoveryRetriever,
        problem_frame: Dict[str, Any],
        analogies: Dict[str, Any],
    ) -> Dict[str, Any]:
        fallback = self._collect_evidence_fallback(task, retriever, problem_frame, analogies)
        if not self.llm_client or not fallback.get("document_hits"):
            return fallback

        system_prompt = self._stage_system_prompt(
            (
            "你是 Evidence Explorer。你只能从候选文档片段里提取支持或反驳候选规则的证据，"
            "不得直接宣告规则成立。只输出 JSON，字段固定为：evidence_items, open_questions。"
            ),
            task.discovery_mode,
            "evidence",
        )
        user_payload = {
            "problem_frame": problem_frame,
            "analogies": {
                "reuse_candidates": analogies.get("reuse_candidates", []),
                "adaptation_candidates": analogies.get("adaptation_candidates", []),
                "gaps": analogies.get("gaps", []),
            },
            "document_hits": fallback.get("document_hits", []),
        }
        llm_result = self._call_json_with_fallback(
            stage="evidence",
            payload=user_payload,
            system_prompt=system_prompt,
            fallback=fallback,
        )
        return self._normalize_evidence_result(llm_result, fallback)

    def _collect_evidence_fallback(
        self,
        task: DiscoveryTask,
        retriever: RuleDiscoveryRetriever,
        problem_frame: Dict[str, Any],
        analogies: Dict[str, Any],
    ) -> Dict[str, Any]:
        search_queries = problem_frame.get("search_queries", []) or [task.query]
        aggregated: List[Dict[str, Any]] = []
        seen_chunk_ids = set()

        for query in search_queries[:4]:
            for hit in retriever.search_documents(query, top_k=4):
                if hit["chunk_id"] in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(hit["chunk_id"])
                aggregated.append(hit)
                if len(aggregated) >= 8:
                    break
            if len(aggregated) >= 8:
                break

        evidence_items = [
            {
                "reference": hit["reference"],
                "source_name": hit["source_name"],
                "excerpt": hit["excerpt"],
                "why_relevant": (
                    "用于支撑候选规则的适用条件"
                    if analogies.get("reuse_candidates") or analogies.get("adaptation_candidates")
                    else "用于补充现有规则无法覆盖的新场景证据"
                ),
            }
            for hit in aggregated
        ]

        return {
            "evidence_items": evidence_items,
            "open_questions": [] if evidence_items else ["尚未在原始文档中找到足够证据"],
            "document_hits": aggregated,
        }

    def _propose_candidates(
        self,
        task: DiscoveryTask,
        problem_frame: Dict[str, Any],
        analogies: Dict[str, Any],
        evidence: Dict[str, Any],
        rule_set: Any,
    ) -> List[CandidateRule]:
        fallback = self._propose_candidates_fallback(task, problem_frame, analogies, evidence, rule_set)
        if not self.llm_client:
            return fallback

        system_prompt = self._stage_system_prompt(
            (
            "你是 Rule Hypothesizer。你的任务是提出候选规则，只能输出候选，不得把候选描述为最终有效规则。"
            "候选类型只能是 exact_reuse、adapted_rule、novel_rule。"
            "只输出 JSON，字段固定为：candidates。"
            "每个候选只允许包含这些字段：candidate_type, rule_id, rule_title, rule_text, derived_from, adaptation_note, why_applicable。"
            "不要输出 confidence、knowledge_sources、grounding_score、speculation_score、source_provenance。"
            "rule_text 必须精炼，控制在 120 字以内。"
            ),
            task.discovery_mode,
            "candidates",
        )
        compact_rule_lookup = {
            rule.rule_id: {
                "title": rule.title,
                "content": (rule.content or "")[:220],
                "conditions": list(rule.conditions or [])[:4],
            }
            for rule in rule_set.rules[:8]
        }
        user_payload = {
            "problem_frame": problem_frame,
            "analogies": {
                "analogies": analogies.get("analogies", []),
                "gaps": analogies.get("gaps", []),
            },
            "evidence_items": evidence.get("evidence_items", []),
            "rule_lookup": compact_rule_lookup,
        }
        llm_result = self._call_json_with_fallback(
            stage="candidates",
            payload=user_payload,
            system_prompt=system_prompt,
            fallback={"candidates": [item.to_dict() for item in fallback]},
        )
        normalized_candidates = self._normalize_candidates(llm_result.get("candidates", []), fallback)
        return self._backfill_candidate_provenance(normalized_candidates, fallback)

    def _propose_candidates_fallback(
        self,
        task: DiscoveryTask,
        problem_frame: Dict[str, Any],
        analogies: Dict[str, Any],
        evidence: Dict[str, Any],
        rule_set: Any,
    ) -> List[CandidateRule]:
        candidates: List[CandidateRule] = []
        evidence_refs = [item["reference"] for item in evidence.get("evidence_items", [])[:4]]
        rule_by_id = {rule.rule_id: rule for rule in rule_set.rules}
        draft_context = self._build_rule_draft_context(task, problem_frame, evidence)

        if analogies.get("reuse_candidates"):
            rule_id = analogies["reuse_candidates"][0]
            rule = rule_by_id.get(rule_id)
            if rule:
                candidates.append(
                    CandidateRule(
                        candidate_id=f"cand_{len(candidates) + 1:02d}",
                        candidate_type=CandidateType.EXACT_REUSE,
                        rule_id=rule.rule_id,
                        rule_title=rule.title,
                        rule_text=rule.content,
                        derived_from=[rule.rule_id],
                        adaptation_note="无需改造，可直接复用现有规则",
                        why_applicable="现有规则与问题结构高度一致",
                        evidence_refs=evidence_refs,
                        knowledge_sources=["rule_library", "document_evidence"],
                        source_provenance=self._build_source_provenance(
                            task.discovery_mode,
                            evidence_refs,
                            allow_general=False,
                            derived_from=[rule.rule_id],
                        ),
                        confidence=0.88,
                        grounding_score=0.92,
                        speculation_score=0.08,
                        metadata={"draft_context": draft_context},
                    )
                )

        if analogies.get("adaptation_candidates"):
            rule_id = analogies["adaptation_candidates"][0]
            rule = rule_by_id.get(rule_id)
            if rule:
                candidates.append(
                    CandidateRule(
                        candidate_id=f"cand_{len(candidates) + 1:02d}",
                        candidate_type=CandidateType.ADAPTED_RULE,
                        rule_id=rule.rule_id,
                        rule_title=self._resolve_candidate_title(rule.title, draft_context, CandidateType.ADAPTED_RULE),
                        rule_text=self._compose_adapted_rule_text(rule, draft_context),
                        derived_from=[rule.rule_id],
                        adaptation_note="在现有规则结构上增加当前上下文约束，使其覆盖新的问题情境",
                        why_applicable="已有规则结构相似，但需补充上下文条件后才能适用",
                        evidence_refs=evidence_refs,
                        knowledge_sources=["rule_library", "document_evidence"],
                        source_provenance=self._build_source_provenance(
                            task.discovery_mode,
                            evidence_refs,
                            allow_general=False,
                            derived_from=[rule.rule_id],
                        ),
                        confidence=0.72,
                        grounding_score=0.82,
                        speculation_score=0.18,
                        metadata={"draft_context": draft_context},
                    )
                )

        if not candidates:
            rule_text = self._compose_novel_rule_text(draft_context)
            provenance = self._build_source_provenance(
                task.discovery_mode,
                evidence_refs,
                allow_general=task.discovery_mode == DiscoveryMode.EMERGENT,
                derived_from=analogies.get("adaptation_candidates", [])[:1],
            )
            candidates.append(
                CandidateRule(
                    candidate_id="cand_01",
                    candidate_type=CandidateType.NOVEL_RULE,
                    rule_title=self._resolve_candidate_title("候选新规则", draft_context, CandidateType.NOVEL_RULE),
                    rule_text=rule_text,
                    derived_from=analogies.get("adaptation_candidates", [])[:1],
                    adaptation_note="规则库中没有可直接适用规则，需基于上下文和证据形成候选新规则",
                    why_applicable="该规则直接覆盖了当前 Query + Context 的核心约束",
                    evidence_refs=evidence_refs,
                    knowledge_sources=provenance["knowledge_sources"],
                    source_provenance=provenance,
                    confidence=0.62 if evidence_refs else 0.38,
                    grounding_score=provenance["grounding_score"],
                    speculation_score=provenance["speculation_score"],
                    metadata={"draft_context": draft_context},
                )
            )

        return candidates

    def _build_rule_draft_context(
        self,
        task: DiscoveryTask,
        problem_frame: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        scenario_id = str(task.metadata.get("scenario_id") or "")
        subject = self._extract_subject_text(problem_frame)
        action = self._infer_action_label(problem_frame)
        risks = self._extract_risk_clauses(problem_frame, evidence)
        controls, prohibitions = self._infer_control_measures(problem_frame, evidence)
        risk_categories = self._detect_risk_categories(problem_frame, evidence, subject, action, risks)
        template_name = self._select_rule_template(risk_categories, subject, action, scenario_id=scenario_id)
        review_roles = self._infer_review_roles(risk_categories, subject, action)
        confirmation_targets = self._infer_confirmation_targets(risk_categories, risks)
        template_config = self._get_template_config(template_name)
        controls = self._merge_required_items(controls, template_config.get("required_controls", []))
        review_roles = self._merge_required_items(review_roles, template_config.get("required_review_roles", []))
        confirmation_targets = self._merge_required_items(
            confirmation_targets,
            template_config.get("required_confirmation_targets", []),
        )
        return {
            "subject": subject,
            "action": action,
            "scenario_id": scenario_id,
            "risks": risks,
            "controls": controls,
            "prohibitions": prohibitions,
            "risk_categories": risk_categories,
            "template_name": template_name,
            "review_roles": review_roles,
            "confirmation_targets": confirmation_targets,
            "template_config": template_config,
        }

    def _resolve_candidate_title(
        self,
        fallback_title: str,
        draft_context: Dict[str, Any],
        candidate_type: CandidateType,
    ) -> str:
        template_name = draft_context.get("template_name") or "generic_control"
        template = self._get_template_config(template_name)
        if candidate_type == CandidateType.NOVEL_RULE:
            return template.get("title", fallback_title)
        if candidate_type == CandidateType.ADAPTED_RULE:
            return f"{template.get('title', fallback_title)}（改造版）"
        return fallback_title

    def _compose_novel_rule_text(self, draft_context: Dict[str, Any]) -> str:
        template_name = draft_context.get("template_name") or "generic_control"
        if template_name == "financial_analysis_method":
            return self._render_financial_analysis_template(draft_context)
        if template_name == "ai_external_communication":
            return self._render_ai_external_template(draft_context)
        if template_name == "external_commitment_review":
            return self._render_external_commitment_template(draft_context)
        if template_name == "ambiguous_disclosure":
            return self._render_ambiguous_disclosure_template(draft_context)
        if template_name == "data_external_sharing":
            return self._render_data_sharing_template(draft_context)
        if template_name == "human_review_gate":
            return self._render_human_review_gate_template(draft_context)
        trigger = self._render_trigger_clause(draft_context)
        control_text = self._render_control_clause(draft_context.get("controls", []))
        prohibition_text = self._render_prohibition_clause(draft_context.get("prohibitions", []))
        return f"当{trigger}时，发送前应{control_text}；{prohibition_text}。"

    def _compose_adapted_rule_text(self, rule: Any, draft_context: Dict[str, Any]) -> str:
        template_name = draft_context.get("template_name") or "generic_control"
        trigger = self._render_trigger_clause(draft_context)
        control_text = self._render_control_clause(draft_context.get("controls", []))
        prohibition_text = self._render_prohibition_clause(draft_context.get("prohibitions", []))
        base_requirement = (rule.content or "").strip().rstrip("。；;")
        if template_name == "financial_analysis_method":
            return (
                f"对于{draft_context.get('subject') or '相关分析对象'}，除遵守“{base_requirement}”外，"
                f"还应优先提取文档中的关键经营指标、趋势判断、风险来源和原文证据，"
                f"形成结构化分析结论；若关键数据缺失，应明确说明缺口，不得用治理性兜底表述替代分析结论。"
            )
        if template_name == "ai_external_communication":
            return (
                f"对于{draft_context.get('subject') or '相关内容'}，除遵守“{base_requirement}”外，"
                f"在对外发送前还必须{control_text}；{prohibition_text}。"
            )
        if template_name == "external_commitment_review":
            return (
                f"对于{draft_context.get('subject') or '相关事项'}，除遵守“{base_requirement}”外，"
                f"在形成或发送涉及对外承诺的内容前还应{control_text}；{prohibition_text}。"
            )
        return (
            f"当{trigger}时，除遵守“{base_requirement}”外，"
            f"还应{control_text}；{prohibition_text}。"
        )

    def _extract_subject_text(self, problem_frame: Dict[str, Any]) -> str:
        action_text = problem_frame.get("action", "") or ""
        patterns = [
            r"对于(.+?)(?:，|,|在|发送前|应|需要)",
            r"针对(.+?)(?:，|,|在|发送前|应|需要)",
            r"对(.+?)(?:，|,|在|发送前|应|需要)",
        ]
        for pattern in patterns:
            match = re.search(pattern, action_text)
            if match:
                candidate = match.group(1).strip("，,。；; ")
                if candidate:
                    return candidate

        entities = [item for item in problem_frame.get("entities", []) if len(item) >= 2]
        if entities:
            entities = sorted(entities, key=len, reverse=True)
            return entities[0]
        return "相关主体"

    def _infer_action_label(self, problem_frame: Dict[str, Any]) -> str:
        combined = " ".join(
            [problem_frame.get("action", "")] + problem_frame.get("constraints", [])
        )
        if "发送" in combined:
            return "对外发送相关内容"
        if "披露" in combined:
            return "披露相关信息"
        if "回复" in combined or "答复" in combined:
            return "对外答复"
        return self._normalize_action_text(problem_frame.get("action") or "相关行为")

    def _extract_risk_clauses(
        self,
        problem_frame: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> List[str]:
        risk_markers = ["误导", "夸大", "未确认", "不确定", "承诺", "模糊", "失实", "默认"]
        candidates: List[str] = []
        sources = list(problem_frame.get("constraints", []))
        sources.extend(item.get("excerpt", "") for item in evidence.get("evidence_items", []))
        for source in sources:
            for part in re.split(r"[。；;，,\n]+", source or ""):
                clause = part.strip()
                if len(clause) < 6:
                    continue
                if any(marker in clause for marker in risk_markers):
                    candidates.append(clause)
        if not candidates:
            return ["存在需要额外核实的事实、表述或承诺风险"]
        return list(dict.fromkeys(candidates))[:3]

    def _infer_control_measures(
        self,
        problem_frame: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> tuple[List[str], List[str]]:
        combined = " ".join(
            [problem_frame.get("action", "")]
            + problem_frame.get("constraints", [])
            + [item.get("excerpt", "") for item in evidence.get("evidence_items", [])]
        )
        controls: List[str] = []
        prohibitions: List[str] = []

        if any(marker in combined.lower() for marker in ["ai", "自动生成", "自动"]):
            controls.append("完成人工复核")
        if any(marker in combined for marker in ["未确认", "不确定", "交付时间", "合作确定性", "夸大", "失实"]):
            controls.append("核实涉及事实、时间、范围和承诺的内容")
        if any(marker in combined for marker in ["误导", "模糊", "歧义"]):
            controls.append("修正可能造成误解的表述")
        if not controls:
            controls.append("完成业务负责人复核")

        if any(marker in combined for marker in ["承诺", "未确认", "合作确定性", "交付时间"]):
            prohibitions.append("不得将未确认事项表述为既定事实或对外承诺")
        if any(marker in combined for marker in ["发送", "对外", "邮件", "公告", "答复"]):
            prohibitions.append("未经复核不得直接对外发送")
        if not prohibitions:
            prohibitions.append("不得在未完成复核前直接执行")

        return list(dict.fromkeys(controls)), list(dict.fromkeys(prohibitions))

    def _detect_risk_categories(
        self,
        problem_frame: Dict[str, Any],
        evidence: Dict[str, Any],
        subject: str,
        action: str,
        risks: List[str],
    ) -> List[str]:
        combined = " ".join(
            [subject, action, problem_frame.get("action", "")]
            + problem_frame.get("constraints", [])
            + risks
            + [item.get("excerpt", "") for item in evidence.get("evidence_items", [])]
        ).lower()
        categories: List[str] = []
        communication_markers = ["对外", "邮件", "公告", "披露", "答复", "发送", "口播", "外发", "公开表述"]
        has_external_communication = any(marker in combined for marker in communication_markers)

        if any(marker in combined for marker in ["ai", "自动生成", "模型生成"]):
            categories.append("ai_generated")
        if has_external_communication:
            categories.append("external_communication")
        if has_external_communication and any(marker in combined for marker in ["模糊", "歧义", "误导", "夸大", "失实"]):
            categories.append("misleading_expression")
        if any(marker in combined for marker in ["未确认", "交付时间", "合作确定性"]) or (
            has_external_communication and any(marker in combined for marker in ["承诺", "承诺措辞"])
        ):
            categories.append("unverified_commitment")
        if any(marker in combined for marker in ["数据", "隐私", "客户信息", "敏感信息"]):
            categories.append("sensitive_data")

        return categories or ["general_risk"]

    def _select_rule_template(
        self,
        risk_categories: List[str],
        subject: str,
        action: str,
        *,
        scenario_id: str = "",
    ) -> str:
        category_set = set(risk_categories)
        templates = RULE_TEMPLATE_LIBRARY.get("templates", {})
        default_template = RULE_TEMPLATE_LIBRARY.get("default_template", "generic_control")
        analysis_markers = ["业绩", "评级", "目标价", "估值", "风险", "研报", "利润", "收入", "净息差", "资产质量", "表现如何", "怎么看"]
        action_text = f"{subject} {action}".lower()

        if scenario_id == "equity_research" or any(marker in action_text for marker in analysis_markers):
            if "external_communication" not in category_set and "sensitive_data" not in category_set:
                return "financial_analysis_method"

        best_name = default_template
        best_score = -1
        for name, template in templates.items():
            if name == default_template:
                continue
            match_all = set(template.get("match_all", []) or [])
            match_any = set(template.get("match_any", []) or [])
            if match_all and not match_all.issubset(category_set):
                continue
            if match_any and not (match_any & category_set):
                continue
            score = len(match_all) * 2 + len(match_any & category_set)
            if score > best_score:
                best_name = name
                best_score = score

        return best_name

    def _get_template_config(self, template_name: str) -> Dict[str, Any]:
        templates = RULE_TEMPLATE_LIBRARY.get("templates", {})
        default_template = RULE_TEMPLATE_LIBRARY.get("default_template", "generic_control")
        return templates.get(template_name, templates.get(default_template, {}))

    def _merge_required_items(self, base_items: List[str], required_items: List[str]) -> List[str]:
        items = list(base_items or [])
        for item in required_items or []:
            if item not in items:
                items.append(item)
        return items

    def _render_ai_external_template(self, draft_context: Dict[str, Any]) -> str:
        subject = draft_context.get("subject") or "相关内容"
        controls = draft_context.get("controls", [])
        prohibitions = draft_context.get("prohibitions", [])
        review_roles = draft_context.get("review_roles", [])
        confirmation_targets = draft_context.get("confirmation_targets", [])
        control_text = self._render_control_clause(controls)
        prohibition_text = self._render_prohibition_clause(prohibitions)
        risks = draft_context.get("risks", [])
        risk_text = f"存在{'、'.join(risks[:2])}等风险" if risks else "存在误导或失实风险"
        review_text = self._render_review_roles(review_roles)
        target_text = self._render_confirmation_targets(confirmation_targets)
        return (
            f"对于{subject}，如拟对外发送且{risk_text}，"
            f"发送前必须由{review_text}{control_text}"
            f"{target_text}；{prohibition_text}。"
        )

    def _render_ambiguous_disclosure_template(self, draft_context: Dict[str, Any]) -> str:
        subject = draft_context.get("subject") or "相关信息"
        controls = draft_context.get("controls", [])
        prohibitions = draft_context.get("prohibitions", [])
        control_text = self._render_control_clause(controls)
        prohibition_text = self._render_prohibition_clause(prohibitions)
        return (
            f"当{subject}拟对外披露且表述可能引发误解时，"
            f"披露前应{control_text}；{prohibition_text}。"
        )

    def _render_data_sharing_template(self, draft_context: Dict[str, Any]) -> str:
        subject = draft_context.get("subject") or "相关数据或信息"
        controls = draft_context.get("controls", [])
        prohibitions = draft_context.get("prohibitions", [])
        control_text = self._render_control_clause(controls)
        prohibition_text = self._render_prohibition_clause(prohibitions)
        return (
            f"当{subject}涉及对外共享或传输时，"
            f"执行前应{control_text}；{prohibition_text}。"
        )

    def _render_external_commitment_template(self, draft_context: Dict[str, Any]) -> str:
        subject = draft_context.get("subject") or "相关事项"
        review_text = self._render_review_roles(draft_context.get("review_roles", []))
        target_text = self._render_confirmation_targets(draft_context.get("confirmation_targets", []))
        control_text = self._render_control_clause(draft_context.get("controls", []))
        prohibition_text = self._render_prohibition_clause(draft_context.get("prohibitions", []))
        return (
            f"对于{subject}中涉及合作结论、交付时间或其他对外承诺的内容，"
            f"对外发送前应由{review_text}{control_text}{target_text}；{prohibition_text}。"
        )

    def _render_human_review_gate_template(self, draft_context: Dict[str, Any]) -> str:
        trigger = self._render_trigger_clause(draft_context)
        review_text = self._render_review_roles(draft_context.get("review_roles", []))
        control_text = self._render_control_clause(draft_context.get("controls", []))
        prohibition_text = self._render_prohibition_clause(draft_context.get("prohibitions", []))
        return (
            f"当{trigger}时，执行前必须由{review_text}{control_text}；{prohibition_text}。"
        )

    def _render_financial_analysis_template(self, draft_context: Dict[str, Any]) -> str:
        subject = draft_context.get("subject") or "相关金融分析对象"
        action = draft_context.get("action") or "形成分析结论"
        risk_text = "；".join(draft_context.get("risks", [])[:2]) or "如关键信息缺失，应明确说明缺口"
        return (
            f"当问题聚焦于{subject}{action}时，系统应优先从文档中提取关键经营指标、趋势变化、风险来源与原文证据，"
            f"再组织成结构化分析结论；{risk_text}，不得用泛化治理条款替代业务分析答案。"
        )

    def _infer_review_roles(self, risk_categories: List[str], subject: str, action: str) -> List[str]:
        category_set = set(risk_categories)
        roles: List[str] = []
        if "ai_generated" in category_set:
            roles.append("发送责任人")
        if "external_communication" in category_set:
            roles.append("业务负责人")
        if "sensitive_data" in category_set:
            roles.append("数据或合规责任人")
        return list(dict.fromkeys(roles)) or ["业务负责人"]

    def _infer_confirmation_targets(self, risk_categories: List[str], risks: List[str]) -> List[str]:
        category_set = set(risk_categories)
        targets: List[str] = []
        if "unverified_commitment" in category_set:
            targets.extend(["合作范围", "交付时间", "承诺措辞"])
        if "misleading_expression" in category_set:
            targets.append("表述准确性")
        if "sensitive_data" in category_set:
            targets.append("数据授权范围")

        risk_text = " ".join(risks)
        if "事实" in risk_text:
            targets.append("事实依据")
        return list(dict.fromkeys(targets))

    def _render_review_roles(self, roles: List[str]) -> str:
        cleaned = [item.strip("。；;，, ") for item in roles if item]
        if not cleaned:
            return "业务负责人"
        if len(cleaned) == 1:
            return cleaned[0]
        return "、".join(cleaned[:3])

    def _render_confirmation_targets(self, targets: List[str]) -> str:
        cleaned = [item.strip("。；;，, ") for item in targets if item]
        if not cleaned:
            return ""
        return f"，并重点核实{'、'.join(cleaned[:4])}"

    def _render_trigger_clause(self, draft_context: Dict[str, Any]) -> str:
        subject = draft_context.get("subject") or "相关主体"
        action = draft_context.get("action") or "实施相关行为"
        risks = draft_context.get("risks", [])
        if risks:
            return f"{subject}{action}，且存在{ '、'.join(risks[:2]) }等风险"
        return f"{subject}{action}"

    def _render_control_clause(self, controls: List[str]) -> str:
        cleaned = [item.strip("。；;，, ") for item in controls if item]
        if not cleaned:
            return "完成必要复核"
        if len(cleaned) == 1:
            return cleaned[0]
        return "，并".join(cleaned[:3])

    def _render_prohibition_clause(self, prohibitions: List[str]) -> str:
        cleaned = [item.strip("。；;，, ") for item in prohibitions if item]
        if not cleaned:
            return "不得在风险未排除前继续处理"
        if len(cleaned) == 1:
            return cleaned[0]
        return "；".join(cleaned[:3])

    def _validate_candidates(
        self,
        task: DiscoveryTask,
        retriever: RuleDiscoveryRetriever,
        problem_frame: Dict[str, Any],
        analogies: Dict[str, Any],
        evidence: Dict[str, Any],
        candidates: List[CandidateRule],
    ) -> Dict[str, Any]:
        fallback = self._validate_candidates_fallback(retriever, problem_frame, analogies, evidence, candidates)
        if not self.llm_client:
            return fallback

        system_prompt = self._stage_system_prompt(
            (
            "你是 Rule Critic。你的任务是反驳和验证候选规则。你必须主动找出证据不足、遗漏前置条件、"
            "与旧规则冲突或只是描述性总结的问题。"
            "只输出 JSON，字段固定为：candidates, rejected_candidates, open_questions。"
            "其中 candidates 只允许包含 candidate_id, validation_status, validation_reason, confidence。"
            ),
            task.discovery_mode,
            "validation",
        )
        user_payload = {
            "problem_frame": problem_frame,
            "evidence_items": evidence.get("evidence_items", []),
            "candidates": [item.to_dict() for item in candidates],
            "analogies": analogies,
            "fallback_critic_report": fallback,
        }
        llm_result = self._call_json_with_fallback(
            stage="validation",
            payload=user_payload,
            system_prompt=system_prompt,
            fallback=fallback,
        )
        normalized_validation = self._normalize_validation_result(llm_result, fallback)
        validation_map = {
            item["candidate_id"]: item
            for item in normalized_validation.get("candidates", [])
            if isinstance(item, dict) and item.get("candidate_id")
        }
        for candidate in candidates:
            data = validation_map.get(candidate.candidate_id)
            if not data:
                continue
            candidate.validation_status = self._normalize_validation_status(
                data.get("validation_status", candidate.validation_status.value),
                candidate.validation_status,
            )
            candidate.validation_reason = data.get("validation_reason", candidate.validation_reason)
            candidate.confidence = float(data.get("confidence", candidate.confidence) or candidate.confidence)

        return {
            "candidates": [item.to_dict() for item in candidates],
            "rejected_candidates": normalized_validation.get("rejected_candidates", fallback.get("rejected_candidates", [])),
            "open_questions": normalized_validation.get("open_questions", fallback.get("open_questions", [])),
        }

    def _validate_candidates_fallback(
        self,
        retriever: RuleDiscoveryRetriever,
        problem_frame: Dict[str, Any],
        analogies: Dict[str, Any],
        evidence: Dict[str, Any],
        candidates: List[CandidateRule],
    ) -> Dict[str, Any]:
        reviewed: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        open_questions = list(evidence.get("open_questions", []))
        evidence_count = len(evidence.get("evidence_items", []))

        for candidate in candidates:
            critic_report = self._build_candidate_critic_report(
                retriever=retriever,
                candidate=candidate,
                problem_frame=problem_frame,
                analogies=analogies,
                evidence=evidence,
            )
            status = ValidationStatus.PROVISIONALLY_SUPPORTED
            confidence = candidate.confidence
            reason = "候选规则具备初步证据支持。"

            if candidate.candidate_type == CandidateType.EXACT_REUSE and candidate.rule_id:
                status = ValidationStatus.SUPPORTED
                confidence = max(confidence, 0.86)
                reason = "已有规则可直接复用，且当前问题未发现明显冲突。"
            elif candidate.candidate_type == CandidateType.ADAPTED_RULE:
                if evidence_count == 0:
                    status = ValidationStatus.WEAKLY_SUPPORTED
                    confidence = min(confidence, 0.48)
                    reason = "改造规则缺少文档证据支撑，目前仅具备弱支持。"
                else:
                    status = ValidationStatus.PROVISIONALLY_SUPPORTED
                    confidence = max(confidence, 0.68)
                    reason = "改造规则有证据支撑，但仍需关注新增条件是否完备。"
            elif candidate.candidate_type == CandidateType.NOVEL_RULE:
                if evidence_count == 0:
                    status = ValidationStatus.REJECTED
                    confidence = min(confidence, 0.25)
                    reason = "新规则缺少证据支撑，暂不能成立。"
                    rejected.append({
                        "candidate_id": candidate.candidate_id,
                        "reason": reason,
                    })
                elif evidence_count < 2:
                    status = ValidationStatus.WEAKLY_SUPPORTED
                    confidence = min(max(confidence, 0.45), 0.58)
                    reason = "新规则有少量证据支撑，但证据仍偏薄弱。"
                    open_questions.append("新规则的适用边界仍需更多证据确认")
                else:
                    status = ValidationStatus.PROVISIONALLY_SUPPORTED
                    confidence = max(confidence, 0.66)
                    reason = "新规则有初步证据支撑，但仍应视为候选规则而非正式规则。"

            if critic_report["conflict_alerts"]:
                status = ValidationStatus.NEED_HUMAN_REVIEW
                confidence = min(confidence, 0.55)
                reason = "候选规则与现有规则存在潜在冲突，需人工复核。"
                open_questions.append("需确认候选规则与现有规则体系是否冲突")

            adjudication = critic_report.get("adjudication", {})
            if adjudication.get("has_conflict") and adjudication.get("preferred_side") == "existing_rule":
                status = ValidationStatus.NEED_HUMAN_REVIEW
                confidence = min(confidence, 0.52)
                reason = adjudication.get("reason", reason)
                open_questions.append("需根据既有规则优先原则决定候选规则是否成立")

            if critic_report["counterexamples"]:
                confidence = min(confidence, 0.58)
                if status == ValidationStatus.SUPPORTED:
                    status = ValidationStatus.PROVISIONALLY_SUPPORTED
                if status == ValidationStatus.PROVISIONALLY_SUPPORTED:
                    reason = "候选规则具备初步支持，但存在需要进一步验证的反例或边界条件。"

            if critic_report["missing_elements"]:
                if status == ValidationStatus.SUPPORTED:
                    status = ValidationStatus.PROVISIONALLY_SUPPORTED
                confidence = min(confidence, 0.62)
                open_questions.extend(critic_report["missing_elements"])

            relation_impact = self._apply_relation_impact(candidate, critic_report, status, confidence, reason)
            status = relation_impact["status"]
            confidence = relation_impact["confidence"]
            reason = relation_impact["reason"]
            open_questions.extend(relation_impact["open_questions"])

            candidate.validation_status = status
            candidate.validation_reason = reason
            candidate.confidence = round(confidence, 3)
            candidate.metadata["critic_report"] = critic_report
            reviewed.append({
                "candidate_id": candidate.candidate_id,
                "validation_status": status.value,
                "validation_reason": reason,
                "confidence": candidate.confidence,
                "critic_report": critic_report,
            })

        return {
            "candidates": reviewed,
            "rejected_candidates": rejected,
            "open_questions": list(dict.fromkeys(open_questions)),
        }

    def _apply_relation_impact(
        self,
        candidate: CandidateRule,
        critic_report: Dict[str, Any],
        status: ValidationStatus,
        confidence: float,
        reason: str,
    ) -> Dict[str, Any]:
        relation_types = [item.get("relation_type") for item in critic_report.get("related_rules", [])]
        open_questions: List[str] = []

        if "conflict" in relation_types:
            status = ValidationStatus.NEED_HUMAN_REVIEW
            confidence = min(confidence, 0.55)
            reason = "候选规则与现有规则存在冲突关系，必须人工裁决。"
            open_questions.append("需确认候选规则与现有规则冲突后的优先适用关系")

        if "duplicate" in relation_types and candidate.candidate_type == CandidateType.NOVEL_RULE:
            status = ValidationStatus.NEED_HUMAN_REVIEW
            confidence = min(confidence, 0.5)
            reason = "候选新规则与既有规则可能重复，需确认是否应降级为复用或改造规则。"
            open_questions.append("需确认该候选规则是否实质重复于既有规则")

        if "tighten" in relation_types:
            confidence = min(max(confidence, 0.68), 0.82)
            if status == ValidationStatus.PROVISIONALLY_SUPPORTED:
                reason = "候选规则在现有规则基础上形成更严格控制，具备较强合理性。"

        if "supplement" in relation_types:
            confidence = min(max(confidence, 0.64), 0.78)
            if status == ValidationStatus.PROVISIONALLY_SUPPORTED:
                reason = "候选规则作为现有规则的补充条款，具备一定合理性。"

        return {
            "status": status,
            "confidence": confidence,
            "reason": reason,
            "open_questions": open_questions,
        }

    def _build_candidate_critic_report(
        self,
        *,
        retriever: RuleDiscoveryRetriever,
        candidate: CandidateRule,
        problem_frame: Dict[str, Any],
        analogies: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        draft_context = candidate.metadata.get("draft_context", {}) if isinstance(candidate.metadata, dict) else {}
        derived_from = candidate.derived_from if isinstance(candidate.derived_from, list) else [candidate.derived_from] if candidate.derived_from else []
        related_rules = retriever.scan_related_rules(
            query="\n".join([
                candidate.rule_title or "",
                candidate.rule_text or "",
                problem_frame.get("action", "") or "",
            ]),
            exclude_rule_ids=[rid for rid in [candidate.rule_id] + derived_from if rid],
            min_score=0.12,
            top_k=4,
        )
        related_rule_reports = self._build_base_relation_reports(candidate, analogies, draft_context)
        related_rule_reports.extend(
            self._build_rule_relation_reports(candidate, related_rules, draft_context)
        )
        adjudication = self._build_conflict_adjudication(candidate, related_rule_reports)
        conflict_alerts = [
            item["relation_reason"]
            for item in related_rule_reports
            if item["relation_type"] == "conflict"
        ]
        counterexamples = self._build_counterexamples(candidate, problem_frame, evidence, draft_context)
        missing_elements = self._detect_missing_elements(candidate, draft_context, evidence)

        return {
            "related_rules": related_rule_reports,
            "conflict_alerts": conflict_alerts,
            "adjudication": adjudication,
            "counterexamples": counterexamples,
            "missing_elements": missing_elements,
            "analogy_gaps": analogies.get("gaps", []),
        }

    def _build_base_relation_reports(
        self,
        candidate: CandidateRule,
        analogies: Dict[str, Any],
        draft_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        reports: List[Dict[str, Any]] = []
        seen_rule_ids = set()
        rule_hits = {
            item["rule_id"]: item
            for item in analogies.get("rule_hits", [])
            if item.get("rule_id")
        }

        for rule_id in [candidate.rule_id] + candidate.derived_from:
            if not rule_id or rule_id in seen_rule_ids:
                continue
            seen_rule_ids.add(rule_id)
            hit = rule_hits.get(rule_id, {"rule_id": rule_id, "title": rule_id, "score": 0.0, "matched_terms": []})

            if candidate.candidate_type == CandidateType.EXACT_REUSE and candidate.rule_id == rule_id:
                relation_type = "duplicate"
                relation_reason = f"候选规则与既有规则 {rule_id} 直接复用同一要求。"
            elif candidate.candidate_type == CandidateType.ADAPTED_RULE and candidate.rule_id == rule_id:
                if any("人工复核" in item for item in draft_context.get("controls", [])):
                    relation_type = "tighten"
                    relation_reason = f"候选规则在既有规则 {rule_id} 基础上增加了更严格的复核要求。"
                else:
                    relation_type = "supplement"
                    relation_reason = f"候选规则在既有规则 {rule_id} 基础上补充了新的适用条件。"
            else:
                relation_type = "analogous"
                relation_reason = f"候选规则参考了既有规则 {rule_id} 的结构，但并未直接复用。"

            reports.append({
                "rule_id": hit["rule_id"],
                "title": hit.get("title", rule_id),
                "score": hit.get("score", 0.0),
                "priority": hit.get("priority", 0),
                "matched_terms": hit.get("matched_terms", []),
                "relation_type": relation_type,
                "relation_reason": relation_reason,
            })

        return reports

    def _build_rule_relation_reports(
        self,
        candidate: CandidateRule,
        related_rules: List[Dict[str, Any]],
        draft_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        reports: List[Dict[str, Any]] = []
        candidate_text = candidate.rule_text or ""
        prohibitions = " ".join(draft_context.get("prohibitions", []))
        controls = " ".join(draft_context.get("controls", []))

        for rule in related_rules:
            content = rule.get("content", "")
            matched_terms = rule.get("matched_terms", [])
            if not matched_terms:
                continue
            relation_type = "analogous"
            relation_reason = f"候选规则与既有规则 {rule['rule_id']} 存在主题相关性。"

            if any(term in content for term in ["允许", "可以直接", "无需审批"]) and "不得" in candidate_text:
                relation_type = "conflict"
                relation_reason = f"候选规则可能与既有规则 {rule['rule_id']} 的允许性表述冲突。"
            elif any(term in content for term in ["不得", "禁止"]) and any(term in candidate_text for term in ["应", "可以"]):
                relation_type = "conflict"
                relation_reason = f"候选规则可能弱化既有规则 {rule['rule_id']} 的禁止性要求。"
            elif "例外" in content or "除外" in content or "except" in content.lower():
                relation_type = "supplement"
                relation_reason = f"既有规则 {rule['rule_id']} 含例外条件，候选规则可能需要补充边界。"
            elif any(term in prohibitions for term in ["未经复核不得", "不得将未确认事项"]) and "允许" in content:
                relation_type = "conflict"
                relation_reason = f"候选规则与既有规则 {rule['rule_id']} 在执行边界上可能冲突。"
            elif any(term in controls for term in ["核实", "复核"]) and "自动" in content and "人工" not in content:
                relation_type = "tighten"
                relation_reason = f"候选规则相较既有规则 {rule['rule_id']} 增加了更严格的人工复核要求。"
            elif any(term in candidate_text for term in ["还应", "还必须", "并重点核实"]):
                relation_type = "supplement"
                relation_reason = f"候选规则在既有规则 {rule['rule_id']} 基础上补充了新的控制要求。"
            elif candidate.rule_id == rule.get("rule_id"):
                relation_type = "duplicate"
                relation_reason = f"候选规则与既有规则 {rule['rule_id']} 可能存在重复。"

            reports.append({
                "rule_id": rule["rule_id"],
                "title": rule["title"],
                "score": rule["score"],
                "priority": rule.get("priority", 0),
                "matched_terms": matched_terms,
                "relation_type": relation_type,
                "relation_reason": relation_reason,
            })

        return reports

    def _build_conflict_adjudication(
        self,
        candidate: CandidateRule,
        related_rule_reports: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        conflict_reports = [
            item for item in related_rule_reports
            if item.get("relation_type") == "conflict"
        ]
        if not conflict_reports:
            return {
                "has_conflict": False,
                "preferred_side": "candidate",
                "preferred_rule_id": candidate.rule_id,
                "reason": "未检测到需要裁决的冲突关系。",
            }

        strongest = max(
            conflict_reports,
            key=lambda item: (item.get("score", 0.0), item.get("priority", 0)),
        )
        preferred_side = "existing_rule"
        preferred_rule_id = strongest.get("rule_id")
        reason = (
            f"检测到与既有规则 {preferred_rule_id} 的冲突；在未明确更高优先级依据前，"
            "默认既有规则优先，候选规则需人工裁决。"
        )

        if candidate.candidate_type == CandidateType.EXACT_REUSE:
            preferred_side = "candidate"
            preferred_rule_id = candidate.rule_id
            reason = "候选规则为直接复用规则，不应再与自身构成冲突。"

        return {
            "has_conflict": True,
            "preferred_side": preferred_side,
            "preferred_rule_id": preferred_rule_id,
            "reason": reason,
        }

    def _build_counterexamples(
        self,
        candidate: CandidateRule,
        problem_frame: Dict[str, Any],
        evidence: Dict[str, Any],
        draft_context: Dict[str, Any],
    ) -> List[str]:
        counterexamples: List[str] = []
        risk_categories = set(draft_context.get("risk_categories", []))
        evidence_count = len(evidence.get("evidence_items", []))
        subject = draft_context.get("subject", "")

        if candidate.candidate_type == CandidateType.NOVEL_RULE and evidence_count < 2:
            counterexamples.append("若该场景只在个别样本中出现，当前新规则可能过宽")
        if "external_communication" in risk_categories and "内部" in subject:
            counterexamples.append("若内容仅用于内部流转，则对外发送类约束可能不适用")
        if "unverified_commitment" in risk_categories and "默认写入未确认的交付时间" not in " ".join(draft_context.get("risks", [])):
            counterexamples.append("若不存在未确认承诺或时间信息，候选规则的禁止条款可能过重")
        if "ai_generated" in risk_categories and "人工复核" not in " ".join(draft_context.get("controls", [])):
            counterexamples.append("若 AI 生成内容已被结构化校验，人工复核要求可能需要区分等级")

        return list(dict.fromkeys(counterexamples))

    def _detect_missing_elements(
        self,
        candidate: CandidateRule,
        draft_context: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> List[str]:
        missing: List[str] = []
        risk_categories = set(draft_context.get("risk_categories", []))

        if "external_communication" in risk_categories and not draft_context.get("review_roles"):
            missing.append("尚未明确由谁承担发送前复核责任")
        if "unverified_commitment" in risk_categories and not draft_context.get("confirmation_targets"):
            missing.append("尚未明确需要核实的事实或承诺对象")
        if candidate.candidate_type == CandidateType.ADAPTED_RULE and not candidate.derived_from:
            missing.append("改造规则缺少明确的来源规则")
        if len(evidence.get("evidence_items", [])) == 0:
            missing.append("尚未取得可支持候选规则的文档证据")

        return list(dict.fromkeys(missing))

    def _finalize_decision(
        self,
        task: DiscoveryTask,
        candidates: List[CandidateRule],
        validated: Dict[str, Any],
    ) -> DiscoveryDecision:
        fallback = self._finalize_decision_fallback(task.discovery_mode, candidates, validated)
        if not self.llm_client:
            return fallback

        system_prompt = self._stage_system_prompt(
            (
            "你是 Decision Synthesizer。你需要根据候选规则及其验证结果，决定最终输出类型。"
            "只输出 JSON，字段固定为：resolution_type, selected_candidate_ids, rejected_candidate_ids, open_questions, summary, need_human_review。"
            ),
            task.discovery_mode,
            "decision",
        )
        user_payload = {
            "candidates": [item.to_dict() for item in candidates],
            "validation": validated,
        }
        llm_result = self._call_json_with_fallback(
            stage="decision",
            payload=user_payload,
            system_prompt=system_prompt,
            fallback={
                "resolution_type": fallback.resolution_type.value,
                "selected_candidate_ids": [item.candidate_id for item in fallback.candidate_rules],
                "rejected_candidate_ids": self._extract_candidate_ids(fallback.rejected_candidates),
                "open_questions": fallback.open_questions,
                "summary": fallback.summary,
                "need_human_review": fallback.need_human_review,
            },
        )
        normalized_decision = self._normalize_decision_result(llm_result, fallback)

        selected_ids = set(self._extract_candidate_ids(normalized_decision.get("selected_candidate_ids", [])))
        selected = [item for item in candidates if item.candidate_id in selected_ids]
        if not selected and fallback.candidate_rules:
            selected = fallback.candidate_rules

        resolution_type = self._normalize_resolution_type(
            normalized_decision.get("resolution_type", fallback.resolution_type.value),
            fallback.resolution_type,
        )
        rejected_ids = set(self._extract_candidate_ids(normalized_decision.get("rejected_candidate_ids", [])))
        rejected_candidates = [
            item for item in validated.get("rejected_candidates", [])
            if isinstance(item, dict) and (item.get("candidate_id") in rejected_ids or not rejected_ids)
        ]

        return DiscoveryDecision(
            resolution_type=resolution_type,
            discovery_mode=task.discovery_mode,
            candidate_rules=selected,
            rejected_candidates=rejected_candidates,
            open_questions=normalized_decision.get("open_questions", fallback.open_questions),
            summary=normalized_decision.get("summary", fallback.summary),
            need_human_review=bool(normalized_decision.get("need_human_review", fallback.need_human_review)),
        )

    def _extract_candidate_ids(self, value: Any) -> List[str]:
        items = value if isinstance(value, list) else [value] if value else []
        ids: List[str] = []
        for item in items:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict):
                candidate_id = item.get("candidate_id") or item.get("id")
                if isinstance(candidate_id, str):
                    ids.append(candidate_id)
        return list(dict.fromkeys(ids))

    def _normalize_problem_frame_result(
        self,
        llm_result: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = llm_result if isinstance(llm_result, dict) else {}
        return {
            "intent": self._coerce_text(result.get("intent"), fallback.get("intent", "discover_rule")),
            "entities": self._coerce_string_list(result.get("entities"), fallback.get("entities", []), limit=8),
            "action": self._coerce_text(result.get("action"), fallback.get("action", "")),
            "constraints": self._coerce_string_list(result.get("constraints"), fallback.get("constraints", []), limit=6),
            "exceptions": self._coerce_string_list(result.get("exceptions"), fallback.get("exceptions", []), limit=6),
            "ambiguities": self._coerce_string_list(result.get("ambiguities"), fallback.get("ambiguities", []), limit=6),
            "search_queries": self._coerce_string_list(result.get("search_queries"), fallback.get("search_queries", []), limit=6),
        }

    def _normalize_evidence_result(
        self,
        llm_result: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = llm_result if isinstance(llm_result, dict) else {}
        raw_items = result.get("evidence_items", fallback.get("evidence_items", []))
        evidence_items: List[Dict[str, Any]] = []
        for item in self._coerce_list(raw_items):
            if isinstance(item, dict):
                evidence_items.append({
                    "reference": self._coerce_text(item.get("reference"), ""),
                    "source_name": self._coerce_text(item.get("source_name"), ""),
                    "excerpt": self._coerce_text(item.get("excerpt"), ""),
                    "why_relevant": self._coerce_text(item.get("why_relevant"), ""),
                })
            elif isinstance(item, str):
                evidence_items.append({
                    "reference": "",
                    "source_name": "",
                    "excerpt": item,
                    "why_relevant": "",
                })
        if not evidence_items:
            evidence_items = fallback.get("evidence_items", [])
        return {
            "evidence_items": evidence_items,
            "open_questions": self._coerce_string_list(result.get("open_questions"), fallback.get("open_questions", []), limit=10),
            "document_hits": fallback.get("document_hits", []),
        }

    def _normalize_validation_result(
        self,
        llm_result: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = llm_result if isinstance(llm_result, dict) else {}
        normalized_candidates: List[Dict[str, Any]] = []
        for item in self._coerce_list(result.get("candidates", [])):
            if not isinstance(item, dict):
                continue
            candidate_id = self._coerce_text(item.get("candidate_id"), "")
            if not candidate_id:
                continue
            normalized_candidates.append({
                "candidate_id": candidate_id,
                "validation_status": self._normalize_validation_status(
                    item.get("validation_status"),
                    ValidationStatus.PROVISIONALLY_SUPPORTED,
                ).value,
                "validation_reason": self._coerce_text(item.get("validation_reason"), ""),
                "confidence": self._coerce_float(item.get("confidence"), 0.0),
                "critic_report": item.get("critic_report", {}),
            })
        if not normalized_candidates:
            normalized_candidates = fallback.get("candidates", [])

        rejected_candidates = self._normalize_rejected_candidates(
            result.get("rejected_candidates"),
            fallback.get("rejected_candidates", []),
        )

        return {
            "candidates": normalized_candidates,
            "rejected_candidates": rejected_candidates,
            "open_questions": self._coerce_string_list(result.get("open_questions"), fallback.get("open_questions", []), limit=12),
        }

    def _normalize_decision_result(
        self,
        llm_result: Dict[str, Any],
        fallback: DiscoveryDecision,
    ) -> Dict[str, Any]:
        result = llm_result if isinstance(llm_result, dict) else {}
        return {
            "resolution_type": self._coerce_text(result.get("resolution_type"), fallback.resolution_type.value),
            "selected_candidate_ids": self._extract_candidate_ids(result.get("selected_candidate_ids", [])),
            "rejected_candidate_ids": self._extract_candidate_ids(result.get("rejected_candidate_ids", [])),
            "open_questions": self._coerce_string_list(result.get("open_questions"), fallback.open_questions, limit=12),
            "summary": self._coerce_text(result.get("summary"), fallback.summary),
            "need_human_review": self._coerce_bool(result.get("need_human_review"), fallback.need_human_review),
        }

    def _normalize_validation_status(
        self,
        value: Any,
        fallback: ValidationStatus,
    ) -> ValidationStatus:
        if isinstance(value, ValidationStatus):
            return value
        if isinstance(value, str):
            aliases = {
                "provisional": ValidationStatus.PROVISIONALLY_SUPPORTED,
                "provisionally_supported": ValidationStatus.PROVISIONALLY_SUPPORTED,
                "weak": ValidationStatus.WEAKLY_SUPPORTED,
                "weakly_supported": ValidationStatus.WEAKLY_SUPPORTED,
                "supported": ValidationStatus.SUPPORTED,
                "rejected": ValidationStatus.REJECTED,
                "need_human_review": ValidationStatus.NEED_HUMAN_REVIEW,
                "human_review": ValidationStatus.NEED_HUMAN_REVIEW,
                "pending": ValidationStatus.PENDING,
            }
            if value in aliases:
                return aliases[value]
            try:
                return ValidationStatus(value)
            except ValueError:
                pass
        return fallback

    def _normalize_rejected_candidates(
        self,
        value: Any,
        fallback: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        items = self._coerce_list(value)
        normalized: List[Dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                candidate_id = self._coerce_text(item.get("candidate_id"), "")
                reason = self._coerce_text(item.get("reason"), "")
                if candidate_id or reason:
                    normalized.append({"candidate_id": candidate_id, "reason": reason})
            elif isinstance(item, str):
                normalized.append({"candidate_id": "", "reason": item})
        return normalized or fallback

    def _coerce_list(self, value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if value is None:
            return []
        return [value]

    def _coerce_text(self, value: Any, fallback: str = "") -> str:
        if isinstance(value, str):
            return value.strip()
        if value is None:
            return fallback
        return str(value).strip()

    def _coerce_string_list(self, value: Any, fallback: List[str], limit: int = 10) -> List[str]:
        items = self._coerce_list(value)
        normalized: List[str] = []
        for item in items:
            if isinstance(item, dict):
                for key in ("text", "value", "content", "name", "title"):
                    if isinstance(item.get(key), str) and item.get(key).strip():
                        normalized.append(item[key].strip())
                        break
            else:
                text = self._coerce_text(item, "")
                if text:
                    normalized.append(text)
        if not normalized:
            normalized = list(fallback or [])
        return list(dict.fromkeys(normalized))[:limit]

    def _coerce_float(self, value: Any, fallback: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _coerce_bool(self, value: Any, fallback: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y"}:
                return True
            if lowered in {"false", "0", "no", "n"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return fallback

    def _normalize_resolution_type(
        self,
        value: Any,
        fallback: ResolutionType,
    ) -> ResolutionType:
        if isinstance(value, str):
            aliases = {
                "no_valid_rule": ResolutionType.INSUFFICIENT_EVIDENCE,
                "no_match": ResolutionType.INSUFFICIENT_EVIDENCE,
                "need_human_review": fallback,
            }
            if value in aliases:
                return aliases[value]
            try:
                return ResolutionType(value)
            except ValueError:
                pass
        return fallback

    def _finalize_decision_fallback(
        self,
        discovery_mode: DiscoveryMode,
        candidates: List[CandidateRule],
        validated: Dict[str, Any],
    ) -> DiscoveryDecision:
        accepted = [
            item for item in candidates
            if item.validation_status in {
                ValidationStatus.SUPPORTED,
                ValidationStatus.PROVISIONALLY_SUPPORTED,
                ValidationStatus.WEAKLY_SUPPORTED,
            }
        ]
        accepted.sort(key=lambda item: item.confidence, reverse=True)
        rejected = validated.get("rejected_candidates", [])
        open_questions = validated.get("open_questions", [])

        if not accepted:
            exploratory = sorted(
                candidates,
                key=lambda item: item.confidence,
                reverse=True,
            )[:3]
            rejection_map = {
                item.get("candidate_id"): item.get("reason")
                for item in rejected
                if isinstance(item, dict) and item.get("candidate_id")
            }
            for candidate in exploratory:
                candidate.metadata.setdefault("output_role", "exploratory")
                if rejection_map.get(candidate.candidate_id):
                    candidate.metadata["decision_rejected_reason"] = rejection_map[candidate.candidate_id]

            summary = (
                "未形成可直接采纳的规则，但保留探索性候选产物供继续补证与人工研究。"
                if exploratory
                else "未形成具有足够证据支撑的规则结果。"
            )
            return DiscoveryDecision(
                resolution_type=ResolutionType.INSUFFICIENT_EVIDENCE,
                discovery_mode=discovery_mode,
                candidate_rules=exploratory,
                rejected_candidates=rejected,
                open_questions=open_questions,
                summary=summary,
                need_human_review=True,
            )

        selected = accepted[:1]
        top = selected[0]
        resolution_type = ResolutionType(top.candidate_type.value)
        critic_report = top.metadata.get("critic_report", {}) if isinstance(top.metadata, dict) else {}
        relation_types = [item.get("relation_type") for item in critic_report.get("related_rules", [])]
        relation_priority = max([RELATION_PRIORITY.get(item, 0) for item in relation_types], default=0)
        adjudication = critic_report.get("adjudication", {})

        need_human_review = top.validation_status in {
            ValidationStatus.WEAKLY_SUPPORTED,
            ValidationStatus.NEED_HUMAN_REVIEW,
        } or bool(open_questions) or relation_priority >= RELATION_PRIORITY["duplicate"]

        if "duplicate" in relation_types and top.candidate_type == CandidateType.NOVEL_RULE:
            resolution_type = ResolutionType.ADAPTED_RULE
            open_questions = list(dict.fromkeys(open_questions + ["候选新规则可能应降级为改造规则处理"]))

        if "conflict" in relation_types:
            need_human_review = True
            open_questions = list(dict.fromkeys(open_questions + ["需人工判定与既有规则的冲突优先级"]))
            if adjudication.get("preferred_side") == "existing_rule":
                open_questions = list(dict.fromkeys(open_questions + [adjudication.get("reason", "")]))

        summary = {
            ResolutionType.EXACT_REUSE: "现有规则可直接复用。",
            ResolutionType.ADAPTED_RULE: "现有规则可在补充条件后适用。",
            ResolutionType.NOVEL_RULE: "规则库无法直接覆盖，已形成候选新规则。",
            ResolutionType.INSUFFICIENT_EVIDENCE: "现有证据不足，尚未形成可采纳规则。",
        }[resolution_type]

        if adjudication.get("has_conflict") and adjudication.get("preferred_side") == "existing_rule":
            summary += " 当前结果与既有规则存在冲突，默认应以既有规则优先。"
        elif "tighten" in relation_types:
            summary += " 当前结果相较既有规则体现了更严格的控制要求。"
        elif "supplement" in relation_types:
            summary += " 当前结果主要作为既有规则的补充条款。"

        return DiscoveryDecision(
            resolution_type=resolution_type,
            discovery_mode=discovery_mode,
            candidate_rules=selected,
            rejected_candidates=rejected,
            open_questions=open_questions,
            summary=summary,
            need_human_review=need_human_review,
        )

    def _normalize_candidates(
        self,
        raw_candidates: List[Dict[str, Any]],
        fallback_candidates: List[CandidateRule],
    ) -> List[CandidateRule]:
        normalized: List[CandidateRule] = []
        for index, item in enumerate(self._coerce_list(raw_candidates)):
            if not isinstance(item, dict):
                continue
            candidate_type = self._normalize_candidate_type(
                item.get("candidate_type", CandidateType.NOVEL_RULE.value),
                None,
            )
            if candidate_type is None:
                continue
            derived_from = self._coerce_string_list(item.get("derived_from", []), [], limit=8)
            evidence_refs = self._coerce_string_list(item.get("evidence_refs", []), [], limit=8)
            knowledge_sources = self._coerce_string_list(item.get("knowledge_sources", []), [], limit=8)
            source_provenance = item.get("source_provenance", {}) if isinstance(item.get("source_provenance", {}), dict) else {}

            normalized.append(
                CandidateRule(
                    candidate_id=item.get("candidate_id") or f"cand_{index + 1:02d}",
                    candidate_type=candidate_type,
                    rule_id=self._coerce_text(item.get("rule_id"), None) if item.get("rule_id") is not None else None,
                    rule_title=self._coerce_text(item.get("rule_title"), ""),
                    rule_text=self._coerce_text(item.get("rule_text"), ""),
                    derived_from=derived_from,
                    adaptation_note=self._coerce_text(item.get("adaptation_note"), ""),
                    why_applicable=self._coerce_text(item.get("why_applicable"), ""),
                    evidence_refs=evidence_refs,
                    knowledge_sources=knowledge_sources,
                    source_provenance=source_provenance,
                    confidence=self._coerce_float(item.get("confidence", 0.0), 0.0),
                    grounding_score=self._coerce_float(item.get("grounding_score", 0.0), 0.0),
                    speculation_score=self._coerce_float(item.get("speculation_score", 0.0), 0.0),
                )
            )

        return normalized or fallback_candidates

    def _backfill_candidate_provenance(
        self,
        candidates: List[CandidateRule],
        fallback_candidates: List[CandidateRule],
    ) -> List[CandidateRule]:
        fallback_map = {item.candidate_id: item for item in fallback_candidates}
        fallback_by_type = {item.candidate_type: item for item in fallback_candidates}

        for candidate in candidates:
            reference = fallback_map.get(candidate.candidate_id) or fallback_by_type.get(candidate.candidate_type)
            if not reference:
                continue
            if not candidate.knowledge_sources:
                candidate.knowledge_sources = list(reference.knowledge_sources)
            if not candidate.source_provenance:
                candidate.source_provenance = dict(reference.source_provenance)
            if candidate.grounding_score == 0.0 and reference.grounding_score:
                candidate.grounding_score = reference.grounding_score
            if candidate.speculation_score == 0.0 and reference.speculation_score:
                candidate.speculation_score = reference.speculation_score
            self._postprocess_candidate_for_domain(candidate, reference)
        return candidates

    def _postprocess_candidate_for_domain(
        self,
        candidate: CandidateRule,
        reference: CandidateRule,
    ) -> None:
        draft_context = reference.metadata.get("draft_context", {}) if isinstance(reference.metadata, dict) else {}
        scenario_id = str(draft_context.get("scenario_id") or "")
        if scenario_id != "equity_research":
            return
        generic_titles = {"风险控制规则", "人工复核门槛规则", "风险控制规则（改造版）", "人工复核门槛规则（改造版）"}
        if candidate.rule_title in generic_titles:
            if candidate.candidate_type == CandidateType.ADAPTED_RULE:
                candidate.rule_title = "研报分析方法（改造版）"
            else:
                candidate.rule_title = "研报分析方法"

        if any(token in (candidate.rule_text or "") for token in ["人工复核门槛", "对外发送前", "不得在未完成复核前直接执行"]):
            subject = draft_context.get("subject") or "相关公司"
            action = draft_context.get("action") or "形成分析结论"
            risks = "；".join(draft_context.get("risks", [])[:2]) or "如关键数据缺失，应明确说明缺口"
            candidate.rule_text = (
                f"当问题聚焦于{subject}{action}时，系统应优先从文档中提取关键经营指标、趋势变化、风险来源与原文证据，"
                f"形成结构化分析结论；{risks}，不得用泛化治理条款替代业务分析答案。"
            )

    def _normalize_candidate_type(
        self,
        value: Any,
        fallback: Optional[CandidateType],
    ) -> Optional[CandidateType]:
        if isinstance(value, CandidateType):
            return value
        if isinstance(value, str):
            aliases = {
                "exact": CandidateType.EXACT_REUSE,
                "exact_reuse": CandidateType.EXACT_REUSE,
                "reuse": CandidateType.EXACT_REUSE,
                "adapted": CandidateType.ADAPTED_RULE,
                "adapted_rule": CandidateType.ADAPTED_RULE,
                "adaptation": CandidateType.ADAPTED_RULE,
                "novel": CandidateType.NOVEL_RULE,
                "novel_rule": CandidateType.NOVEL_RULE,
                "new_rule": CandidateType.NOVEL_RULE,
            }
            if value in aliases:
                return aliases[value]
            try:
                return CandidateType(value)
            except ValueError:
                pass
        return fallback

    def _call_json_with_fallback(
        self,
        *,
        stage: str,
        payload: Dict[str, Any],
        system_prompt: str,
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.llm_client:
            return fallback

        try:
            result = self.llm_client.chat_json(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
                ],
                temperature=1.0,
                max_tokens=4096,
            )
            if isinstance(result, dict):
                return result
            if stage == "analogies" and isinstance(result, list):
                return {
                    "analogies": result,
                    "reuse_candidates": [],
                    "adaptation_candidates": [],
                    "gaps": [],
                }
        except Exception as exc:
            logger.warning("规则发现阶段 %s 调用 LLM 失败，回退到启发式逻辑: %s", stage, exc)

        return fallback

    def _compose_search_query(self, task: DiscoveryTask, problem_frame: Dict[str, Any]) -> str:
        segments = [task.query, task.context]
        segments.extend(problem_frame.get("entities", [])[:4])
        segments.extend(problem_frame.get("constraints", [])[:2])
        return "\n".join(segment for segment in segments if segment).strip()

    def _extract_keywords(self, text: str, limit: int = 8) -> List[str]:
        counts: Dict[str, int] = {}
        for token in TOKEN_PATTERN.findall((text or "").lower()):
            token = token.strip()
            if not token or token in STOPWORDS:
                continue
            if len(token) == 1 and not re.fullmatch(r"[\u4e00-\u9fff]", token):
                continue
            counts[token] = counts.get(token, 0) + 1

        return [
            token for token, _ in sorted(
                counts.items(),
                key=lambda item: (-item[1], -len(item[0]), item[0]),
            )[:limit]
        ]

    def _split_sentences(self, text: str, limit: int = 3) -> List[str]:
        parts = re.split(r"[。\n！？!?；;]+", text or "")
        cleaned = [part.strip() for part in parts if part.strip()]
        return cleaned[:limit]

    def _normalize_action_text(self, text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = re.sub(r"[？?]\s*$", "", cleaned)
        cleaned = re.sub(r"(应适用什么规则|适用什么规则|该适用什么规则)$", "", cleaned)
        cleaned = re.sub(r"^面对", "", cleaned)
        cleaned = cleaned.strip("，,。；; ")
        return cleaned or "相关行为"


class DiscoveryCancelledError(RuntimeError):
    """规则发现任务被取消。"""


class DiscoveryTimedOutError(RuntimeError):
    """规则发现任务超时。"""
