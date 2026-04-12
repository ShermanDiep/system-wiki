# public API for AST extraction — dispatcher, collect_files, main extract()
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_walker = importlib.import_module("system_wiki.extract_ast_walker")
_cfgs = importlib.import_module("system_wiki.extract_language_configs")
_custom = importlib.import_module("system_wiki.extract_custom_languages")
_custom2 = importlib.import_module("system_wiki.extract_custom_languages_2")
_elixir_mod = importlib.import_module("system_wiki.extract_elixir")
_postprocess = importlib.import_module("system_wiki.extract_python_postprocess")
_cache = importlib.import_module("system_wiki.cache_file_hash")

_extract_generic = _walker._extract_generic
load_cached = _cache.load_cached
save_cached = _cache.save_cached

extract_python_rationale = _postprocess.extract_python_rationale
resolve_cross_file_imports = _postprocess.resolve_cross_file_imports
resolve_python_module_dependencies = _postprocess.resolve_python_module_dependencies
resolve_cross_file_js_ts_imports = _postprocess.resolve_cross_file_js_ts_imports
resolve_cross_file_mobile_imports = _postprocess.resolve_cross_file_mobile_imports
resolve_cross_file_objc_imports = _postprocess.resolve_cross_file_objc_imports

extract_go = _custom.extract_go
extract_rust = _custom.extract_rust
extract_zig = _custom2.extract_zig
extract_powershell = _custom2.extract_powershell
extract_elixir = _elixir_mod.extract_elixir


# ── Per-language extract functions (generic-backed) ───────────────────────────

def extract_python(path: Path) -> dict:
    result = _extract_generic(path, _cfgs._PYTHON_CONFIG)
    if "error" not in result:
        extract_python_rationale(path, result)
    return result


def extract_js(path: Path) -> dict:
    config = _cfgs._TS_CONFIG if path.suffix in (".ts", ".tsx") else _cfgs._JS_CONFIG
    return _extract_generic(path, config)


def extract_java(path: Path) -> dict:
    return _extract_generic(path, _cfgs._JAVA_CONFIG)


def extract_c(path: Path) -> dict:
    return _extract_generic(path, _cfgs._C_CONFIG)


def extract_cpp(path: Path) -> dict:
    return _extract_generic(path, _cfgs._CPP_CONFIG)


def extract_ruby(path: Path) -> dict:
    return _extract_generic(path, _cfgs._RUBY_CONFIG)


def extract_csharp(path: Path) -> dict:
    return _extract_generic(path, _cfgs._CSHARP_CONFIG)


def extract_kotlin(path: Path) -> dict:
    return _extract_generic(path, _cfgs._KOTLIN_CONFIG)


def extract_scala(path: Path) -> dict:
    return _extract_generic(path, _cfgs._SCALA_CONFIG)


def extract_php(path: Path) -> dict:
    return _extract_generic(path, _cfgs._PHP_CONFIG)


def extract_lua(path: Path) -> dict:
    return _extract_generic(path, _cfgs._LUA_CONFIG)


def extract_swift(path: Path) -> dict:
    return _extract_generic(path, _cfgs._SWIFT_CONFIG)


def extract_objc(path: Path) -> dict:
    return _extract_generic(path, _cfgs._OBJC_CONFIG)


# ── Dispatch table ────────────────────────────────────────────────────────────

_DISPATCH: dict[str, Any] = {
    ".py":    extract_python,
    ".js":    extract_js,    ".ts":   extract_js,   ".tsx":  extract_js,
    ".go":    extract_go,    ".rs":   extract_rust,
    ".java":  extract_java,
    ".c":     extract_c,     ".h":    extract_c,
    ".cpp":   extract_cpp,   ".cc":   extract_cpp,  ".cxx":  extract_cpp, ".hpp": extract_cpp,
    ".rb":    extract_ruby,  ".cs":   extract_csharp,
    ".kt":    extract_kotlin, ".kts": extract_kotlin,
    ".scala": extract_scala, ".php":  extract_php,
    ".swift": extract_swift, ".lua":  extract_lua,  ".toc":  extract_lua,
    ".m":     extract_objc,  ".mm":   extract_objc,
    ".zig":   extract_zig,   ".ps1":  extract_powershell,
    ".ex":    extract_elixir, ".exs": extract_elixir,
}


# ── Main entry points ─────────────────────────────────────────────────────────


def _clean_symbol_name(label: str, source_file: str = "") -> str:
    """Normalize a node label into a symbol-like name."""
    clean = label.strip()
    if clean.startswith("."):
        clean = clean[1:]
    if clean.endswith("()"):
        clean = clean[:-2]
    if not clean and source_file:
        clean = Path(source_file).stem
    return clean


def _module_name(source_file: str) -> str:
    """Convert `path/to/file.py` into `path.to.file`."""
    if not source_file:
        return ""
    return ".".join(Path(source_file).with_suffix("").parts)


