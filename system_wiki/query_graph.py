# CLI query interface for wiki-out/graph.json.
# Supports navigation, dependency, explanation, and lightweight impact queries.
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

_analyze = importlib.import_module("system_wiki.analyze_graph")
_god_nodes = _analyze.god_nodes
_module_graph = importlib.import_module("system_wiki.module_graph")

build_module_graph = _module_graph.build_module_graph
module_hotspots = _module_graph.module_hotspots
module_bridges = _module_graph.module_bridges
module_stats = _module_graph.module_stats
module_source_map = _module_graph.module_source_map

_TASK_STOPWORDS = {
    "a", "an", "and", "are", "around", "at", "by", "for", "from", "how", "in", "into",
    "investigate", "is", "it", "of", "on", "or", "the", "this", "to", "understand", "with",
}

_CONTEXT_MODE_KEYWORDS = {
    "bugfix": {"bug", "fix", "broken", "fail", "failing", "failure", "crash", "error", "issue", "regression"},
    "feature": {"feature", "add", "support", "enable", "implement", "introduce", "build", "new"},
    "refactor": {"refactor", "cleanup", "rename", "restructure", "extract", "simplify", "dedupe", "untangle"},
    "onboarding": {"explain", "architecture", "overview", "learn", "understand", "tour", "map", "context"},
}

_CONTEXT_MODE_WEIGHTS: dict[str, dict[str, float]] = {
    "bugfix": {
        "seed": 1.0,
        "container": 2.0,
        "module": 2.0,
        "caller": 5.0,
        "importer": 4.0,
        "callee": 2.5,
        "dependency": 2.0,
        "doc": 2.0,
        "test": 5.0,
        "entrypoint": 2.0,
        "module_neighbor": 2.0,
        "community": 0.5,
    },
    "feature": {
        "seed": 1.0,
        "container": 1.5,
        "module": 2.5,
        "caller": 2.0,
        "importer": 2.0,
        "callee": 3.0,
        "dependency": 3.0,
        "doc": 3.0,
        "test": 2.0,
        "entrypoint": 4.0,
        "module_neighbor": 3.0,
        "community": 1.0,
    },
    "refactor": {
        "seed": 1.0,
        "container": 2.5,
        "module": 3.0,
        "caller": 4.5,
        "importer": 4.0,
        "callee": 1.5,
        "dependency": 1.5,
        "doc": 1.5,
        "test": 2.5,
        "entrypoint": 1.5,
        "module_neighbor": 3.0,
        "community": 1.5,
    },
    "onboarding": {
        "seed": 1.0,
        "container": 1.5,
        "module": 3.0,
        "caller": 1.5,
        "importer": 1.5,
        "callee": 1.5,
        "dependency": 1.5,
        "doc": 4.0,
        "test": 1.0,
        "entrypoint": 2.5,
        "module_neighbor": 2.5,
        "community": 2.0,
    },
}

_DOC_SUBTYPE_MODE_WEIGHTS: dict[str, dict[str, float]] = {
    "bugfix": {
        "runbook": 4.0,
        "incident": 3.5,
        "api_contract": 2.5,
        "readme": 1.5,
        "spec": 1.0,
        "design": 0.5,
        "domain": 0.5,
        "adr": 0.5,
        "general": 1.0,
    },
    "feature": {
        "spec": 4.0,
        "design": 3.5,
        "api_contract": 3.0,
        "adr": 2.5,
        "domain": 1.5,
        "readme": 1.0,
        "runbook": 0.5,
        "incident": 0.25,
        "general": 1.0,
    },
    "refactor": {
        "design": 4.0,
        "adr": 3.5,
        "spec": 2.0,
        "domain": 1.5,
        "readme": 1.0,
        "api_contract": 1.0,
        "runbook": 0.5,
        "incident": 0.25,
        "general": 1.0,
    },
    "onboarding": {
        "readme": 4.0,
        "domain": 3.5,
        "design": 3.0,
        "adr": 2.0,
        "spec": 1.5,
        "api_contract": 1.5,
        "runbook": 1.0,
        "incident": 0.5,
        "general": 1.0,
    },
}


def _load_graph(graph_path: str) -> nx.Graph:
    """Load graph from JSON file, returning a NetworkX graph."""
    data = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    try:
        return json_graph.node_link_graph(data, edges="links")
    except TypeError:
        return json_graph.node_link_graph(data, link="links")


def _communities_from_graph(G: nx.Graph) -> dict[int, list[str]]:
    """Reconstruct community dict from community property stored on nodes."""
    communities: dict[int, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(node_id)
    return communities


def _find_nodes(G: nx.Graph, term: str) -> list[str]:
    """Case-insensitive search by label, qualified name, source file, or node ID."""
    t = term.lower()
    ranked: list[tuple[float, str]] = []
    for nid, data in G.nodes(data=True):
        label = data.get("label", "").lower()
        qname = data.get("qualified_name", "").lower()
        source = data.get("source_file", "").lower()
        clean = label.lstrip(".")
        if clean.endswith("()"):
            clean = clean[:-2]

        score = 0.0
        if label == t or nid.lower() == t or qname == t or source == t:
            score += 100
        if clean == t or qname.endswith(f".{t}"):
            score += 80
        if t in qname:
            score += 25
        if t in clean or t in label:
            score += 20
        if t in source:
            score += 10

        if data.get("file_type") == "code":
            score += 8
        if data.get("symbol_kind") in {"function", "method", "class", "module"}:
            score += 6
        if data.get("symbol_kind") == "rationale":
            score -= 15

        if score > 0:
            ranked.append((score, nid))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [nid for _, nid in ranked]


def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    """Score nodes by keyword match on label + qualified name + source file."""
    scored = []
    for nid, data in G.nodes(data=True):
        label = data.get("label", "").lower()
        qname = data.get("qualified_name", "").lower()
        source = data.get("source_file", "").lower()
        score = (
            sum(1.5 for t in terms if t in qname)
            + sum(1.0 for t in terms if t in label)
            + sum(0.5 for t in terms if t in source)
        )
        if score > 0:
            scored.append((score, nid))
    return sorted(scored, reverse=True)


def _node_title(G: nx.Graph, nid: str) -> str:
    return G.nodes[nid].get("label", nid)


def _node_source(G: nx.Graph, nid: str) -> str:
    data = G.nodes[nid]
    source = data.get("source_file", "")
    location = data.get("source_location", "")
    return f"{source} {location}".strip()


def _is_test_source(source: str) -> bool:
    parts = source.split("/")
    name = parts[-1] if parts else source
    parent_parts = parts[:-1]
    in_fixture = "fixtures" in parent_parts
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".spec.ts")
        or name.endswith(".test.ts")
        or "__tests__" in parent_parts
        or ("tests" in parent_parts and not in_fixture)
    )


def _iter_directional_edges(G: nx.Graph, nid: str):
    for u, v, data in G.edges(nid, data=True):
        src = data.get("_src", u)
        tgt = data.get("_tgt", v)
        yield src, tgt, data


def _incoming_edges(G: nx.Graph, nid: str, relations: set[str] | None = None) -> list[tuple[str, dict]]:
    result = []
    for src, tgt, data in _iter_directional_edges(G, nid):
        if tgt != nid:
            continue
        if relations and data.get("relation") not in relations:
            continue
        result.append((src, data))
    return result


def _outgoing_edges(G: nx.Graph, nid: str, relations: set[str] | None = None) -> list[tuple[str, dict]]:
    result = []
    for src, tgt, data in _iter_directional_edges(G, nid):
        if src != nid:
            continue
        if relations and data.get("relation") not in relations:
            continue
        result.append((tgt, data))
    return result


def _transitive_incoming(
    G: nx.Graph,
    nid: str,
    relations: set[str],
    max_depth: int = 3,
) -> dict[str, int]:
    """Return upstream nodes reachable via incoming edges, with hop depth."""
    seen: dict[str, int] = {}
    frontier: list[tuple[str, int]] = [(nid, 0)]
    while frontier:
        current, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for src, _ in _incoming_edges(G, current, relations):
            next_depth = depth + 1
            prev = seen.get(src)
            if prev is None or next_depth < prev:
                seen[src] = next_depth
                frontier.append((src, next_depth))
    seen.pop(nid, None)
    return seen


def _transitive_outgoing(
    G: nx.Graph,
    nid: str,
    relations: set[str],
    max_depth: int = 3,
) -> dict[str, int]:
    """Return downstream nodes reachable via outgoing edges, with hop depth."""
    seen: dict[str, int] = {}
    frontier: list[tuple[str, int]] = [(nid, 0)]
    while frontier:
        current, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for tgt, _ in _outgoing_edges(G, current, relations):
            next_depth = depth + 1
            prev = seen.get(tgt)
            if prev is None or next_depth < prev:
                seen[tgt] = next_depth
                frontier.append((tgt, next_depth))
    seen.pop(nid, None)
    return seen


def _format_match(G: nx.Graph, nid: str) -> list[str]:
    data = G.nodes[nid]
    lines = [
        f"  {_node_title(G, nid)}",
        f"    source: {_node_source(G, nid)}",
        f"    kind: {data.get('symbol_kind', data.get('file_type', ''))}  type: {data.get('file_type', '')}  community: {data.get('community', '')}  degree: {G.degree(nid)}",
    ]
    if data.get("qualified_name"):
        lines.append(f"    qname: {data['qualified_name']}")
    if data.get("container"):
        lines.append(f"    container: {data['container']}")
    if data.get("signature"):
        lines.append(f"    signature: {data['signature']}")
    if data.get("summary"):
        lines.append(f"    summary: {data['summary']}")
    elif data.get("description"):
        lines.append(f"    doc: {data['description']}")
    return lines


def _format_edge_list(title: str, G: nx.Graph, edges: list[tuple[str, dict]], direction: str) -> str:
    if not edges:
        return f"{title}\n  None"
    lines = [title]
    for other, data in sorted(edges, key=lambda item: _node_title(G, item[0]).lower()):
        arrow = "<-" if direction == "in" else "->"
        lines.append(
            f"  {arrow} {_node_title(G, other)}  [{data.get('relation', '')}] [{data.get('confidence', '')}]"
        )
    return "\n".join(lines)


def _match_source_files(G: nx.Graph, term: str) -> list[str]:
    t = term.lower()
    matched = set()
    for _, data in G.nodes(data=True):
        source = data.get("source_file", "")
        if source and (source.lower() == t or source.lower().endswith(t) or t in source.lower()):
            matched.add(source)
    return sorted(matched)


def _module_source_map(G: nx.Graph) -> dict[str, str]:
    return module_source_map(G)


def _module_matches(G: nx.Graph, term: str) -> list[str]:
    """Match real source modules by path, basename, or qualified name."""
    source_to_nid = _module_source_map(G)
    t = term.lower()
    ranked: list[tuple[float, str]] = []
    for source, nid in source_to_nid.items():
        data = G.nodes[nid]
        label = data.get("label", "").lower()
        qname = data.get("qualified_name", "").lower()
        score = 0.0
        if source.lower() == t or label == t or qname == t:
            score += 100
        if source.lower().endswith(t) or label.endswith(t) or qname.endswith(t):
            score += 60
        if t in source.lower():
            score += 25
        if t in label or t in qname:
            score += 20
        if score > 0:
            ranked.append((score, nid))
    ranked.sort(key=lambda item: (-item[0], G.nodes[item[1]].get("source_file", "")))
    return [nid for _, nid in ranked]


def _prefer_module_term(term: str) -> bool:
    return "/" in term or "\\" in term or term.endswith((
        ".py", ".ts", ".tsx", ".js", ".java", ".kt", ".swift", ".m", ".mm", ".h", ".md"
    ))


def _select_node_match(G: nx.Graph, term: str) -> str | None:
    module_matches = _module_matches(G, term)
    if module_matches:
        module_nid = module_matches[0]
        module_data = G.nodes[module_nid]
        source = module_data.get("source_file", "")
        stem = Path(source).stem.lower() if source else ""
        qname = module_data.get("qualified_name", "").lower()
        t = term.lower()
        if t == stem or qname == t or qname.endswith(f".{t}"):
            return module_nid
    matches = _find_nodes(G, term)
    if not matches:
        return None
    if _prefer_module_term(term):
        return next((nid for nid in matches if G.nodes[nid].get("symbol_kind") == "module"), matches[0])
    return next((nid for nid in matches if G.nodes[nid].get("symbol_kind") != "module"), matches[0])


