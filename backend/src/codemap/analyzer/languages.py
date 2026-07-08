"""Language registry: which extensions we ingest and how deeply.

Deep tier: real import edges + class/function symbols via tree-sitter queries
(Python keeps its native ast path). Universal tier: any other extension with a
bundled tree-sitter grammar gets nodes, generic symbol extraction, and no edges.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def rust_module_name(repo: Path, file: Path) -> str:
    """Rust strategy: mod.rs files collapse to their directory."""
    parts = list(file.relative_to(repo).with_suffix("").parts)
    if parts and parts[-1] == "mod":
        parts = parts[:-1]
    return ".".join(parts) if parts else "root"


def path_module_name(repo: Path, file: Path) -> str:
    """C/C++ strategy: keep the extension so foo.c and foo.h stay distinct."""
    parts = list(file.relative_to(repo).parts)
    return ".".join(parts) if parts else "root"


def _within_repo(repo: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(repo.resolve())
    except ValueError:
        return False  # escaped the repo root
    return True


def _ancestor_dirs(repo: Path, file: Path) -> list[Path]:
    """The importing file's directory, then each parent up to the repo root."""
    root = repo.resolve()
    out: list[Path] = []
    current = file.resolve().parent
    while True:
        out.append(current)
        if current == root or current.parent == current:
            break
        current = current.parent
    return out


# Probing order for relative JS/TS specifiers: exact file first, then source
# extensions, then directory index files.
_JS_PROBES = ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js")


def resolve_js_import(repo: Path, file: Path, specifier: str) -> list[Path]:
    """Resolve a relative import specifier to a file inside the repo.

    Bare specifiers (packages, node builtins) are ignored in v1.1.
    """
    if not specifier.startswith("."):
        return []
    base = (file.parent / specifier).resolve()
    for probe in _JS_PROBES:
        candidate = Path(str(base) + probe) if probe else base
        if candidate.is_file():
            return [candidate] if _within_repo(repo, candidate) else []
    return []


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


# --- Go -----------------------------------------------------------------------


def _go_module(repo: Path, file: Path) -> tuple[str, Path] | None:
    """Nearest go.mod at or above the file: (module path, its directory)."""
    for ancestor in _ancestor_dirs(repo, file):
        gomod = ancestor / "go.mod"
        if not gomod.is_file():
            continue
        for raw in gomod.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line.startswith("module ") or line.startswith("module\t"):
                fields = line.split()
                if len(fields) >= 2:
                    return fields[1].strip('"'), ancestor
        return None
    return None


def resolve_go_import(repo: Path, file: Path, specifier: str) -> list[Path]:
    """Go: import paths under the nearest go.mod module prefix map to that
    package directory; the edge fans out to every .go file directly in it.
    Stdlib and other-module imports drop (same-module only in v1.1)."""
    found = _go_module(repo, file)
    if found is None:
        return []
    module, root = found
    if specifier == module:
        pkg_dir = root
    elif specifier.startswith(module + "/"):
        pkg_dir = root / specifier[len(module) + 1 :]
    else:
        return []
    if not pkg_dir.is_dir() or not _within_repo(repo, pkg_dir):
        return []
    return sorted(p for p in pkg_dir.iterdir() if p.is_file() and p.suffix == ".go")


GO_IMPORT_QUERY = """
(import_spec path: (interpreted_string_literal (interpreted_string_literal_content) @import))
"""

GO_SYMBOL_QUERY = """
(function_declaration name: (identifier) @function.name) @function.def
(method_declaration name: (field_identifier) @method.name) @method.def
(type_declaration
  (type_spec
    name: (type_identifier) @class.name
    type: [(struct_type) (interface_type)])) @class.def
"""


# --- Java / C# / PHP: dotted names -> directory paths --------------------------


