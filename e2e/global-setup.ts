// Before the tests: create the admin on the "main" server and keep its session, so
// tests of the app itself start signed in.
import { mkdirSync } from 'node:fs';
import { request } from '@playwright/test';
import { ADMIN, AUTH_FILE, PORTS, local } from './tests/servers.ts';

export default async function globalSetup() {
  const api = await request.newContext({ baseURL: local(PORTS.main) });
  const response = await api.post('/api/v1/setup', { data: ADMIN });
  if (response.status() !== 201) {
    throw new Error(`Couldn't set up the test server: ${response.status()} ${await response.text()}`);
  }
  mkdirSync('.auth', { recursive: true });
  await api.storageState({ path: AUTH_FILE });
  await api.dispose();
}
