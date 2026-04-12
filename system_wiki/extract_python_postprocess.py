# Python-specific post-processing: docstring/rationale extraction and cross-file import resolution
from __future__ import annotations

import importlib
import re
from pathlib import Path

_core = importlib.import_module("system_wiki.extract_core")
_make_id = _core._make_id

_RATIONALE_PREFIXES = (
    "# NOTE:", "# IMPORTANT:", "# HACK:", "# WHY:",
    "# RATIONALE:", "# TODO:", "# FIXME:",
)

_JS_TS_SUFFIXES = (".js", ".jsx", ".ts", ".tsx")
_JAVA_KOTLIN_SUFFIXES = (".java", ".kt", ".kts")
_OBJC_SUFFIXES = (".m", ".mm", ".h")
_PACKAGE_RE = re.compile(r"^\s*package\s+([A-Za-z_][\w.]*)", re.MULTILINE)
_PY_IMPORTLIB_RE = re.compile(r'importlib\.import_module\(\s*["\']([A-Za-z_][\w.]*)["\']\s*\)')
_PY_IMPORT_RE = re.compile(r'^\s*import\s+([A-Za-z_][\w\., \t]+)', re.MULTILINE)
_PY_FROM_IMPORT_RE = re.compile(r'^\s*from\s+([A-Za-z_][\w.]*)\s+import\s+([A-Za-z_][\w\., \t]*)', re.MULTILINE)


