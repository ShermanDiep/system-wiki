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


if __name__ == "__main__":
    unittest.main()