def _parse_depth_arg(args: list[str], default: int = 3) -> tuple[int, list[str]]:
    if len(args) >= 2 and args[0] == "--depth":
        try:
            depth = max(1, int(args[1]))
        except ValueError:
            depth = default
        return depth, args[2:]
    return default, args


def _parse_mode_arg(args: list[str]) -> tuple[str | None, list[str]]:
    if len(args) >= 2 and args[0] == "--mode":
        return args[1].lower(), args[2:]
    return None, args


def _parse_type_arg(args: list[str]) -> tuple[str | None, list[str]]:
    if len(args) >= 2 and args[0] == "--type":
        return args[1].lower(), args[2:]
    return None, args


def _task_terms(task: str) -> list[str]:
    terms = []
    for raw_term in re.findall(r"[A-Za-z0-9_./-]+", task.lower()):
        candidate_terms = [raw_term]
        candidate_terms.extend(part for part in re.split(r"[._/\-]+", raw_term) if part)
        for term in candidate_terms:
            if len(term) <= 2:
                continue
            if term in _TASK_STOPWORDS:
                continue
            if term not in terms:
                terms.append(term)
    return terms


def _infer_context_mode(task: str) -> str:
    terms = _task_terms(task)
    if not terms:
        return "feature"
    scores = {mode: 0 for mode in _CONTEXT_MODE_WEIGHTS}
    for term in terms:
        for mode, keywords in _CONTEXT_MODE_KEYWORDS.items():
            if term in keywords:
                scores[mode] += 2
            elif any(term in keyword or keyword in term for keyword in keywords):
                scores[mode] += 1
    best_mode = max(scores.items(), key=lambda item: item[1])[0]
    return best_mode if scores[best_mode] > 0 else "feature"


def _node_kind(data: dict) -> str:
    return data.get("symbol_kind", data.get("file_type", ""))


def _is_doc_node(data: dict) -> bool:
    return data.get("file_type") in {"document", "paper"}


def _doc_subtype(data: dict) -> str:
    subtype = str(data.get("doc_subtype", "") or "").lower()
    if subtype:
        return subtype
    haystack = " ".join(
        part for part in (
            data.get("source_file", "").lower(),
            data.get("label", "").lower(),
            data.get("summary", "").lower(),
        )
        if part
    )
    if "readme" in haystack:
        return "readme"
    if any(term in haystack for term in ("adr", "decision record", "architecture decision")):
        return "adr"
    if any(term in haystack for term in ("runbook", "playbook", "troubleshooting", "operations")):
        return "runbook"
    if any(term in haystack for term in ("incident", "postmortem", "post-mortem", "rca", "outage")):
        return "incident"
    if any(term in haystack for term in ("openapi", "swagger", "api contract", "schema", "contract")):
        return "api_contract"
    if any(term in haystack for term in ("spec", "requirements", "rfc", "proposal")):
        return "spec"
    if any(term in haystack for term in ("design", "architecture")):
        return "design"
    if any(term in haystack for term in ("domain", "glossary", "concept")):
        return "domain"
    return "general"


def _doc_subtype_label(data: dict) -> str:
    return _doc_subtype(data).replace("_", " ")


def _doc_mode_weight(mode: str, subtype: str) -> float:
    table = _DOC_SUBTYPE_MODE_WEIGHTS.get(mode, {})
    return table.get(subtype, table.get("general", 1.0))


def _is_module_node(data: dict) -> bool:
    return data.get("symbol_kind") == "module"


def _is_code_symbol(data: dict) -> bool:
    return data.get("file_type") == "code" and _node_kind(data) in {"module", "class", "function", "method"}


def _looks_like_entrypoint(data: dict) -> bool:
    label = data.get("label", "").lower().lstrip(".")
    if label.endswith("()"):
        label = label[:-2]
    qname = data.get("qualified_name", "").lower()
    source = data.get("source_file", "").lower()
    return (
        label in {"main", "query_main", "run", "watch", "serve", "ingest", "cli"}
        or qname.endswith(".main")
        or qname.endswith(".query_main")
        or source.endswith("/__main__.py")
        or source == "__main__.py"
    )


def _lexical_context_score(data: dict, task: str, terms: list[str]) -> tuple[float, list[str]]:
    task_lower = task.lower().strip()
    label = data.get("label", "").lower()
    qname = data.get("qualified_name", "").lower()
    source = data.get("source_file", "").lower()
    summary = data.get("summary", "").lower()
    description = data.get("description", "").lower()
    text = " ".join(part for part in (label, qname, source, summary, description) if part)
    if not text:
        return 0.0, []

    score = 0.0
    reasons: list[str] = []
    if task_lower and task_lower in text:
        score += 12.0
        reasons.append("full task phrase match")
    if task_lower and (label == task_lower or qname == task_lower or source == task_lower):
        score += 15.0
        reasons.append("exact identifier match")

    matched_terms = 0
    for term in terms:
        term_score = 0.0
        if label == term or qname == term or source == term:
            term_score += 8.0
        if qname.endswith(f".{term}") or label.endswith(term):
            term_score += 4.0
        if term in qname:
            term_score += 3.0
        if term in label:
            term_score += 2.5
        if term in source:
            term_score += 1.5
        if term in summary:
            term_score += 1.5
        if term in description:
            term_score += 1.0
        if term_score > 0:
            matched_terms += 1
            score += term_score

    if matched_terms >= 2:
        score += 2.0
        reasons.append(f"{matched_terms} task terms matched")
    elif matched_terms == 1:
        reasons.append("task term matched")

    return score, reasons


def _context_mode_bonus(
    G: nx.Graph,
    nid: str,
    mode: str,
    entrypoint_scores: dict[str, float],
) -> tuple[float, list[str]]:
    data = G.nodes[nid]
    kind = _node_kind(data)
    score = 0.0
    reasons: list[str] = []

    if data.get("file_type") == "rationale":
        return -20.0, ["rationale node"]

    if data.get("summary"):
        score += 1.5
        reasons.append("has summary")

    if _is_doc_node(data):
        subtype = _doc_subtype(data)
        subtype_weight = _doc_mode_weight(mode, subtype)
        score += subtype_weight
        reasons.append(f"{_doc_subtype_label(data)} doc")
        if mode == "onboarding":
            reasons.append("doc/spec useful for onboarding")
        elif mode == "feature":
            reasons.append("doc/spec relevant for feature work")
        elif mode == "bugfix" and subtype in {"runbook", "incident"}:
            reasons.append("operational doc useful for debugging")
        return score, reasons

    if data.get("source_file") and _is_test_source(data["source_file"]):
        if mode == "bugfix":
            score += 1.0
            reasons.append("test-adjacent source")
        else:
            score -= 3.0
            reasons.append("test source de-prioritized")

    callers = len(_incoming_edges(G, nid, {"calls"}))
    importers = len(_incoming_edges(G, nid, {"imports", "imports_from", "uses"}))
    callees = len(_outgoing_edges(G, nid, {"calls"}))
    dependencies = len(_outgoing_edges(G, nid, {"imports", "imports_from", "uses"}))
    entry_score = entrypoint_scores.get(nid, 0.0)

    if mode == "bugfix":
        if kind in {"function", "method"}:
            score += 3.0
            reasons.append("execution-level symbol")
        elif kind == "class":
            score += 2.0
        elif kind == "module":
            score += 1.0
        if callers:
            score += min(callers, 4) * 0.8
            reasons.append(f"{callers} caller(s)")
        if importers:
            score += min(importers, 3) * 0.7
        if "error" in data.get("label", "").lower() or "fail" in data.get("label", "").lower():
            score += 1.0
            reasons.append("error-oriented name")
    elif mode == "feature":
        if kind == "module":
            score += 4.0
            reasons.append("module-level scope")
        elif kind == "class":
            score += 3.0
            reasons.append("API/class boundary")
        elif kind in {"function", "method"}:
            score += 2.0
        if callees:
            score += min(callees, 4) * 0.7
            reasons.append(f"{callees} downstream call(s)")
        if dependencies:
            score += min(dependencies, 4) * 0.5
        if entry_score > 0:
            score += min(entry_score / 4.0, 3.0)
            reasons.append("entrypoint-like")
    elif mode == "refactor":
        if kind == "module":
            score += 3.5
            reasons.append("module boundary")
        elif kind == "class":
            score += 3.0
            reasons.append("shared abstraction")
        elif kind in {"function", "method"}:
            score += 1.5
        dependent_count = callers + importers
        if dependent_count:
            score += min(dependent_count, 5) * 0.9
            reasons.append(f"{dependent_count} upstream dependent(s)")
        score += min(G.degree(nid), 6) * 0.3
    elif mode == "onboarding":
        if kind == "module":
            score += 4.0
            reasons.append("good architecture anchor")
        elif kind == "class":
            score += 3.0
        elif kind in {"function", "method"}:
            score += 1.5
        if data.get("community") is not None:
            score += 1.0
            reasons.append("connected community member")
        score += min(G.degree(nid), 6) * 0.4
        if entry_score > 0:
            score += min(entry_score / 5.0, 2.0)
            reasons.append("orchestration point")

    if not _is_code_symbol(data):
        score -= 4.0

    return score, reasons


def _directed_shortest_path(
    G: nx.Graph,
    source: str,
    target: str,
    relations: set[str],
    max_depth: int = 5,
) -> list[str] | None:
    """Shortest directed path over outgoing edges filtered by relation."""
    if source == target:
        return [source]
    frontier: list[list[str]] = [[source]]
    seen = {source}
    while frontier:
        path = frontier.pop(0)
        current = path[-1]
        depth = len(path) - 1
        if depth >= max_depth:
            continue
        for nxt, _ in _outgoing_edges(G, current, relations):
            if nxt in seen:
                continue
            new_path = path + [nxt]
            if nxt == target:
                return new_path
            seen.add(nxt)
            frontier.append(new_path)
    return None


def _build_module_graph(G: nx.Graph) -> nx.DiGraph:
    return build_module_graph(G)


def _format_module_node(M: nx.DiGraph, nid: str) -> list[str]:
    data = M.nodes[nid]
    incoming = M.in_degree(nid)
    outgoing = M.out_degree(nid)
    lines = [
        f"  {data.get('label', nid)}",
        f"    source: {data.get('source_file', '')}",
        f"    qname: {data.get('qualified_name', '')}",
        f"    module deps: out={outgoing} in={incoming}",
    ]
    return lines


def _format_module_edge_list(title: str, M: nx.DiGraph, edges: list[tuple[str, dict]], direction: str) -> str:
    if not edges:
        return f"{title}\n  None"
    lines = [title]
    for other, data in sorted(edges, key=lambda item: M.nodes[item[0]].get("source_file", "")):
        arrow = "->" if direction == "out" else "<-"
        rels = ", ".join(
            f"{name} x{count}" if count > 1 else name
            for name, count in sorted(data.get("relations", {}).items())
        )
        lines.append(f"  {arrow} {M.nodes[other].get('source_file', other)}  [{rels}]")
    return "\n".join(lines)


