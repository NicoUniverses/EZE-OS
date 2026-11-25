<?php

declare(strict_types=1);

/*
 * Dependency-free test runner for the bridge. Run: php tests/run.php
 * Needs the EZE OS Python package importable by EZEOS_PYTHON (default python3).
 */

use EzeOs\Doctrine\Bridge\ProcessBridge;
use EzeOs\Doctrine\Exception\QuantumQueryException;
use EzeOs\Doctrine\Qql\QqlLexer;
use EzeOs\Doctrine\Qql\QueryInspector;
use EzeOs\Doctrine\QuantumConnection;
use EzeOs\Doctrine\QuantumQueryBuilder;

require __DIR__ . '/../examples/bootstrap.php';

$failures = 0;
$passed   = 0;
function check(bool $cond, string $name): void
{
    global $failures, $passed;
    if ($cond) {
        $passed++;
        return;
    }
    $failures++;
    fwrite(STDERR, "FAIL: $name\n");
}

function throws(callable $fn): bool
{
    try {
        $fn();
    } catch (QuantumQueryException) {
        return true;
    }
    return false;
}

// lexer: same token stream as the Python port (tests/test_query.py)
$lx = new QqlLexer();
$lx->setInput("SEARCH FROM t WHERE a.b >= :x AND name = 'O''Neil' LIMIT 3");
$types = [];
$values = [];
while ($lx->moveNext()) {
    $types[] = $lx->lookahead->type;
    $values[] = $lx->lookahead->value;
}
check($types === ['SEARCH', 'FROM', 'T_IDENTIFIER', 'WHERE', 'T_IDENTIFIER', 'T_COMPARISON', 'T_INPUT_PARAMETER',
    'AND', 'T_IDENTIFIER', 'T_COMPARISON', 'T_STRING', 'LIMIT', 'T_INTEGER'], 'lexer token types');
check($values[10] === "O'Neil" && $values[6] === 'x', 'lexer values');

// inspector
$info = QueryInspector::inspect('OPTIMIZE PICK 2 FROM assets WHERE sector != :s AND risk < :r MAXIMIZE expected_return');
check($info === ['kind' => 'OPTIMIZE', 'table' => 'assets', 'parameters' => ['s', 'r']], 'inspector');
check(throws(static fn () => QueryInspector::inspect('DROP TABLE assets')), 'inspector rejects non-QQL');
check(throws(static fn () => QueryInspector::inspect('SEARCH FROM assets; DROP')), 'inspector rejects junk');

// builder
$qb = (new QuantumQueryBuilder())->search()->from('suppliers')->where('lead_days <= :d')->andWhere('rating >= 4.7')
    ->setMaxResults(5)->on('iqm_spark')->seed(1)->setParameter(':d', 14);
check($qb->getQQL() === 'SEARCH FROM suppliers WHERE (lead_days <= :d) AND (rating >= 4.7) LIMIT 5 ON iqm_spark SEED 1', 'builder SEARCH');
check($qb->getParameters() === ['d' => 14], 'builder parameters');
$qb = (new QuantumQueryBuilder())->optimize(3)->from('assets')->maximize('expected_return')->minimize('risk', 0.5);
check($qb->getQQL() === 'OPTIMIZE PICK 3 FROM assets MAXIMIZE expected_return MINIMIZE risk WEIGHT 0.5', 'builder OPTIMIZE');

// end to end through Doctrine DBAL (SQLite) and the EZE OS kernel
$qc = new QuantumConnection(ezeos_demo_connection(), new ProcessBridge(getenv('EZEOS_PYTHON') ?: 'python3'));

$r = $qc->createQuantumQueryBuilder()->optimize(3)->from('assets')->where('sector != :x')->setParameter('x', 'crypto')
    ->maximize('expected_return')->minimize('risk', 0.5)->seed(7)->executeQuantumQuery();
$symbols = $r->fetchFirstColumn();
sort($symbols);
check($symbols === ['NESN', 'NOVN', 'ROG'], 'OPTIMIZE picks the optimal portfolio');
check($r->getStats()['optimality_gap'] == 0 && $r->getPlan()['algorithm'] === 'qaoa', 'OPTIMIZE uses QAOA with zero gap');
check(count($r->getKernelLog()) >= 3, 'kernel log is returned');

$r = $qc->executeQuantumQuery('SEARCH FROM suppliers WHERE lead_days <= :d AND rating >= :r SEED 3', ['d' => 14, 'r' => 4.7]);
$names = array_column($r->fetchAllAssociative(), 'name');
sort($names);
check($names === ['S01', 'S09', 'S16'], 'SEARCH finds the matching suppliers');
check($r->getStats()['success_probability'] > 0.9, 'Grover amplification');

$r = $qc->executeQuantumQuery('SAMPLE 2000 FROM scenarios WEIGHT BY probability SEED 5');
check($r->fetchAssociative()['scenario'] === 'base' && $r->getStats()['total_variation_distance'] < 0.05, 'SAMPLE follows weights');

$qc->registerSource('cheap', 'SELECT * FROM assets WHERE risk < ?', [0.15]);
$r = $qc->executeQuantumQuery('OPTIMIZE PICK 1 FROM cheap MAXIMIZE expected_return SEED 1');
check($r->fetchFirstColumn() === ['ROG'], 'registerSource feeds an SQL result to QQL');

check(throws(static fn () => $qc->executeQuantumQuery('SEARCH FROM suppliers WHERE rating > :r')), 'missing parameter');
check(throws(static fn () => $qc->executeQuantumQuery('SEARCH FROM nope')), 'unknown table');
check(throws(static fn () => $qc->executeQuantumQuery('SEARCH FROM suppliers ON warp_drive')), 'unknown device reported by kernel');

printf("%d passed, %d failed\n", $passed, $failures);
exit($failures === 0 ? 0 : 1);
