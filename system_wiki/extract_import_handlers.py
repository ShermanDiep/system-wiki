# per-language import edge handlers — called by the generic AST walker for import nodes
from __future__ import annotations

import importlib

_core = importlib.import_module("system_wiki.extract_core")
_make_id = _core._make_id
_read_text = _core._read_text


def _parse_js_import_clause(text: str) -> tuple[list[str], bool, bool]:
    """Extract imported symbol names from a JS/TS import statement.

    Returns (named_imports, has_default_import, has_namespace_import).
    The names returned are export-side names, not local aliases.
    """
    stripped = " ".join(text.replace("\n", " ").split())
    if not stripped.startswith("import ") or " from " not in stripped:
        return [], False, False

    clause = stripped[len("import "):].split(" from ", 1)[0].strip().rstrip(";")
    if not clause:
        return [], False, False

    has_namespace = clause.startswith("* as ")
    has_default = False
    names: list[str] = []

    brace_start = clause.find("{")
    brace_end = clause.find("}", brace_start + 1) if brace_start != -1 else -1
    if brace_start != -1 and brace_end != -1:
        inside = clause[brace_start + 1:brace_end]
        for part in inside.split(","):
            raw = part.strip()
            if not raw:
                continue
            exported = raw.split(" as ", 1)[0].strip()
            if exported:
                names.append(exported)

    prefix = clause if brace_start == -1 else clause[:brace_start]
    prefix = prefix.strip().rstrip(",").strip()
    if prefix and not prefix.startswith("*"):
        has_default = True

    return names, has_default, has_namespace


def _import_python(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> None:
    t = node.type
    if t == "import_statement":
        for child in node.children:
            if child.type in ("dotted_name", "aliased_import"):
                raw = _read_text(child, source)
                module_name = raw.split(" as ")[0].strip().lstrip(".")
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid, "target": tgt_nid, "relation": "imports",
                    "confidence": "EXTRACTED", "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
                    "import_path": module_name,
                })
    elif t == "import_from_statement":
        module_node = node.child_by_field_name("module_name")
        if module_node:
            raw = _read_text(module_node, source).lstrip(".")
            tgt_nid = _make_id(raw)
            imported_names: list[str] = []
            past_import_kw = False
            for child in node.children:
                if child.type == "import":
                    past_import_kw = True
                    continue
                if not past_import_kw:
                    continue
                if child.type == "dotted_name":
                    imported_names.append(_read_text(child, source))
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        imported_names.append(_read_text(name_node, source))
            edges.append({
                "source": file_nid, "target": tgt_nid, "relation": "imports_from",
                "confidence": "EXTRACTED", "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
                "import_path": raw,
                "import_names": ",".join(imported_names),
            })


def _import_js(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> None:
    statement_text = _read_text(node, source)
    import_names, import_default, import_namespace = _parse_js_import_clause(statement_text)
    for child in node.children:
        if child.type == "string":
            raw = _read_text(child, source).strip("'\"` ")
            module_name = raw.lstrip("./").split("/")[-1]
            if module_name:
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid, "target": tgt_nid, "relation": "imports_from",
                    "confidence": "EXTRACTED", "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
                    "import_path": raw,
                    "import_names": ",".join(import_names),
                    "import_default": import_default,
                    "import_namespace": import_namespace,
                })
            break


def _import_java(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> None:
    def _walk_scoped(n) -> str:
        parts: list[str] = []
        cur = n
        while cur:
            if cur.type == "scoped_identifier":
                name_node = cur.child_by_field_name("name")
                if name_node:
                    parts.append(_read_text(name_node, source))
                cur = cur.child_by_field_name("scope")
            elif cur.type == "identifier":
                parts.append(_read_text(cur, source))
                break
            else:
                break
        parts.reverse()
        return ".".join(parts)

    for child in node.children:
        if child.type in ("scoped_identifier", "identifier"):
            path_str = _walk_scoped(child)
            module_name = path_str.split(".")[-1].strip("*").strip(".") or (
                path_str.split(".")[-2] if len(path_str.split(".")) > 1 else path_str
            )
            if module_name:
                import_symbol = ""
                import_wildcard = path_str.endswith(".*")
                if not import_wildcard and "." in path_str:
                    import_symbol = path_str.split(".")[-1].strip()
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid, "target": tgt_nid, "relation": "imports",
                    "confidence": "EXTRACTED", "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
                    "import_path": path_str,
                    "import_symbol": import_symbol,
                    "import_wildcard": import_wildcard,
                })
            break


