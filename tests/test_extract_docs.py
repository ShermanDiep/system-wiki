from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from system_wiki.extract_docs import extract_doc


class ExtractDocsTests(unittest.TestCase):
    def test_extract_doc_infers_runbook_subtype(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "docs" / "service-runbook.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Troubleshooting\n\nHow to recover the service.\n", encoding="utf-8")

            result = extract_doc(path, root=root)

            self.assertEqual(result["nodes"][0]["doc_subtype"], "runbook")
            self.assertEqual(result["nodes"][0]["summary"], "Troubleshooting")

    def test_extract_doc_infers_adr_subtype(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "docs" / "adr" / "ADR-001-routing.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Architecture Decision Record\n\nUse module boundaries.\n", encoding="utf-8")

            result = extract_doc(path, root=root)

            self.assertEqual(result["nodes"][0]["doc_subtype"], "adr")

    def test_extract_doc_semantic_signals_for_workflow_constraints_and_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "docs" / "checkout-design.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "\n".join(
                    [
                        "# Checkout Design",
                        "",
                        "## Workflow",
                        "1. Validate the request payload.",
                        "2. Persist the order before emitting events.",
                        "",
                        "## Constraints",
                        "- Requests must include an idempotency key.",
                        "- Workers should not publish duplicate events.",
                        "",
                        "## Decision",
                        "- We chose the outbox pattern for event delivery.",
                    ]
                ),
                encoding="utf-8",
            )

            result = extract_doc(path, root=root)
            hub = result["nodes"][0]

            self.assertEqual(hub["doc_subtype"], "design")
            self.assertIn("Validate the request payload", hub["workflow_signals"][0])
            self.assertIn("must include an idempotency key", hub["constraint_signals"][0].lower())
            self.assertIn("outbox pattern", hub["decision_signals"][0].lower())
            self.assertIn("Workflow:", hub["summary"])
            self.assertIn("Constraint:", hub["summary"])
            self.assertIn("Decision:", hub["summary"])


if __name__ == "__main__":
    unittest.main()
