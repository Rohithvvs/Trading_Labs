"""Structured compile/runtime errors for the Pine-compatible subset."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class CompileIssue:
    line: int
    column: int
    message: str
    severity: str = "error"  # error | warning
    code: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class PineCompileError(Exception):
    def __init__(self, message: str, *, line: int = 0, column: int = 0, code: str | None = None):
        super().__init__(message)
        self.issue = CompileIssue(line=line, column=column, message=message, code=code)

    @property
    def line(self) -> int:
        return self.issue.line

    @property
    def column(self) -> int:
        return self.issue.column


class PineRuntimeError(Exception):
    def __init__(self, message: str, *, symbol: str | None = None):
        super().__init__(message)
        self.symbol = symbol
