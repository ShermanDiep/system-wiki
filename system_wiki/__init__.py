"""system-wiki — turn any folder into a queryable knowledge graph.

Pipeline: detect → extract → build → cluster → analyze → report → export

Usage:
    from system_wiki import detect, extract, build, cluster, analyze, generate, to_html, to_vault
"""
from __future__ import annotations
import importlib


def __getattr__(name: str):
    """Lazy imports — all heavy deps load only when accessed."""
    _map = {
        # detection
        "detect": ("system_wiki.detect_files", "detect"),
        "classify_file": ("system_wiki.detect_files", "classify_file"),
        "detect_incremental": ("system_wiki.detect_office_convert", "detect_incremental"),
        # extraction
        "extract": ("system_wiki.extract_public_api", "extract"),
        "collect_files": ("system_wiki.extract_public_api", "collect_files"),
        # graph build
        "build_from_json": ("system_wiki.build_graph", "build_from_json"),
        "build": ("system_wiki.build_graph", "build"),
        # clustering
        "cluster": ("system_wiki.cluster_communities", "cluster"),
        "score_all": ("system_wiki.cluster_communities", "score_all"),
        "cohesion_score": ("system_wiki.cluster_communities", "cohesion_score"),
        "label_communities": ("system_wiki.cluster_label_communities", "label_communities"),
        # analysis
        "god_nodes": ("system_wiki.analyze_graph", "god_nodes"),
        "surprising_connections": ("system_wiki.analyze_graph", "surprising_connections"),
        "suggest_questions": ("system_wiki.analyze_questions", "suggest_questions"),
        # report
        "generate": ("system_wiki.report_markdown", "generate"),
        # exports
        "to_json": ("system_wiki.export_json", "to_json"),
        "to_html": ("system_wiki.export_html", "to_html"),
        "to_wiki": ("system_wiki.export_wiki", "to_wiki"),
        "to_vault": ("system_wiki.export_vault", "to_vault"),
        # doc extraction
        "extract_docs": ("system_wiki.extract_docs", "extract_docs"),
        # cross-reference
        "cross_reference": ("system_wiki.extract_cross_reference", "cross_reference"),
        # url ingest
        "ingest": ("system_wiki.ingest_url", "ingest"),
        # note write-back
        "write_note": ("system_wiki.note_writer", "write_note"),
        # file watcher
        "watch": ("system_wiki.watch_folder", "watch"),
        # schema
        "load_schema": ("system_wiki.schema_rules", "load_schema"),
        "validate_graph": ("system_wiki.schema_rules", "validate_graph"),
        # query
        "query_main": ("system_wiki.query_graph", "query_main"),
    }
    if name in _map:
        mod_name, attr = _map[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise AttributeError(f"module 'system_wiki' has no attribute {name!r}")
