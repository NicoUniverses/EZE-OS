<?php

declare(strict_types=1);

use Doctrine\DBAL\Connection;
use Doctrine\DBAL\DriverManager;

// Composer install, or the no-Composer autoloader plus DOCTRINE_* source paths (see tests/run.php).
if (is_file(__DIR__ . '/../vendor/autoload.php')) {
    require __DIR__ . '/../vendor/autoload.php';
} else {
    require __DIR__ . '/../autoload.php';
    $paths = [
        'Doctrine\\DBAL\\'         => getenv('DOCTRINE_DBAL_SRC'),
        'Doctrine\\Deprecations\\' => getenv('DOCTRINE_DEPRECATIONS_SRC'),
        'Psr\\Log\\'               => getenv('PSR_LOG_SRC'),
        'Psr\\Cache\\'             => getenv('PSR_CACHE_SRC'),
    ];
    spl_autoload_register(static function (string $class) use ($paths): void {
        foreach ($paths as $prefix => $dir) {
            if ($dir && strncmp($class, $prefix, strlen($prefix)) === 0) {
                $file = rtrim($dir, '/') . '/' . str_replace('\\', '/', substr($class, strlen($prefix))) . '.php';
                if (is_file($file)) {
                    require $file;
                }
                return;
            }
        }
    });
}

/** In-memory SQLite database with the three demo tables used on ezeos.org. */
function ezeos_demo_connection(): Connection
{
    $conn = DriverManager::getConnection(['driver' => 'pdo_sqlite', 'memory' => true]);
    $conn->executeStatement('CREATE TABLE assets (symbol TEXT, sector TEXT, expected_return REAL, risk REAL)');
    foreach ([['GOLD', 'metals', 0.06, 0.10], ['SILV', 'metals', 0.08, 0.22], ['NESN', 'consumer', 0.07, 0.09],
              ['ROG', 'health', 0.09, 0.14], ['NOVN', 'health', 0.08, 0.12], ['UBSG', 'banks', 0.11, 0.25],
              ['ABBN', 'industry', 0.10, 0.16], ['BTC', 'crypto', 0.30, 0.80]] as [$s, $sec, $r, $k]) {
        $conn->insert('assets', ['symbol' => $s, 'sector' => $sec, 'expected_return' => $r, 'risk' => $k]);
    }

    $conn->executeStatement('CREATE TABLE suppliers (id INTEGER, name TEXT, country TEXT, lead_days INTEGER, rating REAL)');
    $rows = [['CH', 12, 4.8], ['DE', 30, 4.1], ['AR', 45, 3.9], ['CH', 8, 4.2], ['PL', 20, 4.6], ['US', 15, 4.9],
             ['CN', 60, 3.5], ['CH', 25, 4.7], ['DE', 9, 4.85], ['BR', 40, 4.0], ['JP', 18, 4.3], ['CH', 5, 3.8],
             ['FR', 14, 4.4], ['IT', 22, 4.1], ['ES', 35, 3.7], ['NL', 11, 4.75]];
    foreach ($rows as $i => [$c, $d, $rt]) {
        $conn->insert('suppliers', ['id' => $i + 1, 'name' => sprintf('S%02d', $i + 1), 'country' => $c,
            'lead_days' => $d, 'rating' => $rt]);
    }

    $conn->executeStatement('CREATE TABLE scenarios (scenario TEXT, probability REAL, impact REAL)');
    foreach ([['base', 0.55, 0.0], ['mild recession', 0.20, -0.08], ['rate cut', 0.15, 0.05],
              ['crisis', 0.07, -0.25], ['boom', 0.03, 0.18]] as [$n, $p, $im]) {
        $conn->insert('scenarios', ['scenario' => $n, 'probability' => $p, 'impact' => $im]);
    }

    return $conn;
}
