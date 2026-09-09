/**
 * Creates the end-to-end database if it is not there yet.
 *
 * Alembic can create the schema but not the database that holds it, so this
 * runs first, connected to the `postgres` maintenance database. Reads
 * `DATABASE_URL` from the environment — start-backend.sh is invoked by
 * Playwright with `.env.e2e` already applied.
 */
import pg from 'pg';

const databaseUrl = process.env.DATABASE_URL;
if (!databaseUrl) {
  console.error('ensure-db: DATABASE_URL is not set');
  process.exit(1);
}

const target = new URL(databaseUrl.replace('+asyncpg', ''));
const databaseName = target.pathname.replace(/^\//, '');

const maintenance = new URL(target.toString());
maintenance.pathname = '/postgres';

const client = new pg.Client({ connectionString: maintenance.toString() });
await client.connect();
try {
  const { rowCount } = await client.query('SELECT 1 FROM pg_database WHERE datname = $1', [
    databaseName,
  ]);
  if (rowCount === 0) {
    // No parameter binding in CREATE DATABASE; quote the identifier instead.
    await client.query(`CREATE DATABASE "${databaseName.replace(/"/g, '""')}"`);
    console.log(`ensure-db: created ${databaseName}`);
  } else {
    console.log(`ensure-db: ${databaseName} already exists`);
  }
} finally {
  await client.end();
}
