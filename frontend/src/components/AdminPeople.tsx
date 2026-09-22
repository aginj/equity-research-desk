"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert, Badge, Button, Card, CardHeader, EmptyState, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { relativeTime, when } from "@/lib/format";
import type { AuditEntry, DeskUser, Role } from "@/lib/types";

export function AdminPeople() {
  const [users, setUsers] = useState<DeskUser[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [passwordDraft, setPasswordDraft] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [people, log] = await Promise.all([api.adminUsers(), api.audit()]);
      setUsers(people.users);
      setAudit(log.entries);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function setRole(id: string, role: Role) {
    setError(null);
    try {
      await api.setUserRole(id, role);
      setMessage(`Role set to ${role}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change role");
    }
  }

  async function setDisabled(id: string, disabled: boolean) {
    setError(null);
    try {
      await api.setUserDisabled(id, disabled);
      setMessage(disabled ? "Account disabled" : "Account re-enabled");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update account");
    }
  }

  async function resetPassword(id: string) {
    const password = passwordDraft[id]?.trim();
    if (!password || password.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    setError(null);
    try {
      await api.resetUserPassword(id, password);
      setPasswordDraft((current) => ({ ...current, [id]: "" }));
      setMessage("Password reset");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset password");
    }
  }

  return (
    <div className="space-y-6">
      {error ? <Alert tone="danger">{error}</Alert> : null}
      {message ? <Alert tone="success">{message}</Alert> : null}

      <Card className="fade-up overflow-hidden">
        <CardHeader title="Users" description="Local accounts. The last admin cannot be demoted or disabled." />
        {loading ? (
          <div className="space-y-2 p-5">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : users.length === 0 ? (
          <EmptyState title="No local accounts" description="People who register at sign-in appear here." />
        ) : (
          <>
            <ul className="divide-y divide-border md:hidden">
              {users.map((user) => (
                <UserCard
                  key={user.id}
                  user={user}
                  password={passwordDraft[user.id] ?? ""}
                  onPassword={(value) => setPasswordDraft((current) => ({ ...current, [user.id]: value }))}
                  onRole={(role) => void setRole(user.id, role)}
                  onDisabled={(disabled) => void setDisabled(user.id, disabled)}
                  onReset={() => void resetPassword(user.id)}
                />
              ))}
            </ul>
            <div className="hidden overflow-x-auto md:block">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-[11px] uppercase tracking-wider text-muted">
                    <th className="px-5 py-3 font-medium">User</th>
                    <th className="px-3 py-3 font-medium">Role</th>
                    <th className="px-3 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id} className="border-b border-border last:border-0">
                      <td className="px-5 py-3.5">
                        <div className="text-sm font-medium text-fg">{user.username}</div>
                        <div className="text-[11px] text-muted">{user.email ?? user.id}</div>
                      </td>
                      <td className="px-3 py-3.5">
                        <Badge tone={user.role === "admin" ? "accent" : "neutral"}>{user.role}</Badge>
                      </td>
                      <td className="px-3 py-3.5 text-xs text-muted">
                        {user.disabled ? "Disabled" : user.locked ? "Locked" : "Active"}
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => void setRole(user.id, user.role === "admin" ? "user" : "admin")}
                          >
                            {user.role === "admin" ? "Demote" : "Make admin"}
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => void setDisabled(user.id, !user.disabled)}>
                            {user.disabled ? "Enable" : "Disable"}
                          </Button>
                          <input
                            type="password"
                            placeholder="New password"
                            aria-label={`New password for ${user.username}`}
                            value={passwordDraft[user.id] ?? ""}
                            onChange={(e) => setPasswordDraft((current) => ({ ...current, [user.id]: e.target.value }))}
                            className="h-8 w-36 rounded-lg border border-border-strong bg-surface px-2 text-xs"
                          />
                          <Button variant="ghost" size="sm" onClick={() => void resetPassword(user.id)}>
                            Reset
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>

      <Card className="fade-up overflow-hidden">
        <CardHeader title="Audit" description="Admin mutations on universe, appetite, schedule, and users." />
        {loading ? (
          <div className="p-5">
            <Skeleton className="h-24" />
          </div>
        ) : audit.length === 0 ? (
          <EmptyState title="No audit entries yet" description="Saving desk settings writes a row here." />
        ) : (
          <ul className="divide-y divide-border">
            {audit.map((entry) => (
              <li key={entry.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-xs">
                <span className="font-medium text-fg">{entry.action}</span>
                <span className="text-muted">{entry.target}</span>
                <span className="text-muted-2">{entry.at ? when(entry.at) : relativeTime(entry.at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function UserCard({
  user,
  password,
  onPassword,
  onRole,
  onDisabled,
  onReset,
}: {
  user: DeskUser;
  password: string;
  onPassword: (value: string) => void;
  onRole: (role: Role) => void;
  onDisabled: (disabled: boolean) => void;
  onReset: () => void;
}) {
  return (
    <li className="space-y-2 px-4 py-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-fg">{user.username}</span>
        <Badge tone={user.role === "admin" ? "accent" : "neutral"}>{user.role}</Badge>
      </div>
      <div className="text-[11px] text-muted">{user.disabled ? "Disabled" : user.locked ? "Locked" : "Active"}</div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" onClick={() => onRole(user.role === "admin" ? "user" : "admin")}>
          {user.role === "admin" ? "Demote" : "Make admin"}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => onDisabled(!user.disabled)}>
          {user.disabled ? "Enable" : "Disable"}
        </Button>
      </div>
      <div className="flex gap-2">
        <input
          type="password"
          placeholder="New password"
          aria-label={`New password for ${user.username}`}
          value={password}
          onChange={(e) => onPassword(e.target.value)}
          className="h-8 flex-1 rounded-lg border border-border-strong bg-surface px-2 text-xs"
        />
        <Button variant="ghost" size="sm" onClick={onReset}>
          Reset
        </Button>
      </div>
    </li>
  );
}
