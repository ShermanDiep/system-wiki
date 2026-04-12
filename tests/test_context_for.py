from __future__ import annotations

import unittest

import networkx as nx

from system_wiki.query_graph import (
    cmd_context_for,
    cmd_docs_for,
    cmd_files_for_change,
    cmd_impact,
    cmd_untested_impact,
    cmd_verify_after_change,
)


def _add_edge(G: nx.Graph, source: str, target: str, relation: str) -> None:
    G.add_edge(
        source,
        target,
        relation=relation,
        confidence="EXTRACTED",
        _src=source,
        _tgt=target,
    )


def _build_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node(
        "mod_main",
        label="main.py",
        file_type="code",
        symbol_kind="module",
        source_file="app/main.py",
        source_location="L1",
        qualified_name="app.main",
        summary="Module with main entrypoint.",
        community=1,
    )
    G.add_node(
        "main_fn",
        label="main()",
        file_type="code",
        symbol_kind="function",
        source_file="app/main.py",
        source_location="L3",
        qualified_name="app.main.main",
        container="app.main",
        summary="Entrypoint that triggers the service flow.",
        community=1,
    )
    G.add_node(
        "mod_service",
        label="service.py",
        file_type="code",
        symbol_kind="module",
        source_file="app/service.py",
        source_location="L1",
        qualified_name="app.service",
        summary="Module with request handling logic.",
        community=1,
    )
    G.add_node(
        "service_fn",
        label="handle_request()",
        file_type="code",
        symbol_kind="function",
        source_file="app/service.py",
        source_location="L5",
        qualified_name="app.service.handle_request",
        container="app.service",
        summary="Main request handler.",
        community=1,
    )
    G.add_node(
        "helper_fn",
        label="validate_input()",
        file_type="code",
        symbol_kind="function",
        source_file="app/helpers.py",
        source_location="L2",
        qualified_name="app.helpers.validate_input",
        container="app.helpers",
        summary="Validation helper.",
        community=1,
    )
    G.add_node(
        "test_fn",
        label="test_handle_request()",
        file_type="code",
        symbol_kind="function",
        source_file="tests/test_service.py",
        source_location="L8",
        qualified_name="tests.test_service.test_handle_request",
        container="tests.test_service",
        summary="Regression test for handle_request.",
        community=2,
    )
    G.add_node(
        "doc_runbook",
        label="Service Troubleshooting",
        file_type="document",
        source_file="docs/runbook-service.md",
        source_location="L1",
        summary="Operational notes for service failures.",
        doc_subtype="runbook",
        community=3,
    )
    G.add_node(
        "doc_spec",
        label="Service Feature Spec",
        file_type="document",
        source_file="docs/service-spec.md",
        source_location="L1",
        summary="Spec for extending the request flow.",
        doc_subtype="spec",
        community=3,
    )
    G.add_node(
        "doc_adr",
        label="Request Routing ADR",
        file_type="document",
        source_file="docs/adr/ADR-001-routing.md",
        source_location="L1",
        summary="Decision record for request routing boundaries.",
        doc_subtype="adr",
        community=3,
    )
    G.add_node(
        "doc_readme",
        label="README",
        file_type="document",
        source_file="README.md",
        source_location="L1",
        summary="Project overview and entrypoint usage.",
        doc_subtype="readme",
        community=3,
    )

    _add_edge(G, "mod_main", "main_fn", "contains")
    _add_edge(G, "mod_service", "service_fn", "contains")
    _add_edge(G, "main_fn", "service_fn", "calls")
    _add_edge(G, "service_fn", "helper_fn", "calls")
    _add_edge(G, "test_fn", "service_fn", "calls")
    _add_edge(G, "doc_runbook", "service_fn", "mentions")
    _add_edge(G, "doc_spec", "service_fn", "mentions")
    _add_edge(G, "doc_adr", "mod_service", "references")
    _add_edge(G, "mod_main", "mod_service", "imports")
    return G


