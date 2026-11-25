<?php

declare(strict_types=1);

namespace EzeOs\Doctrine\Bridge;

/** Transport between PHP and the EZE OS kernel (JSON request in, JSON response out). */
interface BridgeInterface
{
    /**
     * @param array<string, mixed> $request
     *
     * @return array<string, mixed>
     */
    public function send(array $request): array;
}
