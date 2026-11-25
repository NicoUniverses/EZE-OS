# Third-party notices

EZE OS is licensed under GPL-2.0-only. It includes or adapts the following MIT-licensed code,
which is compatible with the GPL.

## doctrine/lexer

- Source: <https://github.com/doctrine/lexer> (commit 51489dad40bc2361ba3ab022cde6cba10575dbea)
- Copyright (c) 2006-2018 Doctrine Project
- License: MIT, full text in `third_party/doctrine-lexer/LICENSE`
- Used in: `third_party/doctrine-lexer/` (unmodified copy), `ezeos/query/lexer.py` (Python port),
  `bridges/doctrine-php/src/Qql/QqlLexer.php` (extends it)

## doctrine/dbal

- Source: <https://github.com/doctrine/dbal>, License: MIT
- Not copied. `bridges/doctrine-php` depends on it through Composer (`doctrine/dbal ^4.0`).
