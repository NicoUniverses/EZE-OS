import json
import math
import subprocess
import sys

import pytest

from ezeos.query import QQLLexer, QQLSyntaxError, QueryBuilder, execute, handle_request, parse
from ezeos.query.engine import grover_search_circuit, selection_qubo, state_preparation
from ezeos.simulator import Simulator

ASSETS = [{"symbol": s, "sector": sec, "expected_return": r, "risk": k} for s, sec, r, k in [
    ("GOLD", "metals", 0.06, 0.10), ("SILV", "metals", 0.08, 0.22), ("NESN", "consumer", 0.07, 0.09),
    ("ROG", "health", 0.09, 0.14), ("NOVN", "health", 0.08, 0.12), ("UBSG", "banks", 0.11, 0.25),
    ("ABBN", "industry", 0.10, 0.16), ("BTC", "crypto", 0.30, 0.80)]]

SUPPLIERS = [{"id": i + 1, "name": f"S{i + 1:02d}", "country": c, "lead_days": d, "rating": rt}
             for i, (c, d, rt) in enumerate([
                 ("CH", 12, 4.8), ("DE", 30, 4.1), ("AR", 45, 3.9), ("CH", 8, 4.2), ("PL", 20, 4.6),
                 ("US", 15, 4.9), ("CN", 60, 3.5), ("CH", 25, 4.7), ("DE", 9, 4.85), ("BR", 40, 4.0),
                 ("JP", 18, 4.3), ("CH", 5, 3.8), ("FR", 14, 4.4), ("IT", 22, 4.1), ("ES", 35, 3.7),
                 ("NL", 11, 4.75)])]


# lexer (Doctrine port) ------------------------------------------------------------
def test_lexer_tokens_and_navigation():
    lx = QQLLexer()
    lx.set_input("SEARCH FROM t WHERE a.b >= :x AND name = 'O''Neil' LIMIT 3")
    types = [t.type for t in lx.tokens]
    assert types == ["SEARCH", "FROM", "T_IDENTIFIER", "WHERE", "T_IDENTIFIER", "T_COMPARISON", "T_INPUT_PARAMETER",
                     "AND", "T_IDENTIFIER", "T_COMPARISON", "T_STRING", "LIMIT", "T_INTEGER"]
    assert lx.tokens[10].value == "O'Neil"
    assert lx.tokens[6].value == "x"
    lx.move_next()
    assert lx.is_next_token("SEARCH")
    assert lx.peek().type == "FROM" and lx.peek().type == "T_IDENTIFIER"
    assert lx.glimpse().type == "WHERE"          # same as Doctrine: glimpse peeks once more, then resets
    assert lx.peek().type == "FROM"
    lx.skip_until("LIMIT")
    assert lx.lookahead.type == "LIMIT"
    lx.reset_position(0)
    lx.move_next()
    assert lx.lookahead.type == "SEARCH"


def test_parser_and_errors():
    q = parse("OPTIMIZE PICK 2 FROM assets WHERE NOT (risk > 0.5 OR sector = 'crypto') "
              "MAXIMIZE expected_return MINIMIZE risk WEIGHT 0.25 ON iqm_spark SHOTS 500 SEED 4 NOISY")
    assert (q.kind, q.pick, q.maximize, q.minimize, q.weight) == ("OPTIMIZE", 2, "expected_return", "risk", 0.25)
    assert (q.device, q.shots, q.seed, q.noisy) == ("iqm_spark", 500, 4, True)
    for bad in ["SELECT * FROM x", "SEARCH FROM", "SEARCH FROM t WHERE a >", "SAMPLE 3 FROM t",
                "SEARCH FROM t LIMIT x", "SEARCH FROM t junk"]:
        with pytest.raises(QQLSyntaxError):
            parse(bad)


def test_builder_matches_parser():
    qb = (QueryBuilder().search().from_("suppliers").where("lead_days <= :d").and_where("rating >= 4.7")
          .set_max_results(2).on("ezeos_sim").seed(1).set_parameter(":d", 14))
    q = parse(qb.get_qql(), qb.get_parameters())
    assert q.kind == "SEARCH" and q.limit == 2 and q.params == {"d": 14}


