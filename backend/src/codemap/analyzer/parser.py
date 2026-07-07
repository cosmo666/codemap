import ast
from pathlib import Path

from codemap.analyzer.models import ClassInfo, FunctionInfo, ModuleInfo, ParsedModule

_SKIP_DIRS = {"__pycache__", "node_modules", ".codemap", "venv"}


def discover_python_files(repo: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(repo.rglob("*.py")):
        rel_parts = path.relative_to(repo).parts
        if any(p in _SKIP_DIRS or p.startswith(".") for p in rel_parts):
            continue
        files.append(path)
    return files


def _dotted(repo: Path, file: Path) -> str:
    rel = file.relative_to(repo).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "root"


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
        return [node.module] if node.module else []
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


def parse_module(repo: Path, file: Path) -> ParsedModule:
    rel_posix = file.relative_to(repo).as_posix()
    parts = file.relative_to(repo).parts
    package = parts[0] if len(parts) > 1 else "root"
    is_package = file.name == "__init__.py"
    source = file.read_text(encoding="utf-8", errors="replace")
    module_dotted = _dotted(repo, file)
    base = ModuleInfo(
        path=rel_posix,
        module=module_dotted,
        package=package,
        imports=[],
        classes=[],
        functions=[],
        docstring=None,
        loc=source.count("\n") + 1,
        status="ok",
    )
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return ParsedModule(info=base.model_copy(update={"status": "parse_error"}), source=source)

    imports: list[str] = []
    classes: list[ClassInfo] = []
    functions: list[FunctionInfo] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(_resolve_from_import(module_dotted, node, is_package))
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

    info = base.model_copy(
        update={
            "imports": sorted(set(imports)),
            "classes": classes,
            "functions": functions,
            "docstring": ast.get_docstring(tree),
        }
    )
    return ParsedModule(info=info, source=source)


def parse_repo(repo: Path) -> list[ParsedModule]:
    return [parse_module(repo, f) for f in discover_python_files(repo)]
