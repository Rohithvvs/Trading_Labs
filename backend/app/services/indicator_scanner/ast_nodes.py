"""AST nodes for the TradingLabs Pine subset. No executable payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass
class Span:
    line: int = 1
    column: int = 1


@dataclass
class Node:
    span: Span = field(default_factory=Span)


@dataclass
class NumberLit(Node):
    value: float = 0.0


@dataclass
class StringLit(Node):
    value: str = ""


@dataclass
class BoolLit(Node):
    value: bool = False


@dataclass
class NaLit(Node):
    pass


@dataclass
class Ident(Node):
    name: str = ""


@dataclass
class Member(Node):
    object: "Expr" = field(default_factory=lambda: Ident(name=""))
    attr: str = ""


@dataclass
class Index(Node):
    target: "Expr" = field(default_factory=lambda: Ident(name=""))
    offset: int = 0


@dataclass
class Call(Node):
    callee: "Expr" = field(default_factory=lambda: Ident(name=""))
    args: list["Expr"] = field(default_factory=list)
    kwargs: dict[str, "Expr"] = field(default_factory=dict)


@dataclass
class UnaryOp(Node):
    op: str = "-"
    expr: "Expr" = field(default_factory=NaLit)


@dataclass
class BinaryOp(Node):
    op: str = "+"
    left: "Expr" = field(default_factory=NaLit)
    right: "Expr" = field(default_factory=NaLit)


@dataclass
class Ternary(Node):
    condition: "Expr" = field(default_factory=NaLit)
    then_expr: "Expr" = field(default_factory=NaLit)
    else_expr: "Expr" = field(default_factory=NaLit)


Expr = Union[NumberLit, StringLit, BoolLit, NaLit, Ident, Member, Index, Call, UnaryOp, BinaryOp, Ternary]


@dataclass
class Assignment(Node):
    name: str = ""
    expr: Expr = field(default_factory=NaLit)


@dataclass
class ExprStmt(Node):
    expr: Expr = field(default_factory=NaLit)


Stmt = Union[Assignment, ExprStmt]


@dataclass
class Program:
    version: int | None
    statements: list[Stmt]
    source: str
    node_count: int = 0