def _entrypoint_candidates(G: nx.Graph) -> list[tuple[float, str, list[str]]]:
    """Heuristic ranking for entrypoint-like nodes."""
    action_names = {
        "main", "query_main", "watch", "ingest", "run", "serve", "start",
        "handle", "process", "execute", "cli", "bootstrap",
    }
    candidates: list[tuple[float, str, list[str]]] = []
    for nid, data in G.nodes(data=True):
        label = data.get("label", "")
        qname = data.get("qualified_name", "")
        source = data.get("source_file", "")
        if source and (_is_test_source(source) or "fixtures/" in source or source.startswith("tests/fixtures/")):
            continue
        symbol_kind = data.get("symbol_kind", data.get("file_type", ""))
        clean = label.lstrip(".")
        if clean.endswith("()"):
            clean = clean[:-2]

        score = 0.0
        reasons: list[str] = []

        if symbol_kind == "module" and (label == "__main__.py" or source.endswith("/__main__.py") or source == "__main__.py"):
            score += 12
            reasons.append("main module")
        if clean in action_names:
            score += 10
            reasons.append(f"action-style name `{clean}`")
        if clean.startswith("cmd_"):
            score += 8
            reasons.append("command handler")
        if qname.endswith(".main") or qname.endswith(".query_main"):
            score += 8
            reasons.append("entry function qname")
        if source.endswith("__main__.py"):
            score += 6
            reasons.append("declared in __main__.py")
        if any(part in source.lower() for part in ("cli", "watch", "server", "app", "ingest")):
            score += 3
            reasons.append("entry-oriented module path")

        outgoing_calls = len(_outgoing_edges(G, nid, {"calls", "uses", "imports", "imports_from"}))
        if outgoing_calls >= 3:
            score += min(outgoing_calls, 6)
            reasons.append(f"{outgoing_calls} outgoing control/dependency edges")

        if symbol_kind in {"function", "method"} and data.get("container"):
            container = data["container"]
            module_qname = ".".join(container.split(".")[:-1])
            if module_qname and qname.startswith(module_qname):
                score += 1

        if score > 0:
            candidates.append((score, nid, reasons))

    candidates.sort(key=lambda item: (-item[0], _node_source(G, item[1]), item[1]))
    return candidates


def _entrypoint_rows_for_target(
    G: nx.Graph,
    target_nid: str | None,
    target_module_nid: str | None,
    max_depth: int = 4,
) -> list[dict]:
    candidates = _entrypoint_candidates(G)
    relations = {"calls", "uses", "imports", "imports_from"}
    M = _build_module_graph(G)
    rows: list[dict] = []

    for score, entry_nid, reasons in candidates:
        entry_data = G.nodes[entry_nid]
        path_desc = ""
        hop_count = 999
        explicit_entry_reason = any(
            "action-style name" in reason
            or "command handler" in reason
            or "main module" in reason
            or "entry function qname" in reason
            for reason in reasons
        )

        if target_nid and entry_data.get("symbol_kind") != "module":
            path_nodes = _directed_shortest_path(G, entry_nid, target_nid, relations, max_depth=max_depth)
            if path_nodes:
                hop_count = len(path_nodes) - 1
                path_desc = " -> ".join(_node_title(G, nid) for nid in path_nodes)

        if not path_desc and target_module_nid:
            if entry_data.get("symbol_kind") == "module":
                entry_module_nid = entry_nid
            else:
                entry_module_nid = _module_source_map(G).get(entry_data.get("source_file", ""))
            if entry_module_nid and entry_module_nid in M and target_module_nid in M:
                try:
                    module_path = nx.shortest_path(M, entry_module_nid, target_module_nid)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    module_path = None
                if module_path and len(module_path) - 1 <= max_depth:
                    if (
                        len(module_path) == 1
                        and entry_nid != target_nid
                        and entry_data.get("symbol_kind") != "module"
                        and not explicit_entry_reason
                    ):
                        continue
                    hop_count = len(module_path) - 1
                    path_desc = " -> ".join(M.nodes[nid].get("label", nid) for nid in module_path)

        if path_desc:
            rows.append({
                "entry_nid": entry_nid,
                "entry_score": score,
                "hop_count": hop_count,
                "reasons": reasons,
                "path_desc": path_desc,
            })

    rows.sort(key=lambda item: (item["hop_count"], -item["entry_score"], _node_source(G, item["entry_nid"])))
    return rows


def _tests_for_node_map(G: nx.Graph, nid: str, max_depth: int = 3) -> dict[str, int]:
    direct = _incoming_edges(G, nid, {"calls", "imports", "imports_from", "uses", "mentions", "references"})
    transitive = _transitive_incoming(G, nid, {"calls", "imports", "imports_from", "uses"}, max_depth=max_depth)
    tests: dict[str, int] = {}

    for src, _ in direct:
        source = G.nodes[src].get("source_file", "")
        if _is_test_source(source):
            tests[src] = 1

    for src, depth in transitive.items():
        source = G.nodes[src].get("source_file", "")
        if _is_test_source(source):
            prev = tests.get(src)
            if prev is None or depth < prev:
                tests[src] = depth

    return tests


def _tests_for_source_map(G: nx.Graph, source: str, max_depth: int = 3) -> dict[str, int]:
    """Aggregate test coverage for any meaningful node in a source file."""
    tests: dict[str, int] = {}
    for nid, data in G.nodes(data=True):
        if data.get("source_file") != source:
            continue
        if _is_doc_node(data) or data.get("file_type") == "rationale":
            continue
        if not (_is_code_symbol(data) or _node_kind(data) in {"module", "class", "function", "method"}):
            continue
        for test_nid, depth in _tests_for_node_map(G, nid, max_depth=max_depth).items():
            prev = tests.get(test_nid)
            if prev is None or depth < prev:
                tests[test_nid] = depth
    return tests


def _community_support_nodes(G: nx.Graph, nid: str, limit: int = 4) -> list[str]:
    community = G.nodes[nid].get("community")
    if community is None:
        return []
    members = []
    for other, data in G.nodes(data=True):
        if other == nid or data.get("community") != community:
            continue
        if not (_is_code_symbol(data) or _is_doc_node(data)):
            continue
        if data.get("source_file") and _is_test_source(data["source_file"]):
            continue
        members.append(other)
    members.sort(key=lambda other: (-G.degree(other), _node_title(G, other).lower()))
    return members[:limit]


def _context_file_rows(
    G: nx.Graph,
    candidate_rows: list[tuple[str, float, list[str]]],
    max_files: int = 8,
) -> list[tuple[str, float, list[str], list[str]]]:
    file_scores: dict[str, float] = {}
    file_reasons: dict[str, list[str]] = {}
    file_nodes: dict[str, list[str]] = {}

    for nid, score, reasons in candidate_rows:
        source = G.nodes[nid].get("source_file", "")
        if not source:
            continue
        file_scores[source] = file_scores.get(source, 0.0) + score
        seen_reasons = file_reasons.setdefault(source, [])
        for reason in reasons:
            if reason not in seen_reasons:
                seen_reasons.append(reason)
            if len(seen_reasons) >= 4:
                break
        names = file_nodes.setdefault(source, [])
        title = _node_title(G, nid)
        if title not in names:
            names.append(title)

    rows = [
        (source, file_scores[source], file_reasons.get(source, []), file_nodes.get(source, []))
        for source in file_scores
    ]
    rows.sort(key=lambda item: (-item[1], item[0]))
    return rows[:max_files]


def _doc_rows_for_target(
    G: nx.Graph,
    nid: str,
    max_docs: int = 6,
    mode: str | None = None,
    doc_type: str | None = None,
) -> list[tuple[str, float, list[str]]]:
    data = G.nodes[nid]
    doc_scores: dict[str, float] = {}
    doc_reasons: dict[str, list[str]] = {}
    resolved_mode = mode or "onboarding"
    requested_type = doc_type.lower() if doc_type else None

    def add_doc(doc_nid: str, score: float, reason: str) -> None:
        if doc_nid not in G.nodes or not _is_doc_node(G.nodes[doc_nid]):
            return
        doc_data = G.nodes[doc_nid]
        subtype = _doc_subtype(doc_data)
        if requested_type and subtype != requested_type:
            return
        score *= _doc_mode_weight(resolved_mode, subtype)
        doc_scores[doc_nid] = doc_scores.get(doc_nid, 0.0) + score
        reasons = doc_reasons.setdefault(doc_nid, [])
        subtype_reason = f"{_doc_subtype_label(doc_data)} doc"
        if subtype_reason not in reasons:
            reasons.append(subtype_reason)
        if reason not in reasons:
            reasons.append(reason)

    title = _node_title(G, nid)
    for doc_nid, _ in _incoming_edges(G, nid, {"mentions", "references"}):
        add_doc(doc_nid, 6.0, f"directly mentions {title}")

    source = data.get("source_file", "")
    module_nid = _module_source_map(G).get(source) if source else None
    if module_nid and module_nid != nid:
        module_title = _node_title(G, module_nid)
        for doc_nid, _ in _incoming_edges(G, module_nid, {"mentions", "references"}):
            add_doc(doc_nid, 4.0, f"mentions module {module_title}")

    community = data.get("community")
    if community is not None:
        for doc_nid, doc_data in G.nodes(data=True):
            if not _is_doc_node(doc_data):
                continue
            if doc_data.get("community") == community:
                add_doc(doc_nid, 1.5, f"same community {community}")

    if resolved_mode == "onboarding" or requested_type == "readme":
        for doc_nid, doc_data in G.nodes(data=True):
            if not _is_doc_node(doc_data):
                continue
            if _doc_subtype(doc_data) != "readme":
                continue
            if _looks_like_entrypoint(data) or data.get("symbol_kind") == "module":
                add_doc(doc_nid, 3.5, "readme overview for entrypoint/module")
            else:
                add_doc(doc_nid, 1.5, "readme overview")

    if not doc_scores:
        terms = _task_terms(" ".join(part for part in (data.get("label", ""), data.get("qualified_name", "")) if part))
        for score, doc_nid in _score_nodes(G, terms)[:10]:
            if _is_doc_node(G.nodes[doc_nid]):
                add_doc(doc_nid, score, "lexical match")

    rows = [(doc_nid, doc_scores[doc_nid], doc_reasons.get(doc_nid, [])) for doc_nid in doc_scores]
    rows.sort(key=lambda item: (-item[1], _node_source(G, item[0]), item[0]))
    return rows[:max_docs]


def _impact_dependency_rows(
    G: nx.Graph,
    nid: str,
    max_depth: int = 3,
) -> dict[str, list[tuple[str, float, list[str]]]]:
    title = _node_title(G, nid)
    direct_rows: list[tuple[str, float, list[str]]] = []
    transitive_rows: list[tuple[str, float, list[str]]] = []
    seen_direct: set[str] = set()
    seen_transitive: set[str] = set()

    for src, data in _incoming_edges(G, nid, {"calls", "imports", "imports_from", "uses", "extends", "implements"}):
        src_data = G.nodes[src]
        if _is_doc_node(src_data) or _is_test_source(src_data.get("source_file", "")):
            continue
        reason = f"direct {data.get('relation', 'dependency')} on {title}"
        direct_rows.append((src, 5.0, [reason]))
        seen_direct.add(src)

    transitive = _transitive_incoming(
        G,
        nid,
        {"calls", "imports", "imports_from", "uses", "extends", "implements"},
        max_depth=max_depth,
    )
    for src, depth in transitive.items():
        if src in seen_direct:
            continue
        src_data = G.nodes[src]
        if _is_doc_node(src_data) or _is_test_source(src_data.get("source_file", "")):
            continue
        transitive_rows.append((src, 2.5 / depth, [f"{depth}-hop dependent on {title}"]))
        seen_transitive.add(src)

    return {"direct": direct_rows, "transitive": transitive_rows}


def _aggregate_file_rows(
    G: nx.Graph,
    rows: list[tuple[str, float, list[str]]],
    max_files: int = 6,
) -> list[tuple[str, float, list[str], list[str]]]:
    file_scores: dict[str, float] = {}
    file_reasons: dict[str, list[str]] = {}
    file_nodes: dict[str, list[str]] = {}

    for nid, score, reasons in rows:
        source = G.nodes[nid].get("source_file", "")
        if not source:
            continue
        file_scores[source] = file_scores.get(source, 0.0) + score
        reason_list = file_reasons.setdefault(source, [])
        for reason in reasons:
            if reason not in reason_list:
                reason_list.append(reason)
            if len(reason_list) >= 4:
                break
        node_list = file_nodes.setdefault(source, [])
        title = _node_title(G, nid)
        if title not in node_list:
            node_list.append(title)

    grouped = [
        (source, file_scores[source], file_reasons.get(source, []), file_nodes.get(source, []))
        for source in file_scores
    ]
    grouped.sort(key=lambda item: (-item[1], item[0]))
    return grouped[:max_files]


