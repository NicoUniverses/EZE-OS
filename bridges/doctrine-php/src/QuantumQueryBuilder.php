<?php

declare(strict_types=1);

namespace EzeOs\Doctrine;

use LogicException;

use function implode;
use function ltrim;
use function sprintf;

/**
 * Fluent builder for QQL, with the look and feel of Doctrine's QueryBuilder.
 *
 *   $result = $qc->createQuantumQueryBuilder()
 *       ->optimize(3)->from('assets')
 *       ->where('sector != :excluded')->setParameter('excluded', 'crypto')
 *       ->maximize('expected_return')->minimize('risk', 0.5)
 *       ->on('iqm_spark')
 *       ->executeQuantumQuery();
 */
final class QuantumQueryBuilder
{
    private ?string $kind = null;
    private ?int $n = null;
    private ?string $table = null;
    /** @var list<string> */
    private array $where = [];
    private ?string $maximize = null;
    private ?string $minimize = null;
    private ?float $weight = null;
    private ?string $weightBy = null;
    private ?int $limit = null;
    private ?string $device = null;
    private ?int $shots = null;
    private ?int $seed = null;
    private bool $noisy = false;
    /** @var array<string, mixed> */
    private array $params = [];

    public function __construct(private readonly ?QuantumConnection $connection = null)
    {
    }

    public function search(): self
    {
        $this->kind = 'SEARCH';

        return $this;
    }

    public function optimize(int $pick): self
    {
        $this->kind = 'OPTIMIZE';
        $this->n    = $pick;

        return $this;
    }

    public function sample(int $samples): self
    {
        $this->kind = 'SAMPLE';
        $this->n    = $samples;

        return $this;
    }

    public function from(string $table): self
    {
        $this->table = $table;

        return $this;
    }

    public function where(string $condition): self
    {
        $this->where = ['(' . $condition . ')'];

        return $this;
    }

    public function andWhere(string $condition): self
    {
        $this->where[] = ($this->where === [] ? '' : 'AND ') . '(' . $condition . ')';

        return $this;
    }

    public function orWhere(string $condition): self
    {
        $this->where[] = ($this->where === [] ? '' : 'OR ') . '(' . $condition . ')';

        return $this;
    }

    public function maximize(string $column): self
    {
        $this->maximize = $column;

        return $this;
    }

    public function minimize(string $column, ?float $weight = null): self
    {
        $this->minimize = $column;
        $this->weight   = $weight;

        return $this;
    }

    public function weightBy(string $column): self
    {
        $this->weightBy = $column;

        return $this;
    }

    public function setMaxResults(?int $limit): self
    {
        $this->limit = $limit;

        return $this;
    }

    public function on(string $device): self
    {
        $this->device = $device;

        return $this;
    }

    public function shots(int $shots): self
    {
        $this->shots = $shots;

        return $this;
    }

    public function seed(int $seed): self
    {
        $this->seed = $seed;

        return $this;
    }

    public function noisy(bool $noisy = true): self
    {
        $this->noisy = $noisy;

        return $this;
    }

    public function setParameter(string $name, mixed $value): self
    {
        $this->params[ltrim($name, ':')] = $value;

        return $this;
    }

    /** @return array<string, mixed> */
    public function getParameters(): array
    {
        return $this->params;
    }

    public function getQQL(): string
    {
        if ($this->kind === null || $this->table === null) {
            throw new LogicException('call search(), optimize() or sample() and from() first');
        }

        $qql = match ($this->kind) {
            'SEARCH'   => 'SEARCH FROM ' . $this->table,
            'OPTIMIZE' => sprintf('OPTIMIZE PICK %d FROM %s', $this->n, $this->table),
            default    => sprintf('SAMPLE %d FROM %s', $this->n, $this->table),
        };

        if ($this->where !== []) {
            $qql .= ' WHERE ' . implode(' ', $this->where);
        }

        if ($this->kind === 'OPTIMIZE') {
            if ($this->maximize === null) {
                throw new LogicException('OPTIMIZE needs maximize()');
            }

            $qql .= ' MAXIMIZE ' . $this->maximize;
            if ($this->minimize !== null) {
                $qql .= ' MINIMIZE ' . $this->minimize;
                if ($this->weight !== null) {
                    $qql .= ' WEIGHT ' . $this->weight;
                }
            }
        }

        if ($this->kind === 'SAMPLE') {
            if ($this->weightBy === null) {
                throw new LogicException('SAMPLE needs weightBy()');
            }

            $qql .= ' WEIGHT BY ' . $this->weightBy;
        }

        if ($this->kind === 'SEARCH' && $this->limit !== null) {
            $qql .= ' LIMIT ' . $this->limit;
        }

        if ($this->device !== null) {
            $qql .= ' ON ' . $this->device;
        }

        if ($this->shots !== null) {
            $qql .= ' SHOTS ' . $this->shots;
        }

        if ($this->seed !== null) {
            $qql .= ' SEED ' . $this->seed;
        }

        if ($this->noisy) {
            $qql .= ' NOISY';
        }

        return $qql;
    }

    public function executeQuantumQuery(): QuantumResult
    {
        if ($this->connection === null) {
            throw new LogicException('this builder is not attached to a QuantumConnection');
        }

        return $this->connection->executeQuantumQuery($this->getQQL(), $this->params);
    }

    public function __toString(): string
    {
        return $this->getQQL();
    }
}
