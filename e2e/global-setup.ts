// Before the tests: on the "shots" server (when it runs), create the admin, add its fixed test
// data (review/seed-shots.ts) for the saved screenshots, and keep its session. The other tests'
// servers are each worker's own (tests/clock.ts), set up there.
import { mkdirSync } from 'node:fs';
import { request } from '@playwright/test';
import { seed } from './review/seed-shots.ts';
import { ADMIN, PORTS, SHOTS_AUTH_FILE, local } from './tests/servers.ts';

export default async function globalSetup() {
  // The screenshots server only runs when the screenshots are tested (E2E_SERVERS, see serve.mjs).
  if (process.env.E2E_SERVERS !== undefined && !process.env.E2E_SERVERS.split(',').includes('shots')) return;
  mkdirSync('.auth', { recursive: true });
  const shots = await request.newContext({ baseURL: local(PORTS.shots) });
  const made = await shots.post('/api/v1/setup', { data: ADMIN });
  if (made.status() !== 201) {
    throw new Error(`Couldn't set up the screenshots server: ${made.status()} ${await made.text()}`);
  }
  await seed(shots);
  // The theme comes from the device setting: put the account on Auto.
  await shots.put('/api/v1/me/preferences', { data: { theme: 'auto' } });
  await shots.storageState({ path: SHOTS_AUTH_FILE });
  await shots.dispose();
}