def _resolve_dotted(
    repo: Path, file: Path, parts: list[str], ext: str, strip_root: bool = False
) -> list[Path]:
    """Map a dotted/namespaced import onto source paths, longest prefix first,
    trying every ancestor directory of the importing file as a source root.

    For each length of the (possibly truncated) namespace, also tries
    collapsing a leading run of segments into ONE literal dotted folder name
    before resuming normal per-segment nesting for the remainder. This is the
    common convention in .NET (and occasionally Java/PHP): a project's root
    namespace becomes a single folder whose name contains literal dots (e.g.
    "Statements.Core/Batch/…" for `using Statements.Core.Batch;`), not nested
    "Statements/Core/Batch/…" directories as Java's package convention would
    assume. Trying the smallest collapse first (k=1) reproduces the original
    fully-nested behavior exactly, so existing nested-convention resolution is
    unaffected.

    A file hit wins; a directory hit (package/namespace import) fans out to
    every source file directly inside it. strip_root additionally probes with
    the leading segment removed (root namespaces that do not exist on disk).
    """
    if not parts:
        return []
    variants = [parts]
    if strip_root and len(parts) > 1:
        variants.append(parts[1:])
    for ancestor in _ancestor_dirs(repo, file):
        for variant in variants:
            for end in range(len(variant), 0, -1):
                truncated = variant[:end]
                for collapse in range(1, len(truncated) + 1):
                    base = ancestor.joinpath(
                        ".".join(truncated[:collapse]), *truncated[collapse:]
                    )
                    candidate = base.with_name(base.name + ext)
                    if candidate.is_file() and _within_repo(repo, candidate):
                        return [candidate]
                    if base.is_dir() and _within_repo(repo, base):
                        hits = sorted(
                            p for p in base.iterdir() if p.is_file() and p.suffix == ext
                        )
                        if hits:
                            return hits
    return []


def resolve_java_import(repo: Path, file: Path, specifier: str) -> list[Path]:
    """Java: dotted package/type names -> directory paths (longest prefix);
    the ancestor walk discovers source roots like src/main/java."""
    return _resolve_dotted(repo, file, specifier.strip().split("."), ".java")


def resolve_csharp_import(repo: Path, file: Path, specifier: str) -> list[Path]:
    """C#: using namespaces -> directory paths, same strategy as Java."""
    return _resolve_dotted(repo, file, specifier.strip().split("."), ".cs")


def resolve_php_import(repo: Path, file: Path, specifier: str) -> list[Path]:
    """PHP `use`: PSR-4-ish best effort. Assumption: namespace separators map
    to directories under some ancestor of the importing file, and the leading
    segment (the composer root namespace, e.g. App\\) may not exist on disk,
    so we also probe with it stripped. composer.json maps are not consulted."""
    parts = [p for p in specifier.strip().lstrip("\\").split("\\") if p]
    return _resolve_dotted(repo, file, parts, ".php", strip_root=True)


JAVA_IMPORT_QUERY = """
(import_declaration (scoped_identifier) @import)
"""

JAVA_SYMBOL_QUERY = """
(class_declaration name: (identifier) @class.name) @class.def
(interface_declaration name: (identifier) @class.name) @class.def
(enum_declaration name: (identifier) @class.name) @class.def
(record_declaration name: (identifier) @class.name) @class.def
(method_declaration name: (identifier) @method.name) @method.def
(constructor_declaration name: (identifier) @method.name) @method.def
"""

CSHARP_IMPORT_QUERY = """
(using_directive [(qualified_name) (identifier)] @import)
"""

CSHARP_SYMBOL_QUERY = """
(class_declaration name: (identifier) @class.name) @class.def
(interface_declaration name: (identifier) @class.name) @class.def
(struct_declaration name: (identifier) @class.name) @class.def
(enum_declaration name: (identifier) @class.name) @class.def
(record_declaration name: (identifier) @class.name) @class.def
(method_declaration name: (identifier) @method.name) @method.def
(constructor_declaration name: (identifier) @method.name) @method.def
"""

