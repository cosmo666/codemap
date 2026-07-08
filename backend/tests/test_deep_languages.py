"""Stage-2 deep languages: exact import edges + symbols for Go, Java, Rust,
C#, C/C++, Ruby, and PHP against the polyglot fixture."""

from functools import cache
from pathlib import Path

from codemap.analyzer.graph import GraphData, build_graph
from codemap.analyzer.models import ParsedModule
from codemap.analyzer.parser import parse_module, parse_repo

POLYGLOT = Path(__file__).parent / "fixtures" / "demo_polyglot"


@cache
def _graph() -> GraphData:
    return build_graph(parse_repo(POLYGLOT))


def _edges(prefix: str) -> set[tuple[str, str]]:
    # These tests are exact-import-resolution assertions; the separate
    # folder-sibling "structural" edges (see test_graph.py) are out of scope
    # here and would make every exact set spuriously larger.
    return {
        (e.source, e.target)
        for e in _graph().edges
        if e.kind == "import" and (e.source.startswith(prefix) or e.target.startswith(prefix))
    }


def _parse(*rel: str) -> ParsedModule:
    pm = parse_module(POLYGLOT, POLYGLOT.joinpath(*rel))
    assert pm.info.status == "ok"
    return pm


# --- Go ------------------------------------------------------------------------


def test_go_imports_resolve_via_go_mod_module_prefix() -> None:
    info = _parse("go", "main.go").info
    assert info.language == "go"
    # example.com/demo/util -> every .go file in go/util; stdlib "fmt" drops
    assert info.imports == ["go.util.count", "go.util.strings"]
    assert [f.name for f in info.functions] == ["main"]
    assert info.functions[0].docstring == "Entry point for the demo CLI."


def test_go_symbols_structs_and_methods() -> None:
    info = _parse("go", "util", "strings.go").info
    assert info.imports == []  # stdlib "strings" is outside the module prefix
    assert [c.name for c in info.classes] == ["Labeler"]
    assert info.classes[0].docstring == "Labeler renders labels."
    assert [f.name for f in info.functions] == ["Upper", "Label"]
    assert info.functions[0].signature == "func Upper(s string) string {"


def test_go_edges_exact() -> None:
    assert _edges("go/") == {
        ("go/main.go", "go/util/count.go"),
        ("go/main.go", "go/util/strings.go"),
    }


# --- Java ----------------------------------------------------------------------


def test_java_imports_dotted_to_directory() -> None:
    info = _parse("java", "com", "acme", "app", "Main.java").info
    assert info.language == "java"
    assert info.imports == ["java.com.acme.util.Strings"]
    assert [c.name for c in info.classes] == ["Main"]
    assert info.classes[0].docstring == "Demo entry point."
    assert [m.name for m in info.classes[0].methods] == ["main"]


def test_java_symbols_and_edges() -> None:
    info = _parse("java", "com", "acme", "util", "Strings.java").info
    cls = info.classes[0]
    assert cls.name == "Strings" and cls.docstring == "String helpers."
    assert [m.name for m in cls.methods] == ["upper"]
    assert cls.methods[0].docstring == "Upper-cases a value."
    assert _edges("java/") == {
        ("java/com/acme/app/Main.java", "java/com/acme/util/Strings.java")
    }


# --- Rust ----------------------------------------------------------------------


def test_rust_mod_and_use_crate_resolution() -> None:
    info = _parse("rust", "src", "main.rs").info
    assert info.language == "rust"
    # mod helpers -> helpers.rs; mod util -> util/mod.rs; use crate::util::geometry
    assert info.imports == ["rust.src.helpers", "rust.src.util", "rust.src.util.geometry"]
    assert [f.name for f in info.functions] == ["main"]
    assert info.functions[0].docstring == "Entry point for the demo binary."


def test_rust_mod_rs_owns_its_directory() -> None:
    info = _parse("rust", "src", "util", "mod.rs").info
    assert info.module == "rust.src.util"  # mod.rs collapses to the directory
    assert info.imports == ["rust.src.util.geometry"]


def test_rust_symbols_doc_comments() -> None:
    info = _parse("rust", "src", "util", "geometry.rs").info
    assert info.imports == ["rust.src.helpers"]  # use crate::helpers::greet
    assert [c.name for c in info.classes] == ["Point"]
    assert info.classes[0].docstring == "A point on the plane."
    # impl methods surface as functions (impl blocks are not class captures)
    assert [f.name for f in info.functions] == ["origin", "norm"]
    assert info.functions[1].docstring == "Euclidean norm."


def test_rust_edges_exact() -> None:
    assert _edges("rust/") == {
        ("rust/src/main.rs", "rust/src/helpers.rs"),
        ("rust/src/main.rs", "rust/src/util/mod.rs"),
        ("rust/src/main.rs", "rust/src/util/geometry.rs"),
        ("rust/src/util/mod.rs", "rust/src/util/geometry.rs"),
        ("rust/src/util/geometry.rs", "rust/src/helpers.rs"),
    }


# --- C# ------------------------------------------------------------------------


