"""Recursive-descent parser for the TradingLabs Pine subset."""

from __future__ import annotations

import re

from .ast_nodes import (
    Assignment,
    BinaryOp,
    BoolLit,
    Call,
    Expr,
    ExprStmt,
    Ident,
    Index,
    Member,
    NaLit,
    NumberLit,
    Program,
    Span,
    Stmt,
    StringLit,
    Ternary,
    UnaryOp,
)
from .errors import PineCompileError
from .limits import MAX_AST_NODES, MAX_EXPRESSION_DEPTH, MAX_STATEMENTS
from .tokenizer import TOKEN_EOF, TOKEN_IDENT, TOKEN_NUMBER, TOKEN_STRING, TOKEN_VERSION, Token, tokenize


class Parser:
    def __init__(self, source: str):
        self.source = source
        self.tokens = tokenize(source)
        self.i = 0
        self.node_count = 0
        self.version: int | None = None

    def parse(self) -> Program:
        while self._check(TOKEN_VERSION):
            self._parse_version(self._advance())
        statements: list[Stmt] = []
        while not self._check(TOKEN_EOF):
            if len(statements) >= MAX_STATEMENTS:
                tok = self._peek()
                raise PineCompileError(
                    f"Script exceeds the {MAX_STATEMENTS} statement limit.",
                    line=tok.line,
                    column=tok.column,
                    code="TOO_MANY_STATEMENTS",
                )
            statements.append(self._statement())
        if self.version is None:
            self.version = 6
        return Program(version=self.version, statements=statements, source=self.source, node_count=self.node_count)

    def _parse_version(self, tok: Token) -> None:
        match = re.search(r"//@version\s*=\s*(\d+)", tok.value)
        if not match:
            raise PineCompileError("Invalid version directive. Use //@version=6.", line=tok.line, column=tok.column)
        self.version = int(match.group(1))

    def _statement(self) -> Stmt:
        tok = self._peek()
        if tok.kind in {"FOR", "WHILE", "VAR", "VARIP", "SWITCH", "IMPORT", "EXPORT", "TYPE", "ENUM", "METHOD", "BREAK", "CONTINUE"}:
            raise PineCompileError(
                f"Unsupported statement '{tok.value}'. The Indicator scanner supports a Pine-compatible subset without loops, var persistence, or user-defined types.",
                line=tok.line,
                column=tok.column,
                code="UNSUPPORTED_STATEMENT",
            )
        if tok.kind == "IF":
            raise PineCompileError(
                "if/else statements are not supported in version 1. Use a ternary expression: condition ? valueIfTrue : valueIfFalse.",
                line=tok.line,
                column=tok.column,
                code="UNSUPPORTED_IF",
            )
        if tok.kind == TOKEN_IDENT:
            nxt = self._peek_ahead(1)
            if nxt.kind == "EQ":
                return self._assignment()
            if nxt.kind == "ARROW" or nxt.kind == "ASSIGN_REBIND":
                raise PineCompileError(
                    "User-defined functions and ':=' reassignment are not supported in version 1.",
                    line=tok.line,
                    column=tok.column,
                    code="UNSUPPORTED_FUNCTION",
                )
            if nxt.kind == "LPAREN" and self._peek_ahead(2).kind == TOKEN_IDENT and self._peek_ahead(3).kind == "RPAREN" and self._peek_ahead(4).kind == "ARROW":
                raise PineCompileError(
                    "User-defined functions are not supported in version 1.",
                    line=tok.line,
                    column=tok.column,
                    code="UNSUPPORTED_FUNCTION",
                )
        expr = self._expression()
        return self._node(ExprStmt(span=self._span_of(tok), expr=expr))

    def _assignment(self) -> Assignment:
        name_tok = self._expect(TOKEN_IDENT, "Expected identifier")
        eq = self._expect("EQ", "Expected '='")
        if eq.kind == "ASSIGN_REBIND":
            raise PineCompileError("':=' reassignment is not supported in version 1.", line=eq.line, column=eq.column)
        expr = self._expression()
        return self._node(Assignment(span=Span(name_tok.line, name_tok.column), name=name_tok.value, expr=expr))

    def _expression(self, depth: int = 0) -> Expr:
        self._check_depth(depth)
        return self._ternary(depth + 1)

    def _ternary(self, depth: int) -> Expr:
        expr = self._or(depth)
        if self._match("QUESTION"):
            then_expr = self._expression(depth + 1)
            self._expect("COLON", "Expected ':' in ternary expression")
            else_expr = self._expression(depth + 1)
            return self._node(Ternary(span=expr.span, condition=expr, then_expr=then_expr, else_expr=else_expr))
        return expr

    def _or(self, depth: int) -> Expr:
        expr = self._and(depth)
        while self._match("OR"):
            right = self._and(depth)
            expr = self._node(BinaryOp(span=expr.span, op="or", left=expr, right=right))
        return expr

    def _and(self, depth: int) -> Expr:
        expr = self._not(depth)
        while self._match("AND"):
            right = self._not(depth)
            expr = self._node(BinaryOp(span=expr.span, op="and", left=expr, right=right))
        return expr

    def _not(self, depth: int) -> Expr:
        if self._match("NOT"):
            tok = self._prev()
            return self._node(UnaryOp(span=Span(tok.line, tok.column), op="not", expr=self._not(depth + 1)))
        return self._comparison(depth)

    def _comparison(self, depth: int) -> Expr:
        expr = self._add(depth)
        while True:
            op_map = {"GT": ">", "GE": ">=", "LT": "<", "LE": "<=", "EQEQ": "==", "NE": "!="}
            if self._peek().kind in op_map:
                tok = self._advance()
                right = self._add(depth)
                expr = self._node(BinaryOp(span=expr.span, op=op_map[tok.kind], left=expr, right=right))
                continue
            break
        return expr

    def _add(self, depth: int) -> Expr:
        expr = self._mul(depth)
        while self._peek().kind in {"PLUS", "MINUS"}:
            tok = self._advance()
            right = self._mul(depth)
            expr = self._node(BinaryOp(span=expr.span, op=tok.value, left=expr, right=right))
        return expr

    def _mul(self, depth: int) -> Expr:
        expr = self._unary(depth)
        while self._peek().kind in {"STAR", "SLASH", "PERCENT"}:
            tok = self._advance()
            right = self._unary(depth)
            expr = self._node(BinaryOp(span=expr.span, op=tok.value, left=expr, right=right))
        return expr

    def _unary(self, depth: int) -> Expr:
        if self._match("MINUS"):
            tok = self._prev()
            return self._node(UnaryOp(span=Span(tok.line, tok.column), op="-", expr=self._unary(depth + 1)))
        if self._match("PLUS"):
            return self._unary(depth + 1)
        return self._postfix(depth)

    def _postfix(self, depth: int) -> Expr:
        expr = self._primary(depth)
        while True:
            if self._match("LPAREN"):
                args, kwargs = self._arg_list()
                self._expect("RPAREN", "Expected ')' after arguments")
                expr = self._node(Call(span=expr.span, callee=expr, args=args, kwargs=kwargs))
                continue
            if self._match("DOT"):
                attr = self._expect(TOKEN_IDENT, "Expected identifier after '.'")
                expr = self._node(Member(span=expr.span, object=expr, attr=attr.value))
                continue
            if self._match("LBRACKET"):
                idx_tok = self._peek()
                if idx_tok.kind == "MINUS":
                    raise PineCompileError(
                        "Negative/future indexing is not allowed.",
                        line=idx_tok.line,
                        column=idx_tok.column,
                        code="NEGATIVE_INDEX",
                    )
                if idx_tok.kind != TOKEN_NUMBER or "." in idx_tok.value:
                    raise PineCompileError(
                        "Series index must be a non-negative integer literal in version 1 (for example close[1]).",
                        line=idx_tok.line,
                        column=idx_tok.column,
                        code="DYNAMIC_INDEX",
                    )
                self._advance()
                offset = int(idx_tok.value)
                self._expect("RBRACKET", "Expected ']'")
                expr = self._node(Index(span=expr.span, target=expr, offset=offset))
                continue
            break
        return expr

    def _arg_list(self) -> tuple[list[Expr], dict[str, Expr]]:
        args: list[Expr] = []
        kwargs: dict[str, Expr] = {}
        if self._check("RPAREN"):
            return args, kwargs
        while True:
            if (
                self._check(TOKEN_IDENT)
                and self._peek_ahead(1).kind == "EQ"
                and self._peek_ahead(2).kind != "EQEQ"
            ):
                name = self._advance().value
                self._expect("EQ", "Expected '=' in named argument")
                if name in kwargs:
                    tok = self._prev()
                    raise PineCompileError(f"Duplicate named argument '{name}'.", line=tok.line, column=tok.column)
                kwargs[name] = self._expression()
            else:
                if kwargs:
                    tok = self._peek()
                    raise PineCompileError(
                        "Positional arguments cannot follow named arguments.",
                        line=tok.line,
                        column=tok.column,
                    )
                args.append(self._expression())
            if not self._match("COMMA"):
                break
            if self._check("RPAREN"):
                break
        return args, kwargs

    def _primary(self, depth: int) -> Expr:
        tok = self._peek()
        if self._match(TOKEN_NUMBER):
            return self._node(NumberLit(span=Span(tok.line, tok.column), value=float(tok.value)))
        if self._match(TOKEN_STRING):
            return self._node(StringLit(span=Span(tok.line, tok.column), value=tok.value))
        if self._match("TRUE"):
            return self._node(BoolLit(span=Span(tok.line, tok.column), value=True))
        if self._match("FALSE"):
            return self._node(BoolLit(span=Span(tok.line, tok.column), value=False))
        if self._match("NA"):
            # Pine uses both the na literal and na(x). If a call follows, treat it as the function.
            if self._check("LPAREN"):
                return self._node(Ident(span=Span(tok.line, tok.column), name="na"))
            return self._node(NaLit(span=Span(tok.line, tok.column)))
        if self._match(TOKEN_IDENT):
            return self._node(Ident(span=Span(tok.line, tok.column), name=tok.value))
        if self._match("LPAREN"):
            expr = self._expression(depth + 1)
            self._expect("RPAREN", "Expected ')'")
            return expr
        if tok.kind == "ASSIGN_REBIND":
            raise PineCompileError("':=' is not supported in version 1.", line=tok.line, column=tok.column)
        if tok.kind == "ARROW":
            raise PineCompileError("User-defined functions ('=>') are not supported in version 1.", line=tok.line, column=tok.column)
        raise PineCompileError(
            f"Unexpected token '{tok.value or tok.kind}'.",
            line=tok.line,
            column=tok.column,
            code="UNEXPECTED_TOKEN",
        )

    def _check_depth(self, depth: int) -> None:
        if depth > MAX_EXPRESSION_DEPTH:
            tok = self._peek()
            raise PineCompileError(
                f"Expression exceeds the maximum depth of {MAX_EXPRESSION_DEPTH}.",
                line=tok.line,
                column=tok.column,
                code="EXPR_TOO_DEEP",
            )

    def _node(self, node):
        self.node_count += 1
        if self.node_count > MAX_AST_NODES:
            raise PineCompileError(
                f"Script exceeds the {MAX_AST_NODES} AST node limit.",
                line=node.span.line,
                column=node.span.column,
                code="TOO_MANY_NODES",
            )
        return node

    def _span_of(self, tok: Token) -> Span:
        return Span(tok.line, tok.column)

    def _peek(self) -> Token:
        return self.tokens[self.i]

    def _peek_ahead(self, n: int) -> Token:
        j = min(self.i + n, len(self.tokens) - 1)
        return self.tokens[j]

    def _prev(self) -> Token:
        return self.tokens[self.i - 1]

    def _check(self, kind: str) -> bool:
        return self._peek().kind == kind

    def _advance(self) -> Token:
        tok = self.tokens[self.i]
        if tok.kind != TOKEN_EOF:
            self.i += 1
        return tok

    def _match(self, kind: str) -> bool:
        if self._check(kind):
            self._advance()
            return True
        return False

    def _expect(self, kind: str, message: str) -> Token:
        if self._check(kind):
            return self._advance()
        tok = self._peek()
        raise PineCompileError(f"{message}. Found '{tok.value or tok.kind}'.", line=tok.line, column=tok.column)


def parse_source(source: str) -> Program:
    return Parser(source).parse()