def _looks_like_objc_header(path: Path) -> bool:
    """Heuristic: detect Objective-C headers so `.h` can use the right parser."""
    if path.suffix.lower() != ".h":
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:4000]
    except OSError:
        return False
    signals = ("@interface", "@protocol", "@implementation", "@property", "@end")
    return any(signal in text for signal in signals)


def _enrich_symbol_metadata(nodes: list[dict], edges: list[dict]) -> None:
    """Populate Phase 1 symbol metadata used by navigation queries."""
    id_to_node = {node.get("id"): node for node in nodes if node.get("id")}
    parent_map: dict[str, str] = {}
    child_rel: dict[str, str] = {}

    for edge in edges:
        relation = edge.get("relation")
        if relation in ("contains", "method"):
            src = edge.get("source")
            tgt = edge.get("target")
            if src in id_to_node and tgt in id_to_node and tgt not in parent_map:
                parent_map[tgt] = src
                child_rel[tgt] = relation

    for node in nodes:
        source_file = node.get("source_file", "")
        label = node.get("label", "")
        file_type = node.get("file_type", "")
        node_id = node.get("id", "")

        if file_type == "rationale":
            symbol_kind = "rationale"
        elif file_type != "code":
            symbol_kind = file_type or "entity"
        elif source_file and label == Path(source_file).name:
            symbol_kind = "module"
        elif child_rel.get(node_id) == "method" or (label.startswith(".") and label.endswith("()")):
            symbol_kind = "method"
        elif label.endswith("()"):
            symbol_kind = "function"
        else:
            symbol_kind = "class"

        node["symbol_kind"] = symbol_kind
        node["name"] = _clean_symbol_name(label, source_file)

    qname_cache: dict[str, str] = {}

    def build_qname(node_id: str) -> str:
        if node_id in qname_cache:
            return qname_cache[node_id]
        node = id_to_node.get(node_id, {})
        source_file = node.get("source_file", "")
        symbol_kind = node.get("symbol_kind", "")
        name = node.get("name", "") or _clean_symbol_name(node.get("label", ""), source_file)
        module_name = _module_name(source_file)
        parent_id = parent_map.get(node_id)

        if symbol_kind == "module":
            qname = module_name or name or node_id
        elif parent_id and parent_id in id_to_node:
            parent_qname = build_qname(parent_id)
            qname = f"{parent_qname}.{name}" if parent_qname and name else parent_qname or name or node_id
        elif module_name and name and name != module_name.split(".")[-1]:
            qname = f"{module_name}.{name}"
        else:
            qname = module_name or name or node_id

        qname_cache[node_id] = qname
        return qname

    for node in nodes:
        node_id = node.get("id", "")
        parent_id = parent_map.get(node_id)
        node["qualified_name"] = build_qname(node_id) if node_id else ""
        node["container"] = build_qname(parent_id) if parent_id else ""
        if node.get("description") and not node.get("summary"):
            node["summary"] = node["description"]

    outgoing: dict[str, list[tuple[str, str]]] = {}
    incoming: dict[str, list[tuple[str, str]]] = {}
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        relation = edge.get("relation", "")
        if src and tgt:
            outgoing.setdefault(src, []).append((relation, tgt))
            incoming.setdefault(tgt, []).append((relation, src))

    def _labels(node_ids: list[str], limit: int = 3) -> list[str]:
        labels = []
        for nid in node_ids:
            label = id_to_node.get(nid, {}).get("name") or id_to_node.get(nid, {}).get("label", nid)
            if label and label not in labels:
                labels.append(label)
            if len(labels) >= limit:
                break
        return labels

    for node in nodes:
        if node.get("summary") or node.get("file_type") != "code":
            continue

        node_id = node.get("id", "")
        symbol_kind = node.get("symbol_kind", "")
        container = node.get("container", "")
        outs = outgoing.get(node_id, [])
        ins = incoming.get(node_id, [])

        rationale_sources = [src for relation, src in ins if relation == "rationale_for"]
        if rationale_sources:
            rationale_label = id_to_node.get(rationale_sources[0], {}).get("label", "").strip()
            if rationale_label:
                node["summary"] = rationale_label
                continue

        if symbol_kind == "module":
            children = [tgt for relation, tgt in outs if relation == "contains"]
            child_labels = _labels(children)
            if children:
                summary = f"Module with {len(children)} top-level symbols"
                if child_labels:
                    summary += f": {', '.join(child_labels)}"
                node["summary"] = summary + "."
            else:
                node["summary"] = "Module node."
            continue

        if symbol_kind == "class":
            methods = [tgt for relation, tgt in outs if relation == "method"]
            bases = [tgt for relation, tgt in outs if relation in ("extends", "implements")]
            parts = [f"Class in {container}." if container else "Class."]
            if methods:
                parts.append(f"{len(methods)} methods")
            if bases:
                base_labels = _labels(bases, limit=2)
                if base_labels:
                    parts.append(f"related to {', '.join(base_labels)}")
            node["summary"] = " ".join(parts).strip()
            continue

        if symbol_kind in ("function", "method"):
            calls = [tgt for relation, tgt in outs if relation == "calls"]
            uses = [tgt for relation, tgt in outs if relation in ("uses", "imports", "imports_from")]
            parts = []
            if container:
                parts.append(f"{symbol_kind.capitalize()} in {container}.")
            else:
                parts.append(f"{symbol_kind.capitalize()}.")
            if calls:
                call_labels = _labels(calls)
                call_text = f"Calls {', '.join(call_labels)}" if call_labels else f"{len(calls)} outgoing calls"
                parts.append(call_text + ".")
            elif uses:
                use_labels = _labels(uses)
                use_text = f"Depends on {', '.join(use_labels)}" if use_labels else f"{len(uses)} dependencies"
                parts.append(use_text + ".")
            node["summary"] = " ".join(parts).strip()
            continue

        node["summary"] = f"{symbol_kind.capitalize()} in {container}." if container else f"{symbol_kind.capitalize()}."

