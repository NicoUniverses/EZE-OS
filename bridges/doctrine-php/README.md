# ezeos/doctrine-quantum

Run quantum queries (QQL) on data from any [Doctrine DBAL](https://www.doctrine-project.org/projects/dbal.html)
connection. Part of [EZE OS](https://ezeos.org/index.php) — experimental software for managing quantum chips.

```bash
pip install ezeos            # or the wheel from https://ezeos.org/index.php#download
composer require ezeos/doctrine-quantum   # from this folder: composer install
php examples/demo.php        # the three cases shown on ezeos.org
php tests/run.php
```

See [../../docs/DOCTRINE.md](../../docs/DOCTRINE.md) for the layer diagram, the QQL language and
what each statement does on the quantum side.

- `QuantumConnection` wraps a `Doctrine\DBAL\Connection`; rows are read through Doctrine.
- `QuantumQueryBuilder` builds QQL with a Doctrine-style fluent API.
- `Qql\QqlLexer` extends `Doctrine\Common\Lexer\AbstractLexer`.
- `Bridge\ProcessBridge` talks to the EZE OS kernel (`python3 -m ezeos query`) with JSON.

License GPL-2.0-only. Maintained by EZE Capital (Switzerland). Experimental, no warranty, no liability.
