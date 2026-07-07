import ast
import re
from functools import cache
from pathlib import Path
from typing import cast

from tree_sitter import Language, Node, Parser, Query, QueryCursor
from tree_sitter_language_pack import SupportedLanguage, get_language

from codemap.analyzer.languages import EXT_TO_LANGUAGE, LanguageSpec
from codemap.analyzer.models import ClassInfo, FunctionInfo, ModuleInfo, ParsedModule

_SKIP_DIRS = {"__pycache__", "node_modules", ".codemap", "venv"}
_MAX_FILE_BYTES = 1_572_864  # 1.5 MB: anything larger is generated or vendored


def discover_source_files(repo: Path) -> list[Path]:
    """Every registered-language file in the repo, minus junk dirs, minified
    bundles, and oversized files."""
    files: list[Path] = []
    for path in sorted(repo.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EXT_TO_LANGUAGE:
            continue
        rel_parts = path.relative_to(repo).parts
        if any(p in _SKIP_DIRS or p.startswith(".") for p in rel_parts):
            continue
        suffixes = [s.lower() for s in path.suffixes]
        if len(suffixes) >= 2 and suffixes[-2] == ".min":
            continue
        if path.stat().st_size > _MAX_FILE_BYTES:
            continue
        files.append(path)
    return files


def discover_python_files(repo: Path) -> list[Path]:
    return [f for f in discover_source_files(repo) if f.suffix.lower() == ".py"]


def _function_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
    return FunctionInfo(
        name=node.name,
        signature=f"def {node.name}({ast.unparse(node.args)})",
        lineno=node.lineno,
        end_lineno=node.end_lineno or node.lineno,
        docstring=ast.get_docstring(node),
    )


def _resolve_from_import(
    module_dotted: str, node: ast.ImportFrom, is_package: bool
) -> list[str]:
    if node.level == 0:
        if node.module:
            candidates = [node.module]
            candidates.extend(f"{node.module}.{alias.name}" for alias in node.names)
            return candidates
        return []
    parts = module_dotted.split(".")
    drop = node.level - 1 if is_package else node.level
    if drop > len(parts):
        return []
    parts = parts[: len(parts) - drop]
    if node.module:
        parts = [*parts, node.module]
    prefix = ".".join(parts)
    if not prefix:
        return []
    if node.module:
        return [prefix]
    return [f"{prefix}.{alias.name}" for alias in node.names]


def _parse_python(base: ModuleInfo, source: str, is_package: bool) -> ModuleInfo:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return base.model_copy(update={"status": "parse_error"})

    imports: list[str] = []
    classes: list[ClassInfo] = []
    functions: list[FunctionInfo] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(_resolve_from_import(base.module, node, is_package))
        elif isinstance(node, ast.ClassDef):
            methods = [
                _function_info(n)
                for n in node.body
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            classes.append(
                ClassInfo(
                    name=node.name,
                    lineno=node.lineno,
                    end_lineno=node.end_lineno or node.lineno,
                    docstring=ast.get_docstring(node),
                    methods=methods,
                )
            )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            functions.append(_function_info(node))

    return base.model_copy(
        update={
            "imports": sorted(set(imports)),
            "classes": classes,
            "functions": functions,
            "docstring": ast.get_docstring(tree),
        }
    )


# --- tree-sitter path ---------------------------------------------------------


@cache
def _load_language(ts_language: str) -> Language | None:
    try:
        return get_language(cast(SupportedLanguage, ts_language))
    except Exception:  # noqa: BLE001 - a missing grammar must never be fatal
        return None


@cache
def _compile_query(ts_language: str, query_source: str) -> Query:
    language = _load_language(ts_language)
    if language is None:
        raise LookupError(f"no tree-sitter grammar for {ts_language!r}")
    return Query(language, query_source)


def _decode(node: Node) -> str:
    return (node.text or b"").decode("utf-8", errors="replace")


def _clean_comment(text: str) -> str:
    cleaned: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("/**"):
            line = line[3:]
        elif line.startswith(("/*", "//", "--")):
            line = line[2:]
        elif line.startswith(("#", "*")):
            line = line[1:]
        if line.endswith("*/"):
            line = line[:-2]
        line = line.strip()
        if line:
            cleaned.append(line)
    return " ".join(cleaned)


def _doc_comment(node: Node) -> str | None:
    """Comment ending on the line directly above the declaration (or its
    export wrapper), cleaned of comment markers."""
    current = node
    while current.parent is not None and current.parent.type == "export_statement":
        current = current.parent
    prev = current.prev_named_sibling
    if prev is None or "comment" not in prev.type:
        return None
    if prev.end_point.row < current.start_point.row - 1:
        return None  # blank line between comment and declaration
    return _clean_comment(_decode(prev)) or None


def _function_from_node(name: str, node: Node, lines: list[str]) -> FunctionInfo:
    row = node.start_point.row  # tree-sitter rows are 0-based; linenos are 1-based
    return FunctionInfo(
        name=name,
        signature=lines[row].strip() if row < len(lines) else name,
        lineno=row + 1,
        end_lineno=node.end_point.row + 1,
        docstring=_doc_comment(node),
    )


def _class_from_node(name: str, node: Node) -> ClassInfo:
    return ClassInfo(
        name=name,
        lineno=node.start_point.row + 1,
        end_lineno=node.end_point.row + 1,
        docstring=_doc_comment(node),
        methods=[],
    )


def _ts_imports(spec: LanguageSpec, root: Node, repo: Path, file: Path) -> list[str]:
    if spec.import_query is None or spec.resolve_import is None:
        return []
    query = _compile_query(spec.ts_language, spec.import_query)
    modules: set[str] = set()
    for node in QueryCursor(query).captures(root).get("import", []):
        target = spec.resolve_import(repo, file, _decode(node))
        if target is None:
            continue
        target_spec = EXT_TO_LANGUAGE.get(target.suffix.lower())
        if target_spec is not None:
            modules.add(target_spec.module_name(repo, target))
    return sorted(modules)


_CAPTURE_KINDS = ("function", "class", "method")


def _ts_symbols(
    spec: LanguageSpec, root: Node, lines: list[str]
) -> tuple[list[ClassInfo], list[FunctionInfo]]:
    if spec.symbol_query is None:
        return [], []
    query = _compile_query(spec.ts_language, spec.symbol_query)
    records: list[tuple[str, str, Node]] = []
    for _pattern, match in QueryCursor(query).matches(root):
        for kind in _CAPTURE_KINDS:
            defs = match.get(f"{kind}.def")
            names = match.get(f"{kind}.name")
            if defs and names:
                records.append((kind, _decode(names[0]), defs[0]))

    # Nested defs (closures, functions inside methods) stay invisible, matching
    # the Python path which only reads module top-level statements.
    def_ranges = [
        (n.start_byte, n.end_byte) for k, _, n in records if k in ("function", "method")
    ]

    def nested(node: Node) -> bool:
        return any(s < node.start_byte and node.end_byte <= e for s, e in def_ranges)

    classes: list[tuple[ClassInfo, int, int]] = []
    pending: list[tuple[str, Node, FunctionInfo]] = []
    for kind, name, node in records:
        if nested(node):
            continue
        if kind == "class":
            classes.append((_class_from_node(name, node), node.start_byte, node.end_byte))
        else:
            pending.append((kind, node, _function_from_node(name, node, lines)))
    functions: list[FunctionInfo] = []
    for _kind, node, fn in pending:
        owner = next(
            (c for c, s, e in classes if s <= node.start_byte and node.end_byte <= e),
            None,
        )
        if owner is not None:
            owner.methods.append(fn)
        else:
            functions.append(fn)
    for cls, _, _ in classes:
        cls.methods.sort(key=lambda m: m.lineno)
    return (
        sorted((c for c, _, _ in classes), key=lambda c: c.lineno),
        sorted(functions, key=lambda f: f.lineno),
    )


_FUNC_TYPES = re.compile(
    r"(function|method|func|fun)_(declaration|definition|item|statement)$"
)
_FUNC_EXACT = {"method", "singleton_method", "subroutine_declaration_statement"}
_CLASS_TYPES = re.compile(
    r"(class|interface|trait|struct|enum|object|protocol|impl)"
    r"_(declaration|definition|specifier|item|statement)$"
)
_CLASS_EXACT = {"class", "module"}


def _node_name(node: Node) -> str | None:
    named = node.child_by_field_name("name")
    if named is not None:
        return _decode(named)
    for child in node.children:
        if "identifier" in child.type or child.type == "name":
            return _decode(child)
    return None


def _generic_symbols(
    root: Node, lines: list[str]
) -> tuple[list[ClassInfo], list[FunctionInfo]]:
    """Best-effort symbol walk for universal-tier grammars: nodes whose types
    look like function/class declarations, methods nested under classes."""
    classes: list[ClassInfo] = []
    functions: list[FunctionInfo] = []

    def walk(node: Node, owner: ClassInfo | None, depth: int) -> None:
        if depth > 12:
            return
        for child in node.named_children:
            ctype = child.type
            if _CLASS_TYPES.search(ctype) or ctype in _CLASS_EXACT:
                name = _node_name(child)
                if name is None:
                    walk(child, owner, depth + 1)
                    continue
                cls = _class_from_node(name, child)
                classes.append(cls)
                walk(child, cls, depth + 1)
            elif _FUNC_TYPES.search(ctype) or ctype in _FUNC_EXACT:
                name = _node_name(child)
                if name is not None:
                    target = owner.methods if owner is not None else functions
                    target.append(_function_from_node(name, child, lines))
                # function bodies are not descended into: nested defs stay invisible
            else:
                walk(child, owner, depth + 1)

    walk(root, None, 0)
    return classes, functions


def _parse_with_treesitter(
    spec: LanguageSpec, repo: Path, file: Path, source: str, base: ModuleInfo
) -> ModuleInfo:
    language = _load_language(spec.ts_language)
    if language is None:
        if spec.tier == "universal":
            return base  # raw fallback: node with no symbols, status stays ok
        return base.model_copy(update={"status": "parse_error"})
    try:
        tree = Parser(language).parse(source.encode("utf-8"))
        lines = source.splitlines()
        if spec.tier == "deep":
            if tree.root_node.has_error:
                return base.model_copy(update={"status": "parse_error"})
            classes, functions = _ts_symbols(spec, tree.root_node, lines)
            return base.model_copy(
                update={
                    "imports": _ts_imports(spec, tree.root_node, repo, file),
                    "classes": classes,
                    "functions": functions,
                }
            )
        classes, functions = _generic_symbols(tree.root_node, lines)
        return base.model_copy(update={"classes": classes, "functions": functions})
    except Exception:  # noqa: BLE001 - grammar failures must never kill analysis
        return base.model_copy(update={"status": "parse_error"})


def parse_module(repo: Path, file: Path) -> ParsedModule:
    rel = file.relative_to(repo)
    parts = rel.parts
    spec = EXT_TO_LANGUAGE[file.suffix.lower()]
    source = file.read_text(encoding="utf-8", errors="replace")
    base = ModuleInfo(
        path=rel.as_posix(),
        module=spec.module_name(repo, file),
        package=parts[0] if len(parts) > 1 else "root",
        imports=[],
        classes=[],
        functions=[],
        docstring=None,
        loc=source.count("\n") + 1,
        status="ok",
        language=spec.name,
    )
    if spec.name == "python":
        info = _parse_python(base, source, is_package=file.name == "__init__.py")
    else:
        info = _parse_with_treesitter(spec, repo, file, source, base)
    return ParsedModule(info=info, source=source)


def parse_repo(repo: Path) -> list[ParsedModule]:
    return [parse_module(repo, f) for f in discover_source_files(repo)]
