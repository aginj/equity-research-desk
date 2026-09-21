/**
 * Full Auth.js instance for the Node runtime (route handlers, server components).
 *
 * With `DATABASE_URL` set, users/accounts/verification tokens persist in Postgres via
 * `@auth/pg-adapter` (tables are created by the backend's Alembic migration 0002). Without
 * it — typical local development — OAuth sign-in still works with pure JWT sessions, but
 * email magic links are unavailable.
 */

import PostgresAdapter from "@auth/pg-adapter";
import NextAuth from "next-auth";
import { Pool } from "pg";

import { authConfig } from "@/auth.config";

declare global {
  // Reuse one pool across hot reloads in development.
  var __smpPgPool: Pool | undefined;
}

function pool(): Pool | null {
  const url = process.env.DATABASE_URL;
  if (!url) return null;
  if (!globalThis.__smpPgPool) {
    globalThis.__smpPgPool = new Pool({ connectionString: url, max: 5 });
  }
  return globalThis.__smpPgPool;
}

const pg = pool();

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  ...(pg ? { adapter: PostgresAdapter(pg) } : {}),
});
