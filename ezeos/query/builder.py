"""Fluent QQL builder, modelled on Doctrine DBAL's QueryBuilder API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class QueryBuilder:
    """Build QQL step by step, the way Doctrine's QueryBuilder builds SQL.

    >>> qb = QueryBuilder().optimize(3).from_("assets").where("sector != :s") \\
    ...     .maximize("expected_return").minimize("risk", 0.5).set_parameter("s", "crypto")
    >>> qb.get_qql()
    "OPTIMIZE PICK 3 FROM assets WHERE sector != :s MAXIMIZE expected_return MINIMIZE risk WEIGHT 0.5"
    """

    def __init__(self) -> None:
        self._kind: Optional[str] = None
        self._n: Optional[int] = None
        self._table: Optional[str] = None
        self._where: List[str] = []
        self._max: Optional[str] = None
        self._min: Optional[str] = None
        self._weight: Optional[float] = None
        self._weight_by: Optional[str] = None
        self._limit: Optional[int] = None
        self._device: Optional[str] = None
        self._shots: Optional[int] = None
        self._seed: Optional[int] = None
        self._noisy = False
        self._params: Dict[str, Any] = {}

    # statement kind
    def search(self) -> "QueryBuilder":
        self._kind = "SEARCH"
        return self

    def optimize(self, pick: int) -> "QueryBuilder":
        self._kind, self._n = "OPTIMIZE", pick
        return self

    def sample(self, n: int) -> "QueryBuilder":
        self._kind, self._n = "SAMPLE", n
        return self

    # clauses
    def from_(self, table: str) -> "QueryBuilder":
        self._table = table
        return self

    def where(self, condition: str) -> "QueryBuilder":
        self._where = [f"({condition})"] if condition else []
        return self

    def and_where(self, condition: str) -> "QueryBuilder":
        self._where.append(("AND ", f"({condition})"))  # type: ignore[arg-type]
        return self

    def or_where(self, condition: str) -> "QueryBuilder":
        self._where.append(("OR ", f"({condition})"))  # type: ignore[arg-type]
        return self

    def maximize(self, column: str) -> "QueryBuilder":
        self._max = column
        return self

    def minimize(self, column: str, weight: Optional[float] = None) -> "QueryBuilder":
        self._min, self._weight = column, weight
        return self

    def weight_by(self, column: str) -> "QueryBuilder":
        self._weight_by = column
        return self

    def set_max_results(self, limit: int) -> "QueryBuilder":
        self._limit = limit
        return self

    def on(self, device: str) -> "QueryBuilder":
        self._device = device
        return self

    def shots(self, shots: int) -> "QueryBuilder":
        self._shots = shots
        return self

    def seed(self, seed: int) -> "QueryBuilder":
        self._seed = seed
        return self

    def noisy(self, flag: bool = True) -> "QueryBuilder":
        self._noisy = flag
        return self

    def set_parameter(self, name: str, value: Any) -> "QueryBuilder":
        self._params[name.lstrip(":")] = value
        return self

    def get_parameters(self) -> Dict[str, Any]:
        return dict(self._params)

    def _where_sql(self) -> str:
        parts: List[str] = []
        for item in self._where:
            if isinstance(item, tuple):
                parts.append(item[0] + item[1] if parts else item[1])
            else:
                parts.append(item)
        return " ".join(parts)

    def get_qql(self) -> str:
        if not self._kind or not self._table:
            raise ValueError("call search()/optimize()/sample() and from_() first")
        if self._kind == "SEARCH":
            s = f"SEARCH FROM {self._table}"
        elif self._kind == "OPTIMIZE":
            s = f"OPTIMIZE PICK {self._n} FROM {self._table}"
        else:
            s = f"SAMPLE {self._n} FROM {self._table}"
        if self._where:
            s += f" WHERE {self._where_sql()}"
        if self._kind == "OPTIMIZE":
            if not self._max:
                raise ValueError("OPTIMIZE needs maximize()")
            s += f" MAXIMIZE {self._max}"
            if self._min:
                s += f" MINIMIZE {self._min}"
                if self._weight is not None:
                    s += f" WEIGHT {self._weight:g}"
        if self._kind == "SAMPLE":
            if not self._weight_by:
                raise ValueError("SAMPLE needs weight_by()")
            s += f" WEIGHT BY {self._weight_by}"
        if self._limit is not None and self._kind == "SEARCH":
            s += f" LIMIT {self._limit}"
        if self._device:
            s += f" ON {self._device}"
        if self._shots:
            s += f" SHOTS {self._shots}"
        if self._seed is not None:
            s += f" SEED {self._seed}"
        if self._noisy:
            s += " NOISY"
        return s

    def __str__(self) -> str:
        return self.get_qql()
