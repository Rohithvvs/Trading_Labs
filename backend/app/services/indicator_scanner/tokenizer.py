"""Tokenizer for the TradingLabs Pine-compatible subset. No eval."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import PineCompileError
from .limits import MAX_SOURCE_CHARS

TOKEN_EOF = "EOF"
TOKEN_IDENT = "IDENT"
TOKEN_NUMBER = "NUMBER"
TOKEN_STRING = "STRING"
TOKEN_VERSION = "VERSION"

KEYWORDS = {
    "and": "AND",
    "or": "OR",
    "not": "NOT",
    "true": "TRUE",
    "false": "FALSE",
    "na": "NA",
    "for": "FOR",
    "while": "WHILE",
    "if": "IF",
    "else": "ELSE",
    "var": "VAR",
    "varip": "VARIP",
    "switch": "SWITCH",
    "import": "IMPORT",
    "export": "EXPORT",
    "type": "TYPE",
    "enum": "ENUM",
    "method": "METHOD",
    "break": "BREAK",
    "continue": "CONTINUE",
}

TWO_CHAR = {
    "==": "EQEQ",
    "!=": "NE",
    ">=": "GE",
    "<=": "LE",
    ":=": "ASSIGN_REBIND",
    "=>": "ARROW",
    "//": "COMMENT",
    "/*": "BLOCK_COMMENT",
}

ONE_CHAR = {
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
    "%": "PERCENT",
    "=": "EQ",
    ">": "GT",
    "<": "LT",
    "?": "QUESTION",
    ":": "COLON",
    "(": "LPAREN",
    ")": "RPAREN",
    "[": "LBRACKET",
    "]": "RBRACKET",
    ",": "COMMA",
    ".": "DOT",
}


@dataclass
class Token:
    kind: str
    value: str
    line: int
    column: int


class Tokenizer:
    def __init__(self, source: str):
        if len(source) > MAX_SOURCE_CHARS:
            raise PineCompileError(
                f"Source exceeds the {MAX_SOURCE_CHARS} character limit.",
                line=1,
                column=1,
                code="SOURCE_TOO_LARGE",
            )
        self.source = source.replace("\r\n", "\n").replace("\r", "\n")
        self.n = len(self.source)
        self.i = 0
        self.line = 1
        self.column = 1

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while True:
            tok = self._next()
            if tok.kind == "COMMENT":
                continue
            tokens.append(tok)
            if tok.kind == TOKEN_EOF:
                break
        return tokens

    def _peek(self, ahead: int = 0) -> str:
        j = self.i + ahead
        return self.source[j] if j < self.n else ""

    def _advance(self) -> str:
        ch = self.source[self.i]
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _next(self) -> Token:
        self._skip_ws()
        if self.i >= self.n:
            return Token(TOKEN_EOF, "", self.line, self.column)
        line, col = self.line, self.column
        pair = self._peek() + self._peek(1)

        if pair == "//":
            start = self.i
            if self.source[self.i :].startswith("//@version"):
                while self.i < self.n and self._peek() != "\n":
                    self._advance()
                raw = self.source[start : self.i]
                return Token(TOKEN_VERSION, raw.strip(), line, col)
            while self.i < self.n and self._peek() != "\n":
                self._advance()
            return Token("COMMENT", "", line, col)

        if pair == "/*":
            self._advance()
            self._advance()
            while self.i < self.n and not (self._peek() == "*" and self._peek(1) == "/"):
                self._advance()
            if self.i >= self.n:
                raise PineCompileError("Unterminated block comment.", line=line, column=col)
            self._advance()
            self._advance()
            return Token("COMMENT", "", line, col)

        if pair in TWO_CHAR and pair not in {"//", "/*"}:
            self._advance()
            self._advance()
            return Token(TWO_CHAR[pair], pair, line, col)

        ch = self._peek()
        if ch in {'"', "'"}:
            return self._string(line, col)
        if ch.isdigit() or (ch == "." and self._peek(1).isdigit()):
            return self._number(line, col)
        if ch.isalpha() or ch == "_":
            return self._ident(line, col)
        if ch in ONE_CHAR:
            self._advance()
            return Token(ONE_CHAR[ch], ch, line, col)
        raise PineCompileError(f"Unexpected character {ch!r}.", line=line, column=col)

    def _skip_ws(self) -> None:
        while self.i < self.n and self._peek() in " \t\n\r":
            self._advance()

    def _ident(self, line: int, col: int) -> Token:
        start = self.i
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self.source[start : self.i]
        kind = KEYWORDS.get(text.lower(), TOKEN_IDENT)
        return Token(kind, text, line, col)

    def _number(self, line: int, col: int) -> Token:
        start = self.i
        while self._peek().isdigit():
            self._advance()
        if self._peek() == "." and self._peek(1).isdigit():
            self._advance()
            while self._peek().isdigit():
                self._advance()
        return Token(TOKEN_NUMBER, self.source[start : self.i], line, col)

    def _string(self, line: int, col: int) -> Token:
        quote = self._advance()
        chars: list[str] = []
        while self.i < self.n:
            ch = self._advance()
            if ch == quote:
                return Token(TOKEN_STRING, "".join(chars), line, col)
            if ch == "\\":
                nxt = self._advance() if self.i < self.n else ""
                escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"}
                chars.append(escapes.get(nxt, nxt))
                continue
            if ch == "\n":
                raise PineCompileError("Unterminated string literal.", line=line, column=col)
            chars.append(ch)
        raise PineCompileError("Unterminated string literal.", line=line, column=col)


def tokenize(source: str) -> list[Token]:
    return Tokenizer(source).tokenize()
