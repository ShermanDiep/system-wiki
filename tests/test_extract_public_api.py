from __future__ import annotations

import unittest

from system_wiki.extract_public_api import _enrich_symbol_metadata


class ExtractPublicApiSummaryTests(unittest.TestCase):
    def test_enrich_symbol_metadata_builds_structural_summaries(self) -> None:
        nodes = [
            {
                "id": "orders_mod",
                "label": "orders.py",
                "file_type": "code",
                "source_file": "app/orders.py",
                "source_location": "L1",
            },
            {
                "id": "service_cls",
                "label": "OrderService",
                "file_type": "code",
                "source_file": "app/orders.py",
                "source_location": "L5",
            },
            {
                "id": "checkout_method",
                "label": ".checkout()",
                "file_type": "code",
                "source_file": "app/orders.py",
                "source_location": "L12",
                "signature": "checkout(order_id)",
            },
            {
                "id": "validate_method",
                "label": ".validate()",
                "file_type": "code",
                "source_file": "app/orders.py",
                "source_location": "L18",
            },
            {
                "id": "helper_fn",
                "label": "build_payload()",
                "file_type": "code",
                "source_file": "app/orders.py",
                "source_location": "L25",
            },
            {
                "id": "controller_fn",
                "label": "create_order()",
                "file_type": "code",
                "source_file": "app/controller.py",
                "source_location": "L8",
            },
            {
                "id": "payments_mod",
                "label": "payments.py",
                "file_type": "code",
                "source_file": "app/payments.py",
                "source_location": "L1",
            },
        ]
        edges = [
            {"source": "orders_mod", "target": "service_cls", "relation": "contains"},
            {"source": "orders_mod", "target": "helper_fn", "relation": "contains"},
            {"source": "service_cls", "target": "checkout_method", "relation": "method"},
            {"source": "service_cls", "target": "validate_method", "relation": "method"},
            {"source": "checkout_method", "target": "helper_fn", "relation": "calls"},
            {"source": "controller_fn", "target": "checkout_method", "relation": "calls"},
            {"source": "orders_mod", "target": "payments_mod", "relation": "imports"},
        ]

        _enrich_symbol_metadata(nodes, edges)
        by_id = {node["id"]: node for node in nodes}

        self.assertEqual(by_id["orders_mod"]["qualified_name"], "app.orders")
        self.assertIn("Module with 2 top-level symbols", by_id["orders_mod"]["summary"])
        self.assertIn("Depends on payments", by_id["orders_mod"]["summary"])

        self.assertEqual(by_id["service_cls"]["container"], "app.orders")
        self.assertIn("Class in app.orders.", by_id["service_cls"]["summary"])
        self.assertIn("Methods: checkout, validate.", by_id["service_cls"]["summary"])

        self.assertEqual(by_id["checkout_method"]["qualified_name"], "app.orders.OrderService.checkout")
        self.assertIn("Method in app.orders.OrderService.", by_id["checkout_method"]["summary"])
        self.assertIn("Signature: checkout(order_id).", by_id["checkout_method"]["summary"])
        self.assertIn("Calls build_payload.", by_id["checkout_method"]["summary"])
        self.assertIn("Called by create_order.", by_id["checkout_method"]["summary"])

    def test_enrich_symbol_metadata_adds_typed_semantic_edges(self) -> None:
        nodes = [
            {
                "id": "service_mod",
                "label": "service.py",
                "file_type": "code",
                "source_file": "app/service.py",
                "source_location": "L1",
            },
            {
                "id": "validate_fn",
                "label": "validate_request()",
                "file_type": "code",
                "source_file": "app/service.py",
                "source_location": "L5",
            },
            {
                "id": "store_fn",
                "label": "store_order()",
                "file_type": "code",
                "source_file": "app/service.py",
                "source_location": "L12",
            },
            {
                "id": "persist_fn",
                "label": "persist_order()",
                "file_type": "code",
                "source_file": "app/service.py",
                "source_location": "L18",
            },
            {
                "id": "dispatch_fn",
                "label": "dispatch_order()",
                "file_type": "code",
                "source_file": "app/service.py",
                "source_location": "L24",
            },
        ]
        edges = [
            {"source": "service_mod", "target": "validate_fn", "relation": "contains"},
            {"source": "service_mod", "target": "store_fn", "relation": "contains"},
            {"source": "service_mod", "target": "persist_fn", "relation": "contains"},
            {"source": "service_mod", "target": "dispatch_fn", "relation": "contains"},
            {"source": "dispatch_fn", "target": "validate_fn", "relation": "calls"},
            {"source": "dispatch_fn", "target": "persist_fn", "relation": "calls"},
            {"source": "store_fn", "target": "persist_fn", "relation": "calls"},
        ]

        _enrich_symbol_metadata(nodes, edges)
        by_id = {node["id"]: node for node in nodes}
        typed_relations = {(edge["source"], edge["target"], edge["relation"]) for edge in edges}

        self.assertIn("validates", by_id["validate_fn"]["semantic_roles"])
        self.assertIn("persists", by_id["store_fn"]["semantic_roles"])
        self.assertIn("orchestrates", by_id["dispatch_fn"]["semantic_roles"])

        self.assertIn(("store_fn", "persist_fn", "persists"), typed_relations)
        self.assertIn(("dispatch_fn", "validate_fn", "orchestrates"), typed_relations)
        self.assertIn(("dispatch_fn", "persist_fn", "orchestrates"), typed_relations)

        self.assertIn("Semantic roles: validates.", by_id["validate_fn"]["summary"])
        self.assertIn("Semantic roles: persists.", by_id["store_fn"]["summary"])
        self.assertIn("Semantic roles: orchestrates.", by_id["dispatch_fn"]["summary"])


if __name__ == "__main__":
    unittest.main()