def _untested_impact_file_rows(
    G: nx.Graph,
    nid: str,
    max_depth: int = 3,
) -> list[tuple[str, float, list[str], list[str]]]:
    impacted = _impact_dependency_rows(G, nid, max_depth=max_depth)
    rows: list[tuple[str, float, list[str]]] = []
    for bucket in ("direct", "transitive"):
        for dep_nid, score, reasons in impacted[bucket]:
            source = G.nodes[dep_nid].get("source_file", "")
            tests = _tests_for_node_map(G, dep_nid, max_depth=max_depth)
            if not tests and source:
                tests = _tests_for_source_map(G, source, max_depth=max_depth)
            if tests:
                continue
            rows.append((dep_nid, score, reasons + ["no related tests found for node or source file"]))
    return _aggregate_file_rows(G, rows, max_files=8)


def _impact_file_rows(
    G: nx.Graph,
    focus_rows: list[tuple[str, float, list[str]]],
    max_depth: int = 3,
) -> dict[str, list[tuple[str, float, list[str], list[str]]]]:
    M = _build_module_graph(G)
    verify_scores: dict[str, float] = {}
    verify_reasons: dict[str, list[str]] = {}
    verify_nodes: dict[str, list[str]] = {}
    watch_scores: dict[str, float] = {}
    watch_reasons: dict[str, list[str]] = {}
    watch_nodes: dict[str, list[str]] = {}
    direct_sources: set[str] = set()

    def add_row(
        bucket_scores: dict[str, float],
        bucket_reasons: dict[str, list[str]],
        bucket_nodes: dict[str, list[str]],
        source: str,
        score: float,
        reason: str,
        node_label: str,
    ) -> None:
        if not source or score <= 0:
            return
        bucket_scores[source] = bucket_scores.get(source, 0.0) + score
        reasons = bucket_reasons.setdefault(source, [])
        if reason not in reasons:
            reasons.append(reason)
        nodes = bucket_nodes.setdefault(source, [])
        if node_label and node_label not in nodes:
            nodes.append(node_label)

    for nid, _, _ in focus_rows:
        data = G.nodes[nid]
        title = _node_title(G, nid)
        origin_source = data.get("source_file", "")

        for src, _ in _incoming_edges(G, nid, {"calls", "imports", "imports_from", "uses", "extends", "implements"}):
            src_data = G.nodes[src]
            source = src_data.get("source_file", "")
            if not source or source == origin_source or _is_test_source(source) or _is_doc_node(src_data):
                continue
            add_row(
                verify_scores,
                verify_reasons,
                verify_nodes,
                source,
                5.0,
                f"direct dependent on {title}",
                _node_title(G, src),
            )
            direct_sources.add(source)

        module_nid = _module_source_map(G).get(origin_source) if origin_source else None
        target_module_nid = module_nid if module_nid and module_nid in M else None
        for row in _entrypoint_rows_for_target(G, nid, target_module_nid, max_depth=max_depth)[:4]:
            entry_nid = row["entry_nid"]
            entry_source = G.nodes[entry_nid].get("source_file", "")
            if (
                not entry_source
                or entry_source == origin_source
                or _is_test_source(entry_source)
                or _is_doc_node(G.nodes[entry_nid])
            ):
                continue
            add_row(
                verify_scores,
                verify_reasons,
                verify_nodes,
                entry_source,
                4.0 / max(row["hop_count"], 1),
                f"entry path reaches {title}",
                _node_title(G, entry_nid),
            )
            direct_sources.add(entry_source)

        transitive = _transitive_incoming(
            G,
            nid,
            {"calls", "imports", "imports_from", "uses", "extends", "implements"},
            max_depth=max_depth,
        )
        for src, depth in transitive.items():
            src_data = G.nodes[src]
            source = src_data.get("source_file", "")
            if (
                not source
                or source == origin_source
                or source in direct_sources
                or _is_test_source(source)
                or _is_doc_node(src_data)
            ):
                continue
            add_row(
                watch_scores,
                watch_reasons,
                watch_nodes,
                source,
                2.5 / depth,
                f"{depth}-hop dependent on {title}",
                _node_title(G, src),
            )

        if target_module_nid:
            for other in M.predecessors(target_module_nid):
                source = M.nodes[other].get("source_file", "")
                if not source or source == origin_source or source in direct_sources:
                    continue
                add_row(
                    watch_scores,
                    watch_reasons,
                    watch_nodes,
                    source,
                    2.0,
                    f"module depends on {origin_source}",
                    M.nodes[other].get("label", other),
                )

    def finalize(
        scores: dict[str, float],
        reasons: dict[str, list[str]],
        nodes: dict[str, list[str]],
    ) -> list[tuple[str, float, list[str], list[str]]]:
        rows = [(source, scores[source], reasons.get(source, []), nodes.get(source, [])) for source in scores]
        rows.sort(key=lambda item: (-item[1], item[0]))
        return rows

    return {
        "verify": finalize(verify_scores, verify_reasons, verify_nodes),
        "watch": finalize(watch_scores, watch_reasons, watch_nodes),
    }


def _build_context_bundle(
    G: nx.Graph,
    task: str,
    mode: str | None = None,
    max_depth: int = 3,
) -> dict:
    resolved_mode = mode or _infer_context_mode(task)
    weights = _CONTEXT_MODE_WEIGHTS[resolved_mode]
    terms = _task_terms(task)
    entrypoint_candidates = _entrypoint_candidates(G)
    entrypoint_scores = {nid: score for score, nid, _ in entrypoint_candidates}

    seeds: list[tuple[str, float, list[str]]] = []
    for nid, data in G.nodes(data=True):
        lexical_score, lexical_reasons = _lexical_context_score(data, task, terms)
        if lexical_score <= 0:
            continue
        mode_bonus, mode_reasons = _context_mode_bonus(G, nid, resolved_mode, entrypoint_scores)
        total_score = lexical_score + mode_bonus
        if total_score <= 0:
            continue
        reasons = lexical_reasons + [reason for reason in mode_reasons if reason not in lexical_reasons]
        seeds.append((nid, total_score, reasons))

    if not seeds:
        for score, nid in _score_nodes(G, terms or [task.lower()])[:5]:
            reasons = ["fallback text match"]
            mode_bonus, mode_reasons = _context_mode_bonus(G, nid, resolved_mode, entrypoint_scores)
            seeds.append((nid, score + max(mode_bonus, 0.0), reasons + mode_reasons))

    seeds.sort(key=lambda item: (-item[1], _node_source(G, item[0]), item[0]))
    seed_rows = seeds[:6]
    M = _build_module_graph(G)
    qname_to_nid = {
        data.get("qualified_name", ""): nid
        for nid, data in G.nodes(data=True)
        if data.get("qualified_name")
    }

    candidate_scores: dict[str, float] = {}
    candidate_reasons: dict[str, list[str]] = {}
    candidate_roles: dict[str, set[str]] = {}

    def add_candidate(nid: str, score: float, reason: str, role: str) -> None:
        if nid not in G.nodes:
            return
        if score < 0:
            return
        if score > 0:
            candidate_scores[nid] = candidate_scores.get(nid, 0.0) + score
        elif nid not in candidate_scores:
            return
        reasons = candidate_reasons.setdefault(nid, [])
        if reason not in reasons:
            reasons.append(reason)
        candidate_roles.setdefault(nid, set()).add(role)

    for nid, seed_score, reasons in seed_rows:
        add_candidate(nid, seed_score * weights["seed"], "task-aligned seed", "seed")
        for reason in reasons[:3]:
            add_candidate(nid, 0.0, reason, "seed")

        data = G.nodes[nid]
        container = data.get("container", "")
        container_nid = qname_to_nid.get(container)
        if container_nid:
            add_candidate(container_nid, weights["container"], f"contains {_node_title(G, nid)}", "support")

        source = data.get("source_file", "")
        module_nid = _module_source_map(G).get(source) if source else None
        if module_nid and module_nid != nid:
            add_candidate(module_nid, weights["module"], f"module for {_node_title(G, nid)}", "module")

        for src, _ in _incoming_edges(G, nid, {"calls"}):
            add_candidate(src, weights["caller"], f"calls {_node_title(G, nid)}", "support")
        for src, _ in _incoming_edges(G, nid, {"imports", "imports_from", "uses"}):
            add_candidate(src, weights["importer"], f"depends on {_node_title(G, nid)}", "support")
        for tgt, _ in _outgoing_edges(G, nid, {"calls"}):
            add_candidate(tgt, weights["callee"], f"called by {_node_title(G, nid)}", "support")
        for tgt, _ in _outgoing_edges(G, nid, {"imports", "imports_from", "uses", "extends", "implements"}):
            add_candidate(tgt, weights["dependency"], f"dependency of {_node_title(G, nid)}", "support")
        for doc_nid, _ in _incoming_edges(G, nid, {"mentions", "references"}):
            add_candidate(doc_nid, weights["doc"], f"documents {_node_title(G, nid)}", "doc")
        for test_nid, depth in _tests_for_node_map(G, nid, max_depth=max_depth).items():
            label = "direct test" if depth == 1 else f"{depth}-hop test"
            add_candidate(test_nid, weights["test"] / depth, f"{label} for {_node_title(G, nid)}", "test")

        target_module_nid = module_nid if module_nid and module_nid in M else None
        for row in _entrypoint_rows_for_target(G, nid, target_module_nid, max_depth=max_depth)[:4]:
            path_reason = f"reaches {_node_title(G, nid)} via {row['hop_count']}-hop path"
            add_candidate(row["entry_nid"], weights["entrypoint"] / max(row["hop_count"], 1), path_reason, "entrypoint")

        if module_nid and module_nid in M:
            for other in M.successors(module_nid):
                add_candidate(other, weights["module_neighbor"], f"module dependency of {source}", "module")
            for other in M.predecessors(module_nid):
                add_candidate(other, weights["module_neighbor"], f"module dependent of {source}", "module")

        if resolved_mode == "onboarding":
            for other in _community_support_nodes(G, nid):
                add_candidate(other, weights["community"], f"same community as {_node_title(G, nid)}", "support")

    ranked_rows = [
        (nid, candidate_scores[nid], candidate_reasons.get(nid, []))
        for nid in candidate_scores
    ]
    ranked_rows.sort(key=lambda item: (-item[1], _node_source(G, item[0]), item[0]))

    focus_symbols = [
        (nid, score, reasons) for nid, score, reasons in ranked_rows
        if _is_code_symbol(G.nodes[nid]) and not _is_test_source(G.nodes[nid].get("source_file", ""))
    ][:6]
    entrypoints = [
        (nid, score, reasons) for nid, score, reasons in ranked_rows
        if "entrypoint" in candidate_roles.get(nid, set())
    ][:4]
    tests = [
        (nid, score, reasons) for nid, score, reasons in ranked_rows
        if "test" in candidate_roles.get(nid, set()) or _is_test_source(G.nodes[nid].get("source_file", ""))
    ][:4]
    doc_scores: dict[str, float] = {}
    doc_reasons: dict[str, list[str]] = {}
    for target_nid, _, _ in (focus_symbols or seed_rows[:4]):
        for doc_nid, score, reasons in _doc_rows_for_target(G, target_nid, max_docs=4, mode=resolved_mode):
            doc_scores[doc_nid] = doc_scores.get(doc_nid, 0.0) + score
            reason_list = doc_reasons.setdefault(doc_nid, [])
            for reason in reasons:
                if reason not in reason_list:
                    reason_list.append(reason)
    if not doc_scores:
        for doc_nid, score, reasons in [
            (nid, score, reasons) for nid, score, reasons in ranked_rows if _is_doc_node(G.nodes[nid])
        ]:
            doc_scores[doc_nid] = doc_scores.get(doc_nid, 0.0) + score
            doc_reasons.setdefault(doc_nid, []).extend(
                reason for reason in reasons if reason not in doc_reasons.setdefault(doc_nid, [])
            )
    docs = [
        (doc_nid, score, doc_reasons.get(doc_nid, []))
        for doc_nid, score in sorted(
            doc_scores.items(),
            key=lambda item: (-item[1], _node_source(G, item[0]), item[0]),
        )
    ][:4]
    files = _context_file_rows(G, ranked_rows)

    return {
        "task": task,
        "mode": resolved_mode,
        "terms": terms,
        "seeds": seed_rows,
        "focus_symbols": focus_symbols,
        "entrypoints": entrypoints,
        "tests": tests,
        "docs": docs,
        "files": files,
    }