PHP_IMPORT_QUERY = """
(namespace_use_clause (qualified_name) @import)
"""

PHP_SYMBOL_QUERY = """
(class_declaration name: (name) @class.name) @class.def
(interface_declaration name: (name) @class.name) @class.def
(trait_declaration name: (name) @class.name) @class.def
(enum_declaration name: (name) @class.name) @class.def
(function_definition name: (name) @function.name) @function.def
(method_declaration name: (name) @method.name) @method.def
"""


# --- Rust -----------------------------------------------------------------------


def _rust_crate_root(repo: Path, file: Path) -> Path:
    """Directory of the nearest lib.rs/main.rs at or above the file."""
    for ancestor in _ancestor_dirs(repo, file):
        if (ancestor / "lib.rs").is_file() or (ancestor / "main.rs").is_file():
            return ancestor
    return file.resolve().parent


def _probe_rust(base_dir: Path, parts: list[str]) -> Path | None:
    """x.rs then x/mod.rs, longest path prefix first."""
    for end in range(len(parts), 0, -1):
        stem = base_dir.joinpath(*parts[:end])
        for candidate in (stem.with_name(stem.name + ".rs"), stem / "mod.rs"):
            if candidate.is_file():
                return candidate
    return None


def resolve_rust_import(repo: Path, file: Path, specifier: str) -> list[Path]:
    """Rust: `mod x;` probes x.rs|x/mod.rs relative to the declaring module
    (lib/main/mod files own their directory; foo.rs owns foo/). `use crate::…`
    probes from the crate root; non-crate use paths are external and drop."""
    spec = specifier.strip()
    if "::" in spec or spec.startswith("crate"):
        if spec != "crate" and not spec.startswith("crate::"):
            return []
        segments: list[str] = []
        for raw in spec.split("::")[1:]:
            seg = raw.strip()
            if not _IDENT.match(seg):
                break  # brace groups, globs, `as` renames: keep the valid prefix
            segments.append(seg)
        if not segments:
            return []
        target = _probe_rust(_rust_crate_root(repo, file), segments)
    else:
        if not _IDENT.match(spec):
            return []
        resolved = file.resolve()
        owns_dir = resolved.stem in ("lib", "main", "mod")
        base = resolved.parent if owns_dir else resolved.parent / resolved.stem
        target = _probe_rust(base, [spec])
    if target is not None and _within_repo(repo, target):
        return [target]
    return []


RUST_IMPORT_QUERY = """
(mod_item name: (identifier) @import)
(use_declaration argument: (_) @import)
"""

RUST_SYMBOL_QUERY = """
(function_item name: (identifier) @function.name) @function.def
(struct_item name: (type_identifier) @class.name) @class.def
(enum_item name: (type_identifier) @class.name) @class.def
(trait_item name: (type_identifier) @class.name) @class.def
"""


# --- C / C++ --------------------------------------------------------------------


def resolve_c_include(repo: Path, file: Path, specifier: str) -> list[Path]:
    """C/C++: quoted includes resolve relative to the including file only
    (angle-bracket includes never reach here: the query skips them)."""
    candidate = file.resolve().parent / specifier
    if candidate.is_file() and _within_repo(repo, candidate):
        return [candidate]
    return []


C_IMPORT_QUERY = """
(preproc_include path: (string_literal (string_content) @import))
"""

C_SYMBOL_QUERY = """
(function_definition
  declarator: (function_declarator declarator: (identifier) @function.name)) @function.def
(struct_specifier
  name: (type_identifier) @class.name
  body: (field_declaration_list)) @class.def
"""

CPP_SYMBOL_QUERY = (
    C_SYMBOL_QUERY
    + """
(class_specifier name: (type_identifier) @class.name body: (field_declaration_list)) @class.def
(function_definition
  declarator: (function_declarator declarator: (field_identifier) @method.name)) @method.def
(function_definition
  declarator: (function_declarator declarator: (qualified_identifier) @function.name)) @function.def
"""
)


