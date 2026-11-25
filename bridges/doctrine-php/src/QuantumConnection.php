<?php

declare(strict_types=1);

namespace EzeOs\Doctrine;

use Doctrine\DBAL\Connection;
use EzeOs\Doctrine\Bridge\BridgeInterface;
use EzeOs\Doctrine\Bridge\ProcessBridge;
use EzeOs\Doctrine\Exception\QuantumQueryException;
use EzeOs\Doctrine\Qql\QueryInspector;

use function array_diff;
use function array_key_exists;
use function array_keys;
use function implode;
use function ltrim;
use function sprintf;

/**
 * Quantum layer on top of a Doctrine DBAL connection.
 *
 *   Doctrine DBAL  ->  QuantumConnection  ->  bridge (JSON)  ->  EZE OS query engine  ->  kernel  ->  chip
 *
 * Rows are always read through Doctrine (any platform it supports); the quantum
 * part runs in the EZE OS kernel on the device named in the query (ON <device>).
 */
final class QuantumConnection
{
    /** @var array<string, array{sql: string, params: array<int|string, mixed>, types: array<int|string, mixed>}> */
    private array $sources = [];

    public function __construct(
        private readonly Connection $connection,
        private readonly BridgeInterface $bridge = new ProcessBridge(),
        private readonly string $defaultDevice = 'ezeos_sim',
    ) {
    }

    public function getConnection(): Connection
    {
        return $this->connection;
    }

    /** Start a fluent QQL query, like Connection::createQueryBuilder() does for SQL. */
    public function createQuantumQueryBuilder(): QuantumQueryBuilder
    {
        return new QuantumQueryBuilder($this);
    }

    /**
     * Use the result of an SQL query (instead of a whole table) as the QQL table `$name`.
     *
     * @param array<int|string, mixed> $params
     * @param array<int|string, mixed> $types
     */
    public function registerSource(string $name, string $sql, array $params = [], array $types = []): self
    {
        $this->sources[$name] = ['sql' => $sql, 'params' => $params, 'types' => $types];

        return $this;
    }

    /**
     * Execute a QQL statement.
     *
     * @param array<string, mixed> $params named parameters (:name) used in the QQL text
     */
    public function executeQuantumQuery(string $qql, array $params = [], ?int $shots = null, ?int $seed = null): QuantumResult
    {
        $info = QueryInspector::inspect($qql);
        $clean = [];
        foreach ($params as $key => $value) {
            $clean[ltrim((string) $key, ':')] = $value;
        }

        $missing = array_diff($info['parameters'], array_keys($clean));
        if ($missing !== []) {
            throw new QuantumQueryException('missing value for parameter(s): :' . implode(', :', $missing));
        }

        $request = [
            'qql'    => $qql,
            'params' => (object) $clean,
            'tables' => [$info['table'] => $this->loadRows($info['table'])],
            'device' => $this->defaultDevice,
        ];
        if ($shots !== null) {
            $request['shots'] = $shots;
        }

        if ($seed !== null) {
            $request['seed'] = $seed;
        }

        $response = $this->bridge->send($request);
        if (($response['ok'] ?? false) !== true) {
            throw new QuantumQueryException((string) ($response['error'] ?? 'unknown EZE OS error'));
        }

        return new QuantumResult($response);
    }

    /** @return list<array<string, mixed>> */
    private function loadRows(string $table): array
    {
        if (array_key_exists($table, $this->sources)) {
            $s = $this->sources[$table];

            return $this->connection->fetchAllAssociative($s['sql'], $s['params'], $s['types']);
        }

        // Table names come from the lexer as plain identifiers; quote them per platform anyway.
        $qb = $this->connection->createQueryBuilder()
            ->select('*')
            ->from($this->connection->quoteSingleIdentifier($table));

        try {
            return $qb->executeQuery()->fetchAllAssociative();
        } catch (\Throwable $e) {
            throw new QuantumQueryException(sprintf('could not read table "%s" through Doctrine: %s', $table, $e->getMessage()), 0, $e);
        }
    }
}
