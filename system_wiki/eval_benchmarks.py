"""Repeatable benchmark runner for retrieval/context quality."""
from __future__ import annotations

import json
import math
from pathlib import Path

import networkx as nx

from system_wiki.query_graph import (
    _build_context_bundle,
    _doc_drift_plan,
    _doc_rows_for_target,
    _files_for_change_plan,
    _load_graph,
    _select_node_match,
    _untested_impact_file_rows,
    _verify_after_change_plan,
    cmd_context_for,
    cmd_doc_drift,
    cmd_docs_for,
    cmd_files_for_change,
    cmd_untested_impact,
    cmd_verify_after_change,
)


def _approx_tokens(text: str) -> int:
    """Cheap token proxy for local evals when no model tokenizer is involved."""
    return max(1, math.ceil(len(text) / 4))


def _score_expected(actual: list[str], expected: list[str]) -> dict[str, float | int | list[str]]:
    actual_unique = []
    for item in actual:
        if item and item not in actual_unique:
            actual_unique.append(item)

    expected_unique = []
    for item in expected:
        if item and item not in expected_unique:
            expected_unique.append(item)

    hits = [item for item in expected_unique if item in actual_unique]
    recall = len(hits) / len(expected_unique) if expected_unique else 1.0
    precision = len(hits) / len(actual_unique) if actual_unique else (1.0 if not expected_unique else 0.0)
    return {
        "hits": len(hits),
        "expected": len(expected_unique),
        "actual": len(actual_unique),
        "recall": round(recall, 3),
        "precision": round(precision, 3),
        "matched": hits,
        "missed": [item for item in expected_unique if item not in hits],
    }


def _assertions_for_case(case: dict, result: dict) -> dict:
    assertions = case.get("assertions", {})
    failures: list[str] = []

    min_case_recall = assertions.get("min_case_recall")
    if min_case_recall is not None and result["case_recall"] < float(min_case_recall):
        failures.append(
            f"case_recall {result['case_recall']} < min_case_recall {float(min_case_recall):.3f}"
        )

    min_case_precision = assertions.get("min_case_precision")
    if min_case_precision is not None and result["case_precision"] < float(min_case_precision):
        failures.append(
            f"case_precision {result['case_precision']} < min_case_precision {float(min_case_precision):.3f}"
        )

    max_files_opened = assertions.get("max_files_opened")
    if max_files_opened is not None and result["files_opened"] > int(max_files_opened):
        failures.append(
            f"files_opened {result['files_opened']} > max_files_opened {int(max_files_opened)}"
        )

    max_approx_tokens = assertions.get("max_approx_tokens")
    if max_approx_tokens is not None and result["approx_tokens"] > int(max_approx_tokens):
        failures.append(
            f"approx_tokens {result['approx_tokens']} > max_approx_tokens {int(max_approx_tokens)}"
        )

    return {"passed": not failures, "failures": failures}


def _assertions_for_summary(summary: dict, suite: dict) -> dict:
    assertions = suite.get("assertions", {})
    failures: list[str] = []

    min_avg_context_recall = assertions.get("min_avg_context_recall")
    if min_avg_context_recall is not None and summary["avg_context_recall"] < float(min_avg_context_recall):
        failures.append(
            f"avg_context_recall {summary['avg_context_recall']} < min_avg_context_recall {float(min_avg_context_recall):.3f}"
        )

    min_avg_context_precision = assertions.get("min_avg_context_precision")
    if (
        min_avg_context_precision is not None
        and summary["avg_context_precision"] < float(min_avg_context_precision)
    ):
        failures.append(
            f"avg_context_precision {summary['avg_context_precision']} < min_avg_context_precision {float(min_avg_context_precision):.3f}"
        )

    max_avg_files_opened = assertions.get("max_avg_files_opened")
    if max_avg_files_opened is not None and summary["avg_files_opened"] > float(max_avg_files_opened):
        failures.append(
            f"avg_files_opened {summary['avg_files_opened']} > max_avg_files_opened {float(max_avg_files_opened):.3f}"
        )

    max_avg_approx_tokens = assertions.get("max_avg_approx_tokens")
    if max_avg_approx_tokens is not None and summary["avg_approx_tokens"] > float(max_avg_approx_tokens):
        failures.append(
            f"avg_approx_tokens {summary['avg_approx_tokens']} > max_avg_approx_tokens {float(max_avg_approx_tokens):.3f}"
        )

    return {"passed": not failures, "failures": failures}