# --- Ruby -----------------------------------------------------------------------


def resolve_ruby_require(repo: Path, file: Path, specifier: str) -> list[Path]:
    """Ruby: require_relative paths resolve against the requiring file's dir."""
    base = file.resolve().parent / specifier
    for candidate in (Path(str(base) + ".rb"), base):
        if candidate.is_file() and _within_repo(repo, candidate):
            return [candidate]
    return []


RUBY_IMPORT_QUERY = """
(call
  method: (identifier) @_fn
  arguments: (argument_list (string (string_content) @import))
  (#eq? @_fn "require_relative"))
"""

RUBY_SYMBOL_QUERY = """
(class name: (constant) @class.name) @class.def
(module name: (constant) @class.name) @class.def
(method name: (identifier) @method.name) @method.def
(singleton_method name: (identifier) @method.name) @method.def
"""


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
    resolve_import: Callable[[Path, Path, str], list[Path]] | None = None


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
_GO = LanguageSpec(
    name="go",
    ts_language="go",
    tier="deep",
    import_query=GO_IMPORT_QUERY,
    symbol_query=GO_SYMBOL_QUERY,
    resolve_import=resolve_go_import,
)
_JAVA = LanguageSpec(
    name="java",
    ts_language="java",
    tier="deep",
    import_query=JAVA_IMPORT_QUERY,
    symbol_query=JAVA_SYMBOL_QUERY,
    resolve_import=resolve_java_import,
)
_RUST = LanguageSpec(
    name="rust",
    ts_language="rust",
    tier="deep",
    module_name=rust_module_name,
    import_query=RUST_IMPORT_QUERY,
    symbol_query=RUST_SYMBOL_QUERY,
    resolve_import=resolve_rust_import,
)
_CSHARP = LanguageSpec(
    name="csharp",
    ts_language="csharp",
    tier="deep",
    import_query=CSHARP_IMPORT_QUERY,
    symbol_query=CSHARP_SYMBOL_QUERY,
    resolve_import=resolve_csharp_import,
)
_C = LanguageSpec(
    name="c",
    ts_language="c",
    tier="deep",
    module_name=path_module_name,
    import_query=C_IMPORT_QUERY,
    symbol_query=C_SYMBOL_QUERY,
    resolve_import=resolve_c_include,
)
_CPP = LanguageSpec(
    name="cpp",
    ts_language="cpp",
    tier="deep",
    module_name=path_module_name,
    import_query=C_IMPORT_QUERY,
    symbol_query=CPP_SYMBOL_QUERY,
    resolve_import=resolve_c_include,
)
# The `.h` convention is shared by C and C++. Headers map to the C grammar
# first; when it rejects one (classes, namespaces, templates), the parser
# retries with this spec — the C++ grammar is a practical superset of C.
GRAMMAR_FALLBACKS: dict[str, LanguageSpec] = {".h": _CPP}

_RUBY = LanguageSpec(
    name="ruby",
    ts_language="ruby",
    tier="deep",
    import_query=RUBY_IMPORT_QUERY,
    symbol_query=RUBY_SYMBOL_QUERY,
    resolve_import=resolve_ruby_require,
)
_PHP = LanguageSpec(
    name="php",
    ts_language="php",
    tier="deep",
    import_query=PHP_IMPORT_QUERY,
    symbol_query=PHP_SYMBOL_QUERY,
    resolve_import=resolve_php_import,
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
    ".go": _GO,
    ".java": _JAVA,
    ".rs": _RUST,
    ".cs": _CSHARP,
    ".c": _C,
    ".h": _C,
    ".cpp": _CPP,
    ".cc": _CPP,
    ".cxx": _CPP,
    ".hpp": _CPP,
    ".hh": _CPP,
    ".rb": _RUBY,
    ".php": _PHP,
    # universal tier: symbol-count parsing only, no import edges.
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
