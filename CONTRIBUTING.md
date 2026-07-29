# Contributing

## Workflow

1. Create a focused branch.
2. Change only the files required for the task.
3. Add tests for security-relevant behaviour.
4. Run the relevant test suites and static checks.
5. Review staged content before committing.
6. Open a pull request with the risk, evidence, and rollback plan.

## Project constraints

Contributions must preserve:

- append-only JSON event history;
- terminal-controlled scans;
- a read-only dashboard;
- fail-secure decision routing;
- no SQL database;
- no application login or JWT unless project scope changes explicitly.

## Required checks

```bash
python -m compileall -q app terminal
python -m pytest -q
ruff check app tests terminal
mypy app
```

## Prohibited content

Do not commit secrets, private keys, runtime state, generated audit evidence,
local virtual environments, caches, temporary repair bundles, or private viva
materials.
