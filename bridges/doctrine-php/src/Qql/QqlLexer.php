<?php

declare(strict_types=1);

namespace EzeOs\Doctrine\Qql;

use Doctrine\Common\Lexer\AbstractLexer;

use function ctype_alpha;
use function in_array;
use function is_numeric;
use function str_contains;
use function str_replace;
use function strtoupper;
use function substr;

/**
 * Tokenizer for QQL (the EZE OS Quantum Query Language), built on doctrine/lexer.
 *
 * The same token rules are implemented in Python (ezeos/query/qql.py) so both sides
 * of the bridge agree on what a query means.
 *
 * @extends AbstractLexer<string, string|int|float>
 */
final class QqlLexer extends AbstractLexer
{
    public const T_NONE        = 'T_NONE';
    public const T_IDENTIFIER  = 'T_IDENTIFIER';
    public const T_INTEGER     = 'T_INTEGER';
    public const T_FLOAT       = 'T_FLOAT';
    public const T_STRING      = 'T_STRING';
    public const T_PARAMETER   = 'T_INPUT_PARAMETER';
    public const T_COMPARISON  = 'T_COMPARISON';
    public const T_OPEN_PAREN  = 'T_OPEN_PARENTHESIS';
    public const T_CLOSE_PAREN = 'T_CLOSE_PARENTHESIS';
    public const T_COMMA       = 'T_COMMA';

    public const KEYWORDS = [
        'SEARCH', 'OPTIMIZE', 'SAMPLE', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'LIMIT',
        'ON', 'SHOTS', 'SEED', 'NOISY', 'PICK', 'MAXIMIZE', 'MINIMIZE', 'WEIGHT', 'BY',
        'TRUE', 'FALSE', 'NULL',
    ];

    /** {@inheritDoc} */
    protected function getCatchablePatterns(): array
    {
        return [
            ':[a-z_][a-z0-9_]*',
            '[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*',
            '(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:e[+-]?[0-9]+)?',
            "'(?:[^']|'')*'",
            '<=|>=|!=|<>|=|<|>',
            '[(),]',
        ];
    }

    /** {@inheritDoc} */
    protected function getNonCatchablePatterns(): array
    {
        return ['\s+'];
    }

    protected function getType(string &$value): string
    {
        if ($value[0] === ':') {
            $value = substr($value, 1);

            return self::T_PARAMETER;
        }

        if (is_numeric($value)) {
            return str_contains($value, '.') || str_contains(strtoupper($value), 'E') ? self::T_FLOAT : self::T_INTEGER;
        }

        if ($value[0] === "'") {
            $value = str_replace("''", "'", substr($value, 1, -1));

            return self::T_STRING;
        }

        if (in_array($value, ['<=', '>=', '!=', '<>', '=', '<', '>'], true)) {
            return self::T_COMPARISON;
        }

        if ($value === '(') {
            return self::T_OPEN_PAREN;
        }

        if ($value === ')') {
            return self::T_CLOSE_PAREN;
        }

        if ($value === ',') {
            return self::T_COMMA;
        }

        if (ctype_alpha($value[0]) || $value[0] === '_') {
            $upper = strtoupper($value);

            return in_array($upper, self::KEYWORDS, true) ? $upper : self::T_IDENTIFIER;
        }

        return self::T_NONE;
    }
}