def _context_case_result(G: nx.Graph, case: dict) -> dict:
    task = case.get("task", "")
    mode = case.get("mode")
    depth = int(case.get("max_depth", 3))
    bundle = _build_context_bundle(G, task, mode=mode, max_depth=depth)
    rendered = cmd_context_for(G, task, mode=mode, max_depth=depth)
    actual = {
        "focus_sources": [G.nodes[nid].get("source_file", "") for nid, _, _ in bundle["focus_symbols"]],
        "doc_sources": [G.nodes[nid].get("source_file", "") for nid, _, _ in bundle["docs"]],
        "test_sources": [G.nodes[nid].get("source_file", "") for nid, _, _ in bundle["tests"]],
        "file_sources": [source for source, _, _, _ in bundle["files"]],
    }
    return {
        "command": "context-for",
        "rendered": rendered,
        "approx_tokens": _approx_tokens(rendered),
        "files_opened": len(set(actual["file_sources"])),
        "actual": actual,
    }


def _docs_case_result(G: nx.Graph, case: dict) -> dict:
    label = case.get("label", "")
    mode = case.get("mode")
    doc_type = case.get("doc_type")
    nid = _select_node_match(G, label)
    rendered = cmd_docs_for(G, label, mode=mode, doc_type=doc_type)
    rows = _doc_rows_for_target(G, nid, mode=mode, doc_type=doc_type) if nid else []
    actual = {
        "doc_sources": [G.nodes[doc_nid].get("source_file", "") for doc_nid, _, _ in rows],
    }
    return {
        "command": "docs-for",
        "rendered": rendered,
        "approx_tokens": _approx_tokens(rendered),
        "files_opened": len(set(actual["doc_sources"])),
        "actual": actual,
    }


def _doc_drift_case_result(G: nx.Graph, case: dict) -> dict:
    label = case.get("label", "")
    mode = case.get("mode")
    doc_type = case.get("doc_type")
    depth = int(case.get("max_depth", 3))
    plan = _doc_drift_plan(G, label, mode=mode, max_depth=depth, doc_type=doc_type)
    rendered = cmd_doc_drift(G, label, mode=mode, max_depth=depth, doc_type=doc_type)
    actual = {
        "stale_doc_sources": [source for source, _, _, _ in (plan["stale_docs"] if plan else [])],
        "missing_doc_sources": [source for source, _, _, _ in (plan["missing_docs"] if plan else [])],
        "weak_link_doc_sources": [source for source, _, _, _ in (plan["weak_links"] if plan else [])],
        "review_doc_sources": [source for source, _, _, _ in (plan["review_docs"] if plan else [])],
    }
    all_sources = (
        actual["stale_doc_sources"]
        + actual["missing_doc_sources"]
        + actual["weak_link_doc_sources"]
        + actual["review_doc_sources"]
    )
    return {
        "command": "doc-drift",
        "rendered": rendered,
        "approx_tokens": _approx_tokens(rendered),
        "files_opened": len(set(all_sources)),
        "impact_risk": plan["risk"] if plan else None,
        "actual": actual,
    }


def _files_case_result(G: nx.Graph, case: dict) -> dict:
    task = case.get("task", "")
    mode = case.get("mode")
    depth = int(case.get("max_depth", 3))
    plan = _files_for_change_plan(G, task, mode=mode, max_depth=depth)
    rendered = cmd_files_for_change(G, task, mode=mode, max_depth=depth)
    actual = {
        "edit_sources": [source for source, _, _, _ in plan["edit_files"]],
        "verify_sources": [source for source, _, _, _ in plan["verify_files"]],
        "watch_sources": [source for source, _, _, _ in plan["watch_files"]],
        "test_sources": [source for source, _, _, _ in plan["test_files"]],
        "doc_sources": [source for source, _, _, _ in plan["doc_files"]],
    }
    all_sources = (
        actual["edit_sources"]
        + actual["verify_sources"]
        + actual["watch_sources"]
        + actual["test_sources"]
        + actual["doc_sources"]
    )
    return {
        "command": "files-for-change",
        "rendered": rendered,
        "approx_tokens": _approx_tokens(rendered),
        "files_opened": len(set(all_sources)),
        "impact_risk": plan["impact_risk"],
        "actual": actual,
    }