class ContextForTests(unittest.TestCase):
    def test_bugfix_context_surfaces_tests_and_docs(self) -> None:
        graph = _build_graph()

        result = cmd_context_for(graph, "fix handle_request bug", mode="bugfix")

        self.assertIn("Context for 'fix handle_request bug' [bugfix]:", result)
        self.assertIn("handle_request()", result)
        self.assertIn("Tests to check:", result)
        self.assertIn("test_handle_request()", result)
        self.assertIn("Docs/specs:", result)
        self.assertIn("Service Troubleshooting", result)
        self.assertIn("[runbook]", result)

    def test_feature_context_surfaces_entry_path(self) -> None:
        graph = _build_graph()

        result = cmd_context_for(graph, "add feature around handle_request", mode="feature")

        self.assertIn("Context for 'add feature around handle_request' [feature]:", result)
        self.assertIn("Entry paths:", result)
        self.assertIn("main()", result)

    def test_docs_for_symbol_surfaces_related_docs(self) -> None:
        graph = _build_graph()

        result = cmd_docs_for(graph, "handle_request")

        self.assertIn("Docs/specs for handle_request():", result)
        self.assertIn("Service Troubleshooting", result)
        self.assertIn("directly mentions handle_request()", result)
        self.assertIn("[runbook]", result)

    def test_docs_for_feature_mode_prefers_spec_and_design_docs(self) -> None:
        graph = _build_graph()

        result = cmd_docs_for(graph, "handle_request", mode="feature")

        self.assertIn("Docs/specs for handle_request() [feature]:", result)
        self.assertLess(result.index("Service Feature Spec"), result.index("Service Troubleshooting"))
        self.assertIn("[spec]", result)

    def test_docs_for_type_filter_limits_results(self) -> None:
        graph = _build_graph()

        result = cmd_docs_for(graph, "handle_request", mode="bugfix", doc_type="runbook")

        self.assertIn("Docs/specs for handle_request() [bugfix type=runbook]:", result)
        self.assertIn("Service Troubleshooting", result)
        self.assertNotIn("Service Feature Spec", result)

    def test_docs_for_onboarding_entrypoint_falls_back_to_readme(self) -> None:
        graph = _build_graph()

        result = cmd_docs_for(graph, "main", mode="onboarding", doc_type="readme")

        self.assertIn("Docs/specs for main.py [onboarding type=readme]:", result)
        self.assertIn("README", result)
        self.assertIn("readme overview for entrypoint/module", result)

    def test_files_for_change_groups_code_tests_and_docs(self) -> None:
        graph = _build_graph()

        result = cmd_files_for_change(graph, "fix handle_request bug", mode="bugfix")

        self.assertIn("Files for change for 'fix handle_request bug' [bugfix]:", result)
        self.assertIn("impact:", result)
        self.assertIn("Edit first:", result)
        self.assertIn("app/service.py", result)
        self.assertIn("Verify adjacent code:", result)
        self.assertIn("app/main.py", result)
        self.assertIn("Tests to update/check:", result)
        self.assertIn("tests/test_service.py", result)
        self.assertIn("Docs to review:", result)
        self.assertIn("docs/runbook-service.md", result)

    def test_untested_impact_surfaces_adjacent_code_without_tests(self) -> None:
        graph = _build_graph()

        result = cmd_untested_impact(graph, "handle_request")

        self.assertIn("Untested impact for handle_request():", result)
        self.assertIn("app/main.py", result)
        self.assertIn("no related tests found", result)

    def test_verify_after_change_builds_post_change_checklist(self) -> None:
        graph = _build_graph()

        result = cmd_verify_after_change(graph, "fix handle_request bug", mode="bugfix")

        self.assertIn("Verify after change for 'fix handle_request bug' [bugfix]:", result)
        self.assertIn("Re-check adjacent code:", result)
        self.assertIn("app/main.py", result)
        self.assertIn("Smoke likely entry paths:", result)
        self.assertIn("main()", result)
        self.assertIn("Run or update tests:", result)
        self.assertIn("tests/test_service.py", result)
        self.assertIn("Review docs/runbooks:", result)
        self.assertIn("docs/runbook-service.md", result)

    def test_impact_reports_doc_types_and_untested_files(self) -> None:
        graph = _build_graph()

        result = cmd_impact(graph, "handle_request")

        self.assertIn("Impact for handle_request():", result)
        self.assertIn("doc types:", result)
        self.assertIn("runbook: 1", result)
        self.assertIn("spec: 1", result)
        self.assertIn("untested impacted files:", result)
        self.assertIn("app/main.py", result)


if __name__ == "__main__":
    unittest.main()
