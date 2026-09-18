/**
 * Reads `.env.e2e` and derives the handful of values the tests and the
 * Playwright web servers need.
 *
 * Deliberately hand-rolled rather than pulling in `dotenv`: the file is a flat
 * `KEY=value` list with comments and nothing else, and the backend is the only
 * consumer of the raw map.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

/** Repository root — the parent of `e2e/`. */
export const repoRoot = resolve(here, '../..');

/** `e2e/` itself; the Playwright config directory. */
export const e2eRoot = resolve(here, '..');

function parseEnvFile(path: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of readFileSync(path, 'utf8').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    out[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  }
  return out;
}

/**
 * Every key in `.env.e2e`, passed verbatim to the backend process.
 *
 * `E2E_DATABASE_URL` overrides the database, for a machine whose Postgres does
 * not match the default. Only that one key is overridable: honouring the whole
 * ambient environment would let a stray `DATABASE_URL` in a shell silently
 * redirect the suite at a real database.
 */
export const backendEnv: Record<string, string> = {
  ...parseEnvFile(resolve(e2eRoot, '.env.e2e')),
  ...(process.env.E2E_DATABASE_URL ? { DATABASE_URL: process.env.E2E_DATABASE_URL } : {}),
};

function required(key: string): string {
  const value = backendEnv[key];
  if (!value) throw new Error(`e2e/.env.e2e is missing ${key}`);
  return value;
}

export const backendUrl = required('API_BASE_URL');
export const frontendUrl = required('FRONTEND_BASE_URL');

function portOf(url: string): string {
  const parsed = new URL(url);
  return parsed.port || (parsed.protocol === 'https:' ? '443' : '80');
}

export const backendPort = portOf(backendUrl);
export const frontendPort = portOf(frontendUrl);

/**
 * `DATABASE_URL` as a libpq connection string.
 *
 * The backend's value carries SQLAlchemy's `+asyncpg` driver marker, which
 * `pg` does not understand.
 */
export const pgConnectionString = required('DATABASE_URL').replace('+asyncpg', '');

/** Name of the database the run owns, parsed out of `DATABASE_URL`. */
export const databaseName = new URL(pgConnectionString).pathname.replace(/^\//, '');

/**
 * A `timedelta` key from `.env.e2e`, in seconds.
 *
 * Understands the two forms the backend's `timedelta` fields accept: a bare
 * number of seconds, or an ISO-8601 `PT#H#M#S` duration.
 */
function durationSeconds(key: string): number {
  const raw = required(key);
  if (/^\d+$/.test(raw)) return Number(raw);
  const match = /^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/.exec(raw);
  if (!match) throw new Error(`Cannot read ${key}=${raw} as a duration`);
  const [, h = '0', m = '0', s = '0'] = match;
  return Number(h) * 3600 + Number(m) * 60 + Number(s);
}

/** `ACCESS_TOKEN_EXP` in seconds, so a spec can wait a session out. */
export const accessTokenExpSeconds = durationSeconds('ACCESS_TOKEN_EXP');

/** `REFRESH_TOKEN_REUSE_GRACE` in seconds, so a replay is not mistaken for a race. */
export const refreshTokenReuseGraceSeconds = durationSeconds('REFRESH_TOKEN_REUSE_GRACE');

/**
 * The same server with the database swapped for `postgres`, so a client can
 * connect before the run's own database exists.
 */
export const maintenanceConnectionString = (() => {
  const url = new URL(pgConnectionString);
  url.pathname = '/postgres';
  return url.toString();
})();
