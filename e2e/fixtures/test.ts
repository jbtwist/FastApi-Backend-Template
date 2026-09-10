/**
 * The `test` every spec imports, with the two things all of them need: a
 * database handle and a fresh account address.
 *
 * There is no per-test cleanup. Every test mints a unique address, so accounts
 * never collide and nothing has to be torn down — cheaper and less brittle
 * than truncating tables between tests.
 */
import { randomUUID } from 'node:crypto';

import { test as base } from '@playwright/test';

import { Db } from './db';

type WorkerFixtures = {
  db: Db;
};

type TestFixtures = {
  /** A never-before-used address for this test. */
  email: string;
  /** A password that satisfies the medium strength floor (12 characters). */
  password: string;
};

export const test = base.extend<TestFixtures, WorkerFixtures>({
  db: [
    async ({}, use) => {
      const db = await Db.connect();
      await use(db);
      await db.close();
    },
    { scope: 'worker' },
  ],

  // `example.com`, not `example.test`: email-validator rejects `.test` as a
  // special-use domain, so the API answers 422 before any logic runs.
  email: async ({}, use) => {
    await use(`e2e-${randomUUID()}@example.com`);
  },

  password: async ({}, use) => {
    await use('e2e-Passw0rd-2026');
  },
});

export { expect } from '@playwright/test';
