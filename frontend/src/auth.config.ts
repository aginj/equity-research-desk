/**
 * Auth.js configuration that is safe to run in the Edge runtime (middleware).
 *
 * Nothing here touches Postgres; `auth.ts` adds the database adapter for the Node runtime.
 * Sessions are JWTs in an encrypted cookie. On each session read we mint (or refresh) a
 * separate short-lived HS256 token — `apiToken` — that the browser presents to FastAPI as
 * `Authorization: Bearer`. FastAPI verifies it with the same `SMP_AUTH_JWT_SECRET`.
 */

import type { NextAuthConfig } from "next-auth";
import type { Provider } from "next-auth/providers";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";
import Resend from "next-auth/providers/resend";
// Subpath import keeps JWE/deflate (Node-only) out of the Edge middleware bundle.
import { SignJWT } from "jose/jwt/sign";

export type Role = "user" | "admin";

export const API_TOKEN_TTL_SECONDS = 60 * 60;
/** Refresh the API token when less than this remains, so a live tab never sees a 401. */
const API_TOKEN_REFRESH_WINDOW_SECONDS = 10 * 60;
const API_TOKEN_AUDIENCE = "desk-api";
const API_TOKEN_ISSUER = "desk-web";

export function adminEmails(): Set<string> {
  return new Set(
    (process.env.SMP_ADMIN_EMAILS ?? "")
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean),
  );
}

/** Display-only: the API decides authorization from its own allowlist. */
export function roleFor(email: string | null | undefined): Role {
  return email && adminEmails().has(email.toLowerCase()) ? "admin" : "user";
}

export function configuredProviders(): Provider[] {
  const providers: Provider[] = [];
  if (process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET) providers.push(Google);
  if (process.env.AUTH_GITHUB_ID && process.env.AUTH_GITHUB_SECRET) providers.push(GitHub);
  // Magic links need somewhere to store verification tokens, hence the Postgres requirement.
  if (process.env.AUTH_RESEND_KEY && process.env.DATABASE_URL) {
    providers.push(Resend({ from: process.env.AUTH_RESEND_FROM ?? "Equity Research Desk <login@example.com>" }));
  }
  return providers;
}

async function mintApiToken(input: {
  sub: string;
  email?: string | null;
  name?: string | null;
  picture?: string | null;
  role: Role;
}): Promise<{ token: string; exp: number }> {
  const secret = process.env.SMP_AUTH_JWT_SECRET;
  if (!secret) throw new Error("SMP_AUTH_JWT_SECRET is not set");
  const now = Math.floor(Date.now() / 1000);
  const exp = now + API_TOKEN_TTL_SECONDS;
  const token = await new SignJWT({
    email: input.email ?? undefined,
    name: input.name ?? undefined,
    picture: input.picture ?? undefined,
    role: input.role,
  })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setSubject(input.sub)
    .setAudience(API_TOKEN_AUDIENCE)
    .setIssuer(API_TOKEN_ISSUER)
    .setIssuedAt(now)
    .setExpirationTime(exp)
    .sign(new TextEncoder().encode(secret));
  return { token, exp };
}

export const authConfig: NextAuthConfig = {
  providers: configuredProviders(),
  session: { strategy: "jwt", maxAge: 30 * 24 * 60 * 60 },
  pages: { signIn: "/signin", error: "/signin" },
  trustHost: true,
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        // First sign-in: pin identity fields from the provider profile.
        token.sub = user.id ?? token.sub;
        token.email = user.email ?? token.email;
        token.name = user.name ?? token.name;
        token.picture = user.image ?? token.picture;
      }
      token.role = roleFor(token.email);

      const now = Math.floor(Date.now() / 1000);
      const needsToken =
        !token.apiToken ||
        !token.apiTokenExp ||
        token.apiTokenExp - now < API_TOKEN_REFRESH_WINDOW_SECONDS;
      if (needsToken && token.sub && process.env.SMP_AUTH_JWT_SECRET) {
        const minted = await mintApiToken({
          sub: token.sub,
          email: token.email,
          name: token.name,
          picture: token.picture,
          role: token.role,
        });
        token.apiToken = minted.token;
        token.apiTokenExp = minted.exp;
      }
      return token;
    },
    async session({ session, token }) {
      session.user.id = token.sub ?? "";
      session.user.role = token.role ?? "user";
      session.apiToken = token.apiToken;
      session.apiTokenExp = token.apiTokenExp;
      return session;
    },
  },
};
