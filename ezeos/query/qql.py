"""QQL - the EZE OS Quantum Query Language.

QQL is a small SQL-like language for asking a quantum processor questions
about rows that come from an ordinary database (typically through Doctrine
DBAL on the PHP side). Three statement kinds are supported::

    SEARCH   FROM <table> [WHERE <cond>] [LIMIT n] [options]
    OPTIMIZE PICK n FROM <table> MAXIMIZE <col> [MINIMIZE <col> [WEIGHT x]] [options]
    SAMPLE   n FROM <table> WEIGHT BY <col> [options]

    options: ON <device> | SHOTS n | SEED n | NOISY

Conditions use = != <> < <= > >= combined with AND / OR / NOT and parentheses.
Values are numbers, 'strings' (with '' as escaped quote), TRUE/FALSE/NULL or
named parameters such as :max_risk bound at execution time, exactly like
Doctrine DBAL parameters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .lexer import AbstractLexer


class QQLSyntaxError(ValueError):
    """Raised for malformed QQL, with the character offset of the problem."""

    def __init__(self, message: str, position: Optional[int] = None):
        super().__init__(message if position is None else f"{message} at position {position}")
        self.position = position


# token types -------------------------------------------------------------
T_NONE = "T_NONE"
T_IDENT = "T_IDENTIFIER"
T_INT = "T_INTEGER"
T_FLOAT = "T_FLOAT"
T_STRING = "T_STRING"
T_PARAM = "T_INPUT_PARAMETER"
T_OP = "T_COMPARISON"
T_LPAREN = "T_OPEN_PARENTHESIS"
T_RPAREN = "T_CLOSE_PARENTHESIS"
T_COMMA = "T_COMMA"

KEYWORDS = {
    "SEARCH", "OPTIMIZE", "SAMPLE", "FROM", "WHERE", "AND", "OR", "NOT", "LIMIT",
    "ON", "SHOTS", "SEED", "NOISY", "PICK", "MAXIMIZE", "MINIMIZE", "WEIGHT", "BY",
    "TRUE", "FALSE", "NULL",
}


class QQLLexer(AbstractLexer):
    """Tokenizer for QQL, built on the Doctrine lexer port."""

    def get_catchable_patterns(self) -> List[str]:
        return [
            r":[a-z_][a-z0-9_]*",
            r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*",
            r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:e[+-]?[0-9]+)?",
            r"'(?:[^']|'')*'",
            r"<=|>=|!=|<>|=|<|>",
            r"[(),]",
        ]

    def get_non_catchable_patterns(self) -> List[str]:
        return [r"\s+"]

    def get_type(self, value: str) -> Tuple[Any, Any]:
        if value.startswith(":"):
            return T_PARAM, value[1:]
        if value[0].isdigit() or (value[0] == "." and len(value) > 1):
            if any(c in value for c in ".eE"):
                return T_FLOAT, float(value)
            return T_INT, int(value)
        if value.startswith("'") and value.endswith("'") and len(value) >= 2:
            return T_STRING, value[1:-1].replace("''", "'")
        if value in ("<=", ">=", "!=", "<>", "=", "<", ">"):
            return T_OP, "!=" if value == "<>" else value
        if value == "(":
            return T_LPAREN, value
        if value == ")":
            return T_RPAREN, value
        if value == ",":
            return T_COMMA, value
        if value[0].isalpha() or value[0] == "_":
            upper = value.upper()
            if upper in KEYWORDS:
                return upper, upper
            return T_IDENT, value
        return T_NONE, value


# AST ------------------------------------------------------------------------
@dataclass(frozen=True)
class Param:
    name: str


Value = Union[int, float, str, bool, None, Param]


@dataclass(frozen=True)
class Comparison:
    column: str
    op: str
    value: Value


@dataclass(frozen=True)
class BoolOp:
    op: str  # "AND" | "OR"
    items: Tuple["Condition", ...]


@dataclass(frozen=True)
class Not:
    item: "Condition"


Condition = Union[Comparison, BoolOp, Not]


@dataclass
class Query:
    kind: str                       # SEARCH | OPTIMIZE | SAMPLE
    table: str
    where: Optional[Condition] = None
    limit: Optional[int] = None
    pick: Optional[int] = None      # OPTIMIZE PICK k
    maximize: Optional[str] = None
    minimize: Optional[str] = None
    weight: float = 1.0
    samples: Optional[int] = None   # SAMPLE n
    weight_by: Optional[str] = None
    device: Optional[str] = None
    shots: Optional[int] = None
    seed: Optional[int] = None
    noisy: bool = False
    params: Dict[str, Any] = field(default_factory=dict)

    def columns_used(self) -> List[str]:
        cols: List[str] = []

        def walk(c: Optional[Condition]) -> None:
            if isinstance(c, Comparison):
                cols.append(c.column)
            elif isinstance(c, BoolOp):
                for i in c.items:
                    walk(i)
            elif isinstance(c, Not):
                walk(c.item)

        walk(self.where)
        cols += [c for c in (self.maximize, self.minimize, self.weight_by) if c]
        return list(dict.fromkeys(cols))


# parser ---------------------------------------------------------------------
class Parser:
    """Recursive-descent parser producing a :class:`Query`."""

    def __init__(self, text: str):
        self.lexer = QQLLexer()
        self.lexer.set_input(text)
        self.lexer.move_next()

    # helpers
    def _peek_type(self):
        return self.lexer.lookahead.type if self.lexer.lookahead else None

    def _error(self, expected: str) -> QQLSyntaxError:
        la = self.lexer.lookahead
        if la is None:
            return QQLSyntaxError(f"expected {expected}, got end of query")
        return QQLSyntaxError(f"expected {expected}, got '{la.value}'", la.position)

    def _match(self, *types: str):
        if not self.lexer.is_next_token_any(list(types)):
            raise self._error(" or ".join(types))
        self.lexer.move_next()
        return self.lexer.token

    def _accept(self, type_: str) -> bool:
        if self.lexer.is_next_token(type_):
            self.lexer.move_next()
            return True
        return False

    def _integer(self) -> int:
        tok = self._match(T_INT)
        return int(tok.value)

    def _number(self) -> float:
        tok = self._match(T_INT, T_FLOAT)
        return float(tok.value)

    # grammar
    def parse(self) -> Query:
        t = self._peek_type()
        if t == "SEARCH":
            q = self._search()
        elif t == "OPTIMIZE":
            q = self._optimize()
        elif t == "SAMPLE":
            q = self._sample()
        else:
            raise self._error("SEARCH, OPTIMIZE or SAMPLE")
        self._options(q)
        if self.lexer.lookahead is not None:
            raise self._error("end of query")
        return q

    def _search(self) -> Query:
        self._match("SEARCH")
        self._match("FROM")
        q = Query("SEARCH", self._match(T_IDENT).value)
        if self._accept("WHERE"):
            q.where = self._condition()
        if self._accept("LIMIT"):
            q.limit = self._integer()
        return q

    def _optimize(self) -> Query:
        self._match("OPTIMIZE")
        self._match("PICK")
        k = self._integer()
        self._match("FROM")
        q = Query("OPTIMIZE", self._match(T_IDENT).value, pick=k)
        if self._accept("WHERE"):
            q.where = self._condition()
        self._match("MAXIMIZE")
        q.maximize = self._match(T_IDENT).value
        if self._accept("MINIMIZE"):
            q.minimize = self._match(T_IDENT).value
            if self._accept("WEIGHT"):
                q.weight = self._number()
        return q

    def _sample(self) -> Query:
        self._match("SAMPLE")
        n = self._integer()
        self._match("FROM")
        q = Query("SAMPLE", self._match(T_IDENT).value, samples=n)
        if self._accept("WHERE"):
            q.where = self._condition()
        self._match("WEIGHT")
        self._match("BY")
        q.weight_by = self._match(T_IDENT).value
        return q

    def _options(self, q: Query) -> None:
        while self.lexer.lookahead is not None:
            if self._accept("ON"):
                q.device = self._match(T_IDENT).value
            elif self._accept("SHOTS"):
                q.shots = self._integer()
            elif self._accept("SEED"):
                q.seed = self._integer()
            elif self._accept("NOISY"):
                q.noisy = True
            else:
                return

    def _condition(self) -> Condition:
        items = [self._conjunction()]
        while self._accept("OR"):
            items.append(self._conjunction())
        return items[0] if len(items) == 1 else BoolOp("OR", tuple(items))

    def _conjunction(self) -> Condition:
        items = [self._factor()]
        while self._accept("AND"):
            items.append(self._factor())
        return items[0] if len(items) == 1 else BoolOp("AND", tuple(items))

    def _factor(self) -> Condition:
        if self._accept("NOT"):
            return Not(self._factor())
        if self._accept(T_LPAREN):
            c = self._condition()
            self._match(T_RPAREN)
            return c
        col = self._match(T_IDENT).value
        op = self._match(T_OP).value
        return Comparison(col, op, self._value())

    def _value(self) -> Value:
        tok = self._match(T_INT, T_FLOAT, T_STRING, T_PARAM, "TRUE", "FALSE", "NULL")
        if tok.type == T_PARAM:
            return Param(tok.value)
        if tok.type == "TRUE":
            return True
        if tok.type == "FALSE":
            return False
        if tok.type == "NULL":
            return None
        return tok.value


def parse(text: str, params: Optional[Mapping[str, Any]] = None) -> Query:
    q = Parser(text).parse()
    q.params = dict(params or {})
    return q


# evaluation -------------------------------------------------------------------
def _resolve(v: Value, params: Mapping[str, Any]) -> Any:
    if isinstance(v, Param):
        if v.name not in params:
            raise KeyError(f"missing value for parameter :{v.name}")
        return params[v.name]
    return v


def _compare(a: Any, op: str, b: Any) -> bool:
    if a is None or b is None:
        return (a is b) if op == "=" else (a is not b) if op == "!=" else False
    if isinstance(a, str) and not isinstance(b, str):
        try:
            a = float(a)
        except ValueError:
            return False
    if isinstance(b, str) and not isinstance(a, str):
        try:
            b = float(b)
        except ValueError:
            return False
    if op == "=":
        return a == b
    if op == "!=":
        return a != b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    raise ValueError(f"unknown operator {op}")


def evaluate(cond: Optional[Condition], row: Mapping[str, Any], params: Mapping[str, Any]) -> bool:
    if cond is None:
        return True
    if isinstance(cond, Comparison):
        if cond.column not in row:
            raise KeyError(f"unknown column '{cond.column}'")
        return _compare(row[cond.column], cond.op, _resolve(cond.value, params))
    if isinstance(cond, Not):
        return not evaluate(cond.item, row, params)
    if cond.op == "AND":
        return all(evaluate(i, row, params) for i in cond.items)
    return any(evaluate(i, row, params) for i in cond.items)
