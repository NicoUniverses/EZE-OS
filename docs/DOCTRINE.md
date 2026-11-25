# EZE OS + Doctrine: quantum queries over your database

[Doctrine](https://www.doctrine-project.org/) is the most widely used database abstraction layer
for PHP (DBAL, ORM, Lexer). EZE OS plugs into it so that a PHP application can ask a quantum
processor questions about data it already stores in MySQL, PostgreSQL, SQLite, Oracle or SQL Server,
using the same connection, the same parameter binding and a builder that looks like Doctrine's.

> Experimental. On today's hardware these queries demonstrate the quantum workflow; they are not
> faster than SQL. Every result reports how it compares with the exact classical answer.

## Layers

```
 PHP application
   │  $qc->createQuantumQueryBuilder()->optimize(3)->from('assets')->...
   ▼
 Doctrine DBAL                       reads the rows (any platform Doctrine supports)
   ▼
 EzeOs\Doctrine (bridges/doctrine-php)
   │  QqlLexer (on doctrine/lexer) · QueryInspector · QuantumQueryBuilder · QuantumConnection
   │  JSON request {qql, params, tables, device}
   ▼
 ezeos.query (Python)                 QQL lexer (port of doctrine/lexer) → parser → planner
   │  SEARCH   → Grover search over the rows
   │  OPTIMIZE → QUBO → QAOA (gate chips) or annealing (D-Wave)
   │  SAMPLE   → amplitude encoding of a weight column
   ▼
 ezeos.kernel                         job queue, device selection, audit log
   ▼
 ezeos.transpile                      native gates and wiring of the chosen chip
   ▼
 ezeos.backends                       local simulator · IBM · IQM · IonQ · Quantinuum · Braket · OpenQASM 3
```

## QQL in one minute

```sql
SEARCH   FROM suppliers WHERE lead_days <= :days AND rating >= 4.7 LIMIT 5 ON rigetti_novera
OPTIMIZE PICK 3 FROM assets WHERE sector != 'crypto' MAXIMIZE expected_return MINIMIZE risk WEIGHT 0.5 ON iqm_radiance_20
SAMPLE   2000 FROM scenarios WEIGHT BY probability
```

Options after any statement: `ON <device>`, `SHOTS n`, `SEED n`, `NOISY` (apply the device's
error rates in simulation). Parameters (`:name`) are bound like Doctrine parameters.

| Statement | Quantum algorithm | Limits in 0.2 | What the result tells you |
|---|---|---|---|
| `SEARCH` | Grover with an oracle built from the WHERE clause | 1,024 rows | rows found, success probability vs. random guess |
| `OPTIMIZE` | QUBO → QAOA (p=1) or simulated annealing for annealers | 10 candidates for QAOA, 20 for the exact check | chosen rows, objective value, gap to the exact optimum |
| `SAMPLE` | amplitude encoding with multi-controlled RY rotations | 64 rows | sampled frequency vs. expected weight, total variation distance |

## PHP

```php
use Doctrine\DBAL\DriverManager;
use EzeOs\Doctrine\QuantumConnection;

$conn = DriverManager::getConnection(['url' => 'mysql://user:secret@localhost/shop']);
$qc   = new QuantumConnection($conn);                      // runs `python3 -m ezeos query`

$result = $qc->createQuantumQueryBuilder()
    ->optimize(3)->from('assets')
    ->where('sector != :excluded')->setParameter('excluded', 'crypto')
    ->maximize('expected_return')->minimize('risk', 0.5)
    ->on('iqm_radiance_20')
    ->executeQuantumQuery();

foreach ($result as $row) { echo $row['symbol'], PHP_EOL; }
$result->getPlan();       // algorithm, qubits, transpiler report
$result->getStats();      // objective value, optimality gap
$result->getKernelLog();  // EZE OS audit log
```

Use any SQL as a QQL table with `registerSource('cheap', 'SELECT * FROM assets WHERE risk < ?', [0.15])`.

## Python

```python
from ezeos.query import execute, QueryBuilder
qql = QueryBuilder().search().from_("suppliers").where("country = :c").get_qql()
execute(qql, {"suppliers": rows}, {"c": "CH"}).rows
```

## Code taken from Doctrine

- `third_party/doctrine-lexer/`: `AbstractLexer.php` and `Token.php` from doctrine/lexer, unmodified
  (MIT). The PHP bridge's `QqlLexer` extends it.
- `ezeos/query/lexer.py`: line-by-line Python port of the same lexer, so that QQL is tokenized
  identically on both sides of the bridge.
- `QuantumQueryBuilder` and `QuantumResult` follow the API of Doctrine DBAL's `QueryBuilder` and `Result`.

Doctrine is a trademark of its owners; EZE OS is not affiliated with or endorsed by the Doctrine project.