def cmd_context_for(G: nx.Graph, task: str, mode: str | None = None, max_depth: int = 3) -> str:
    """Assemble a task-aware, summary-first context bundle."""
    bundle = _build_context_bundle(G, task, mode=mode, max_depth=max_depth)
    mode_label = bundle["mode"]
    lines = [f"Context for '{bundle['task']}' [{mode_label}]:"]
    if bundle["terms"]:
        lines.append(f"  task terms: {', '.join(bundle['terms'][:8])}")

    if bundle["focus_symbols"]:
        lines.append("Focus symbols:")
        for nid, score, reasons in bundle["focus_symbols"]:
            data = G.nodes[nid]
            kind = _node_kind(data)
            lines.append(f"  - {_node_title(G, nid)}  [{kind}]  [{_node_source(G, nid)}]  score={score:.1f}")
            if data.get("summary"):
                lines.append(f"    summary: {data['summary']}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")
    elif bundle["seeds"]:
        lines.append("Seeds:")
        for nid, score, reasons in bundle["seeds"][:4]:
            lines.append(f"  - {_node_title(G, nid)}  [{_node_source(G, nid)}]  score={score:.1f}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")
    else:
        lines.append("  No strong graph context found.")

    if bundle["files"]:
        lines.append("Key files:")
        for source, score, reasons, symbols in bundle["files"][:6]:
            lines.append(f"  - {source}  score={score:.1f}")
            if symbols:
                lines.append(f"    nodes: {', '.join(symbols[:3])}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")

    if bundle["entrypoints"]:
        lines.append("Entry paths:")
        for nid, _, reasons in bundle["entrypoints"]:
            lines.append(f"  - {_node_title(G, nid)}  [{_node_source(G, nid)}]")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:2])}")

    if bundle["tests"]:
        lines.append("Tests to check:")
        for nid, _, reasons in bundle["tests"]:
            lines.append(f"  - {_node_title(G, nid)}  [{_node_source(G, nid)}]")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:2])}")

    if bundle["docs"]:
        lines.append("Docs/specs:")
        for nid, _, reasons in bundle["docs"]:
            subtype = _doc_subtype_label(G.nodes[nid])
            lines.append(f"  - {_node_title(G, nid)}  [{subtype}]  [{_node_source(G, nid)}]")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:2])}")

    return "\n".join(lines)


def cmd_docs_for(G: nx.Graph, label: str, mode: str | None = None, doc_type: str | None = None) -> str:
    """Show docs/specs most relevant to a symbol or module."""
    nid = _select_node_match(G, label)
    if not nid:
        return f"No symbol or module matching '{label}'."

    rows = _doc_rows_for_target(G, nid, mode=mode, doc_type=doc_type)
    if not rows:
        return f"No docs/specs found for {_node_title(G, nid)}."

    title = f"Docs/specs for {_node_title(G, nid)}:"
    qualifiers = []
    if mode:
        qualifiers.append(mode)
    if doc_type:
        qualifiers.append(f"type={doc_type}")
    if qualifiers:
        title = title[:-1] + f" [{' '.join(qualifiers)}]:"
    lines = [title]
    for doc_nid, score, reasons in rows:
        data = G.nodes[doc_nid]
        lines.append(
            f"  - {_node_title(G, doc_nid)}  [{_doc_subtype_label(data)}]  [{_node_source(G, doc_nid)}]  score={score:.1f}"
        )
        if data.get("summary"):
            lines.append(f"    summary: {data['summary']}")
        if reasons:
            lines.append(f"    why: {', '.join(reasons[:3])}")
    return "\n".join(lines)


def _files_for_change_plan(
    G: nx.Graph,
    task: str,
    mode: str | None = None,
    max_depth: int = 3,
) -> dict:
    bundle = _build_context_bundle(G, task, mode=mode, max_depth=max_depth)
    seed_code_rows = [
        row for row in bundle["seeds"]
        if _is_code_symbol(G.nodes[row[0]]) and not _is_test_source(G.nodes[row[0]].get("source_file", ""))
    ]
    edit_files = _aggregate_file_rows(G, seed_code_rows, max_files=6)
    if not edit_files:
        edit_files = [
            row for row in bundle["files"]
            if not _is_test_source(row[0]) and not row[0].endswith((".md", ".txt", ".rst", ".pdf"))
        ][:6]

    test_files = _aggregate_file_rows(G, bundle["tests"], max_files=4)
    doc_files = _aggregate_file_rows(G, bundle["docs"], max_files=2)
    impact_rows = _impact_file_rows(G, bundle["focus_symbols"], max_depth=max_depth)

    taken_sources = {source for source, _, _, _ in edit_files}
    taken_sources.update(source for source, _, _, _ in test_files)
    taken_sources.update(source for source, _, _, _ in doc_files)

    verify_files = [row for row in impact_rows["verify"] if row[0] not in taken_sources][:4]
    taken_sources.update(source for source, _, _, _ in verify_files)

    watch_files = [row for row in impact_rows["watch"] if row[0] not in taken_sources][:4]

    impact_score = len(verify_files) * 2 + len(watch_files) + len(test_files) + len(doc_files)
    impact_risk = "high" if impact_score >= 8 else "medium" if impact_score >= 4 else "low"

    return {
        "bundle": bundle,
        "impact_risk": impact_risk,
        "impact_score": impact_score,
        "edit_files": edit_files,
        "verify_files": verify_files,
        "watch_files": watch_files,
        "test_files": test_files,
        "doc_files": doc_files,
    }


def _verify_after_change_plan(
    G: nx.Graph,
    task: str,
    mode: str | None = None,
    max_depth: int = 3,
) -> dict:
    plan = _files_for_change_plan(G, task, mode=mode, max_depth=max_depth)
    bundle = plan["bundle"]
    smoke_paths = []
    seen_sources: set[str] = set()
    for nid, _, reasons in bundle["entrypoints"]:
        source = G.nodes[nid].get("source_file", "")
        if source and source not in seen_sources:
            seen_sources.add(source)
            smoke_paths.append((nid, reasons))

    untested_watch = []
    for source, score, reasons, symbols in plan["verify_files"] + plan["watch_files"]:
        if _is_test_source(source):
            continue
        if _tests_for_source_map(G, source, max_depth=max_depth):
            continue
        untested_watch.append((source, score, reasons, symbols))

    return {
        "plan": plan,
        "smoke_paths": smoke_paths[:4],
        "untested_watch": untested_watch[:4],
    }


def cmd_files_for_change(G: nx.Graph, task: str, mode: str | None = None, max_depth: int = 3) -> str:
    """Suggest a compact set of files to inspect/change for a task."""
    plan = _files_for_change_plan(G, task, mode=mode, max_depth=max_depth)
    bundle = plan["bundle"]
    edit_files = plan["edit_files"]
    verify_files = plan["verify_files"]
    watch_files = plan["watch_files"]
    test_files = plan["test_files"]
    doc_files = plan["doc_files"]

    if not edit_files and not verify_files and not watch_files and not test_files and not doc_files:
        return f"No file suggestions found for '{task}'."

    lines = [f"Files for change for '{bundle['task']}' [{bundle['mode']}]:"] 
    lines.append(
        f"  impact: {plan['impact_risk']} "
        f"(edit={len(edit_files)} verify={len(verify_files)} watch={len(watch_files)} "
        f"tests={len(test_files)} docs={len(doc_files)})"
    )
    if bundle["focus_symbols"]:
        lines.append("  focus:")
        lines.append("    " + ", ".join(_node_title(G, nid) for nid, _, _ in bundle["focus_symbols"][:4]))

    if edit_files:
        lines.append("Edit first:")
        for source, score, reasons, symbols in edit_files[:6]:
            lines.append(f"  - {source}  score={score:.1f}")
            if symbols:
                lines.append(f"    nodes: {', '.join(symbols[:3])}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")

    if verify_files:
        lines.append("Verify adjacent code:")
        for source, score, reasons, symbols in verify_files[:4]:
            lines.append(f"  - {source}  score={score:.1f}")
            if symbols:
                lines.append(f"    nodes: {', '.join(symbols[:3])}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")

    if test_files:
        lines.append("Tests to update/check:")
        for source, score, reasons, symbols in test_files[:4]:
            lines.append(f"  - {source}  score={score:.1f}")
            if symbols:
                lines.append(f"    nodes: {', '.join(symbols[:3])}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")

    if doc_files:
        lines.append("Docs to review:")
        for source, score, reasons, symbols in doc_files[:4]:
            score_text = f"  score={score:.1f}" if score > 0 else ""
            lines.append(f"  - {source}{score_text}")
            if symbols:
                lines.append(f"    nodes: {', '.join(symbols[:3])}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")

    if watch_files:
        lines.append("Impact watchlist:")
        for source, score, reasons, symbols in watch_files[:4]:
            lines.append(f"  - {source}  score={score:.1f}")
            if symbols:
                lines.append(f"    nodes: {', '.join(symbols[:3])}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")

    return "\n".join(lines)


def cmd_verify_after_change(G: nx.Graph, task: str, mode: str | None = None, max_depth: int = 3) -> str:
    """Build a post-change verification checklist for a task."""
    verify_plan = _verify_after_change_plan(G, task, mode=mode, max_depth=max_depth)
    plan = verify_plan["plan"]
    bundle = plan["bundle"]

    lines = [f"Verify after change for '{bundle['task']}' [{bundle['mode']}]:"] 
    lines.append(
        f"  impact: {plan['impact_risk']} "
        f"(verify={len(plan['verify_files'])} tests={len(plan['test_files'])} docs={len(plan['doc_files'])} watch={len(plan['watch_files'])})"
    )
    if bundle["focus_symbols"]:
        lines.append("Changed focus:")
        lines.append("  - " + ", ".join(_node_title(G, nid) for nid, _, _ in bundle["focus_symbols"][:4]))

    if plan["verify_files"]:
        lines.append("Re-check adjacent code:")
        for source, score, reasons, symbols in plan["verify_files"][:4]:
            lines.append(f"  - {source}  score={score:.1f}")
            if symbols:
                lines.append(f"    nodes: {', '.join(symbols[:3])}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")

    if verify_plan["smoke_paths"]:
        lines.append("Smoke likely entry paths:")
        for nid, reasons in verify_plan["smoke_paths"]:
            lines.append(f"  - {_node_title(G, nid)}  [{_node_source(G, nid)}]")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:2])}")

    if plan["test_files"]:
        lines.append("Run or update tests:")
        for source, score, reasons, symbols in plan["test_files"][:4]:
            lines.append(f"  - {source}  score={score:.1f}")
            if symbols:
                lines.append(f"    nodes: {', '.join(symbols[:3])}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")
    else:
        lines.append("Run or update tests:")
        lines.append("  - No related tests found.")

    if plan["doc_files"]:
        lines.append("Review docs/runbooks:")
        for source, score, reasons, symbols in plan["doc_files"][:4]:
            score_text = f"  score={score:.1f}" if score > 0 else ""
            lines.append(f"  - {source}{score_text}")
            if symbols:
                lines.append(f"    nodes: {', '.join(symbols[:3])}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")

    if verify_plan["untested_watch"]:
        lines.append("Untested impact watchlist:")
        for source, score, reasons, symbols in verify_plan["untested_watch"][:4]:
            lines.append(f"  - {source}  score={score:.1f}")
            if symbols:
                lines.append(f"    nodes: {', '.join(symbols[:3])}")
            if reasons:
                lines.append(f"    why: {', '.join(reasons[:3])}")

    return "\n".join(lines)


def cmd_untested_impact(G: nx.Graph, label: str, max_depth: int = 3) -> str:
    """Show impacted code files that do not appear to have related test coverage."""
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    rows = _untested_impact_file_rows(G, nid, max_depth=max_depth)
    if not rows:
        return f"No untested impact found for {_node_title(G, nid)}."

    lines = [f"Untested impact for {_node_title(G, nid)}:"]
    for source, score, reasons, symbols in rows[:8]:
        lines.append(f"  - {source}  score={score:.1f}")
        if symbols:
            lines.append(f"    nodes: {', '.join(symbols[:3])}")
        if reasons:
            lines.append(f"    why: {', '.join(reasons[:3])}")
    return "\n".join(lines)


