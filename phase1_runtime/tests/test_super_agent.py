from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from phase1_runtime.agents import build_super_agent_handoff, run_super_agent
from phase1_runtime.agents.super_agent_service import build_super_agent_system_prompt, build_super_agent_user_message


class SuperAgentServiceTests(unittest.TestCase):
    def test_run_super_agent_executes_tool_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace_root = root / "workspace"
            skill_root = root / "skill"
            workspace_root.mkdir()
            skill_root.mkdir()
            (workspace_root / "note.txt").write_text(
                "工商银行研报维持增持评级，主要风险包括零售不良和LPR下调。",
                encoding="utf-8",
            )
            (skill_root / "SKILL.md").write_text(
                "---\nname: equity-research-lite\ndescription: summarize a note\n---\n\n# Skill\n\n## Workflow\n\n1. Read supporting files.\n2. Answer the query.\n",
                encoding="utf-8",
            )

            calls: list[dict[str, object]] = []

            def transport(payload: dict[str, object]) -> dict[str, object]:
                calls.append(payload)
                if len(calls) == 1:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "read_file",
                                                "arguments": '{"path":"note.txt"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                tool_message = payload["messages"][-1]
                self.assertEqual(tool_message["role"], "tool")
                self.assertIn("增持评级", tool_message["content"])
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "最终回答：研报维持增持评级，主要下行风险包括零售不良和LPR下调。"
                            }
                        }
                    ]
                }

            result = run_super_agent(
                query="请总结这份说明",
                skill_root=skill_root,
                workspace_root=workspace_root,
                task_context={"scenario_id": "equity_research"},
                context_packet={"context_summary": "维持增持评级", "relevant_blocks": [{"locator": {"page": 1}, "text": "维持增持评级"}]},
                kimi_client=transport,
                max_turns=4,
            )
            self.assertEqual(result["turns"], 2)
            self.assertEqual(result["tool_call_count"], 1)
            self.assertIn("增持评级", result["final_text"])
            self.assertEqual(result["history"][1]["tool_calls"][0]["name"], "read_file")
            self.assertGreater(len(result["agent_trace"]), 0)
            self.assertEqual(result["context_packet"]["context_summary"], "维持增持评级")

    def test_run_super_agent_supports_python_exec_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace_root = root / "workspace"
            skill_root = root / "skill"
            workspace_root.mkdir()
            skill_root.mkdir()
            (skill_root / "SKILL.md").write_text(
                "---\nname: python-test\ndescription: run python\n---\n\n# Skill\n",
                encoding="utf-8",
            )

            calls: list[dict[str, object]] = []

            def transport(payload: dict[str, object]) -> dict[str, object]:
                calls.append(payload)
                if len(calls) == 1:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "python_exec",
                                                "arguments": '{"code":"print(2 + 3)"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                self.assertEqual(payload["messages"][-1]["role"], "tool")
                self.assertIn("5", payload["messages"][-1]["content"])
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "最终回答：计算结果是 5。"
                            }
                        }
                    ]
                }

            result = run_super_agent(
                query="请计算 2 + 3",
                skill_root=skill_root,
                workspace_root=workspace_root,
                kimi_client=transport,
                max_turns=3,
            )
            self.assertEqual(result["tool_call_count"], 1)
            self.assertIn("计算结果是 5", result["final_text"])
            tool_events = [item for item in result["agent_trace"] if item["event"] == "tool_result"]
            self.assertEqual(tool_events[0]["tool_name"], "python_exec")

    def test_build_super_agent_handoff(self) -> None:
        payload = build_super_agent_handoff(
            query="是否需要风险提示？",
            skill_root="/tmp/runtime-skill",
            workspace_root="/tmp/workspace",
            task_context={"scenario_id": "fund_nav_warning"},
            context_packet={"context_summary": "净值 0.72 低于 0.80"},
            max_turns=6,
        )
        self.assertEqual(payload["action"], "super_agent.run")
        self.assertEqual(payload["payload"]["query"], "是否需要风险提示？")
        self.assertEqual(payload["payload"]["max_turns"], 6)
        self.assertEqual(payload["payload"]["task_context"]["scenario_id"], "fund_nav_warning")
        self.assertEqual(payload["payload"]["context_packet"]["context_summary"], "净值 0.72 低于 0.80")

    def test_build_super_agent_user_message_hides_redundant_reference_files(self) -> None:
        message = build_super_agent_user_message(
            query="这份研报对工商银行的投资评级是什么？",
            skill_root="/tmp/runtime-skill",
            workspace_root="/tmp/workspace",
            skill_file_map={
                "references/bound-context.json": "/tmp/runtime-skill/references/bound-context.json",
                "references/rule-binding.json": "/tmp/runtime-skill/references/rule-binding.json",
                "references/source-rule.json": "/tmp/runtime-skill/references/source-rule.json",
                "scripts/helper.py": "/tmp/runtime-skill/scripts/helper.py",
            },
            context_packet={
                "relevant_blocks": [
                    {"locator": {"page": 1}, "text": "增持（维持）"},
                ]
            },
        )
        self.assertNotIn("references/bound-context.json", message)
        self.assertNotIn("references/rule-binding.json", message)
        self.assertIn("references/source-rule.json", message)
        self.assertIn("scripts/helper.py", message)

    def test_build_super_agent_system_prompt_requires_direct_answer_first(self) -> None:
        prompt = build_super_agent_system_prompt(
            skill_root="/tmp/runtime-skill",
            skill_md="# Skill",
            workspace_root="/tmp/workspace",
            context_packet={"context_summary": "增持（维持）"},
        )
        self.assertIn("first sentence must be the shortest direct answer", prompt)


if __name__ == "__main__":
    unittest.main()
