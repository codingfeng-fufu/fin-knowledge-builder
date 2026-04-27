from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from phase1_runtime.skills import build_kimi_llm_generate, build_kimi_chat_payload, KimiSkillCreatorConfig
from phase1_runtime.runtime_core import bind_rule
from phase1_runtime.skills import (
    build_skill_creator_request,
    compile_rule_to_reusable_skill,
    materialize_skill_artifact,
    validate_skill_artifact,
)
from phase1_runtime.schema import load_rule
from phase1_runtime.runtime_core import build_task_context


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


class RuleToSkillCreatorTests(unittest.TestCase):
    def _build_context_and_binding(self):
        rule = load_rule(FIXTURE_DIR / "rule_private_fund_nav_warning.json")
        task_context = build_task_context(
            question_text="某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
            scenario_hint="fund_nav_warning",
            parser_status="parsed_complete",
            documents=[
                {"doc_id": "upload_doc_001", "title": "fund_clause.docx", "doc_type": "contract", "parse_status": "parsed_docx_text", "source_type": "uploaded_docx"},
            ],
            fact_sheet=[
                {"fact_id": "current_nav", "fact_type": "float", "value": 0.72, "source": "parsed_upload", "evidence_refs": []},
                {"fact_id": "warning_threshold", "fact_type": "float", "value": 0.8, "source": "parsed_upload", "evidence_refs": []},
                {"fact_id": "contract_requires_warning", "fact_type": "bool", "value": True, "source": "parsed_upload", "evidence_refs": []},
            ],
            evidence_packets=[],
        )
        binding = bind_rule(
            rule,
            task_context,
            retrieval_score=61,
            retrieval_reasons=["question_type_match", "intent_match", "document_type_match"],
            eligible_for_direct_match=True,
        )
        return rule, task_context, binding

    def test_build_skill_creator_request(self) -> None:
        rule, task_context, binding = self._build_context_and_binding()
        payload = build_skill_creator_request(rule, task_context, binding)
        self.assertEqual(payload["rule"]["rule_id"], "private_fund.nav_risk_warning.v1")
        self.assertEqual(payload["query"], task_context.question_text)
        self.assertEqual(payload["task_context"]["context_status"], "grounded_enough")
        self.assertEqual(payload["rule_binding"]["binding_status"], "bindable")
        self.assertIn("suggested_skill_name", payload["constraints"])
        self.assertIn("skill_creator_reference_md", payload)

    def test_compile_rule_to_reusable_skill_deterministic(self) -> None:
        rule, task_context, binding = self._build_context_and_binding()
        artifact = compile_rule_to_reusable_skill(rule, task_context, binding)
        self.assertIn("SKILL.md", artifact.file_map())
        self.assertIn("name:", artifact.skill_md)
        self.assertIn("## Workflow", artifact.skill_md)
        self.assertIn("## Validation", artifact.skill_md)
        self.assertEqual(artifact.metadata["source_rule_id"], rule.rule_id)
        self.assertEqual(artifact.metadata["binding_status"], "bindable")

    def test_compile_rule_to_reusable_skill_with_llm_override(self) -> None:
        rule, task_context, binding = self._build_context_and_binding()

        def fake_llm(request):
            return {
                "skill_name": "fund-nav-warning-skill",
                "description": "LLM generated skill description",
                "skill_md": "---\nname: fund-nav-warning-skill\ndescription: LLM generated skill description\n---\n\n# LLM Skill\n",
            }

        artifact = compile_rule_to_reusable_skill(rule, task_context, binding, llm_generate=fake_llm)
        self.assertEqual(artifact.skill_name, "fund-nav-warning-skill")
        self.assertEqual(artifact.description, "LLM generated skill description")
        self.assertIn("# LLM Skill", artifact.skill_md)
        self.assertEqual(artifact.metadata["generator_backend"], "template")

    def test_build_kimi_chat_payload(self) -> None:
        rule, task_context, binding = self._build_context_and_binding()
        request_payload = build_skill_creator_request(rule, task_context, binding)
        config = KimiSkillCreatorConfig(api_key="test-key")
        payload = build_kimi_chat_payload(request_payload, config)
        self.assertEqual(payload["model"], "kimi-k2.5")
        self.assertEqual(payload["thinking"]["type"], "disabled")
        self.assertEqual(payload["messages"][0]["role"], "system")

    def test_compile_rule_to_reusable_skill_with_kimi_transport(self) -> None:
        rule, task_context, binding = self._build_context_and_binding()

        def fake_transport(payload):
            return {
                "choices": [
                    {
                        "message": {
                            "content": """{
  "skill_name": "fund-nav-kimi",
  "description": "Kimi generated reusable skill",
  "skill_md": "---\\nname: fund-nav-kimi\\ndescription: Kimi generated reusable skill\\n---\\n\\n# Kimi Skill\\n",
  "references": {},
  "scripts": {}
}"""
                        }
                    }
                ]
            }

        kimi_generate = build_kimi_llm_generate(
            config=KimiSkillCreatorConfig(api_key="test-key"),
            transport=fake_transport,
        )
        artifact = compile_rule_to_reusable_skill(rule, task_context, binding, llm_generate=kimi_generate)
        self.assertEqual(artifact.skill_name, "fund-nav-kimi")
        self.assertIn("# Kimi Skill", artifact.skill_md)

    def test_materialize_skill_artifact(self) -> None:
        rule, task_context, binding = self._build_context_and_binding()
        artifact = compile_rule_to_reusable_skill(rule, task_context, binding)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = materialize_skill_artifact(artifact, tmpdir)
            self.assertTrue((path / "SKILL.md").exists())
            self.assertTrue((path / "references" / "source-rule.json").exists())

    def test_validate_skill_artifact(self) -> None:
        rule, task_context, binding = self._build_context_and_binding()
        artifact = compile_rule_to_reusable_skill(rule, task_context, binding)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = materialize_skill_artifact(artifact, tmpdir)
            validation = validate_skill_artifact(path)
            self.assertIsNotNone(validation)
            self.assertEqual(validation["validator"], "anthropic_skill_creator.quick_validate")


if __name__ == "__main__":
    unittest.main()