def extract(paths: list[Path]) -> dict:
    """Extract AST nodes and edges from a list of code files.

    Two-pass: per-file structural extraction, then cross-file Python import resolution.
    Results are cached by file hash — unchanged files are skipped on re-runs.
    """
    per_file: list[dict] = []

    # Use CWD as cache root — ensures cache always lands in ./wiki-out/cache/
    root = Path(".")

    total = len(paths)
    for i, path in enumerate(paths, 1):
        extractor = extract_objc if _looks_like_objc_header(path) else _DISPATCH.get(path.suffix)
        if extractor is None:
            continue
        cached = load_cached(path, root)
        if cached is not None:
            per_file.append(cached)
            continue
        # Progress indicator for large codebases
        if total > 50 and i % 50 == 0:
            import sys
            print(f"\r[wiki] AST: {i}/{total} files ({i*100//total}%)", end="", flush=True, file=sys.stderr)
        result = extractor(path)
        if "error" not in result:
            save_cached(path, result, root)
        per_file.append(result)
    if total > 50:
        import sys
        print(f"\r[wiki] AST: {total}/{total} (100%)          ", file=sys.stderr)

    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    for result in per_file:
        all_nodes.extend(result.get("nodes", []))
        all_edges.extend(result.get("edges", []))

    # Cross-file class-level edges (Python only)
    py_paths = [p for p in paths if p.suffix == ".py"]
    py_results = [r for r, p in zip(per_file, paths) if p.suffix == ".py"]
    all_edges.extend(resolve_python_module_dependencies(py_results, py_paths))
    all_edges.extend(resolve_cross_file_imports(py_results, py_paths))

    # Cross-file module/symbol edges for relative JS/TS imports
    js_ts_paths = [p for p in paths if p.suffix in (".js", ".jsx", ".ts", ".tsx")]
    js_ts_results = [r for r, p in zip(per_file, paths) if p.suffix in (".js", ".jsx", ".ts", ".tsx")]
    all_edges.extend(resolve_cross_file_js_ts_imports(js_ts_results, js_ts_paths))

    # Cross-file import resolution for mobile languages (Java/Kotlin/Swift)
    mobile_paths = [p for p in paths if p.suffix in (".java", ".kt", ".kts", ".swift")]
    mobile_results = [r for r, p in zip(per_file, paths) if p.suffix in (".java", ".kt", ".kts", ".swift")]
    all_edges.extend(resolve_cross_file_mobile_imports(mobile_results, mobile_paths))

    objc_paths = [p for p in paths if p.suffix in (".m", ".mm") or _looks_like_objc_header(p)]
    objc_results = [r for r, p in zip(per_file, paths) if p.suffix in (".m", ".mm") or _looks_like_objc_header(p)]
    all_edges.extend(resolve_cross_file_objc_imports(objc_results, objc_paths))

    # Enrich nodes with doc comments (Javadoc, JSDoc, GoDoc, etc.)
    try:
        _doc_comments = importlib.import_module("system_wiki.extract_doc_comments")
        _doc_comments.enrich_nodes_with_comments(all_nodes, all_edges, paths)
    except Exception:
        pass

    _enrich_symbol_metadata(all_nodes, all_edges)

    return {"nodes": all_nodes, "edges": all_edges, "input_tokens": 0, "output_tokens": 0}


def collect_files(target: Path) -> list[Path]:
    """Collect all supported source files under target (file or directory)."""
    if target.is_file():
        return [target]
    _EXTENSIONS = (
        "*.py", "*.js", "*.ts", "*.tsx", "*.go", "*.rs",
        "*.java", "*.c", "*.h", "*.cpp", "*.cc", "*.cxx", "*.hpp",
        "*.rb", "*.cs", "*.kt", "*.kts", "*.scala", "*.php", "*.swift", "*.m", "*.mm",
        "*.lua", "*.toc", "*.zig", "*.ps1", "*.ex", "*.exs",
    )
    results: list[Path] = []
    for pattern in _EXTENSIONS:
        results.extend(
            p for p in target.rglob(pattern)
            if not any(part.startswith(".") for part in p.parts)
        )
    return sorted(results)