def cmd_node(G: nx.Graph, label: str) -> str:
    """Show details for a node matching the label."""
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    lines = []
    for nid in matches[:5]:
        lines += _format_match(G, nid)
    return "\n".join(lines)


def cmd_definitions(G: nx.Graph, term: str) -> str:
    """List matching symbols with source locations."""
    matches = _find_nodes(G, term)
    if not matches:
        return f"No symbol matching '{term}'."
    lines = [f"Definitions for '{term}':"]
    for nid in matches[:15]:
        data = G.nodes[nid]
        lines.append(
            f"  {_node_title(G, nid)}  [{data.get('symbol_kind', data.get('file_type', ''))}]  [{_node_source(G, nid)}]"
        )
        if data.get("qualified_name"):
            lines.append(f"    {data['qualified_name']}")
    return "\n".join(lines)


def cmd_references(G: nx.Graph, label: str) -> str:
    """Show incoming references/dependencies to a node."""
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    incoming = _incoming_edges(G, nid)
    if not incoming:
        return f"No incoming references to {_node_title(G, nid)}."
    lines = [f"References to {_node_title(G, nid)}:"]
    for src, data in sorted(incoming, key=lambda item: (_node_title(G, item[0]).lower(), item[1].get("relation", ""))):
        lines.append(f"  <- {_node_title(G, src)}  [{data.get('relation', '')}] [{data.get('confidence', '')}]")
    return "\n".join(lines)


def cmd_explain(G: nx.Graph, label: str) -> str:
    """Explain a symbol using local metadata and graph relations."""
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    incoming = _incoming_edges(G, nid)
    outgoing = _outgoing_edges(G, nid)
    lines = [f"Explain {_node_title(G, nid)}:"]
    lines += _format_match(G, nid)
    if outgoing:
        lines.append("  outgoing:")
        for tgt, data in outgoing[:8]:
            lines.append(f"    -> {_node_title(G, tgt)}  [{data.get('relation', '')}]")
    if incoming:
        lines.append("  incoming:")
        for src, data in incoming[:8]:
            lines.append(f"    <- {_node_title(G, src)}  [{data.get('relation', '')}]")
    return "\n".join(lines)


def cmd_neighbors(G: nx.Graph, label: str) -> str:
    """Show direct neighbors of a node."""
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    lines = [f"Neighbors of {_node_title(G, nid)}:"]
    for nb in sorted(G.neighbors(nid), key=lambda n: G.nodes[n].get("label", n)):
        data = G.edges[nid, nb]
        lines.append(f"  -> {_node_title(G, nb)}  [{data.get('relation', '')}] [{data.get('confidence', '')}]")
    return "\n".join(lines)


def cmd_callers(G: nx.Graph, label: str) -> str:
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    return _format_edge_list(f"Callers of {_node_title(G, nid)}:", G, _incoming_edges(G, nid, {"calls"}), "in")


def cmd_callees(G: nx.Graph, label: str) -> str:
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    return _format_edge_list(f"Callees of {_node_title(G, nid)}:", G, _outgoing_edges(G, nid, {"calls"}), "out")


def cmd_imported_by(G: nx.Graph, label: str) -> str:
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    relations = {"imports", "imports_from", "uses"}
    return _format_edge_list(f"Imported/used by {_node_title(G, nid)}:", G, _incoming_edges(G, nid, relations), "in")


def cmd_extended_by(G: nx.Graph, label: str) -> str:
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    return _format_edge_list(f"Extended by {_node_title(G, nid)}:", G, _incoming_edges(G, nid, {"extends"}), "in")


def cmd_implements(G: nx.Graph, label: str) -> str:
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    return _format_edge_list(f"Implementers of {_node_title(G, nid)}:", G, _incoming_edges(G, nid, {"implements"}), "in")


def cmd_file(G: nx.Graph, path_term: str) -> str:
    """Show a file and the nodes extracted from it."""
    matches = _match_source_files(G, path_term)
    if not matches:
        return f"No file matching '{path_term}'."
    source = matches[0]
    nodes = [(nid, data) for nid, data in G.nodes(data=True) if data.get("source_file") == source]
    nodes.sort(key=lambda item: item[1].get("source_location", ""))
    lines = [f"File: {source}", f"  Nodes: {len(nodes)}"]
    for nid, data in nodes[:20]:
        lines.append(
            f"  - {data.get('label', nid)}  [{data.get('symbol_kind', data.get('file_type', ''))}]  {data.get('source_location', '')}"
        )
    if len(nodes) > 20:
        lines.append(f"  ... and {len(nodes) - 20} more")
    return "\n".join(lines)


def cmd_symbols(G: nx.Graph, path_term: str) -> str:
    """List non-file symbols found in a file."""
    matches = _match_source_files(G, path_term)
    if not matches:
        return f"No file matching '{path_term}'."
    source = matches[0]
    symbols = [
        (nid, data) for nid, data in G.nodes(data=True)
        if data.get("source_file") == source and data.get("symbol_kind") not in ("module", "document", "paper", "image")
    ]
    symbols.sort(key=lambda item: item[1].get("source_location", ""))
    lines = [f"Symbols in {source}:"]
    for nid, data in symbols:
        lines.append(f"  - {data.get('label', nid)}  [{data.get('symbol_kind', data.get('file_type', ''))}]  {data.get('source_location', '')}")
    return "\n".join(lines)


def cmd_modules(G: nx.Graph, term: str | None = None) -> str:
    """List modules, optionally filtered by a term."""
    M = _build_module_graph(G)
    module_ids = list(M.nodes())
    if term:
        module_ids = _module_matches(G, term)
        if not module_ids:
            return f"No module matching '{term}'."
    else:
        module_ids.sort(key=lambda nid: M.nodes[nid].get("source_file", ""))
    lines = ["Modules:" if not term else f"Modules matching '{term}':"]
    for nid in module_ids[:25]:
        lines.extend(_format_module_node(M, nid))
    if len(module_ids) > 25:
        lines.append(f"  ... and {len(module_ids) - 25} more")
    return "\n".join(lines)


def cmd_module(G: nx.Graph, term: str) -> str:
    """Show a single module and its direct dependencies."""
    M = _build_module_graph(G)
    matches = _module_matches(G, term)
    if not matches:
        return f"No module matching '{term}'."
    nid = matches[0]
    outgoing = [(other, M.edges[nid, other]) for other in M.successors(nid)]
    incoming = [(other, M.edges[other, nid]) for other in M.predecessors(nid)]
    lines = [f"Module {M.nodes[nid].get('label', nid)}:"]
    lines.extend(_format_module_node(M, nid))
    lines.append(_format_module_edge_list("Outgoing module deps:", M, outgoing, "out"))
    lines.append(_format_module_edge_list("Incoming module dependents:", M, incoming, "in"))
    return "\n".join(lines)


def cmd_module_deps(G: nx.Graph, term: str) -> str:
    """Show outgoing module dependencies."""
    M = _build_module_graph(G)
    matches = _module_matches(G, term)
    if not matches:
        return f"No module matching '{term}'."
    nid = matches[0]
    outgoing = [(other, M.edges[nid, other]) for other in M.successors(nid)]
    return _format_module_edge_list(
        f"Module deps for {M.nodes[nid].get('source_file', nid)}:",
        M,
        outgoing,
        "out",
    )


def cmd_module_dependents(G: nx.Graph, term: str) -> str:
    """Show incoming module dependents."""
    M = _build_module_graph(G)
    matches = _module_matches(G, term)
    if not matches:
        return f"No module matching '{term}'."
    nid = matches[0]
    incoming = [(other, M.edges[other, nid]) for other in M.predecessors(nid)]
    return _format_module_edge_list(
        f"Module dependents for {M.nodes[nid].get('source_file', nid)}:",
        M,
        incoming,
        "in",
    )


def cmd_module_path(G: nx.Graph, source: str, target: str) -> str:
    """Find shortest path between two modules in the collapsed module graph."""
    M = _build_module_graph(G)
    src_matches = _module_matches(G, source)
    tgt_matches = _module_matches(G, target)
    if not src_matches:
        return f"No module matching '{source}'."
    if not tgt_matches:
        return f"No module matching '{target}'."
    try:
        path_nodes = nx.shortest_path(M, src_matches[0], tgt_matches[0])
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return f"No module path between '{source}' and '{target}'."
    parts = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        data = M.edges[u, v]
        rels = ", ".join(sorted(data.get("relations", {}).keys()))
        if i == 0:
            parts.append(M.nodes[u].get("source_file", u))
        parts.append(f"--{rels}--> {M.nodes[v].get('source_file', v)}")
    return f"Module path ({len(path_nodes)-1} hops):\n  " + " ".join(parts)


def cmd_module_stats(G: nx.Graph) -> str:
    """Show high-level statistics for the module graph."""
    M = _build_module_graph(G)
    stats = module_stats(M)
    return "\n".join([
        "Module graph stats:",
        f"  modules: {stats['nodes']}",
        f"  module edges: {stats['edges']}",
        f"  weakly connected components: {stats['weak_components']}",
        f"  density: {stats['density']}",
        f"  avg in-degree: {stats['avg_in_degree']}",
        f"  avg out-degree: {stats['avg_out_degree']}",
    ])


def cmd_module_hotspots(G: nx.Graph) -> str:
    """Rank modules by dependency load."""
    M = _build_module_graph(G)
    rows = module_hotspots(M)
    if not rows:
        return "No module hotspots found."
    lines = ["Module hotspots:"]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"  {i}. {row['source_file']}  "
            f"[total={row['total_degree']} in={row['in_degree']} out={row['out_degree']} weight={row['weighted_degree']}]"
        )
    return "\n".join(lines)


def cmd_module_bridges(G: nx.Graph) -> str:
    """Rank modules that bridge otherwise separate areas."""
    M = _build_module_graph(G)
    rows = module_bridges(M)
    if not rows:
        return "No bridge modules found."
    lines = ["Module bridges:"]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"  {i}. {row['source_file']}  "
            f"[betweenness={row['betweenness']} in={row['in_degree']} out={row['out_degree']}]"
        )
    return "\n".join(lines)


def cmd_entrypoints(G: nx.Graph) -> str:
    """List likely entrypoints or orchestration points."""
    candidates = _entrypoint_candidates(G)
    if not candidates:
        return "No likely entrypoints found."
    lines = ["Likely entrypoints:"]
    for score, nid, reasons in candidates[:20]:
        data = G.nodes[nid]
        lines.append(
            f"  - {_node_title(G, nid)}  [{data.get('symbol_kind', data.get('file_type', ''))}]  "
            f"[{_node_source(G, nid)}]  score={score:.1f}"
        )
        if reasons:
            lines.append(f"    why: {', '.join(reasons[:3])}")
    return "\n".join(lines)


def cmd_entrypoints_for(G: nx.Graph, label: str, max_depth: int = 4) -> str:
    """Find likely entrypoints that can reach a symbol or module."""
    target_nid = _select_node_match(G, label)
    target_module_nid = None
    M = _build_module_graph(G)

    if target_nid:
        target_data = G.nodes[target_nid]
        if target_data.get("symbol_kind") == "module":
            target_module_nid = target_nid
        elif target_data.get("source_file"):
            target_module_nid = _module_source_map(G).get(target_data["source_file"])
    else:
        module_matches = _module_matches(G, label)
        if module_matches:
            target_module_nid = module_matches[0]
        else:
            return f"No symbol or module matching '{label}'."

    entry_rows = _entrypoint_rows_for_target(G, target_nid, target_module_nid, max_depth=max_depth)
    rows: list[tuple[int, float, str, list[str], str]] = [
        (row["hop_count"], -row["entry_score"], row["entry_nid"], row["reasons"], row["path_desc"])
        for row in entry_rows
    ]
    if not rows:
        target_label = _node_title(G, target_nid) if target_nid else M.nodes[target_module_nid].get("label", label)
        return f"No likely entrypoints found for {target_label} within {max_depth} hops."

    rows.sort(key=lambda item: (item[0], item[1], _node_source(G, item[2])))
    target_label = _node_title(G, target_nid) if target_nid else M.nodes[target_module_nid].get("label", label)
    lines = [f"Likely entrypoints for {target_label}:"]
    for hop_count, neg_score, entry_nid, reasons, path_desc in rows[:12]:
        entry_data = G.nodes[entry_nid]
        lines.append(
            f"  - {_node_title(G, entry_nid)}  [{entry_data.get('symbol_kind', entry_data.get('file_type', ''))}]  "
            f"[{_node_source(G, entry_nid)}]  {hop_count}-hop"
        )
        lines.append(f"    path: {path_desc}")
        if reasons:
            lines.append(f"    why entrypoint: {', '.join(reasons[:3])}")
    return "\n".join(lines)


