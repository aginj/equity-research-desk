"use client";

import { signIn } from "next-auth/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";

import { useWorkspace } from "@/components/WorkspaceProvider";
import { IconGitHub, IconGoogle, IconLock, IconMail, IconSliders, IconStar } from "@/components/icons";
import { Alert, Button, Card, Skeleton } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

type ProviderInfo = { id: string; name: string; type: string };

const ERRORS: Record<string, string> = {
  OAuthAccountNotLinked: "That email is already linked to a different sign-in method. Use the one you signed up with.",
  AccessDenied: "Access was denied by the provider.",
  Verification: "That sign-in link has expired or was already used. Request a new one.",
  Configuration: "Sign-in is not fully configured on this server yet.",
  Default: "Sign-in failed. Please try again.",
};

export default function SignInPage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto mt-10 h-96 max-w-md" />}>
      <SignIn />
    </Suspense>
  );
}

function SignIn() {
  const params = useSearchParams();
  const router = useRouter();
  const { auth } = useWorkspace();
  const callbackUrl = safeCallback(params.get("callbackUrl"));
  const errorCode = params.get("error");

  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [firstAdmin, setFirstAdmin] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (auth === "authenticated") router.replace(callbackUrl);
  }, [auth, callbackUrl, router]);

  useEffect(() => {
    fetch("/api/auth/providers")
      .then((r) => (r.ok ? r.json() : {}))
      .then((data: Record<string, ProviderInfo>) => setProviders(Object.values(data)))
      .catch(() => setProviders([]));
  }, []);

  useEffect(() => {
    api
      .health()
      .then((health) => {
        const noneYet = health.local_users === false;
        setFirstAdmin(noneYet);
        if (noneYet) setMode("register");
      })
      .catch(() => undefined);
  }, []);

  const oauth = providers?.filter((p) => p.type === "oauth" || p.type === "oidc") ?? [];
  const emailProvider = providers?.find((p) => p.type === "email");

  async function onLocal(event: FormEvent) {
    event.preventDefault();
    const user = username.trim();
    if (!user || password.length < 8) {
      setFormError("Username is required and the password must be at least 8 characters.");
      return;
    }
    setBusy("credentials");
    setFormError(null);
    try {
      if (mode === "register") {
        await api.register(user, password);
      }
      const result = await signIn("credentials", { username: user, password, callbackUrl, redirect: false });
      if (result?.error) {
        setFormError(mode === "register" ? "Account created, but sign-in failed. Try signing in." : "Invalid username or password.");
        return;
      }
      router.replace(callbackUrl);
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setBusy(null);
    }
  }

  async function onEmail(event: FormEvent) {
    event.preventDefault();
    if (!emailProvider || !email.trim()) return;
    setBusy(emailProvider.id);
    try {
      await signIn(emailProvider.id, { email: email.trim(), callbackUrl, redirect: false });
      setSent(true);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto grid max-w-4xl gap-8 py-6 lg:grid-cols-[1fr_1.1fr] lg:items-center lg:py-14">
      <section className="fade-up">
        <div className="eyebrow">Sign in</div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-fg md:text-4xl">Your own view of the desk</h1>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-muted">
          The book, tape, and idea pages stay readable. Signing in saves a personal workspace. Only a desk admin can
          run agents, edit the universe, or change desk defaults.
        </p>
        <ul className="mt-6 space-y-3 text-sm text-fg-2">
          <li className="flex items-start gap-3">
            <span className="mt-0.5 text-accent"><IconSliders size={18} /></span>
            <span>
              <strong className="font-medium text-fg">Venue and risk appetite</strong> — view the shared book re-ranked under
              conservative, balanced, or aggressive policy.
            </span>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-0.5 text-accent"><IconStar size={18} /></span>
            <span>
              <strong className="font-medium text-fg">Watchlist</strong> — star names, filter the book to them, and flag
              tickers you want covered.
            </span>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-0.5 text-accent"><IconLock size={18} /></span>
            <span>
              <strong className="font-medium text-fg">Local accounts</strong> — username and password are stored hashed in
              this desk&apos;s database. The first account is the admin.
            </span>
          </li>
        </ul>
      </section>

      <Card className="fade-up p-6 sm:p-8" style={{ animationDelay: "60ms" }}>
        <h2 className="text-lg font-semibold text-fg">{mode === "register" ? "Create an account" : "Sign in"}</h2>
        <p className="mt-1 text-xs text-muted">Continue to {callbackUrl === "/" ? "the desk" : callbackUrl}</p>

        {firstAdmin && mode === "register" ? (
          <div className="mt-4">
            <Alert tone="warning" title="First account is admin">
              This desk has no users yet. The account you create can run agents and change desk configuration. Later
              sign-ups are regular users.
            </Alert>
          </div>
        ) : null}

        {errorCode ? (
          <div className="mt-4">
            <Alert tone="danger">{ERRORS[errorCode] ?? ERRORS.Default}</Alert>
          </div>
        ) : null}

        {formError ? (
          <div className="mt-4">
            <Alert tone="danger">{formError}</Alert>
          </div>
        ) : null}

        <form onSubmit={onLocal} className="mt-6 space-y-3">
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-fg-2">Username</span>
            <input
              autoComplete="username"
              required
              minLength={3}
              maxLength={32}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              data-testid="local-username"
              className="h-11 w-full rounded-xl border border-border-strong bg-surface px-3 text-sm text-fg placeholder:text-muted-2 focus:border-accent"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-fg-2">Password</span>
            <input
              type="password"
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              data-testid="local-password"
              className="h-11 w-full rounded-xl border border-border-strong bg-surface px-3 text-sm text-fg placeholder:text-muted-2 focus:border-accent"
            />
          </label>
          <Button type="submit" size="lg" className="w-full" loading={busy === "credentials"} data-testid="local-auth-submit">
            {mode === "register" ? "Create account" : "Sign in"}
          </Button>
          <p className="text-center text-xs text-muted">
            {mode === "register" ? "Already have an account?" : "Need an account?"}{" "}
            <button
              type="button"
              className="font-medium text-accent underline-offset-2 hover:underline"
              onClick={() => {
                setFormError(null);
                setMode(mode === "register" ? "signin" : "register");
              }}
            >
              {mode === "register" ? "Sign in" : "Create one"}
            </button>
          </p>
        </form>

        <div className="mt-6 space-y-3">
          {oauth.length || emailProvider ? (
            <div className="flex items-center gap-3 py-1 text-[11px] uppercase tracking-wider text-muted-2">
              <span className="h-px flex-1 bg-border" />
              or
              <span className="h-px flex-1 bg-border" />
            </div>
          ) : null}

          {providers === null ? (
            <>
              <Skeleton className="h-11 w-full" />
            </>
          ) : null}

          {oauth.map((p) => (
            <Button
              key={p.id}
              variant="secondary"
              size="lg"
              className="w-full"
              loading={busy === p.id}
              onClick={() => {
                setBusy(p.id);
                void signIn(p.id, { callbackUrl });
              }}
            >
              {p.id === "google" ? <IconGoogle size={18} /> : p.id === "github" ? <IconGitHub size={18} /> : null}
              Continue with {p.name}
            </Button>
          ))}

          {emailProvider ? (
            <>
              {oauth.length ? (
                <div className="flex items-center gap-3 py-1 text-[11px] uppercase tracking-wider text-muted-2">
                  <span className="h-px flex-1 bg-border" />
                  or
                  <span className="h-px flex-1 bg-border" />
                </div>
              ) : null}
              {sent ? (
                <Alert tone="success" title="Check your inbox">
                  We sent a sign-in link to <span className="font-medium">{email}</span>. It expires in 24 hours.
                </Alert>
              ) : (
                <form onSubmit={onEmail} className="space-y-3">
                  <label className="block">
                    <span className="mb-1.5 block text-xs font-medium text-fg-2">Email address</span>
                    <input
                      type="email"
                      required
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      className="h-11 w-full rounded-xl border border-border-strong bg-surface px-3 text-sm text-fg placeholder:text-muted-2 focus:border-accent"
                    />
                  </label>
                  <Button type="submit" size="lg" className="w-full" loading={busy === emailProvider.id}>
                    <IconMail size={18} />
                    Email me a sign-in link
                  </Button>
                </form>
              )}
            </>
          ) : null}
        </div>

        <p className="mt-6 text-[11px] leading-relaxed text-muted-2">
          By continuing you agree to the <Link href="/terms" className="underline underline-offset-2">terms</Link> and{" "}
          <Link href="/privacy" className="underline underline-offset-2">privacy notice</Link>. Research only — not
          investment advice.
        </p>
      </Card>
    </div>
  );
}

/** Only allow same-origin relative redirects. */
function safeCallback(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/";
  return raw;
}
