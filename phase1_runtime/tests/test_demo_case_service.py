from __future__ import annotations

import unittest

from phase1_runtime.tools.demo_case_service import get_workspace_demo_case, list_workspace_demo_cases


class DemoCaseServiceTests(unittest.TestCase):
    def test_list_workspace_demo_cases(self) -> None:
        payload = list_workspace_demo_cases()
        self.assertEqual(payload["case_count"], 8)
        self.assertEqual(payload["default_case_ref"], "workspace/fund_docx_direct_warn")
        case_refs = {item["case_ref"] for item in payload["cases"]}
        self.assertEqual(
            case_refs,
            {
                "workspace/fund_docx_direct_warn",
                "workspace/workspace_exploration_new_atomic",
                "workspace/disclosure_exploration_major_announcement",
                "workspace/disclosure_exploration_guidance_revision",
                "workspace/equity_research_h3_conflict_adjudication",
                "workspace/equity_research_h3_2025_performance",
                "workspace/equity_research_h3_risk_focus",
                "workspace/equity_research_h3_code_upside_calc",
            },
        )

    def test_get_workspace_demo_case_for_fund_warning(self) -> None:
        payload = get_workspace_demo_case("workspace/fund_docx_direct_warn")
        self.assertEqual(payload["scenario_id"], "fund_nav_warning")
        self.assertIn("风险提示", payload["question_text"])
        self.assertEqual(len(payload["materials"]), 1)
        self.assertEqual(payload["materials"][0]["name"], "fund_clause.docx")
        self.assertIn("content_base64", payload["materials"][0])

    def test_get_workspace_demo_case_with_binary_material(self) -> None:
        payload = get_workspace_demo_case("workspace/equity_research_h3_code_upside_calc")
        self.assertEqual(payload["scenario_id"], "equity_research")
        self.assertIn("Python 代码", payload["question_text"])
        material_names = {item["name"] for item in payload["materials"]}
        self.assertIn("H3_AP202604031821011697_1.pdf", material_names)
        self.assertIn("研报估值复算摘录.txt", material_names)
        pdf_material = next(item for item in payload["materials"] if item["name"] == "H3_AP202604031821011697_1.pdf")
        self.assertIn("content_base64", pdf_material)
        self.assertGreaterEqual(len(payload["related_questions"]), 4)

    def test_get_workspace_demo_case_for_conflict_adjudication_exploration(self) -> None:
        payload = get_workspace_demo_case("workspace/equity_research_h3_conflict_adjudication")
        self.assertEqual(payload["scenario_id"], "equity_research_adjudication")
        self.assertIn("作出最终裁决", payload["question_text"])
        self.assertEqual(payload["expected"]["route_decision"], "exploration")
        material_names = {item["name"] for item in payload["materials"]}
        self.assertIn("H3_AP202604031821011697_1.pdf", material_names)
        self.assertIn("研报观点冲突裁决摘录.txt", material_names)

    def test_get_workspace_demo_case_for_performance_showcase(self) -> None:
        payload = get_workspace_demo_case("workspace/equity_research_h3_2025_performance")
        self.assertEqual(payload["scenario_id"], "equity_research")
        self.assertIn("2025年工商银行的整体业绩表现如何", payload["question_text"])
        self.assertEqual(payload["materials"][0]["name"], "H3_AP202604031821011697_1.pdf")

    def test_get_workspace_demo_case_for_risk_showcase(self) -> None:
        payload = get_workspace_demo_case("workspace/equity_research_h3_risk_focus")
        self.assertEqual(payload["scenario_id"], "equity_research")
        self.assertIn("潜在的投资风险", payload["question_text"])
        self.assertEqual(payload["materials"][0]["name"], "H3_AP202604031821011697_1.pdf")


if __name__ == "__main__":
    unittest.main()