def cmd_flow(G: nx.Graph, label: str, max_depth: int = 3) -> str:
    """Show downstream flow from a symbol or module."""
    nid = _select_node_match(G, label)
    if nid:
        data = G.nodes[nid]
        if data.get("symbol_kind") == "module":
            M = _build_module_graph(G)
            outgoing = [(other, M.edges[nid, other]) for other in M.successors(nid)] if nid in M else []
            if nid not in M:
                return f"No module flow found for {_node_title(G, nid)}."
            downstream = nx.single_source_shortest_path_length(M, nid, cutoff=max_depth)
            downstream.pop(nid, None)
            lines = [f"Module flow from {M.nodes[nid].get('source_file', nid)}:"]
            lines.append(_format_module_edge_list("Direct module deps:", M, outgoing, "out"))
            if downstream:
                lines.append("Transitive module flow:")
                for other, depth in sorted(downstream.items(), key=lambda item: (item[1], M.nodes[item[0]].get("source_file", "")))[:15]:
                    lines.append(f"  - {M.nodes[other].get('source_file', other)}  [{depth}-hop]")
            return "\n".join(lines)

        relations = {"calls", "uses", "imports", "imports_from"}
        direct = _outgoing_edges(G, nid, relations)
        transitive = _transitive_outgoing(G, nid, relations, max_depth=max_depth)
        lines = [f"Flow from {_node_title(G, nid)}:"]
        lines += _format_match(G, nid)
        lines.append(_format_edge_list("Direct downstream:", G, direct, "out"))
        if transitive:
            lines.append("Transitive downstream:")
            for other, depth in sorted(transitive.items(), key=lambda item: (item[1], _node_title(G, item[0]).lower()))[:20]:
                lines.append(
                    f"  - {_node_title(G, other)}  [{depth}-hop]  [{G.nodes[other].get('symbol_kind', G.nodes[other].get('file_type', ''))}]"
                )
        elif data.get("source_file"):
            module_nid = _module_source_map(G).get(data["source_file"])
            if module_nid:
                M = _build_module_graph(G)
                outgoing = [(other, M.edges[module_nid, other]) for other in M.successors(module_nid)] if module_nid in M else []
                if outgoing:
                    lines.append("Module context:")
                    lines.append(_format_module_edge_list("Direct module deps:", M, outgoing, "out"))
        return "\n".join(lines)

    module_matches = _module_matches(G, label)
    if module_matches:
        return cmd_flow(G, module_matches[0], max_depth=max_depth)
    return f"No symbol or module matching '{label}'."


def cmd_why_related(G: nx.Graph, source: str, target: str) -> str:
    """Explain why two symbols or modules are related."""
    src_nid = _select_node_match(G, source)
    tgt_nid = _select_node_match(G, target)

    if src_nid and tgt_nid:
        try:
            path_nodes = nx.shortest_path(G, src_nid, tgt_nid)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            path_nodes = None
        if path_nodes:
            lines = [f"Why {_node_title(G, src_nid)} is related to {_node_title(G, tgt_nid)}:"]
            for i in range(len(path_nodes) - 1):
                u, v = path_nodes[i], path_nodes[i + 1]
                data = G.edges[u, v]
                relation = data.get("relation", "")
                confidence = data.get("confidence", "")
                src = data.get("_src", u)
                tgt = data.get("_tgt", v)
                lines.append(
                    f"  {i+1}. {_node_title(G, src)} --{relation}--> {_node_title(G, tgt)}  [{confidence}]"
                )
                edge_source = data.get("source_file", "")
                if edge_source:
                    location = data.get("source_location", "")
                    lines.append(f"     evidence: {edge_source} {location}".rstrip())
            shared_community = G.nodes[src_nid].get("community") == G.nodes[tgt_nid].get("community")
            if shared_community:
                lines.append(f"  shared community: {G.nodes[src_nid].get('community')}")
            return "\n".join(lines)

    M = _build_module_graph(G)
    src_modules = _module_matches(G, source)
    tgt_modules = _module_matches(G, target)
    if not src_modules and src_nid and G.nodes[src_nid].get("source_file"):
        mid = _module_source_map(G).get(G.nodes[src_nid]["source_file"])
        if mid:
            src_modules = [mid]
    if not tgt_modules and tgt_nid and G.nodes[tgt_nid].get("source_file"):
        mid = _module_source_map(G).get(G.nodes[tgt_nid]["source_file"])
        if mid:
            tgt_modules = [mid]

    if src_modules and tgt_modules:
        try:
            path_nodes = nx.shortest_path(M, src_modules[0], tgt_modules[0])
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            path_nodes = None
        if path_nodes:
            lines = [
                f"Why {M.nodes[src_modules[0]].get('source_file', source)} is related to "
                f"{M.nodes[tgt_modules[0]].get('source_file', target)}:"
            ]
            for i in range(len(path_nodes) - 1):
                u, v = path_nodes[i], path_nodes[i + 1]
                data = M.edges[u, v]
                rels = ", ".join(
                    f"{name} x{count}" if count > 1 else name
                    for name, count in sorted(data.get("relations", {}).items())
                )
                lines.append(
                    f"  {i+1}. {M.nodes[u].get('source_file', u)} --{rels}--> {M.nodes[v].get('source_file', v)}"
                )
            return "\n".join(lines)

    if src_nid and tgt_nid:
        shared = set(G.neighbors(src_nid)) & set(G.neighbors(tgt_nid))
        if shared:
            lines = [f"{_node_title(G, src_nid)} and {_node_title(G, tgt_nid)} share neighbors:"]
            for nid in sorted(shared, key=lambda n: _node_title(G, n).lower())[:8]:
                lines.append(f"  - {_node_title(G, nid)}")
            return "\n".join(lines)
        if G.nodes[src_nid].get("community") == G.nodes[tgt_nid].get("community"):
            return (
                f"{_node_title(G, src_nid)} and {_node_title(G, tgt_nid)} are in the same community "
                f"({G.nodes[src_nid].get('community')})."
            )

    return f"No clear relationship found between '{source}' and '{target}'."


def cmd_tests_for(G: nx.Graph, label: str) -> str:
    """List tests that directly or transitively reference a symbol."""
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    direct = _incoming_edges(G, nid, {"calls", "imports", "imports_from", "uses", "mentions", "references"})
    transitive = _transitive_incoming(G, nid, {"calls", "imports", "imports_from", "uses"}, max_depth=3)

    tests: dict[str, int] = {}
    for src, _ in direct:
        source = G.nodes[src].get("source_file", "")
        if _is_test_source(source):
            tests[src] = 1
    for src, depth in transitive.items():
        source = G.nodes[src].get("source_file", "")
        if _is_test_source(source):
            prev = tests.get(src)
            if prev is None or depth < prev:
                tests[src] = depth

    if not tests:
        return f"No tests found for {_node_title(G, nid)}."

    lines = [f"Tests for {_node_title(G, nid)}:"]
    for test_nid, depth in sorted(tests.items(), key=lambda item: (item[1], _node_title(G, item[0]).lower())):
        depth_label = "direct" if depth == 1 else f"{depth}-hop"
        lines.append(f"  - {_node_title(G, test_nid)}  [{depth_label}]  [{_node_source(G, test_nid)}]")
    return "\n".join(lines)


def cmd_path(G: nx.Graph, source: str, target: str) -> str:
    """Find shortest path between two concepts."""
    src_matches = _find_nodes(G, source)
    tgt_matches = _find_nodes(G, target)
    if not src_matches:
        return f"No node matching '{source}'."
    if not tgt_matches:
        return f"No node matching '{target}'."
    try:
        path_nodes = nx.shortest_path(G, src_matches[0], tgt_matches[0])
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return f"No path between '{source}' and '{target}'."
    parts = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        data = G.edges[u, v]
        if i == 0:
            parts.append(_node_title(G, u))
        parts.append(f"--{data.get('relation', '')}--> {_node_title(G, v)}")
    return f"Path ({len(path_nodes)-1} hops):\n  " + " ".join(parts)


def cmd_impact(G: nx.Graph, label: str) -> str:
    """Show a direct and transitive impact summary for a symbol."""
    matches = _find_nodes(G, label)
    if not matches:
        return f"No node matching '{label}'."
    nid = matches[0]
    callers = _incoming_edges(G, nid, {"calls"})
    importers = _incoming_edges(G, nid, {"imports", "imports_from", "uses"})
    subclasses = _incoming_edges(G, nid, {"extends"})
    implementers = _incoming_edges(G, nid, {"implements"})
    doc_mentions = _incoming_edges(G, nid, {"mentions", "references"})
    tests = [(src, data) for src, data in callers + importers + doc_mentions if _is_test_source(G.nodes[src].get("source_file", ""))]
    transitive = _transitive_incoming(G, nid, {"calls", "imports", "imports_from", "uses", "extends", "implements"}, max_depth=3)
    direct_sources = {src for src, _ in callers + importers + subclasses + implementers}
    transitive_only = {src: depth for src, depth in transitive.items() if src not in direct_sources}
    impacted_nodes = {src for src, _ in callers + importers + subclasses + implementers + doc_mentions}
    untested_rows = _untested_impact_file_rows(G, nid, max_depth=3)
    community = G.nodes[nid].get("community")
    bridge_count = sum(1 for other in set(impacted_nodes) | set(transitive_only) if G.nodes[other].get("community") != community)
    doc_type_counts: dict[str, int] = {}
    for src, _ in doc_mentions:
        if src not in G.nodes:
            continue
        subtype = _doc_subtype(G.nodes[src])
        doc_type_counts[subtype] = doc_type_counts.get(subtype, 0) + 1
    score = (
        len(callers) * 2
        + len(importers) * 2
        + len(subclasses)
        + len(implementers)
        + len(doc_mentions)
        + len(tests)
        + len(transitive_only)
        + bridge_count
    )
    risk = "high" if score >= 10 else "medium" if score >= 4 else "low"

    lines = [
        f"Impact for {_node_title(G, nid)}:",
        f"  risk: {risk}",
        f"  direct callers: {len(callers)}",
        f"  importers/users: {len(importers)}",
        f"  subclasses: {len(subclasses)}",
        f"  implementers: {len(implementers)}",
        f"  transitive upstream dependents: {len(transitive_only)}",
        f"  docs/spec mentions: {len(doc_mentions)}",
        f"  related tests: {len(tests)}",
        f"  untested impacted files: {len(untested_rows)}",
        f"  cross-community touches: {bridge_count}",
    ]
    if callers:
        lines.append("  callers:")
        for src, _ in callers[:5]:
            lines.append(f"    - {_node_title(G, src)}")
    if importers:
        lines.append("  importers/users:")
        for src, _ in importers[:5]:
            lines.append(f"    - {_node_title(G, src)}")
    if doc_mentions:
        lines.append("  docs:")
        for src, _ in doc_mentions[:5]:
            lines.append(f"    - {_node_title(G, src)}  [{_doc_subtype_label(G.nodes[src])}]")
    if doc_type_counts:
        lines.append("  doc types:")
        for subtype, count in sorted(doc_type_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"    - {subtype.replace('_', ' ')}: {count}")
    if tests:
        lines.append("  tests:")
        seen = []
        for src, _ in tests:
            title = _node_title(G, src)
            if title not in seen:
                seen.append(title)
                lines.append(f"    - {title}")
            if len(seen) >= 5:
                break
    if transitive_only:
        lines.append("  transitive dependents:")
        for src, depth in sorted(transitive_only.items(), key=lambda item: (item[1], _node_title(G, item[0]).lower()))[:8]:
            lines.append(f"    - {_node_title(G, src)}  [{depth}-hop]")
    if untested_rows:
        lines.append("  untested impacted files:")
        for source, score, reasons, _ in untested_rows[:5]:
            lines.append(f"    - {source}  score={score:.1f}")
            if reasons:
                lines.append(f"      why: {', '.join(reasons[:2])}")
    return "\n".join(lines)


