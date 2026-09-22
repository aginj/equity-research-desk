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
import Credentials from "next-auth/providers/credentials";
import { Pool } from "pg";

import { authConfig, type Role } from "@/auth.config";

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

function apiBase(): string {
  return (
    process.env.API_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8810"
  ).replace(/\/+$/, "");
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  providers: [
    ...authConfig.providers,
    Credentials({
      id: "credentials",
      name: "Username",
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const username = String(credentials?.username ?? "").trim();
        const password = String(credentials?.password ?? "");
        if (!username || !password) return null;
        const response = await fetch(`${apiBase()}/api/v1/auth/login`, {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        if (!response.ok) return null;
        const data = (await response.json()) as {
          user: { id: string; email?: string | null; name?: string | null; role: Role };
          token: string;
          exp: number;
        };
        return {
          id: data.user.id,
          email: data.user.email ?? `${username}@local`,
          name: data.user.name ?? username,
          role: data.user.role,
          apiToken: data.token,
          apiTokenExp: data.exp,
        };
      },
    }),
  ],
  ...(pg ? { adapter: PostgresAdapter(pg) } : {}),
});
