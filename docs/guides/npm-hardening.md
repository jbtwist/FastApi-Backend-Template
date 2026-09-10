# Harden npm installs

To protect against supply-chain attacks, this project enforces security hardening
on `npm` installs in the frontend.

## Configuration

The `frontend/.npmrc` file contains:

```ini
ignore-scripts=true
min-release-age=3
```

- `ignore-scripts=true`: Prevents the execution of `preinstall`, `install`,
  `postinstall`, and `prepare` lifecycle scripts.
- `min-release-age=3`: Refuses to install package versions published within the
  last 72 hours. This requires `npm` >= 11.10.0.

## Installation

Always install dependencies using:

```bash
npm ci
```

This ensures that the `node_modules` tree is built exactly from the
`package-lock.json` file, maintaining reproducibility.

For more details on the rationale, see [ADR 6](../architecture/decisions/0006-harden-npm-installs-over-pnpm.md).