def cmd_stats(G: nx.Graph, communities: dict[int, list[str]]) -> str:
    """Show graph summary statistics."""
    confs = [data.get("confidence", "EXTRACTED") for _, _, data in G.edges(data=True)]
    total = len(confs) or 1
    return (
        f"Nodes: {G.number_of_nodes()}\n"
        f"Edges: {G.number_of_edges()}\n"
        f"Communities: {len(communities)}\n"
        f"EXTRACTED: {round(confs.count('EXTRACTED') / total * 100)}%\n"
        f"INFERRED: {round(confs.count('INFERRED') / total * 100)}%\n"
        f"AMBIGUOUS: {round(confs.count('AMBIGUOUS') / total * 100)}%"
    )


def cmd_gods(G: nx.Graph) -> str:
    """Show top connected nodes."""
    nodes = _god_nodes(G)
    lines = ["God nodes (most connected):"]
    lines += [f"  {i}. {n['label']} - {n['edges']} edges" for i, n in enumerate(nodes, 1)]
    return "\n".join(lines)


def cmd_search(G: nx.Graph, query: str) -> str:
    """Keyword search across all nodes."""
    terms = [t.lower() for t in query.split() if len(t) > 1]
    if not terms:
        return "Provide search terms."
    scored = _score_nodes(G, terms)
    if not scored:
        return "No matches."
    lines = [f"Search results for '{query}':"]
    for score, nid in scored[:15]:
        data = G.nodes[nid]
        extra = f"  {data.get('qualified_name', '')}" if data.get("qualified_name") else ""
        lines.append(f"  [{score:.1f}] {data.get('label', nid)}  [{data.get('source_file', '')}]{extra}")
    return "\n".join(lines)


_USAGE = """\
Usage: system-wiki query <command> [args]

Commands:
  search <terms>          Keyword search across all nodes
  definitions <term>      List matching symbol definitions
  references <label>      List incoming references to a node
  node <label>            Show node details
  explain <label>         Explain a symbol using graph context
  neighbors <label>       Show direct connections
  callers <label>         Show incoming call edges
  callees <label>         Show outgoing call edges
  imported-by <label>     Show imports/uses pointing at a node
  tests-for <label>       Show tests touching a symbol
  docs-for <label>        Show docs/specs linked to a symbol/module
  untested-impact <x>     Show impacted code with no related tests
  extended-by <label>     Show classes extending this node
  implements <label>      Show implementers of an interface/protocol
  impact <label>          Show direct + transitive blast-radius summary
  files-for-change <task> Suggest code/test/doc files for a task
  verify-after-change <t> Build a post-change verification checklist
  file <path>             Show a file and extracted nodes
  symbols <path>          List symbols found in a file
  modules [term]          List source modules/files
  module <path>           Show one module and its direct deps
  module-deps <path>      Show outgoing module dependencies
  module-dependents <p>   Show incoming module dependents
  module-path <A> <B>     Shortest path between two modules
  module-stats            Show module graph summary
  module-hotspots         Rank modules by dependency load
  module-bridges          Rank modules by bridge centrality
  entrypoints             List likely entrypoints/orchestrators
  entrypoints-for <x>     Find entrypoints that can reach a symbol/module
  flow [--depth N] <x>    Show downstream flow from a symbol or module
  context-for <task>      Assemble task-aware context bundle
  why-related <A> <B>     Explain why two symbols/modules are related
  community <id>          List community members
  path <source> <target>  Shortest path between two concepts
  gods                    Most connected nodes
  stats                   Graph summary statistics

Examples:
  system-wiki query search GraphStore
  system-wiki query definitions GraphStore
  system-wiki query references GraphStore
  system-wiki query node GraphStore
  system-wiki query explain GraphStore
  system-wiki query callers GraphStore
  system-wiki query tests-for GraphStore
  system-wiki query docs-for --mode feature GraphStore
  system-wiki query docs-for --type runbook handle_request
  system-wiki query untested-impact GraphStore
  system-wiki query impact GraphStore
  system-wiki query files-for-change --mode refactor "simplify query graph ranking"
  system-wiki query verify-after-change --mode bugfix "fix query path ranking"
  system-wiki query file src/graph_store.py
  system-wiki query symbols src/graph_store.py
  system-wiki query modules graph
  system-wiki query module system_wiki/query_graph.py
  system-wiki query module-deps system_wiki/extract_public_api.py
  system-wiki query module-path system_wiki/__main__.py system_wiki/extract_public_api.py
  system-wiki query module-stats
  system-wiki query module-hotspots
  system-wiki query module-bridges
  system-wiki query entrypoints
  system-wiki query entrypoints-for extract_public_api
  system-wiki query flow --depth 4 main
  system-wiki query context-for --mode bugfix "fix query path ranking"
  system-wiki query why-related __main__.py extract_python_postprocess
  system-wiki query community 0
  system-wiki query path GraphStore Settings
  system-wiki query gods
  system-wiki query stats
"""


def query_main(args: list[str], graph_path: str = "wiki-out/graph.json") -> None:
    """Entry point for `system-wiki query` subcommand."""
    if not args:
        print(_USAGE)
        return

    path = Path(graph_path)
    if not path.exists():
        print(f"[wiki] Graph not found: {path}")
        print("[wiki] Run `system-wiki .` first to build the graph.")
        sys.exit(1)

    G = _load_graph(graph_path)
    communities = _communities_from_graph(G)

    cmd = args[0]
    rest = args[1:]

    if cmd == "search" and rest:
        print(cmd_search(G, " ".join(rest)))
    elif cmd == "definitions" and rest:
        print(cmd_definitions(G, " ".join(rest)))
    elif cmd == "references" and rest:
        print(cmd_references(G, " ".join(rest)))
    elif cmd == "node" and rest:
        print(cmd_node(G, " ".join(rest)))
    elif cmd == "explain" and rest:
        print(cmd_explain(G, " ".join(rest)))
    elif cmd == "neighbors" and rest:
        print(cmd_neighbors(G, " ".join(rest)))
    elif cmd == "callers" and rest:
        print(cmd_callers(G, " ".join(rest)))
    elif cmd == "callees" and rest:
        print(cmd_callees(G, " ".join(rest)))
    elif cmd == "imported-by" and rest:
        print(cmd_imported_by(G, " ".join(rest)))
    elif cmd == "tests-for" and rest:
        print(cmd_tests_for(G, " ".join(rest)))
    elif cmd == "docs-for" and rest:
        mode, remaining = _parse_mode_arg(rest)
        doc_type, remaining = _parse_type_arg(remaining)
        if mode and mode not in _CONTEXT_MODE_WEIGHTS:
            print(f"Unknown mode '{mode}'. Choose one of: {', '.join(sorted(_CONTEXT_MODE_WEIGHTS))}.")
        elif remaining:
            print(cmd_docs_for(G, " ".join(remaining), mode=mode, doc_type=doc_type))
        else:
            print(_USAGE)
    elif cmd == "untested-impact" and rest:
        depth, remaining = _parse_depth_arg(rest, default=3)
        if remaining:
            print(cmd_untested_impact(G, " ".join(remaining), max_depth=depth))
        else:
            print(_USAGE)
    elif cmd == "extended-by" and rest:
        print(cmd_extended_by(G, " ".join(rest)))
    elif cmd == "implements" and rest:
        print(cmd_implements(G, " ".join(rest)))
    elif cmd == "impact" and rest:
        print(cmd_impact(G, " ".join(rest)))
    elif cmd == "files-for-change" and rest:
        mode, remaining = _parse_mode_arg(rest)
        depth, remaining = _parse_depth_arg(remaining, default=3)
        if mode and mode not in _CONTEXT_MODE_WEIGHTS:
            print(f"Unknown mode '{mode}'. Choose one of: {', '.join(sorted(_CONTEXT_MODE_WEIGHTS))}.")
        elif remaining:
            print(cmd_files_for_change(G, " ".join(remaining), mode=mode, max_depth=depth))
        else:
            print(_USAGE)
    elif cmd == "verify-after-change" and rest:
        mode, remaining = _parse_mode_arg(rest)
        depth, remaining = _parse_depth_arg(remaining, default=3)
        if mode and mode not in _CONTEXT_MODE_WEIGHTS:
            print(f"Unknown mode '{mode}'. Choose one of: {', '.join(sorted(_CONTEXT_MODE_WEIGHTS))}.")
        elif remaining:
            print(cmd_verify_after_change(G, " ".join(remaining), mode=mode, max_depth=depth))
        else:
            print(_USAGE)
    elif cmd == "file" and rest:
        print(cmd_file(G, " ".join(rest)))
    elif cmd == "symbols" and rest:
        print(cmd_symbols(G, " ".join(rest)))
    elif cmd == "modules":
        print(cmd_modules(G, " ".join(rest) if rest else None))
    elif cmd == "module" and rest:
        print(cmd_module(G, " ".join(rest)))
    elif cmd == "module-deps" and rest:
        print(cmd_module_deps(G, " ".join(rest)))
    elif cmd == "module-dependents" and rest:
        print(cmd_module_dependents(G, " ".join(rest)))
    elif cmd == "module-path" and len(rest) >= 2:
        print(cmd_module_path(G, rest[0], " ".join(rest[1:])))
    elif cmd == "module-stats":
        print(cmd_module_stats(G))
    elif cmd == "module-hotspots":
        print(cmd_module_hotspots(G))
    elif cmd == "module-bridges":
        print(cmd_module_bridges(G))
    elif cmd == "entrypoints":
        print(cmd_entrypoints(G))
    elif cmd == "entrypoints-for" and rest:
        depth, remaining = _parse_depth_arg(rest, default=4)
        if remaining:
            print(cmd_entrypoints_for(G, " ".join(remaining), max_depth=depth))
        else:
            print(_USAGE)
    elif cmd == "flow" and rest:
        depth, remaining = _parse_depth_arg(rest, default=3)
        if remaining:
            print(cmd_flow(G, " ".join(remaining), max_depth=depth))
        else:
            print(_USAGE)
    elif cmd == "context-for" and rest:
        mode, remaining = _parse_mode_arg(rest)
        depth, remaining = _parse_depth_arg(remaining, default=3)
        if mode and mode not in _CONTEXT_MODE_WEIGHTS:
            print(f"Unknown mode '{mode}'. Choose one of: {', '.join(sorted(_CONTEXT_MODE_WEIGHTS))}.")
        elif remaining:
            print(cmd_context_for(G, " ".join(remaining), mode=mode, max_depth=depth))
        else:
            print(_USAGE)
    elif cmd == "why-related" and len(rest) >= 2:
        print(cmd_why_related(G, rest[0], " ".join(rest[1:])))
    elif cmd == "community" and rest:
        try:
            print(cmd_community(G, communities, int(rest[0])))
        except ValueError:
            print(f"Community ID must be a number, got '{rest[0]}'")
    elif cmd == "path" and len(rest) >= 2:
        print(cmd_path(G, rest[0], " ".join(rest[1:])))
    elif cmd == "gods":
        print(cmd_gods(G))
    elif cmd == "stats":
        print(cmd_stats(G, communities))
    else:
        print(_USAGE)


def cmd_community(G: nx.Graph, communities: dict[int, list[str]], cid: int) -> str:
    """List all nodes in a community."""
    members = communities.get(cid)
    if not members:
        return f"Community {cid} not found."
    lines = [f"Community {cid} ({len(members)} nodes):"]
    for nid in sorted(members, key=lambda n: G.degree(n), reverse=True):
        data = G.nodes[nid]
        lines.append(f"  {_node_title(G, nid)}  [{data.get('source_file', '')}]  deg={G.degree(nid)}")
    return "\n".join(lines)
