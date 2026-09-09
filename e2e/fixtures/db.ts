/**
 * Direct read access to the end-to-end database.
 *
 * Verification and reset links are only ever delivered by email, so a test has
 * to get the token some other way. `email_outbox` holds it in the clear — that
 * row *is* the delivery payload, and the hashed copy lives in the token tables
 * — so reading it here needs no test-only endpoint and no mail server.
 */
import pg from 'pg';

import { pgConnectionString } from '../config/env';

/** Matches `backend.mail.models.EmailKind`. */
export type EmailKind = 'verification' | 'password_reset';

const POLL_INTERVAL_MS = 100;

export class Db {
  private readonly client: pg.Client;

  private constructor(client: pg.Client) {
    this.client = client;
  }

  static async connect(): Promise<Db> {
    const client = new pg.Client({ connectionString: pgConnectionString });
    await client.connect();
    const { rows } = await client.query<{ ok: boolean }>(
      "SELECT to_regclass('public.email_outbox') IS NOT NULL AS ok",
    );
    if (!rows[0]?.ok) {
      await client.end();
      throw new Error(
        `${pgConnectionString} has no schema — start-backend.sh should have run "alembic upgrade head"`,
      );
    }
    return new Db(client);
  }

  async close(): Promise<void> {
    await this.client.end();
  }

  /**
   * The newest outbox token for an address, waiting for the row to land.
   *
   * The row is committed in the same transaction as the request that triggers
   * it, but the test gets here right after a button press — the request may
   * still be in flight, hence the poll.
   *
   * @param email Address the email was queued for.
   * @param kind Which link to fetch; an address can have both.
   * @param timeoutMs How long to wait for the row before failing.
   * @throws If no matching row appears before the timeout.
   */
  async waitForOutboxToken(
    email: string,
    kind: EmailKind,
    timeoutMs = 15_000,
  ): Promise<string> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const { rows } = await this.client.query<{ token: string }>(
        `SELECT token
           FROM email_outbox
          WHERE email = $1 AND kind = $2
          ORDER BY created_at DESC
          LIMIT 1`,
        [email, kind],
      );
      if (rows.length > 0) return rows[0].token;
      if (Date.now() > deadline) {
        throw new Error(`No ${kind} email queued for ${email} within ${timeoutMs}ms`);
      }
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
  }

  /** Whether the account exists and has confirmed its address. */
  async isEmailVerified(email: string): Promise<boolean> {
    // `user` is a reserved word in Postgres, hence the quoting.
    const { rows } = await this.client.query<{ email_verified_at: Date | null }>(
      'SELECT email_verified_at FROM "user" WHERE email = $1',
      [email],
    );
    return rows.length > 0 && rows[0].email_verified_at !== null;
  }
}