def extract_python_rationale(path: Path, result: dict) -> None:
    """Post-pass: extract docstrings and rationale comments from Python source.
    Mutates result in-place by appending to result['nodes'] and result['edges'].
    """
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
        language = Language(tspython.language())
        parser = Parser(language)
        source = path.read_bytes()
        root = parser.parse(source).root_node
    except Exception:
        return

    stem = path.stem
    str_path = str(path)
    nodes = result["nodes"]
    edges = result["edges"]
    seen_ids = {n["id"] for n in nodes}
    file_nid = _make_id(stem)

    def _get_docstring(body_node) -> tuple[str, int] | None:
        if not body_node:
            return None
        for child in body_node.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type in ("string", "concatenated_string"):
                        text = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                        text = text.strip("\"'").strip('"""').strip("'''").strip()
                        if len(text) > 20:
                            return text, child.start_point[0] + 1
            break
        return None

    def _add_rationale(text: str, line: int, parent_nid: str) -> None:
        label = text[:80].replace("\n", " ").strip()
        rid = _make_id(stem, "rationale", str(line))
        if rid not in seen_ids:
            seen_ids.add(rid)
            nodes.append({"id": rid, "label": label, "file_type": "rationale",
                          "source_file": str_path, "source_location": f"L{line}"})
        edges.append({"source": rid, "target": parent_nid, "relation": "rationale_for",
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    # Module-level docstring
    ds = _get_docstring(root)
    if ds:
        _add_rationale(ds[0], ds[1], file_nid)

    def walk_docstrings(node, parent_nid: str) -> None:
        t = node.type
        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            if name_node and body:
                class_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                nid = _make_id(stem, class_name)
                ds = _get_docstring(body)
                if ds:
                    _add_rationale(ds[0], ds[1], nid)
                for child in body.children:
                    walk_docstrings(child, nid)
            return
        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            if name_node and body:
                func_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                nid = _make_id(parent_nid, func_name) if parent_nid != file_nid else _make_id(stem, func_name)
                ds = _get_docstring(body)
                if ds:
                    _add_rationale(ds[0], ds[1], nid)
            return
        for child in node.children:
            walk_docstrings(child, parent_nid)

    walk_docstrings(root, file_nid)

    # Rationale comments
    source_text = source.decode("utf-8", errors="replace")
    for lineno, line_text in enumerate(source_text.splitlines(), start=1):
        stripped = line_text.strip()
        if any(stripped.startswith(p) for p in _RATIONALE_PREFIXES):
            _add_rationale(stripped, lineno, file_nid)


def resolve_cross_file_imports(per_file: list[dict], paths: list[Path]) -> list[dict]:
    """Turn file-level Python imports into class-level INFERRED edges.

    Two-pass: build global name→node_id map, then for each `from .X import A`
    emit direct INFERRED edges from local classes to the imported entity.
    """
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
    except ImportError:
        return []

    language = Language(tspython.language())
    parser = Parser(language)

    # Pass 1: stem → {ClassName: node_id}
    # Only index real code entities (functions/classes), not rationale/docstring nodes
    stem_to_entities: dict[str, dict[str, str]] = {}
    for file_result in per_file:
        for node in file_result.get("nodes", []):
            src = node.get("source_file", "")
            if not src:
                continue
            stem = Path(src).stem
            label = node.get("label", "")
            nid = node.get("id", "")
            # Skip rationale nodes and sentence-like labels (docstring descriptions)
            if node.get("file_type") == "rationale":
                continue
            if len(label.split()) > 5:
                continue
            if label and not label.endswith((")", ".py")) and "_" not in label[:1]:
                stem_to_entities.setdefault(stem, {})[label] = nid

    new_edges: list[dict] = []

    for file_result, path in zip(per_file, paths):
        stem = path.stem
        str_path = str(path)
        local_classes = [
            n["id"] for n in file_result.get("nodes", [])
            if n.get("source_file") == str_path
            and not n["label"].endswith((")", ".py"))
            and n["id"] != _make_id(stem)
            # Skip rationale/docstring nodes — they are not real code entities
            and n.get("file_type") != "rationale"
            # Skip nodes whose label looks like a sentence (docstring descriptions)
            and len(n["label"].split()) <= 5
        ]
        if not local_classes:
            continue
        try:
            source = path.read_bytes()
            tree = parser.parse(source)
        except Exception:
            continue

        def walk_imports(node) -> None:
            if node.type == "import_from_statement":
                target_stem: str | None = None
                for child in node.children:
                    if child.type == "relative_import":
                        for sub in child.children:
                            if sub.type == "dotted_name":
                                raw = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                                target_stem = raw.split(".")[-1]
                                break
                        break
                    if child.type == "dotted_name" and target_stem is None:
                        raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        target_stem = raw.split(".")[-1]
                if not target_stem or target_stem not in stem_to_entities:
                    return
                imported_names: list[str] = []
                past_import_kw = False
                for child in node.children:
                    if child.type == "import":
                        past_import_kw = True
                        continue
                    if not past_import_kw:
                        continue
                    if child.type == "dotted_name":
                        imported_names.append(
                            source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        )
                    elif child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            imported_names.append(
                                source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                            )
                line = node.start_point[0] + 1
                for name in imported_names:
                    tgt_nid = stem_to_entities[target_stem].get(name)
                    if tgt_nid:
                        for src_class_nid in local_classes:
                            new_edges.append({
                                "source": src_class_nid, "target": tgt_nid,
                                "relation": "uses", "confidence": "INFERRED",
                                "source_file": str_path,
                                "source_location": f"L{line}", "weight": 0.8,
                            })
            for child in node.children:
                walk_imports(child)

        walk_imports(tree.root_node)

    return new_edges


def resolve_python_module_dependencies(per_file: list[dict], paths: list[Path]) -> list[dict]:
    """Resolve Python file-level imports to local module nodes."""
    module_to_file_nid: dict[str, str] = {}
    stem_to_file_nid: dict[str, str] = {}

    for file_result, path in zip(per_file, paths):
        str_path = str(path)
        file_nid = _make_id(path.stem)
        stem_to_file_nid[path.stem] = file_nid
        parts = path.with_suffix("").parts
        for i in range(len(parts)):
            module_name = ".".join(parts[i:])
            module_to_file_nid[module_name] = file_nid
        for node in file_result.get("nodes", []):
            if node.get("id") == file_nid and node.get("source_file") == str_path:
                qname = node.get("qualified_name", "")
                if qname:
                    module_to_file_nid[qname] = file_nid
                break

    new_edges: list[dict] = []
    for file_result, path in zip(per_file, paths):
        str_path = str(path)
        file_nid = _make_id(path.stem)
        package_parts = list(path.with_suffix("").parts[:-1])

        def _resolve_candidate(import_path: str, imported_names: list[str] | None = None) -> str | None:
            candidates: list[str] = [import_path]
            imported_names = imported_names or []
            candidates.extend(f"{import_path}.{name}" for name in imported_names)
            if package_parts:
                joined = ".".join(package_parts)
                candidates.append(f"{joined}.{import_path}")
                candidates.extend(f"{joined}.{import_path}.{name}" for name in imported_names)

            for candidate in candidates:
                if candidate in module_to_file_nid:
                    return module_to_file_nid[candidate]
                tail = candidate.split(".")[-1]
                if tail in stem_to_file_nid:
                    return stem_to_file_nid[tail]
            return None

        for edge in file_result.get("edges", []):
            if edge.get("source") != file_nid or edge.get("relation") not in {"imports", "imports_from"}:
                continue
            import_path = edge.get("import_path", "")
            if not import_path:
                continue

            imported_names = [name.strip() for name in edge.get("import_names", "").split(",") if name.strip()]
            target_nid = _resolve_candidate(import_path, imported_names if edge.get("relation") == "imports_from" else [])
            if not target_nid or target_nid == file_nid:
                continue

            new_edges.append({
                "source": file_nid,
                "target": target_nid,
                "relation": edge.get("relation", "imports"),
                "confidence": "INFERRED",
                "confidence_score": 0.95,
                "source_file": str_path,
                "source_location": edge.get("source_location", ""),
                "weight": 0.95,
                "import_path": import_path,
            })

        try:
            source_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            source_text = ""
        for match in _PY_IMPORTLIB_RE.finditer(source_text):
            import_path = match.group(1)
            target_nid = _resolve_candidate(import_path)
            if not target_nid or target_nid == file_nid:
                continue

            lineno = source_text[:match.start()].count("\n") + 1
            new_edges.append({
                "source": file_nid,
                "target": target_nid,
                "relation": "imports",
                "confidence": "INFERRED",
                "confidence_score": 0.95,
                "source_file": str_path,
                "source_location": f"L{lineno}",
                "weight": 0.95,
                "import_path": import_path,
            })

        for match in _PY_IMPORT_RE.finditer(source_text):
            raw_modules = [part.strip() for part in match.group(1).split(",") if part.strip()]
            lineno = source_text[:match.start()].count("\n") + 1
            for raw_module in raw_modules:
                import_path = raw_module.split(" as ", 1)[0].strip()
                target_nid = _resolve_candidate(import_path)
                if not target_nid or target_nid == file_nid:
                    continue
                new_edges.append({
                    "source": file_nid,
                    "target": target_nid,
                    "relation": "imports",
                    "confidence": "INFERRED",
                    "confidence_score": 0.95,
                    "source_file": str_path,
                    "source_location": f"L{lineno}",
                    "weight": 0.95,
                    "import_path": import_path,
                })

        for match in _PY_FROM_IMPORT_RE.finditer(source_text):
            import_path = match.group(1)
            imported_names = [part.strip() for part in match.group(2).split(",") if part.strip()]
            lineno = source_text[:match.start()].count("\n") + 1
            target_nid = _resolve_candidate(import_path, imported_names)
            if not target_nid or target_nid == file_nid:
                continue
            new_edges.append({
                "source": file_nid,
                "target": target_nid,
                "relation": "imports_from",
                "confidence": "INFERRED",
                "confidence_score": 0.95,
                "source_file": str_path,
                "source_location": f"L{lineno}",
                "weight": 0.95,
                "import_path": import_path,
            })

    return _dedupe_edges(new_edges)


def _iter_local_code_nodes(file_result: dict, path: Path):
    str_path = str(path)
    file_nid = _make_id(path.stem)
    for node in file_result.get("nodes", []):
        if node.get("source_file") != str_path:
            continue
        if node.get("file_type") == "rationale":
            continue
        if node.get("id") == file_nid:
            continue
        label = node.get("label", "")
        if len(label.split()) > 5:
            continue
        yield node


def _entity_name_map(file_result: dict, path: Path) -> dict[str, str]:
    entity_map: dict[str, str] = {}
    for node in _iter_local_code_nodes(file_result, path):
        label = node.get("label", "").strip()
        if not label:
            continue
        clean = label.lstrip(".")
        if clean.endswith("()"):
            clean = clean[:-2]
        if clean:
            entity_map.setdefault(clean, node["id"])
    return entity_map


def _module_node_id(path: Path) -> str:
    return _make_id(path.stem)


def _declared_package(path: Path) -> str:
    if path.suffix not in _JAVA_KOTLIN_SUFFIXES:
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    match = _PACKAGE_RE.search(text)
    return match.group(1).strip() if match else ""


def _swift_module_name(path: Path) -> str:
    parts = list(path.parts)
    if "Sources" in parts:
        idx = parts.index("Sources")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if "Tests" in parts:
        idx = parts.index("Tests")
        if idx + 1 < len(parts):
            name = parts[idx + 1]
            return name[:-5] if name.endswith("Tests") else name
    return path.parent.name


def _resolve_relative_js_import(raw_import: str, source_path: Path, known_paths: set[Path]) -> Path | None:
    if not raw_import.startswith("."):
        return None

    base = source_path.parent / raw_import
    suffix = Path(raw_import).suffix
    candidates: list[Path] = []
    if suffix:
        candidates.append(base)
    else:
        for ext in _JS_TS_SUFFIXES:
            candidates.append(base.with_suffix(ext))
        for ext in _JS_TS_SUFFIXES:
            candidates.append(base / f"index{ext}")

    for candidate in candidates:
        if candidate in known_paths:
            return candidate
    return None


def _dedupe_edges(edges: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[dict] = []
    for edge in edges:
        key = (
            edge.get("source", ""),
            edge.get("target", ""),
            edge.get("relation", ""),
            edge.get("source_file", ""),
            edge.get("source_location", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(edge)
    return unique


def resolve_cross_file_js_ts_imports(per_file: list[dict], paths: list[Path]) -> list[dict]:
    """Resolve relative JS/TS imports to real repo files and exported symbols.

    This is intentionally conservative:
    - only relative imports (`./`, `../`) are resolved
    - file-level imports are always connected when the target file exists
    - named imports additionally create coarse `uses` edges from local code
      entities to matched symbols in the target file
    """
    path_to_result = {path: result for result, path in zip(per_file, paths)}
    known_paths = set(path_to_result)
    entity_maps = {path: _entity_name_map(result, path) for path, result in path_to_result.items()}
    new_edges: list[dict] = []

    for path, file_result in path_to_result.items():
        if path.suffix not in _JS_TS_SUFFIXES:
            continue

        str_path = str(path)
        file_nid = _module_node_id(path)
        local_entities = [node["id"] for node in _iter_local_code_nodes(file_result, path)]

        for edge in file_result.get("edges", []):
            if edge.get("source") != file_nid or edge.get("relation") != "imports_from":
                continue

            raw_import = edge.get("import_path", "")
            if not raw_import.startswith("."):
                continue

            target_path = _resolve_relative_js_import(raw_import, path, known_paths)
            if target_path is None:
                continue

            target_file_nid = _module_node_id(target_path)
            line = edge.get("source_location", "")
            new_edges.append({
                "source": file_nid,
                "target": target_file_nid,
                "relation": "imports_from",
                "confidence": "INFERRED",
                "confidence_score": 0.95,
                "source_file": str_path,
                "source_location": line,
                "weight": 0.95,
                "import_path": raw_import,
                "resolved_target_file": str(target_path),
            })

            import_names = [name.strip() for name in edge.get("import_names", "").split(",") if name.strip()]
            if not import_names:
                continue

            target_entities = entity_maps.get(target_path, {})
            for import_name in import_names:
                target_nid = target_entities.get(import_name)
                if not target_nid:
                    continue
                sources = local_entities or [file_nid]
                for src_nid in sources:
                    new_edges.append({
                        "source": src_nid,
                        "target": target_nid,
                        "relation": "uses",
                        "confidence": "INFERRED",
                        "confidence_score": 0.8,
                        "source_file": str_path,
                        "source_location": line,
                        "weight": 0.8,
                        "import_path": raw_import,
                    })

    return _dedupe_edges(new_edges)


def resolve_cross_file_mobile_imports(per_file: list[dict], paths: list[Path]) -> list[dict]:
    """Resolve Java/Kotlin/Swift imports to local files and symbols when possible."""
    path_to_result = {path: result for result, path in zip(per_file, paths)}
    entity_maps = {path: _entity_name_map(result, path) for path, result in path_to_result.items()}

    qualified_symbol_map: dict[str, list[str]] = {}
    package_to_files: dict[str, list[str]] = {}
    swift_module_to_files: dict[str, list[str]] = {}
    swift_module_symbol_map: dict[tuple[str, str], list[str]] = {}

    for path, file_result in path_to_result.items():
        file_nid = _module_node_id(path)
        if path.suffix in _JAVA_KOTLIN_SUFFIXES:
            package = _declared_package(path)
            if package:
                package_to_files.setdefault(package, []).append(file_nid)
                for name, nid in entity_maps[path].items():
                    qualified_symbol_map.setdefault(f"{package}.{name}", []).append(nid)
        elif path.suffix == ".swift":
            module = _swift_module_name(path)
            if module:
                swift_module_to_files.setdefault(module, []).append(file_nid)
                for name, nid in entity_maps[path].items():
                    swift_module_symbol_map.setdefault((module, name), []).append(nid)

    new_edges: list[dict] = []

    for path, file_result in path_to_result.items():
        file_nid = _module_node_id(path)
        local_entities = [node["id"] for node in _iter_local_code_nodes(file_result, path)] or [file_nid]

        for edge in file_result.get("edges", []):
            if edge.get("source") != file_nid or edge.get("relation") not in {"imports", "imports_from"}:
                continue

            line = edge.get("source_location", "")

            if path.suffix in _JAVA_KOTLIN_SUFFIXES:
                raw_import = edge.get("import_path", "")
                if not raw_import:
                    continue
                import_symbol = edge.get("import_symbol", "")
                import_wildcard = bool(edge.get("import_wildcard"))
                package_name = raw_import[:-2] if import_wildcard and raw_import.endswith(".*") else raw_import.rsplit(".", 1)[0] if "." in raw_import else ""

                for target_file_nid in package_to_files.get(package_name, []):
                    if target_file_nid == file_nid:
                        continue
                    new_edges.append({
                        "source": file_nid,
                        "target": target_file_nid,
                        "relation": "imports",
                        "confidence": "INFERRED",
                        "confidence_score": 0.95,
                        "source_file": str(path),
                        "source_location": line,
                        "weight": 0.95,
                        "import_path": raw_import,
                    })

                if import_symbol and not import_wildcard:
                    for target_nid in qualified_symbol_map.get(raw_import, []):
                        for src_nid in local_entities:
                            if src_nid == target_nid:
                                continue
                            new_edges.append({
                                "source": src_nid,
                                "target": target_nid,
                                "relation": "uses",
                                "confidence": "INFERRED",
                                "confidence_score": 0.8,
                                "source_file": str(path),
                                "source_location": line,
                                "weight": 0.8,
                                "import_path": raw_import,
                            })

            elif path.suffix == ".swift":
                raw_import = edge.get("import_path", "")
                module_name = edge.get("import_module", "") or (raw_import.split(".", 1)[0] if raw_import else "")
                import_symbol = edge.get("import_symbol", "")
                if not module_name:
                    continue

                target_files = [nid for nid in swift_module_to_files.get(module_name, []) if nid != file_nid]
                if len(target_files) <= 12:
                    for target_file_nid in target_files:
                        new_edges.append({
                            "source": file_nid,
                            "target": target_file_nid,
                            "relation": "imports",
                            "confidence": "INFERRED",
                            "confidence_score": 0.9,
                            "source_file": str(path),
                            "source_location": line,
                            "weight": 0.9,
                            "import_path": raw_import,
                        })

                if import_symbol:
                    for target_nid in swift_module_symbol_map.get((module_name, import_symbol), []):
                        for src_nid in local_entities:
                            if src_nid == target_nid:
                                continue
                            new_edges.append({
                                "source": src_nid,
                                "target": target_nid,
                                "relation": "uses",
                                "confidence": "INFERRED",
                                "confidence_score": 0.8,
                                "source_file": str(path),
                                "source_location": line,
                                "weight": 0.8,
                                "import_path": raw_import,
                            })

    return _dedupe_edges(new_edges)


def resolve_cross_file_objc_imports(per_file: list[dict], paths: list[Path]) -> list[dict]:
    """Resolve local Objective-C imports to header/implementation files and classes."""
    path_to_result = {path: result for result, path in zip(per_file, paths)}
    known_paths = set(path_to_result)
    resolved_path_map = {p.resolve(): p for p in known_paths}
    entity_maps = {path: _entity_name_map(result, path) for path, result in path_to_result.items()}
    stem_to_files: dict[str, list[Path]] = {}
    for path in known_paths:
        stem_to_files.setdefault(path.stem, []).append(path)

    def _resolve_target_paths(source_path: Path, raw_import: str) -> list[Path]:
        target_paths: list[Path] = []
        candidate = (source_path.parent / raw_import).resolve()
        if candidate in resolved_path_map:
            target_paths.append(resolved_path_map[candidate])
        else:
            stem = Path(raw_import).stem
            target_paths.extend(stem_to_files.get(stem, []))
        return target_paths

    new_edges: list[dict] = []

    for path, file_result in path_to_result.items():
        if path.suffix not in _OBJC_SUFFIXES:
            continue

        file_nid = _module_node_id(path)
        local_entities = [node["id"] for node in _iter_local_code_nodes(file_result, path)] or [file_nid]

        for edge in file_result.get("edges", []):
            if edge.get("source") != file_nid or edge.get("relation") != "imports":
                continue
            if edge.get("import_system"):
                continue

            raw_import = edge.get("import_path", "")
            if not raw_import:
                continue

            target_paths = _resolve_target_paths(path, raw_import)

            line = edge.get("source_location", "")
            for target_path in target_paths:
                target_file_nid = _module_node_id(target_path)
                if target_file_nid != file_nid:
                    new_edges.append({
                        "source": file_nid,
                        "target": target_file_nid,
                        "relation": "imports",
                        "confidence": "INFERRED",
                        "confidence_score": 0.95,
                        "source_file": str(path),
                        "source_location": line,
                        "weight": 0.95,
                        "import_path": raw_import,
                    })

                import_stem = Path(raw_import).stem
                target_entities = entity_maps.get(target_path, {})
                class_nid = target_entities.get(import_stem)
                if class_nid and import_stem != path.stem:
                    for src_nid in local_entities:
                        if src_nid == class_nid:
                            continue
                        new_edges.append({
                            "source": src_nid,
                            "target": class_nid,
                            "relation": "uses",
                            "confidence": "INFERRED",
                            "confidence_score": 0.8,
                            "source_file": str(path),
                            "source_location": line,
                            "weight": 0.8,
                            "import_path": raw_import,
                        })

                # Implementation files often import their own header, which in turn
                # imports the real collaborators. Propagate one hop through that header.
                if target_path.suffix == ".h" and target_path.stem == path.stem:
                    header_result = path_to_result.get(target_path, {})
                    for header_edge in header_result.get("edges", []):
                        if header_edge.get("relation") != "imports" or header_edge.get("import_system"):
                            continue
                        header_import = header_edge.get("import_path", "")
                        if not header_import:
                            continue
                        for indirect_path in _resolve_target_paths(target_path, header_import):
                            indirect_entities = entity_maps.get(indirect_path, {})
                            indirect_stem = Path(header_import).stem
                            indirect_class_nid = indirect_entities.get(indirect_stem)
                            if not indirect_class_nid:
                                continue
                            for src_nid in local_entities:
                                if src_nid == indirect_class_nid:
                                    continue
                                new_edges.append({
                                    "source": src_nid,
                                    "target": indirect_class_nid,
                                    "relation": "uses",
                                    "confidence": "INFERRED",
                                    "confidence_score": 0.75,
                                    "source_file": str(path),
                                    "source_location": line,
                                    "weight": 0.75,
                                    "import_path": header_import,
                                })

    return _dedupe_edges(new_edges)
