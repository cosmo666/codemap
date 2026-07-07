from codemap.analyzer.models import ParsedModule


def build_skeleton(pm: ParsedModule, max_chars: int = 16000) -> str:
    """Signatures + docstrings + imports: what the LLM sees for one module."""
    info = pm.info
    lines: list[str] = [f"# Module: {info.path} ({info.module})"]
    if info.docstring:
        lines.append(f'"""{info.docstring}"""')
    for imp in info.imports:
        lines.append(f"import {imp}")
    for func in info.functions:
        lines.append(func.signature + ":")
        if func.docstring:
            lines.append(f'    """{func.docstring}"""')
    for cls in info.classes:
        lines.append(f"class {cls.name}:")
        if cls.docstring:
            lines.append(f'    """{cls.docstring}"""')
        for method in cls.methods:
            lines.append(f"    {method.signature}:")
            if method.docstring:
                lines.append(f'        """{method.docstring}"""')
    return "\n".join(lines)[:max_chars]
