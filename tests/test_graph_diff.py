from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from system_wiki.query_graph import _graph_diff_summary, cmd_graph_diff


def _write_graph(path: Path, G: nx.Graph) -> None:
    try:
        data = json_graph.node_link_data(G, edges="links")
    except TypeError:
        data = json_graph.node_link_data(G, link="links")
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_before_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node(
        "mod_api",
        label="api.py",
        file_type="code",
        symbol_kind="module",
        source_file="app/api.py",
        source_location="L1",
        qualified_name="app.api",
    )
    G.add_node(
        "create_user",
        label="create_user()",
        file_type="code",
        symbol_kind="function",
        source_file="app/api.py",
        source_location="L5",
        qualified_name="app.api.create_user",
        container="app.api",
    )
    G.add_edge(
        "mod_api",
        "create_user",
        relation="contains",
        confidence="EXTRACTED",
        source_file="app/api.py",
        source_location="L5",
        _src="mod_api",
        _tgt="create_user",
    )
    return G


def _make_after_graph() -> nx.Graph:
    G = _make_before_graph()
    G.add_node(
        "mod_worker",
        label="worker.py",
        file_type="code",
        symbol_kind="module",
        source_file="jobs/worker.py",
        source_location="L1",
        qualified_name="jobs.worker",
    )
    G.add_node(
        "sync_user",
        label="sync_user()",
        file_type="code",
        symbol_kind="function",
        source_file="jobs/worker.py",
        source_location="L4",
        qualified_name="jobs.worker.sync_user",
        container="jobs.worker",
    )
    G.add_edge(
        "mod_worker",
        "sync_user",
        relation="contains",
        confidence="EXTRACTED",
        source_file="jobs/worker.py",
        source_location="L4",
        _src="mod_worker",
        _tgt="sync_user",
    )
    G.add_edge(
        "sync_user",
        "create_user",
        relation="calls",
        confidence="EXTRACTED",
        source_file="jobs/worker.py",
        source_location="L8",
        _src="sync_user",
        _tgt="create_user",
    )
    return G


class GraphDiffTests(unittest.TestCase):
    def test_graph_diff_summary_reports_added_structural_items(self) -> None:
        before = _make_before_graph()
        after = _make_after_graph()

        result = _graph_diff_summary(before, after, before_label="before.json", after_label="after.json")

        self.assertIn("Graph diff: before.json -> after.json", result)
        self.assertIn("nodes: 2 -> 4", result)
        self.assertIn("edges: 1 -> 3", result)
        self.assertIn("Added files:", result)
        self.assertIn("jobs/worker.py", result)
        self.assertIn("Added modules:", result)
        self.assertIn("jobs.worker", result)
        self.assertIn("Added symbols:", result)
        self.assertIn("jobs.worker.sync_user", result)

    def test_cmd_graph_diff_reads_snapshot_paths(self) -> None:
        before = _make_before_graph()
        after = _make_after_graph()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            before_path = tmp / "before.json"
            after_path = tmp / "after.json"
            _write_graph(before_path, before)
            _write_graph(after_path, after)

            result = cmd_graph_diff(after, str(before_path), after_graph_path=str(after_path))

        self.assertIn("Graph diff:", result)
        self.assertIn("before.json", result)
        self.assertIn("after.json", result)
        self.assertIn("Top changed files:", result)
        self.assertIn("jobs/worker.py", result)


if __name__ == "__main__":
    unittest.main()