def _import_c(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> None:
    for child in node.children:
        if child.type in ("string_literal", "system_lib_string", "string"):
            raw = _read_text(child, source).strip('"<> ')
            module_name = raw.split("/")[-1].split(".")[0]
            if module_name:
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid, "target": tgt_nid, "relation": "imports",
                    "confidence": "EXTRACTED", "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
                    "import_path": raw,
                    "import_system": child.type == "system_lib_string",
                })
            break


def _import_csharp(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> None:
    for child in node.children:
        if child.type in ("qualified_name", "identifier", "name_equals"):
            raw = _read_text(child, source)
            module_name = raw.split(".")[-1].strip()
            if module_name:
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid, "target": tgt_nid, "relation": "imports",
                    "confidence": "EXTRACTED", "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
                })
            break


def _import_kotlin(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> None:
    path_node = node.child_by_field_name("path")
    if path_node is None:
        for child in node.children:
            if child.type in ("qualified_identifier", "identifier"):
                path_node = child
                break
    if path_node:
        raw = _read_text(path_node, source)
        module_name = raw.split(".")[-1].strip()
        if module_name:
            import_symbol = ""
            import_wildcard = raw.endswith(".*")
            if not import_wildcard and "." in raw:
                import_symbol = raw.split(".")[-1].strip()
            tgt_nid = _make_id(module_name)
            edges.append({
                "source": file_nid, "target": tgt_nid, "relation": "imports",
                "confidence": "EXTRACTED", "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
                "import_path": raw,
                "import_symbol": import_symbol,
                "import_wildcard": import_wildcard,
            })
        return
    # Fallback: find identifier child
    for child in node.children:
        if child.type in ("identifier", "qualified_identifier"):
            raw = _read_text(child, source)
            module_name = raw.split(".")[-1].strip()
            tgt_nid = _make_id(module_name)
            edges.append({
                "source": file_nid, "target": tgt_nid, "relation": "imports",
                "confidence": "EXTRACTED", "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
                "import_path": raw,
                "import_symbol": module_name if "." in raw else "",
                "import_wildcard": raw.endswith(".*"),
            })
            break


def _import_scala(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> None:
    for child in node.children:
        if child.type in ("stable_id", "identifier"):
            raw = _read_text(child, source)
            module_name = raw.split(".")[-1].strip("{} ")
            if module_name and module_name != "_":
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid, "target": tgt_nid, "relation": "imports",
                    "confidence": "EXTRACTED", "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
                })
            break


def _import_php(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> None:
    for child in node.children:
        if child.type in ("qualified_name", "name", "identifier"):
            raw = _read_text(child, source)
            module_name = raw.split("\\")[-1].strip()
            if module_name:
                tgt_nid = _make_id(module_name)
                edges.append({
                    "source": file_nid, "target": tgt_nid, "relation": "imports",
                    "confidence": "EXTRACTED", "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
                })
            break


def _import_lua(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> None:
    """Extract require('module') from Lua variable_declaration nodes."""
    import re as _re
    text = _read_text(node, source)
    m = _re.search(r"""require\s*[\('"]\s*['"]?([^'")\s]+)""", text)
    if m:
        module_name = m.group(1).split(".")[-1]
        if module_name:
            edges.append({
                "source": file_nid, "target": module_name, "relation": "imports",
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": str_path,
                "source_location": str(node.start_point[0] + 1), "weight": 1.0,
            })


def _import_swift(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> None:
    statement_text = " ".join(_read_text(node, source).replace("\n", " ").split())
    raw = ""
    if statement_text.startswith("import "):
        payload = statement_text[len("import "):].strip().rstrip(";")
        parts = payload.split()
        if parts:
            if parts[0] in {"typealias", "struct", "class", "enum", "protocol", "let", "var", "func"} and len(parts) > 1:
                raw = parts[1]
            else:
                raw = parts[0]

    if not raw:
        for child in node.children:
            if child.type == "identifier":
                raw = _read_text(child, source)
                break

    if raw:
        module_name = raw.split(".")[0].strip()
        import_symbol = raw.split(".")[-1].strip() if "." in raw else ""
        tgt_nid = _make_id(module_name)
        edges.append({
            "source": file_nid, "target": tgt_nid, "relation": "imports",
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": f"L{node.start_point[0] + 1}", "weight": 1.0,
            "import_path": raw,
            "import_module": module_name,
            "import_symbol": import_symbol,
        })
