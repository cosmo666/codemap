from typing import Literal

from pydantic import BaseModel


class FunctionInfo(BaseModel):
    name: str
    signature: str
    lineno: int
    end_lineno: int
    docstring: str | None


class ClassInfo(BaseModel):
    name: str
    lineno: int
    end_lineno: int
    docstring: str | None
    methods: list[FunctionInfo]


class ModuleInfo(BaseModel):
    path: str
    module: str
    package: str
    imports: list[str]
    classes: list[ClassInfo]
    functions: list[FunctionInfo]
    docstring: str | None
    loc: int
    status: Literal["ok", "parse_error"]


class ParsedModule(BaseModel):
    info: ModuleInfo
    source: str