def _untested_impact_case_result(G: nx.Graph, case: dict) -> dict:
    label = case.get("label", "")
    depth = int(case.get("max_depth", 3))
    nid = _select_node_match(G, label)
    rendered = cmd_untested_impact(G, label, max_depth=depth)
    rows = _untested_impact_file_rows(G, nid, max_depth=depth) if nid else []
    actual = {
        "untested_sources": [source for source, _, _, _ in rows],
    }
    return {
        "command": "untested-impact",
        "rendered": rendered,
        "approx_tokens": _approx_tokens(rendered),
        "files_opened": len(set(actual["untested_sources"])),
        "actual": actual,
    }


def _verify_after_change_case_result(G: nx.Graph, case: dict) -> dict:
    task = case.get("task", "")
    mode = case.get("mode")
    depth = int(case.get("max_depth", 3))
    plan = _verify_after_change_plan(G, task, mode=mode, max_depth=depth)
    rendered = cmd_verify_after_change(G, task, mode=mode, max_depth=depth)
    actual = {
        "verify_sources": [source for source, _, _, _ in plan["plan"]["verify_files"]],
        "smoke_sources": [G.nodes[nid].get("source_file", "") for nid, _ in plan["smoke_paths"]],
        "test_sources": [source for source, _, _, _ in plan["plan"]["test_files"]],
        "doc_sources": [source for source, _, _, _ in plan["plan"]["doc_files"]],
        "watch_sources": [source for source, _, _, _ in plan["untested_watch"]],
    }
    all_sources = (
        actual["verify_sources"]
        + actual["smoke_sources"]
        + actual["test_sources"]
        + actual["doc_sources"]
        + actual["watch_sources"]
    )
    return {
        "command": "verify-after-change",
        "rendered": rendered,
        "approx_tokens": _approx_tokens(rendered),
        "files_opened": len(set(source for source in all_sources if source)),
        "impact_risk": plan["plan"]["impact_risk"],
        "actual": actual,
    }


def evaluate_suite(G: nx.Graph, suite: dict) -> dict:
    cases_out = []
    recall_values: list[float] = []
    precision_values: list[float] = []
    approx_tokens: list[int] = []
    files_opened: list[int] = []

    for case in suite.get("cases", []):
        command = case.get("command")
        if command == "context-for":
            result = _context_case_result(G, case)
        elif command == "docs-for":
            result = _docs_case_result(G, case)
        elif command == "doc-drift":
            result = _doc_drift_case_result(G, case)
        elif command == "files-for-change":
            result = _files_case_result(G, case)
        elif command == "untested-impact":
            result = _untested_impact_case_result(G, case)
        elif command == "verify-after-change":
            result = _verify_after_change_case_result(G, case)
        else:
            cases_out.append({
                "name": case.get("name", "unnamed"),
                "command": command or "",
                "error": f"Unsupported command '{command}'.",
            })
            continue

        expected = case.get("expected", {})
        metrics = {}
        local_recalls: list[float] = []
        local_precisions: list[float] = []
        for key, expected_values in expected.items():
            actual_values = result["actual"].get(key, [])
            metric = _score_expected(actual_values, expected_values)
            metrics[key] = metric
            local_recalls.append(float(metric["recall"]))
            local_precisions.append(float(metric["precision"]))

        case_recall = sum(local_recalls) / len(local_recalls) if local_recalls else 1.0
        case_precision = sum(local_precisions) / len(local_precisions) if local_precisions else 1.0
        recall_values.append(case_recall)
        precision_values.append(case_precision)
        approx_tokens.append(int(result["approx_tokens"]))
        files_opened.append(int(result["files_opened"]))

        cases_out.append({
            "name": case.get("name", "unnamed"),
            "command": result["command"],
            "metrics": metrics,
            "case_recall": round(case_recall, 3),
            "case_precision": round(case_precision, 3),
            "approx_tokens": result["approx_tokens"],
            "files_opened": result["files_opened"],
            "impact_risk": result.get("impact_risk"),
            "rendered": result["rendered"],
        })
        cases_out[-1]["assertions"] = _assertions_for_case(case, cases_out[-1])

    summary = {
        "suite": suite.get("name", "unnamed-suite"),
        "case_count": len(cases_out),
        "avg_context_recall": round(sum(recall_values) / len(recall_values), 3) if recall_values else 0.0,
        "avg_context_precision": round(sum(precision_values) / len(precision_values), 3) if precision_values else 0.0,
        "avg_files_opened": round(sum(files_opened) / len(files_opened), 2) if files_opened else 0.0,
        "avg_approx_tokens": round(sum(approx_tokens) / len(approx_tokens), 1) if approx_tokens else 0.0,
    }
    summary_assertions = _assertions_for_summary(summary, suite)
    failures = []
    if not summary_assertions["passed"]:
        failures.extend(summary_assertions["failures"])
    for case in cases_out:
        if not case.get("assertions", {}).get("passed", True):
            failures.extend(f"{case['name']}: {failure}" for failure in case["assertions"]["failures"])
    return {
        "summary": summary,
        "summary_assertions": summary_assertions,
        "cases": cases_out,
        "passed": not failures,
        "failures": failures,
    }