def test_csharp_using_namespace_fans_out_to_directory() -> None:
    info = _parse("csharp", "Acme", "App", "Program.cs").info
    assert info.language == "csharp"
    assert info.imports == ["csharp.Acme.Util.Strings"]  # using Acme.Util;
    assert [c.name for c in info.classes] == ["Program"]
    assert info.classes[0].docstring == "Demo entry point."  # <summary> stripped


def test_csharp_symbols_and_edges() -> None:
    info = _parse("csharp", "Acme", "Util", "Strings.cs").info
    cls = info.classes[0]
    assert cls.name == "Strings" and cls.docstring == "String helpers."
    assert [m.name for m in cls.methods] == ["Upper"]
    assert cls.methods[0].docstring == "Upper-cases a value."
    assert _edges("csharp/Acme") == {
        ("csharp/Acme/App/Program.cs", "csharp/Acme/Util/Strings.cs")
    }


def test_csharp_dotted_project_folder_resolves() -> None:
    # Real-world .NET convention: the project ROOT namespace segment(s) collapse
    # into a single folder name that contains literal dots (e.g. "Statements.Core",
    # matching the .csproj's RootNamespace), NOT a nested Statements/Core/ path as
    # Java's package convention would assume. `using Statements.Core.Batch;` from a
    # sibling project (`DpSecure.Web`) must still resolve to that directory.
    info = _parse("csharp", "DpSecure.Web", "Pages", "BatchProcessesModel.cs").info
    assert info.imports == ["csharp.Statements.Core.Batch.BatchRepository"]
    assert _edges("csharp/DpSecure.Web") == {
        (
            "csharp/DpSecure.Web/Pages/BatchProcessesModel.cs",
            "csharp/Statements.Core/Batch/BatchRepository.cs",
        )
    }


# --- C / C++ ---------------------------------------------------------------------


def test_c_quoted_includes_only() -> None:
    info = _parse("c", "src", "main.c").info
    assert info.language == "c"
    assert info.imports == ["c.src.util.strings.h"]  # <stdio.h>-style never resolves
    assert [f.name for f in info.functions] == ["main"]
    header = _parse("c", "src", "util", "strings.h").info
    assert header.language == "c"  # plain-C .h stays on the C grammar
    assert [c.name for c in header.classes] == ["counted"]
    assert header.classes[0].docstring == "A counted string."


def test_c_edges_exact() -> None:
    assert _edges("c/") == {
        ("c/src/main.c", "c/src/util/strings.h"),
        ("c/src/util/strings.c", "c/src/util/strings.h"),
    }


def test_cpp_class_with_inline_method() -> None:
    info = _parse("cpp", "geometry.hpp").info
    assert info.language == "cpp"
    assert [c.name for c in info.classes] == ["Rect"]
    assert [m.name for m in info.classes[0].methods] == ["area"]
    assert info.classes[0].methods[0].docstring == "Computes the area."
    main = _parse("cpp", "main.cpp").info
    assert main.imports == ["cpp.geometry.hpp"]
    assert [f.name for f in main.functions] == ["doubled", "main"]
    assert _edges("cpp/") == {
        ("cpp/main.cpp", "cpp/geometry.hpp"),
        ("cpp/widget.h", "cpp/geometry.hpp"),
    }


def test_cpp_header_with_h_extension_retries_cpp_grammar() -> None:
    # .h maps to the C grammar first; a C++-style header (namespace/class) must
    # be retried under the C++ grammar instead of degrading to parse_error.
    info = _parse("cpp", "widget.h").info
    assert info.language == "cpp"
    assert info.imports == ["cpp.geometry.hpp"]
    assert [c.name for c in info.classes] == ["Widget"]
    cls = info.classes[0]
    assert cls.docstring == "A widget that wraps a rectangle."
    assert [m.name for m in cls.methods] == ["size"]
    assert cls.methods[0].docstring == "Number of rectangles tracked."


# --- Ruby ----------------------------------------------------------------------


def test_ruby_require_relative() -> None:
    info = _parse("ruby", "app.rb").info
    assert info.language == "ruby"
    assert info.imports == ["ruby.lib.greeter"]
    greeter = _parse("ruby", "lib", "greeter.rb").info
    cls = greeter.classes[0]
    assert cls.name == "Greeter" and cls.docstring == "Greets people by name."
    assert [m.name for m in cls.methods] == ["hello", "build"]
    assert cls.methods[1].docstring == "Builds a default greeter."
    assert _edges("ruby/") == {("ruby/app.rb", "ruby/lib/greeter.rb")}


# --- PHP -----------------------------------------------------------------------


def test_php_use_psr4_best_effort() -> None:
    info = _parse("php", "src", "index.php").info
    assert info.language == "php"
    # use App\Util\Strings: the App\ root namespace is not on disk; the
    # stripped-root probe finds src/Util/Strings.php
    assert info.imports == ["php.src.Util.Strings"]
    assert [f.name for f in info.functions] == ["banner"]
    assert info.functions[0].docstring == "Prints the banner."
    strings = _parse("php", "src", "Util", "Strings.php").info
    cls = strings.classes[0]
    assert cls.name == "Strings" and cls.docstring == "String helpers."
    assert [m.name for m in cls.methods] == ["upper"]
    assert _edges("php/") == {("php/src/index.php", "php/src/Util/Strings.php")}
