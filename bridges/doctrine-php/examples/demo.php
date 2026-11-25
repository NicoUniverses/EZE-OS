<?php

declare(strict_types=1);

/*
 * The three practical cases shown on https://ezeos.org/index.php#doctrine
 * Run: php examples/demo.php   (needs `pip install ezeos` or PYTHONPATH pointing at the repo)
 */

use EzeOs\Doctrine\Bridge\ProcessBridge;
use EzeOs\Doctrine\QuantumConnection;

require __DIR__ . '/bootstrap.php';

$conn = ezeos_demo_connection();                                  // any Doctrine DBAL connection
$qc   = new QuantumConnection($conn, new ProcessBridge(getenv('EZEOS_PYTHON') ?: 'python3'));

// 1. Portfolio: pick 3 assets (no crypto) maximising return minus half the risk, solved with QAOA.
$portfolio = $qc->createQuantumQueryBuilder()
    ->optimize(3)->from('assets')
    ->where('sector != :excluded')->setParameter('excluded', 'crypto')
    ->maximize('expected_return')->minimize('risk', 0.5)
    ->on('iqm_radiance_20')->seed(7)
    ->executeQuantumQuery();
echo "1) ", $portfolio->getPlan()['qql'], "\n";
foreach ($portfolio as $row) {
    printf("   %-5s %-9s return %.2f risk %.2f\n", $row['symbol'], $row['sector'], $row['expected_return'], $row['risk']);
}
printf("   algorithm=%s gap_to_exact=%s\n\n", $portfolio->getPlan()['algorithm'], $portfolio->getStats()['optimality_gap']);

// 2. Search: suppliers that deliver in 14 days or less with rating >= 4.7, found with Grover.
$search = $qc->executeQuantumQuery(
    'SEARCH FROM suppliers WHERE lead_days <= :days AND rating >= :rating ON rigetti_novera SEED 3',
    ['days' => 14, 'rating' => 4.7],
);
echo "2) ", $search->getPlan()['qql'], "\n";
foreach ($search as $row) {
    printf("   %s %s %2d days rating %.2f  (%d hits)\n", $row['name'], $row['country'], $row['lead_days'], $row['rating'], $row['_hits']);
}
printf("   qubits=%d iterations=%d success=%.1f%% (random guess %.1f%%)\n\n", $search->getPlan()['qubits'],
    $search->getPlan()['iterations'], 100 * $search->getStats()['success_probability'], 100 * $search->getStats()['uniform_baseline']);

// 3. Sampling: draw 2000 economic scenarios in proportion to their probability.
$sample = $qc->executeQuantumQuery('SAMPLE 2000 FROM scenarios WEIGHT BY probability SEED 5');
echo "3) ", $sample->getPlan()['qql'], "\n";
foreach ($sample as $row) {
    printf("   %-15s sampled %5.1f%%  expected %5.1f%%\n", $row['scenario'], 100 * $row['_frequency'], 100 * $row['_expected']);
}
printf("   total variation distance %.3f\n", $sample->getStats()['total_variation_distance']);
