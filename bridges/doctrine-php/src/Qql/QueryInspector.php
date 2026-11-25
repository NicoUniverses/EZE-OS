<?php

declare(strict_types=1);

namespace EzeOs\Doctrine\Qql;

use EzeOs\Doctrine\Exception\QuantumQueryException;

use function array_values;
use function in_array;
use function sprintf;

/**
 * Reads a QQL string with the Doctrine-based lexer and reports what the
 * bridge needs before calling the kernel: the statement kind, the table to
 * load through Doctrine DBAL and the named parameters it expects.
 */
final class QueryInspector
{
    /** @return array{kind: string, table: string, parameters: list<string>} */
    public static function inspect(string $qql): array
    {
        $lexer = new QqlLexer();
        $lexer->setInput($qql);
        $lexer->moveNext();

        if (! $lexer->isNextTokenAny(['SEARCH', 'OPTIMIZE', 'SAMPLE'])) {
            throw new QuantumQueryException('QQL must start with SEARCH, OPTIMIZE or SAMPLE');
        }

        $kind       = (string) $lexer->lookahead->value;
        $table      = null;
        $parameters = [];

        while ($lexer->moveNext()) {
            $token = $lexer->lookahead;
            if ($token->isA(QqlLexer::T_NONE)) {
                throw new QuantumQueryException(sprintf('unexpected "%s" at position %d', $token->value, $token->position));
            }

            if ($token->isA('FROM') && $table === null) {
                $next = $lexer->glimpse();
                if ($next === null || ! $next->isA(QqlLexer::T_IDENTIFIER)) {
                    throw new QuantumQueryException('FROM must be followed by a table name');
                }

                $table = (string) $next->value;
            }

            if (! $token->isA(QqlLexer::T_PARAMETER) || in_array($token->value, $parameters, true)) {
                continue;
            }

            $parameters[] = (string) $token->value;
        }

        if ($table === null) {
            throw new QuantumQueryException('QQL needs a FROM <table> clause');
        }

        return ['kind' => $kind, 'table' => $table, 'parameters' => array_values($parameters)];
    }
}
