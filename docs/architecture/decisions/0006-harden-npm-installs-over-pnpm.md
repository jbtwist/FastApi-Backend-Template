# 6. Harden npm installs instead of adopting pnpm

Date: 2026-09-10

## Status

Accepted

## Context

The npm supply-chain attacks of 2025 — including self-replicating worms — reach
a developer's machine two ways: through a dependency's install lifecycle scripts
(`preinstall`, `install`, `postinstall`, `prepare`), which run automatically on
`npm install`, and through freshly-published compromised versions that automated
installs consume within minutes, well before the release is caught and removed
from the registry.

The frontend is a reusable public JWT-auth template. Its install story is
something every consumer of the template inherits, so the bar is "safe by
default with the ecosystem-standard tool", not "safe if you also adopt our
tooling".

pnpm 10 is often cited as the safer default: it blocks lifecycle scripts unless
a package is on an explicit `onlyBuiltDependencies` allowlist, and it supports a
release-age cooldown. But Expo, Metro and React Native assume a hoisted
`node_modules`; pnpm needs `node-linker=hoisted` to work with them at all, which
removes the dependency isolation that is pnpm's main security advantage. On top
of that it needs `strict-peer-dependencies=false` (this project already carries
a benign peer mismatch, see `.npmrc`) and a build allowlist before it will
install. Every template consumer would inherit that configuration and the
ongoing "does Metro work on pnpm this SDK" compat risk.

npm covers both vectors directly:

- `ignore-scripts` (long-standing) blocks all dependency lifecycle scripts.
- `min-release-age` (npm 11.10.0, February 2026) refuses versions younger than
  a given number of days.

## Decision

Stay on npm. Set in `frontend/.npmrc`:

```ini
ignore-scripts=true
min-release-age=3
```

Install with `npm ci`, so the tree is built only from `package-lock.json`.
`frontend/README.md` documents that, and every install instruction added to the
docs follows it.

## Alternatives considered

- **Adopt pnpm 10** — lifecycle scripts blocked by default, first-class
  `minimumReleaseAge`, content-addressed store. Rejected: Expo/Metro force
  `node-linker=hoisted`, which discards the isolation that makes pnpm safer, so
  the security win over hardened npm is small; and it adds `node-linker`,
  `strict-peer-dependencies`, an `onlyBuiltDependencies` allowlist and a
  standing RN-on-pnpm compat risk that every template consumer inherits. The two
  controls that matter are available in npm.
- **Plain `npm install`, no hardening** — simplest, nothing to explain.
  Rejected: leaves lifecycle-script execution and instant consumption of new
  releases wide open, which are exactly the two vectors the 2025 worms used.
- **`npm ci` only, scripts still allowed** — reproducible, but still runs
  `postinstall` from every dependency. Rejected: reproducibility is not the
  threat being addressed.
- **A third-party gate (Socket, `allow-scripts`)** — finer-grained: a
  per-package script allowlist, registry-anomaly detection. Rejected for now as
  another dependency and, for Socket, another service to run. Revisit if a
  dependency legitimately needs a build step and the blanket block becomes
  painful to manage by hand.
- **A longer cooldown (7+ days)** — more protection. `min-release-age=3` chosen
  as the balance against being pinned to known-stale versions during active
  development. Raise it later by editing one line.

## Consequences

- Installs run no dependency lifecycle scripts. Two packages in the current tree
  ship an install script — `fsevents` (macOS file-watching) and `unrs-resolver`
  (the lint import resolver); both are native-addon fallbacks whose prebuilt
  binaries load without the script on a normal macOS/Linux dev machine, and
  `npm ci` installs the platform-specific optional dependency `unrs-resolver`
  needs. A future dependency that genuinely requires a compile step will not
  build: allow it deliberately with `npm rebuild <pkg>` after reading its
  script, or run that one install with `--ignore-scripts=false`.
- `min-release-age` gates the lockfile, not `npm ci`. `npm ci` replays
  `package-lock.json` whatever the age of its entries; the cooldown bites when
  someone runs `npm install <pkg>` or `npm update`, where a version younger than
  three days is skipped for the newest one that clears the window. To pull a
  just-published version on purpose: `npm install <pkg> --min-release-age 0`.
- The cooldown is silent on npm older than 11.10.0 — the tree is built with no
  age filter and npm does not warn. `.npmrc` records the requirement;
  `ignore-scripts` still works on older npm.
- If Dependabot or Renovate is added later, set its own cooldown
  (`cooldown:` / `minimumReleaseAge`) to 3 days too, or it will keep proposing
  versions npm itself would not pick.
- `e2e/` keeps npm defaults. Its `@playwright/test` postinstall downloads
  browser binaries — a lifecycle script that has to run — and its installs are
  run by maintainers, not by template consumers.