def load_suite(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _comparison_tolerances(suite: dict | None = None, baseline: dict | None = None) -> dict[str, float]:
    tolerances = {
        "context_recall_drop": 0.01,
        "context_precision_drop": 0.05,
        "files_opened_increase": 1.0,
        "approx_tokens_increase": 50.0,
    }
    for source in (baseline or {}, suite or {}):
        for key, value in source.get("comparison_tolerances", {}).items():
            tolerances[key] = float(value)
    return tolerances


def make_baseline_snapshot(report: dict, suite: dict | None = None) -> dict:
    return {
        "suite": report["summary"]["suite"],
        "summary": report["summary"],
        "comparison_tolerances": _comparison_tolerances(suite=suite),
        "cases": [
            {
                "name": case["name"],
                "command": case["command"],
                "case_recall": case["case_recall"],
                "case_precision": case["case_precision"],
                "files_opened": case["files_opened"],
                "approx_tokens": case["approx_tokens"],
            }
            for case in report["cases"]
            if not case.get("error")
        ],
    }


def _summary_delta(report: dict, baseline: dict) -> dict[str, float]:
    summary = report.get("summary", {})
    baseline_summary = baseline.get("summary", {})
    return {
        "avg_context_recall": round(summary.get("avg_context_recall", 0.0) - baseline_summary.get("avg_context_recall", 0.0), 3),
        "avg_context_precision": round(summary.get("avg_context_precision", 0.0) - baseline_summary.get("avg_context_precision", 0.0), 3),
        "avg_files_opened": round(summary.get("avg_files_opened", 0.0) - baseline_summary.get("avg_files_opened", 0.0), 3),
        "avg_approx_tokens": round(summary.get("avg_approx_tokens", 0.0) - baseline_summary.get("avg_approx_tokens", 0.0), 3),
    }


def _case_delta(case: dict, baseline_case: dict) -> dict[str, float]:
    return {
        "case_recall": round(case.get("case_recall", 0.0) - baseline_case.get("case_recall", 0.0), 3),
        "case_precision": round(case.get("case_precision", 0.0) - baseline_case.get("case_precision", 0.0), 3),
        "files_opened": round(case.get("files_opened", 0.0) - baseline_case.get("files_opened", 0.0), 3),
        "approx_tokens": round(case.get("approx_tokens", 0.0) - baseline_case.get("approx_tokens", 0.0), 3),
    }


def compare_to_baseline(report: dict, baseline: dict, suite: dict | None = None) -> dict:
    tolerances = _comparison_tolerances(suite=suite, baseline=baseline)
    failures: list[str] = []
    summary = report["summary"]
    baseline_summary = baseline.get("summary", {})
    summary_delta = _summary_delta(report, baseline)

    if summary["avg_context_recall"] < baseline_summary.get("avg_context_recall", 0.0) - tolerances["context_recall_drop"]:
        failures.append(
            f"avg_context_recall {summary['avg_context_recall']} regressed from "
            f"{baseline_summary.get('avg_context_recall')} beyond tolerance {tolerances['context_recall_drop']}"
        )
    if summary["avg_context_precision"] < baseline_summary.get("avg_context_precision", 0.0) - tolerances["context_precision_drop"]:
        failures.append(
            f"avg_context_precision {summary['avg_context_precision']} regressed from "
            f"{baseline_summary.get('avg_context_precision')} beyond tolerance {tolerances['context_precision_drop']}"
        )
    if summary["avg_files_opened"] > baseline_summary.get("avg_files_opened", 0.0) + tolerances["files_opened_increase"]:
        failures.append(
            f"avg_files_opened {summary['avg_files_opened']} exceeded baseline "
            f"{baseline_summary.get('avg_files_opened')} + tolerance {tolerances['files_opened_increase']}"
        )
    if summary["avg_approx_tokens"] > baseline_summary.get("avg_approx_tokens", 0.0) + tolerances["approx_tokens_increase"]:
        failures.append(
            f"avg_approx_tokens {summary['avg_approx_tokens']} exceeded baseline "
            f"{baseline_summary.get('avg_approx_tokens')} + tolerance {tolerances['approx_tokens_increase']}"
        )

    baseline_cases = {
        (case["name"], case["command"]): case
        for case in baseline.get("cases", [])
    }
    case_deltas = []
    for case in report["cases"]:
        if case.get("error"):
            continue
        key = (case["name"], case["command"])
        base_case = baseline_cases.get(key)
        if base_case is None:
            continue
        delta = _case_delta(case, base_case)
        case_deltas.append({
            "name": case["name"],
            "command": case["command"],
            "delta": delta,
        })
        if case["case_recall"] < base_case.get("case_recall", 0.0) - tolerances["context_recall_drop"]:
            failures.append(
                f"{case['name']}: case_recall {case['case_recall']} regressed from "
                f"{base_case.get('case_recall')} beyond tolerance {tolerances['context_recall_drop']}"
            )
        if case["case_precision"] < base_case.get("case_precision", 0.0) - tolerances["context_precision_drop"]:
            failures.append(
                f"{case['name']}: case_precision {case['case_precision']} regressed from "
                f"{base_case.get('case_precision')} beyond tolerance {tolerances['context_precision_drop']}"
            )
        if case["files_opened"] > base_case.get("files_opened", 0.0) + tolerances["files_opened_increase"]:
            failures.append(
                f"{case['name']}: files_opened {case['files_opened']} exceeded baseline "
                f"{base_case.get('files_opened')} + tolerance {tolerances['files_opened_increase']}"
            )
        if case["approx_tokens"] > base_case.get("approx_tokens", 0.0) + tolerances["approx_tokens_increase"]:
            failures.append(
                f"{case['name']}: approx_tokens {case['approx_tokens']} exceeded baseline "
                f"{base_case.get('approx_tokens')} + tolerance {tolerances['approx_tokens_increase']}"
            )

    return {
        "passed": not failures,
        "failures": failures,
        "tolerances": tolerances,
        "summary_delta": summary_delta,
        "cases": case_deltas,
    }


def _is_better_or_equal(report: dict, baseline: dict) -> bool:
    delta = _summary_delta(report, baseline)
    no_worse = (
        delta["avg_context_recall"] >= 0
        and delta["avg_context_precision"] >= 0
        and delta["avg_files_opened"] <= 0
        and delta["avg_approx_tokens"] <= 0
    )
    strictly_better = any(
        (
            delta["avg_context_recall"] > 0,
            delta["avg_context_precision"] > 0,
            delta["avg_files_opened"] < 0,
            delta["avg_approx_tokens"] < 0,
        )
    )
    return no_worse and strictly_better


def write_baseline(path: str, snapshot: dict) -> None:
    Path(path).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def load_baseline(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def format_report(report: dict) -> str:
    summary = report["summary"]
    lines = [
        f"Eval suite: {summary['suite']}",
        f"  status: {'PASS' if report.get('passed') else 'FAIL'}",
        f"  cases: {summary['case_count']}",
        f"  avg context recall: {summary['avg_context_recall']}",
        f"  avg context precision: {summary['avg_context_precision']}",
        f"  avg files opened: {summary['avg_files_opened']}",
        f"  avg approx tokens: {summary['avg_approx_tokens']}",
    ]
    if not report.get("summary_assertions", {}).get("passed", True):
        for failure in report["summary_assertions"]["failures"]:
            lines.append(f"  summary assertion failed: {failure}")
    comparison = report.get("baseline_comparison")
    if comparison:
        lines.append(
            f"  baseline compare: {'PASS' if comparison.get('passed') else 'FAIL'}"
        )
        summary_delta = comparison.get("summary_delta", {})
        if summary_delta:
            lines.append(
                "  baseline delta: "
                f"recall={summary_delta.get('avg_context_recall', 0.0):+} "
                f"precision={summary_delta.get('avg_context_precision', 0.0):+} "
                f"files={summary_delta.get('avg_files_opened', 0.0):+} "
                f"tokens={summary_delta.get('avg_approx_tokens', 0.0):+}"
            )
        if not comparison.get("passed", True):
            for failure in comparison["failures"]:
                lines.append(f"  baseline regression: {failure}")
        for case_delta in comparison.get("cases", []):
            delta = case_delta["delta"]
            lines.append(
                f"  case delta {case_delta['name']}: "
                f"recall={delta['case_recall']:+} precision={delta['case_precision']:+} "
                f"files={delta['files_opened']:+} tokens={delta['approx_tokens']:+}"
            )
    baseline_update = report.get("baseline_update")
    if baseline_update:
        lines.append(f"  baseline update: {baseline_update}")
    for case in report["cases"]:
        if case.get("error"):
            lines.append(f"- {case['name']} [{case['command']}]: ERROR {case['error']}")
            continue
        lines.append(
            f"- {case['name']} [{case['command']}] "
            f"recall={case['case_recall']} precision={case['case_precision']} "
            f"files={case['files_opened']} approx_tokens={case['approx_tokens']}"
        )
        if not case.get("assertions", {}).get("passed", True):
            for failure in case["assertions"]["failures"]:
                lines.append(f"    assertion failed: {failure}")
        for key, metric in case["metrics"].items():
            lines.append(
                f"    {key}: recall={metric['recall']} precision={metric['precision']} "
                f"matched={metric['matched']}"
            )
            if metric["missed"]:
                lines.append(f"    {key} missed: {metric['missed']}")
    return "\n".join(lines)


def eval_main(args: list[str], graph_path: str = "wiki-out/graph.json") -> int:
    suite_path = "docs/evals/context-engine-starter.json"
    json_mode = False
    write_baseline_path: str | None = None
    compare_baseline_path: str | None = None
    update_baseline_if_better_path: str | None = None
    remaining = list(args)

    while remaining:
        tok = remaining.pop(0)
        if tok == "--graph" and remaining:
            graph_path = remaining.pop(0)
        elif tok == "--write-baseline" and remaining:
            write_baseline_path = remaining.pop(0)
        elif tok == "--compare-baseline" and remaining:
            compare_baseline_path = remaining.pop(0)
        elif tok == "--update-baseline-if-better" and remaining:
            update_baseline_if_better_path = remaining.pop(0)
        elif tok == "--json":
            json_mode = True
        elif tok.startswith("--"):
            print(f"Unknown option '{tok}'.")
            return 1
        else:
            suite_path = tok

    if not Path(graph_path).exists():
        print(f"[wiki] Graph not found: {graph_path}")
        print("[wiki] Run `system-wiki .` first to build the graph.")
        return 1
    if not Path(suite_path).exists():
        print(f"[wiki] Eval suite not found: {suite_path}")
        return 1

    G = _load_graph(graph_path)
    suite = load_suite(suite_path)
    report = evaluate_suite(G, suite)
    if compare_baseline_path:
        if not Path(compare_baseline_path).exists():
            print(f"[wiki] Baseline not found: {compare_baseline_path}")
            return 1
        baseline = load_baseline(compare_baseline_path)
        report["baseline_comparison"] = compare_to_baseline(report, baseline, suite=suite)
        if report["baseline_comparison"]["passed"] is False:
            report["passed"] = False
            report["failures"].extend(report["baseline_comparison"]["failures"])
    if write_baseline_path:
        snapshot = make_baseline_snapshot(report, suite=suite)
        write_baseline(write_baseline_path, snapshot)
    if update_baseline_if_better_path:
        snapshot = make_baseline_snapshot(report, suite=suite)
        baseline_path = Path(update_baseline_if_better_path)
        if not baseline_path.exists():
            if report.get("passed", True):
                write_baseline(str(baseline_path), snapshot)
                report["baseline_update"] = f"created {baseline_path}"
            else:
                report["baseline_update"] = f"skipped baseline create for failing report ({baseline_path})"
        else:
            baseline = load_baseline(str(baseline_path))
            if report.get("passed", True) and _is_better_or_equal(report, baseline):
                write_baseline(str(baseline_path), snapshot)
                report["baseline_update"] = f"updated {baseline_path}"
            else:
                report["baseline_update"] = f"kept existing baseline at {baseline_path}"
    if json_mode:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 0 if report.get("passed", True) else 1
