from __future__ import annotations

import unittest

import networkx as nx

from system_wiki.query_graph import (
    cmd_context_for,
    cmd_definitions,
    cmd_doc_drift,
    cmd_docs_for,
    cmd_files_for_change,
    cmd_hierarchy,
    cmd_impact,
    cmd_references,
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


def _build_drift_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node(
        "mod_app",
        label="app.py",
        file_type="code",
        symbol_kind="module",
        source_file="app/app.py",
        source_location="L1",
        qualified_name="app.app",
        summary="Application module.",
        community=1,
    )
    G.add_node(
        "main_fn",
        label="main()",
        file_type="code",
        symbol_kind="function",
        source_file="app/app.py",
        source_location="L3",
        qualified_name="app.app.main",
        container="app.app",
        summary="Main entrypoint.",
        community=1,
    )
    G.add_node(
        "mod_payments",
        label="payments.py",
        file_type="code",
        symbol_kind="module",
        source_file="app/payments.py",
        source_location="L1",
        qualified_name="app.payments",
        summary="Payment workflow module.",
        community=1,
    )
    G.add_node(
        "checkout_fn",
        label="checkout()",
        file_type="code",
        symbol_kind="function",
        source_file="app/payments.py",
        source_location="L8",
        qualified_name="app.payments.checkout",
        container="app.payments",
        summary="Runs checkout and payment orchestration.",
        community=1,
    )
    G.add_node(
        "gateway_fn",
        label="charge_card()",
        file_type="code",
        symbol_kind="function",
        source_file="app/gateway.py",
        source_location="L4",
        qualified_name="app.gateway.charge_card",
        container="app.gateway",
        summary="Charges the payment method.",
        community=1,
    )
    G.add_node(
        "doc_readme",
        label="README",
        file_type="document",
        source_file="README.md",
        source_location="L1",
        summary="Project overview.",
        doc_subtype="readme",
        community=1,
    )
    G.add_node(
        "doc_spec",
        label="Legacy Payment Spec",
        file_type="document",
        source_file="docs/payment-spec.md",
        source_location="L1",
        summary="Old payment module spec.",
        doc_subtype="spec",
        community=2,
    )
    G.add_node(
        "doc_runbook",
        label="Checkout Runbook",
        file_type="document",
        source_file="docs/checkout-runbook.md",
        source_location="L1",
        summary="Troubleshooting checkout incidents.",
        doc_subtype="runbook",
        community=2,
    )

    _add_edge(G, "mod_app", "main_fn", "contains")
    _add_edge(G, "mod_payments", "checkout_fn", "contains")
    _add_edge(G, "main_fn", "checkout_fn", "calls")
    _add_edge(G, "checkout_fn", "gateway_fn", "calls")
    _add_edge(G, "mod_app", "mod_payments", "imports")
    _add_edge(G, "doc_spec", "mod_payments", "references")
    _add_edge(G, "doc_readme", "mod_app", "references")
    _add_edge(G, "doc_runbook", "checkout_fn", "mentions")
    return G


def _build_ambiguous_symbol_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node(
        "payments_mod",
        label="payments.py",
        file_type="code",
        symbol_kind="module",
        source_file="app/payments.py",
        source_location="L1",
        qualified_name="app.payments",
        name="payments",
        summary="Payments module.",
        community=1,
    )
    G.add_node(
        "payments_checkout",
        label="checkout()",
        file_type="code",
        symbol_kind="function",
        source_file="app/payments.py",
        source_location="L10",
        qualified_name="app.payments.checkout",
        container="app.payments",
        name="checkout",
        summary="Checkout flow for payments.",
        community=1,
    )
    G.add_node(
        "orders_mod",
        label="orders.py",
        file_type="code",
        symbol_kind="module",
        source_file="app/orders.py",
        source_location="L1",
        qualified_name="app.orders",
        name="orders",
        summary="Orders module.",
        community=1,
    )
    G.add_node(
        "orders_checkout",
        label="checkout()",
        file_type="code",
        symbol_kind="function",
        source_file="app/orders.py",
        source_location="L12",
        qualified_name="app.orders.checkout",
        container="app.orders",
        name="checkout",
        summary="Checkout flow for orders.",
        community=1,
    )
    G.add_node(
        "api_fn",
        label="create_order()",
        file_type="code",
        symbol_kind="function",
        source_file="app/api.py",
        source_location="L8",
        qualified_name="app.api.create_order",
        container="app.api",
        name="create_order",
        summary="Creates orders through the API.",
        community=1,
    )
    G.add_node(
        "doc_checkout",
        label="Checkout Design",
        file_type="document",
        source_file="docs/checkout-design.md",
        source_location="L1",
        summary="Design notes for checkout.",
        community=2,
    )

    _add_edge(G, "payments_mod", "payments_checkout", "contains")
    _add_edge(G, "orders_mod", "orders_checkout", "contains")
    _add_edge(G, "api_fn", "orders_checkout", "calls")
    _add_edge(G, "doc_checkout", "orders_checkout", "references")
    return G


def _build_hierarchy_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node(
        "orders_mod",
        label="orders.py",
        file_type="code",
        symbol_kind="module",
        source_file="app/orders.py",
        source_location="L1",
        qualified_name="app.orders",
        name="orders",
        community=1,
    )
    G.add_node(
        "order_service",
        label="OrderService",
        file_type="code",
        symbol_kind="class",
        source_file="app/orders.py",
        source_location="L5",
        qualified_name="app.orders.OrderService",
        container="app.orders",
        name="OrderService",
        community=1,
    )
    G.add_node(
        "order_service_checkout",
        label=".checkout()",
        file_type="code",
        symbol_kind="method",
        source_file="app/orders.py",
        source_location="L12",
        qualified_name="app.orders.OrderService.checkout",
        container="app.orders.OrderService",
        name="checkout",
        community=1,
    )
    G.add_node(
        "order_service_validate",
        label=".validate()",
        file_type="code",
        symbol_kind="method",
        source_file="app/orders.py",
        source_location="L18",
        qualified_name="app.orders.OrderService.validate",
        container="app.orders.OrderService",
        name="validate",
        community=1,
    )

    _add_edge(G, "orders_mod", "order_service", "contains")
    _add_edge(G, "order_service", "order_service_checkout", "method")
    _add_edge(G, "order_service", "order_service_validate", "method")
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

    def test_definitions_prefers_code_symbols_over_docs(self) -> None:
        graph = _build_ambiguous_symbol_graph()

        result = cmd_definitions(graph, "checkout")

        self.assertIn("Definitions for 'checkout':", result)
        self.assertIn("app.orders.checkout", result)
        self.assertIn("app.payments.checkout", result)
        self.assertNotIn("Checkout Design", result)

    def test_references_require_disambiguation_for_duplicate_symbol_names(self) -> None:
        graph = _build_ambiguous_symbol_graph()

        result = cmd_references(graph, "checkout")

        self.assertIn("Ambiguous symbol 'checkout'. Matches:", result)
        self.assertIn("app.orders.checkout", result)
        self.assertIn("app.payments.checkout", result)
        self.assertIn("Use a qualified name or source path to disambiguate.", result)

    def test_references_accept_qualified_name_for_disambiguation(self) -> None:
        graph = _build_ambiguous_symbol_graph()

        result = cmd_references(graph, "app.orders.checkout")

        self.assertIn("References to checkout():", result)
        self.assertIn("create_order()", result)
        self.assertIn("docs/checkout-design.md", result)
        self.assertNotIn("Ambiguous symbol", result)

    def test_hierarchy_for_method_shows_ancestors_and_siblings(self) -> None:
        graph = _build_hierarchy_graph()

        result = cmd_hierarchy(graph, "app.orders.OrderService.checkout")

        self.assertIn("Hierarchy for .checkout():", result)
        self.assertIn("qname: app.orders.OrderService.checkout", result)
        self.assertIn("1. orders.py", result)
        self.assertIn("2. OrderService", result)
        self.assertIn("3. .checkout()", result)
        self.assertIn(".validate()", result)
        self.assertIn("via method", result)

    def test_hierarchy_for_module_shows_package_and_children(self) -> None:
        graph = _build_hierarchy_graph()

        result = cmd_hierarchy(graph, "app.orders")

        self.assertIn("Hierarchy for orders.py:", result)
        self.assertIn("package: app", result)
        self.assertIn("Children:", result)
        self.assertIn("OrderService", result)
        self.assertIn("via contains", result)

    def test_doc_drift_feature_surfaces_stale_missing_and_weak_links(self) -> None:
        graph = _build_drift_graph()

        result = cmd_doc_drift(graph, "checkout", mode="feature")

        self.assertIn("Doc drift for checkout() [feature]:", result)
        self.assertIn("Likely stale docs:", result)
        self.assertIn("docs/payment-spec.md", result)
        self.assertIn("Missing docs for important code:", result)
        self.assertIn("app/payments.py", result)
        self.assertIn("Weak doc-code links:", result)
        self.assertIn("README.md", result)
        self.assertIn("Suggested docs to review:", result)

    def test_doc_drift_type_filter_limits_to_requested_subtype(self) -> None:
        graph = _build_drift_graph()

        result = cmd_doc_drift(graph, "checkout", mode="bugfix", doc_type="runbook")

        self.assertIn("Doc drift for checkout() [bugfix] [type=runbook]:", result)
        self.assertNotIn("docs/payment-spec.md", result)
        self.assertIn("docs/checkout-runbook.md", result)

    def test_doc_drift_mode_changes_expectations(self) -> None:
        graph = _build_drift_graph()

        feature_result = cmd_doc_drift(graph, "checkout", mode="feature")
        bugfix_result = cmd_doc_drift(graph, "checkout", mode="bugfix")

        self.assertIn("missing preferred docs for feature work", feature_result)
        self.assertIn("expected: spec, design, api contract", feature_result)
        self.assertIn("missing preferred docs for bugfix work", bugfix_result)
        self.assertIn("expected: runbook, incident", bugfix_result)

    def test_verify_after_change_surfaces_doc_drift_watchlists(self) -> None:
        graph = _build_drift_graph()

        result = cmd_verify_after_change(graph, "feature checkout payment flow", mode="feature")

        self.assertIn("Likely stale docs after change:", result)
        self.assertIn("docs/payment-spec.md", result)
        self.assertIn("Missing docs to create/update:", result)
        self.assertIn("app/payments.py", result)
        self.assertIn("Weak doc coverage watchlist:", result)
        self.assertIn("README.md", result)

    def test_impact_surfaces_doc_drift_summary(self) -> None:
        graph = _build_drift_graph()

        result = cmd_impact(graph, "checkout")

        self.assertIn("doc drift: stale=", result)
        self.assertIn("likely stale docs:", result)
        self.assertIn("missing docs:", result)
        self.assertIn("docs/payment-spec.md", result)
        self.assertIn("app/app.py", result)


if __name__ == "__main__":
    unittest.main()
