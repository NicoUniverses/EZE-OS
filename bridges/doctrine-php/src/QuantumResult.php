<?php

declare(strict_types=1);

namespace EzeOs\Doctrine;

use ArrayIterator;
use Countable;
use IteratorAggregate;
use Traversable;

use function array_column;
use function array_map;
use function array_values;
use function count;

/**
 * Result of a quantum query. Mirrors the fetch* methods of Doctrine\DBAL\Result
 * and adds the quantum plan, measurement counts and kernel log.
 *
 * @implements IteratorAggregate<int, array<string, mixed>>
 */
final class QuantumResult implements IteratorAggregate, Countable
{
    /** @param array<string, mixed> $response */
    public function __construct(private readonly array $response)
    {
    }

    /** @return list<array<string, mixed>> */
    public function fetchAllAssociative(): array
    {
        return array_values($this->response['rows'] ?? []);
    }

    /** @return list<list<mixed>> */
    public function fetchAllNumeric(): array
    {
        $columns = $this->getColumns();

        return array_map(
            static fn (array $row): array => array_map(static fn (string $c) => $row[$c] ?? null, $columns),
            $this->fetchAllAssociative(),
        );
    }

    /** @return array<string, mixed>|false */
    public function fetchAssociative(): array|false
    {
        return $this->fetchAllAssociative()[0] ?? false;
    }

    /** @return list<mixed> */
    public function fetchFirstColumn(): array
    {
        $columns = $this->getColumns();

        return $columns === [] ? [] : array_column($this->fetchAllAssociative(), $columns[0]);
    }

    /** @return list<string> */
    public function getColumns(): array
    {
        return $this->response['columns'] ?? [];
    }

    public function getKind(): string
    {
        return (string) ($this->response['kind'] ?? '');
    }

    /** @return array<string, mixed> algorithm, qubits, device, transpiler report ... */
    public function getPlan(): array
    {
        return $this->response['plan'] ?? [];
    }

    /** @return array<string, mixed> success probability, optimality gap, distance ... */
    public function getStats(): array
    {
        return $this->response['stats'] ?? [];
    }

    /** @return array<string, int> raw measurement counts (bit string => shots) */
    public function getCounts(): array
    {
        return $this->response['counts'] ?? [];
    }

    /** @return list<array{event: string, detail: string}> EZE OS kernel audit log */
    public function getKernelLog(): array
    {
        return $this->response['log'] ?? [];
    }

    public function rowCount(): int
    {
        return count($this->fetchAllAssociative());
    }

    public function count(): int
    {
        return $this->rowCount();
    }

    public function getIterator(): Traversable
    {
        return new ArrayIterator($this->fetchAllAssociative());
    }
}
