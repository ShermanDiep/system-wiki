# module-level dependency graph helpers
from __future__ import annotations

import networkx as nx


def _is_fixture_or_test_source(source: str) -> bool:
    parts = source.split("/")
    name = parts[-1] if parts else source
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in parts[:-1]
        or "fixtures" in parts[:-1]
        or "__tests__" in parts[:-1]
    )


def module_source_map(G: nx.Graph) -> dict[str, str]:
    """Map source_file -> module node id when available."""
    result: dict[str, str] = {}
    for nid, data in G.nodes(data=True):
        source = data.get("source_file", "")
        if not source:
            continue
        if data.get("symbol_kind") == "module":
            result[source] = nid
    return result


def build_module_graph(G: nx.Graph) -> nx.DiGraph:
    """Collapse node-level graph into a directed module dependency graph."""
    M = nx.DiGraph()
    source_to_nid = module_source_map(G)

    for source, nid in source_to_nid.items():
        data = G.nodes[nid]
        M.add_node(
            nid,
            label=data.get("label", nid),
            source_file=source,
            qualified_name=data.get("qualified_name", ""),
            community=data.get("community"),
        )

    relation_weights = {
        "imports": 3.0,
        "imports_from": 3.0,
        "uses": 2.0,
        "calls": 2.0,
        "extends": 1.5,
        "implements": 1.5,
        "mentions": 1.0,
        "references": 1.0,
    }

    for src, tgt, data in G.edges(data=True):
        real_src = data.get("_src", src)
        real_tgt = data.get("_tgt", tgt)
        if real_src not in G.nodes or real_tgt not in G.nodes:
            continue
        src_file = G.nodes[real_src].get("source_file", "")
        tgt_file = G.nodes[real_tgt].get("source_file", "")
        if not src_file or not tgt_file or src_file == tgt_file:
            continue

        src_module = source_to_nid.get(src_file)
        tgt_module = source_to_nid.get(tgt_file)
        if not src_module or not tgt_module or src_module == tgt_module:
            continue

        relation = data.get("relation", "")
        edge = M.get_edge_data(src_module, tgt_module)
        if edge is None:
            M.add_edge(
                src_module,
                tgt_module,
                relations={relation: 1},
                confidence={data.get("confidence", "EXTRACTED"): 1},
                weight=relation_weights.get(relation, 1.0),
                examples=[relation],
            )
        else:
            edge["relations"][relation] = edge["relations"].get(relation, 0) + 1
            conf = data.get("confidence", "EXTRACTED")
            edge["confidence"][conf] = edge["confidence"].get(conf, 0) + 1
            edge["weight"] += relation_weights.get(relation, 1.0)
            if relation not in edge["examples"]:
                edge["examples"].append(relation)

    return M


def module_stats(M: nx.DiGraph) -> dict[str, float | int]:
    """Basic stats for the module dependency graph."""
    node_count = M.number_of_nodes()
    edge_count = M.number_of_edges()
    total_in = sum(M.in_degree(n) for n in M.nodes())
    total_out = sum(M.out_degree(n) for n in M.nodes())
    return {
        "nodes": node_count,
        "edges": edge_count,
        "weak_components": nx.number_weakly_connected_components(M) if node_count else 0,
        "density": round(nx.density(M), 4) if node_count > 1 else 0.0,
        "avg_in_degree": round(total_in / node_count, 2) if node_count else 0.0,
        "avg_out_degree": round(total_out / node_count, 2) if node_count else 0.0,
    }


def module_hotspots(M: nx.DiGraph, top_n: int = 10) -> list[dict]:
    """Rank modules by total degree and weighted dependency load."""
    rows: list[dict] = []
    for nid in M.nodes():
        source = M.nodes[nid].get("source_file", "")
        if _is_fixture_or_test_source(source):
            continue
        incoming = M.in_degree(nid)
        outgoing = M.out_degree(nid)
        weighted = 0.0
        for _, _, data in M.in_edges(nid, data=True):
            weighted += float(data.get("weight", 1.0))
        for _, _, data in M.out_edges(nid, data=True):
            weighted += float(data.get("weight", 1.0))
        rows.append({
            "id": nid,
            "label": M.nodes[nid].get("label", nid),
            "source_file": source,
            "in_degree": incoming,
            "out_degree": outgoing,
            "total_degree": incoming + outgoing,
            "weighted_degree": round(weighted, 2),
        })
    rows.sort(key=lambda item: (-item["total_degree"], -item["weighted_degree"], item["source_file"]))
    return rows[:top_n]


def module_bridges(M: nx.DiGraph, top_n: int = 10) -> list[dict]:
    """Rank modules by betweenness centrality in the module graph."""
    if M.number_of_nodes() <= 2 or M.number_of_edges() == 0:
        return []
    scores = nx.betweenness_centrality(M)
    rows = []
    for nid, score in scores.items():
        if score <= 0:
            continue
        source = M.nodes[nid].get("source_file", "")
        if _is_fixture_or_test_source(source):
            continue
        rows.append({
            "id": nid,
            "label": M.nodes[nid].get("label", nid),
            "source_file": source,
            "betweenness": round(score, 4),
            "in_degree": M.in_degree(nid),
            "out_degree": M.out_degree(nid),
        })
    rows.sort(key=lambda item: (-item["betweenness"], item["source_file"]))
    return rows[:top_n]
