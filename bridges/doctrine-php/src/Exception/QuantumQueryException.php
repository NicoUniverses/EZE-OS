<?php

declare(strict_types=1);

namespace EzeOs\Doctrine\Exception;

use RuntimeException;

/** Raised when a QQL query is malformed or the EZE OS kernel reports an error. */
final class QuantumQueryException extends RuntimeException
{
}