# algorithms ---------------------------------------------------------------------
@pytest.mark.parametrize("marked,n", [([5], 3), ([0, 9, 15], 4), ([1, 2, 3, 4, 5], 4), ([7], 5)])
def test_grover_amplifies_marked(marked, n):
    c = grover_search_circuit(marked, n)
    probs = Simulator().statevector(c.remove_final_measurements()).probabilities()
    success = sum(probs[i] for i in marked)
    assert abs(success - c.metadata["theoretical_success"]) < 1e-9
    assert success > len(marked) / 2 ** n


@pytest.mark.parametrize("weights", [[1, 1], [0.55, 0.2, 0.15, 0.07, 0.03], [0, 3, 0, 1, 2, 2, 0, 5], list(range(1, 17))])
def test_state_preparation_is_exact(weights):
    n = max(1, math.ceil(math.log2(len(weights))))
    probs = Simulator().statevector(state_preparation(weights, n)).probabilities()
    total = sum(weights)
    for i, w in enumerate(weights):
        assert abs(probs[i] - w / total) < 1e-9


def test_selection_qubo_optimum():
    q = selection_qubo([1, 5, 2, 4], [0, 0, 0, 0], 0.0, 2)
    x, _ = q.brute_force()
    assert sorted(i for i, v in x.items() if v) == [1, 3]


# engine ---------------------------------------------------------------------------
def test_search_returns_matching_rows():
    r = execute("SEARCH FROM suppliers WHERE lead_days <= :d AND rating >= 4.7 SEED 3",
                {"suppliers": SUPPLIERS}, {"d": 14})
    assert sorted(x["name"] for x in r.rows) == ["S01", "S09", "S16"]
    assert r.stats["success_probability"] > 0.9 > r.stats["uniform_baseline"]


def test_search_on_real_device_topology():
    r = execute("SEARCH FROM suppliers WHERE country = 'CH' ON rigetti_novera SEED 1", {"suppliers": SUPPLIERS})
    assert sorted(x["name"] for x in r.rows) == ["S01", "S04", "S08", "S12"]
    assert "rigetti_novera" in r.plan["transpile"]


def test_search_no_match():
    r = execute("SEARCH FROM suppliers WHERE rating > 10", {"suppliers": SUPPLIERS})
    assert r.rows == [] and r.stats["success_probability"] == 0.0


def test_optimize_qaoa_matches_exact():
    r = execute("OPTIMIZE PICK 3 FROM assets WHERE sector != :s MAXIMIZE expected_return MINIMIZE risk WEIGHT 0.5 SEED 7",
                {"assets": ASSETS}, {"s": "crypto"})
    assert r.plan["algorithm"] == "qaoa"
    assert len(r.rows) == 3 and r.stats["optimality_gap"] == 0
    assert all(x["sector"] != "crypto" for x in r.rows)


def test_optimize_on_annealer():
    r = execute("OPTIMIZE PICK 2 FROM assets MAXIMIZE expected_return ON dwave_advantage2 SEED 2", {"assets": ASSETS})
    assert r.plan["algorithm"] == "qubo_annealing"
    assert sorted(x["symbol"] for x in r.rows) == ["BTC", "UBSG"]


def test_sample_follows_weights():
    sc = [{"scenario": n, "probability": p} for n, p in
          [("base", 0.55), ("recession", 0.2), ("rate cut", 0.15), ("crisis", 0.07), ("boom", 0.03)]]
    r = execute("SAMPLE 4000 FROM scenarios WEIGHT BY probability SEED 5", {"scenarios": sc})
    assert r.rows[0]["scenario"] == "base"
    assert r.stats["total_variation_distance"] < 0.03


def test_protocol_and_cli():
    bad = handle_request({"qql": "SEARCH FROM nope", "tables": {}})
    assert bad["ok"] is False and "nope" in bad["error"]
    req = {"qql": "SEARCH FROM suppliers WHERE country = :c SEED 1", "params": {"c": "DE"},
           "tables": {"suppliers": SUPPLIERS}}
    out = subprocess.run([sys.executable, "-m", "ezeos", "query"], input=json.dumps(req),
                         capture_output=True, text=True, check=True).stdout
    res = json.loads(out)
    assert res["ok"] and sorted(r["name"] for r in res["rows"]) == ["S02", "S09"]
