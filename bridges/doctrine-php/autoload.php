<?php

declare(strict_types=1);

/*
 * Autoloader for using the bridge without Composer. With Composer, require
 * vendor/autoload.php instead (it brings doctrine/dbal and doctrine/lexer).
 *
 * Loads EzeOs\Doctrine\* from src/ and, if doctrine/lexer is not installed,
 * the copy vendored in third_party/doctrine-lexer (MIT).
 */
spl_autoload_register(static function (string $class): void {
    $map = [
        'EzeOs\\Doctrine\\'        => __DIR__ . '/src/',
        'Doctrine\\Common\\Lexer\\' => __DIR__ . '/../../third_party/doctrine-lexer/',
    ];
    foreach ($map as $prefix => $dir) {
        if (strncmp($class, $prefix, strlen($prefix)) === 0) {
            $file = $dir . str_replace('\\', '/', substr($class, strlen($prefix))) . '.php';
            if (is_file($file)) {
                require $file;
            }

            return;
        }
    }
});
