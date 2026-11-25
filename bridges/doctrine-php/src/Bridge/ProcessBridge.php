<?php

declare(strict_types=1);

namespace EzeOs\Doctrine\Bridge;

use EzeOs\Doctrine\Exception\QuantumQueryException;

use function fclose;
use function fwrite;
use function is_array;
use function is_resource;
use function json_decode;
use function json_encode;
use function proc_close;
use function proc_open;
use function stream_get_contents;
use function trim;

use const JSON_THROW_ON_ERROR;

/**
 * Runs `python -m ezeos query` and exchanges one JSON document over stdin/stdout.
 *
 * Install the kernel with `pip install ezeos` (or the wheel from ezeos.org).
 */
final class ProcessBridge implements BridgeInterface
{
    /** @param array<string, string>|null $env */
    public function __construct(
        private readonly string $python = 'python3',
        private readonly ?array $env = null,
    ) {
    }

    /** {@inheritDoc} */
    public function send(array $request): array
    {
        $spec = [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']];
        $proc = proc_open([$this->python, '-m', 'ezeos', 'query'], $spec, $pipes, null, $this->env);
        if (! is_resource($proc)) {
            throw new QuantumQueryException('could not start the EZE OS kernel (' . $this->python . ')');
        }

        fwrite($pipes[0], json_encode($request, JSON_THROW_ON_ERROR));
        fclose($pipes[0]);
        $stdout = (string) stream_get_contents($pipes[1]);
        $stderr = (string) stream_get_contents($pipes[2]);
        fclose($pipes[1]);
        fclose($pipes[2]);
        proc_close($proc);

        $response = json_decode($stdout, true);
        if (! is_array($response)) {
            throw new QuantumQueryException('invalid response from the EZE OS kernel: ' . trim($stderr ?: $stdout));
        }

        return $response;
    }
}
