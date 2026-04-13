from __future__ import annotations

import unittest

from system_wiki.eval_benchmarks import (
    _is_better_or_equal,
    compare_to_baseline,
    evaluate_suite,
    make_baseline_snapshot,
)

from test_context_for import _build_graph


class EvalBenchmarkTests(unittest.TestCase):
    def test_evaluate_suite_scores_context_and_files_cases(self) -> None:
        graph = _build_graph()
        suite = {
            "name": "synthetic-context-suite",
            "assertions": {
                "min_avg_context_recall": 0.9,
                "min_avg_context_precision": 0.4,
                "max_avg_files_opened": 5,
            },
            "cases": [
                {
                    "name": "bugfix files",
                    "command": "files-for-change",
                    "task": "fix handle_request bug",
                    "mode": "bugfix",
                    "assertions": {
                        "min_case_recall": 1.0,
                        "min_case_precision": 0.5,
                        "max_files_opened": 5,
                    },
                    "expected": {
                        "edit_sources": ["app/service.py"],
                        "verify_sources": ["app/main.py"],
                        "test_sources": ["tests/test_service.py"],
                        "doc_sources": ["docs/runbook-service.md"],
                    },
                },
                {
                    "name": "feature context",
                    "command": "context-for",
                    "task": "add feature around handle_request",
                    "mode": "feature",
                    "assertions": {
                        "min_case_recall": 1.0,
                    },
                    "expected": {
                        "focus_sources": ["app/service.py"],
                    },
                },
                {
                    "name": "docs lookup",
                    "command": "docs-for",
                    "label": "handle_request",
                    "mode": "bugfix",
                    "doc_type": "runbook",
                    "assertions": {
                        "min_case_recall": 1.0,
                    },
                    "expected": {
                        "doc_sources": ["docs/runbook-service.md"],
                    },
                },
                {
                    "name": "doc drift feature",
                    "command": "doc-drift",
                    "label": "main",
                    "mode": "onboarding",
                    "doc_type": "readme",
                    "assertions": {
                        "min_case_recall": 1.0,
                    },
                    "expected": {
                        "review_doc_sources": ["README.md"],
                    },
                },
                {
                    "name": "untested impact",
                    "command": "untested-impact",
                    "label": "handle_request",
                    "assertions": {
                        "min_case_recall": 1.0,
                    },
                    "expected": {
                        "untested_sources": ["app/main.py"],
                    },
                },
                {
                    "name": "verify checklist",
                    "command": "verify-after-change",
                    "task": "fix handle_request bug",
                    "mode": "bugfix",
                    "assertions": {
                        "min_case_recall": 1.0,
                    },
                    "expected": {
                        "verify_sources": ["app/main.py"],
                        "test_sources": ["tests/test_service.py"],
                        "doc_sources": ["docs/runbook-service.md"],
                        "smoke_sources": ["app/main.py"],
                    },
                },
            ],
        }

        report = evaluate_suite(graph, suite)

        self.assertEqual(report["summary"]["case_count"], 6)
        self.assertGreater(report["summary"]["avg_context_recall"], 0.9)
        self.assertGreater(report["summary"]["avg_context_precision"], 0.4)
        self.assertTrue(report["passed"])
        self.assertTrue(report["summary_assertions"]["passed"])
        self.assertEqual(report["cases"][0]["metrics"]["edit_sources"]["matched"], ["app/service.py"])
        self.assertEqual(report["cases"][0]["metrics"]["verify_sources"]["matched"], ["app/main.py"])
        self.assertEqual(report["cases"][2]["metrics"]["doc_sources"]["matched"], ["docs/runbook-service.md"])
        self.assertEqual(report["cases"][3]["metrics"]["review_doc_sources"]["matched"], ["README.md"])
        self.assertEqual(report["cases"][4]["metrics"]["untested_sources"]["matched"], ["app/main.py"])
        self.assertEqual(report["cases"][5]["metrics"]["smoke_sources"]["matched"], ["app/main.py"])

    def test_evaluate_suite_reports_failed_assertions(self) -> None:
        graph = _build_graph()
        suite = {
            "name": "failing-suite",
            "assertions": {
                "min_avg_context_precision": 0.95,
            },
            "cases": [
                {
                    "name": "too-strict-context",
                    "command": "context-for",
                    "task": "add feature around handle_request",
                    "mode": "feature",
                    "assertions": {
                        "max_files_opened": 1,
                    },
                    "expected": {
                        "focus_sources": ["app/service.py"],
                    },
                }
            ],
        }

        report = evaluate_suite(graph, suite)

        self.assertFalse(report["passed"])
        self.assertFalse(report["summary_assertions"]["passed"])
        self.assertFalse(report["cases"][0]["assertions"]["passed"])
        self.assertTrue(any("max_files_opened" in failure for failure in report["failures"]))

    def test_compare_to_baseline_passes_for_identical_report(self) -> None:
        graph = _build_graph()
        suite = {
            "name": "baseline-suite",
            "comparison_tolerances": {
                "context_recall_drop": 0.0,
                "context_precision_drop": 0.0,
                "files_opened_increase": 0.0,
                "approx_tokens_increase": 0.0,
            },
            "cases": [
                {
                    "name": "feature context",
                    "command": "context-for",
                    "task": "add feature around handle_request",
                    "mode": "feature",
                    "expected": {
                        "focus_sources": ["app/service.py"],
                    },
                }
            ],
        }

        report = evaluate_suite(graph, suite)
        baseline = make_baseline_snapshot(report, suite=suite)
        comparison = compare_to_baseline(report, baseline, suite=suite)

        self.assertTrue(comparison["passed"])
        self.assertEqual(comparison["failures"], [])
        self.assertEqual(comparison["summary_delta"]["avg_context_precision"], 0.0)

    def test_compare_to_baseline_detects_regression(self) -> None:
        graph = _build_graph()
        suite = {
            "name": "baseline-suite",
            "comparison_tolerances": {
                "context_recall_drop": 0.0,
                "context_precision_drop": 0.0,
                "files_opened_increase": 0.0,
                "approx_tokens_increase": 0.0,
            },
            "cases": [
                {
                    "name": "docs lookup",
                    "command": "doc-drift",
                    "label": "handle_request",
                    "expected": {
                        "review_doc_sources": ["docs/runbook-service.md"],
                    },
                }
            ],
        }

        report = evaluate_suite(graph, suite)
        baseline = make_baseline_snapshot(report, suite=suite)
        regressed_report = {
            **report,
            "summary": {
                **report["summary"],
                "avg_context_precision": 0.0,
            },
            "cases": [
                {
                    **report["cases"][0],
                    "case_precision": 0.0,
                }
            ],
        }

        comparison = compare_to_baseline(regressed_report, baseline, suite=suite)

        self.assertFalse(comparison["passed"])
        self.assertTrue(any("avg_context_precision" in failure for failure in comparison["failures"]))
        self.assertEqual(comparison["cases"][0]["name"], "docs lookup")

    def test_is_better_or_equal_requires_no_regressions(self) -> None:
        better_report = {
            "summary": {
                "avg_context_recall": 1.0,
                "avg_context_precision": 0.8,
                "avg_files_opened": 3.0,
                "avg_approx_tokens": 200.0,
            }
        }
        baseline = {
            "summary": {
                "avg_context_recall": 0.9,
                "avg_context_precision": 0.7,
                "avg_files_opened": 4.0,
                "avg_approx_tokens": 220.0,
            }
        }
        worse_report = {
            "summary": {
                "avg_context_recall": 1.0,
                "avg_context_precision": 0.8,
                "avg_files_opened": 5.0,
                "avg_approx_tokens": 180.0,
            }
        }

        self.assertTrue(_is_better_or_equal(better_report, baseline))
        self.assertFalse(_is_better_or_equal(worse_report, baseline))


if __name__ == "__main__":
    unittest.main()
