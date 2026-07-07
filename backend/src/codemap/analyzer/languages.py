"""Language registry: which extensions we ingest and how deeply.

Deep tier: real import edges + class/function symbols via tree-sitter queries
(Python keeps its native ast path). Universal tier: any other extension with a
bundled tree-sitter grammar gets nodes, generic symbol extraction, and no edges.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


def dotted_module_name(repo: Path, file: Path) -> str:
    """Generic strategy: path without extension, '/' -> '.'."""
    parts = list(file.relative_to(repo).with_suffix("").parts)
    return ".".join(parts) if parts else "root"


def python_module_name(repo: Path, file: Path) -> str:
    """Python strategy: __init__ collapses to its package directory."""
    parts = list(file.relative_to(repo).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "root"


def js_module_name(repo: Path, file: Path) -> str:
    """JS/TS strategy: index files collapse to their directory."""
    parts = list(file.relative_to(repo).with_suffix("").parts)
    if parts and parts[-1] == "index":
        parts = parts[:-1]
    return ".".join(parts) if parts else "root"


# Probing order for relative JS/TS specifiers: exact file first, then source
# extensions, then directory index files.
_JS_PROBES = ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js")


def resolve_js_import(repo: Path, file: Path, specifier: str) -> Path | None:
    """Resolve a relative import specifier to a file inside the repo, or None.

    Bare specifiers (packages, node builtins) are ignored in v1.1.
    """
    if not specifier.startswith("."):
        return None
    base = (file.parent / specifier).resolve()
    for probe in _JS_PROBES:
        candidate = Path(str(base) + probe) if probe else base
        if candidate.is_file():
            try:
                candidate.resolve().relative_to(repo.resolve())
            except ValueError:
                return None  # escaped the repo root
            return candidate
    return None


JS_IMPORT_QUERY = """
(import_statement source: (string (string_fragment) @import))
(export_statement source: (string (string_fragment) @import))
(call_expression
  function: (identifier) @_fn
  arguments: (arguments (string (string_fragment) @import))
  (#eq? @_fn "require"))
"""

_JS_SYMBOL_QUERY_BASE = """
(function_declaration name: (_) @function.name) @function.def
(generator_function_declaration name: (_) @function.name) @function.def
(class_declaration name: (_) @class.name) @class.def
(method_definition name: (_) @method.name) @method.def
(lexical_declaration
  (variable_declarator
    name: (identifier) @function.name
    value: [(arrow_function) (function_expression)])) @function.def
"""

JS_SYMBOL_QUERY = _JS_SYMBOL_QUERY_BASE

TS_SYMBOL_QUERY = (
    _JS_SYMBOL_QUERY_BASE
    + """
(abstract_class_declaration name: (_) @class.name) @class.def
"""
)


@dataclass(frozen=True)
class LanguageSpec:
    """How one language is discovered, parsed, and named.

    ts_language is the tree_sitter_language_pack grammar key. Deep languages
    carry queries + an import resolver; universal ones parse for symbols only.
    """

    name: str
    ts_language: str
    tier: Literal["deep", "universal"]
    module_name: Callable[[Path, Path], str] = dotted_module_name
    import_query: str | None = None
    symbol_query: str | None = None
    resolve_import: Callable[[Path, Path, str], Path | None] | None = None


_PYTHON = LanguageSpec(
    name="python", ts_language="python", tier="deep", module_name=python_module_name
)
_TYPESCRIPT = LanguageSpec(
    name="typescript",
    ts_language="typescript",
    tier="deep",
    module_name=js_module_name,
    import_query=JS_IMPORT_QUERY,
    symbol_query=TS_SYMBOL_QUERY,
    resolve_import=resolve_js_import,
)
_TSX = LanguageSpec(
    name="typescript",
    ts_language="tsx",
    tier="deep",
    module_name=js_module_name,
    import_query=JS_IMPORT_QUERY,
    symbol_query=TS_SYMBOL_QUERY,
    resolve_import=resolve_js_import,
)
_JAVASCRIPT = LanguageSpec(
    name="javascript",
    ts_language="javascript",
    tier="deep",
    module_name=js_module_name,
    import_query=JS_IMPORT_QUERY,
    symbol_query=JS_SYMBOL_QUERY,
    resolve_import=resolve_js_import,
)


def _universal(name: str, ts_language: str | None = None) -> LanguageSpec:
    return LanguageSpec(name=name, ts_language=ts_language or name, tier="universal")


EXT_TO_LANGUAGE: dict[str, LanguageSpec] = {
    # deep tier
    ".py": _PYTHON,
    ".ts": _TYPESCRIPT,
    ".tsx": _TSX,
    ".js": _JAVASCRIPT,
    ".jsx": _JAVASCRIPT,
    ".mjs": _JAVASCRIPT,
    ".cjs": _JAVASCRIPT,
    # universal tier: symbol-count parsing only, no import edges (deep support
    # for go/java/rust/csharp/c/cpp/ruby/php lands in a later stage).
    ".go": _universal("go"),
    ".java": _universal("java"),
    ".rs": _universal("rust"),
    ".cs": _universal("csharp"),
    ".c": _universal("c"),
    ".h": _universal("c"),
    ".cpp": _universal("cpp"),
    ".cc": _universal("cpp"),
    ".cxx": _universal("cpp"),
    ".hpp": _universal("cpp"),
    ".hh": _universal("cpp"),
    ".rb": _universal("ruby"),
    ".php": _universal("php"),
    ".kt": _universal("kotlin"),
    ".kts": _universal("kotlin"),
    ".swift": _universal("swift"),
    ".scala": _universal("scala"),
    ".sc": _universal("scala"),
    ".lua": _universal("lua"),
    ".ex": _universal("elixir"),
    ".exs": _universal("elixir"),
    ".erl": _universal("erlang"),
    ".hs": _universal("haskell"),
    ".dart": _universal("dart"),
    ".r": _universal("r"),
    ".jl": _universal("julia"),
    ".zig": _universal("zig"),
    ".sh": _universal("bash"),
    ".bash": _universal("bash"),
    ".pl": _universal("perl"),
    ".ml": _universal("ocaml"),
    ".clj": _universal("clojure"),
    ".groovy": _universal("groovy"),
    ".vue": _universal("vue"),
    ".svelte": _universal("svelte"),
}
