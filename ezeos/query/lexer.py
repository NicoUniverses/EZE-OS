"""Python port of ``Doctrine\\Common\\Lexer\\AbstractLexer`` and ``Token``.

Ported from doctrine/lexer (https://github.com/doctrine/lexer, commit 51489da),
Copyright (c) 2006-2018 Doctrine Project, released under the MIT license
(see third_party/doctrine-lexer/LICENSE). The PHP original is vendored unchanged in
third_party/doctrine-lexer/. This port keeps the same public API and semantics
(setInput, moveNext, isNextToken, peek, glimpse, skipUntil, ...) so that QQL
queries are tokenized identically on the PHP (Doctrine) and Python (EZE OS) sides.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Token:
    """A lexical token: value, type and character offset in the input."""

    value: Any
    type: Any
    position: int

    def is_a(self, *types: Any) -> bool:
        return self.type in types


class AbstractLexer(ABC):
    """Base class for small DSL lexers (port of Doctrine's AbstractLexer)."""

    def __init__(self) -> None:
        self._input = ""
        self._tokens: List[Token] = []
        self._position = 0
        self._peek = 0
        self.lookahead: Optional[Token] = None
        self.token: Optional[Token] = None
        self._regex: Optional[re.Pattern] = None

    # -- input -------------------------------------------------------------
    def set_input(self, text: str) -> None:
        self._input = text
        self._tokens = []
        self.reset()
        self._scan(text)

    def reset(self) -> None:
        self.lookahead = None
        self.token = None
        self._peek = 0
        self._position = 0

    def reset_peek(self) -> None:
        self._peek = 0

    def reset_position(self, position: int = 0) -> None:
        for index, tok in enumerate(self._tokens):
            if tok.position >= position:
                self._position = index
                return
        self._position = len(self._tokens)

    def get_input_until_position(self, position: int) -> str:
        return self._input[:position]

    # -- navigation ----------------------------------------------------------
    def is_next_token(self, type_: Any) -> bool:
        return self.lookahead is not None and self.lookahead.is_a(type_)

    def is_next_token_any(self, types: Sequence[Any]) -> bool:
        return self.lookahead is not None and self.lookahead.is_a(*types)

    def move_next(self) -> bool:
        self._peek = 0
        self.token = self.lookahead
        if self._position < len(self._tokens):
            self.lookahead = self._tokens[self._position]
            self._position += 1
        else:
            self.lookahead = None
        return self.lookahead is not None

    def skip_until(self, type_: Any) -> None:
        while self.lookahead is not None and not self.lookahead.is_a(type_):
            self.move_next()

    def is_a(self, value: str, token_type: Any) -> bool:
        return self.get_type(value)[0] == token_type

    def peek(self) -> Optional[Token]:
        index = self._position + self._peek
        if index < len(self._tokens):
            self._peek += 1
            return self._tokens[index]
        return None

    def glimpse(self) -> Optional[Token]:
        tok = self.peek()
        self._peek = 0
        return tok

    @property
    def tokens(self) -> List[Token]:
        return list(self._tokens)

    # -- scanning ------------------------------------------------------------
    def _scan(self, text: str) -> None:
        if self._regex is None:
            catchable = ")|(".join(self.get_catchable_patterns())
            non_catchable = "|".join(self.get_non_catchable_patterns())
            self._regex = re.compile(f"({catchable})|{non_catchable}", self.get_modifiers())
        # Equivalent of PHP preg_split(..., DELIM_CAPTURE | NO_EMPTY | OFFSET_CAPTURE):
        # captured (catchable) groups and the text between matches become tokens,
        # non-catchable matches (whitespace, ...) are dropped.
        last = 0
        for m in self._regex.finditer(text):
            if m.start() > last:
                self._emit(text[last:m.start()], last)
            if m.lastindex is not None and m.group(m.lastindex):
                # one of the catchable groups matched (PREG_SPLIT_DELIM_CAPTURE)
                self._emit(m.group(m.lastindex), m.start(m.lastindex))
            last = m.end()
        if last < len(text):
            self._emit(text[last:], last)

    def _emit(self, value: str, position: int) -> None:
        token_type, processed = self.get_type(value)
        self._tokens.append(Token(processed, token_type, position))

    def get_modifiers(self) -> int:
        return re.IGNORECASE | re.UNICODE

    @abstractmethod
    def get_catchable_patterns(self) -> List[str]:
        """Regex fragments whose matches become tokens."""

    @abstractmethod
    def get_non_catchable_patterns(self) -> List[str]:
        """Regex fragments that are skipped (e.g. whitespace)."""

    @abstractmethod
    def get_type(self, value: str) -> Tuple[Any, Any]:
        """Return (token type, processed value) for a raw token string."""
