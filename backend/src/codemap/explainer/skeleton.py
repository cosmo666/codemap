from codemap.analyzer.models import ParsedModule


def build_skeleton(pm: ParsedModule, max_chars: int = 16000) -> str:
    """Signatures + doc comments + imports: what the LLM sees for one module.

    Files where no structure was extracted (universal-tier or raw-fallback
    languages) get the raw source instead, under the same character budget.
    """
    info = pm.info
    header = [
        f"# Module: {info.path} ({info.module})",
        f"# Language: {info.language}",
    ]
    is_python = info.language == "python"
    has_structure = bool(info.classes or info.functions or info.imports or info.docstring)
    if not is_python and not has_structure:
        header.append("# No symbols extracted; raw source follows.")
        return "\n".join([*header, pm.source])[:max_chars]

    lines = header
    if info.docstring:
        lines.append(f'"""{info.docstring}"""')
    for imp in info.imports:
        lines.append(f"import {imp}")
    colon = ":" if is_python else ""
    for func in info.functions:
        lines.append(func.signature + colon)
        if func.docstring:
            lines.append(f'    """{func.docstring}"""')
    for cls in info.classes:
        lines.append(f"class {cls.name}{colon}")
        if cls.docstring:
            lines.append(f'    """{cls.docstring}"""')
        for method in cls.methods:
            lines.append(f"    {method.signature}{colon}")
            if method.docstring:
                lines.append(f'        """{method.docstring}"""')
    return "\n".join(lines)[:max_chars]
