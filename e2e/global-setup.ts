// Before the tests: create the admin on the "main" server and keep its session, so
// tests of the app itself start signed in. The same on the "shots" server, which also gets
// its fixed test data (review/seed-shots.ts) for the saved screenshots.
import { mkdirSync } from 'node:fs';
import { request } from '@playwright/test';
import { seed } from './review/seed-shots.ts';
import { ADMIN, AUTH_FILE, PORTS, SHOTS_AUTH_FILE, local } from './tests/servers.ts';

export default async function globalSetup() {
  const api = await request.newContext({ baseURL: local(PORTS.main) });
  const response = await api.post('/api/v1/setup', { data: ADMIN });
  if (response.status() !== 201) {
    throw new Error(`Couldn't set up the test server: ${response.status()} ${await response.text()}`);
  }
  mkdirSync('.auth', { recursive: true });
  await api.storageState({ path: AUTH_FILE });
  await api.dispose();

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
