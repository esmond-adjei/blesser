import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Chip, Field, Select } from "@blesser/ui";
import * as api from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  Confirm,
  MutationError,
  PageHeader,
  Pagination,
  QueryState,
  formatDate,
  useAction,
} from "../components/shared";

type Change = {
  user: api.StaffUser;
  patch: { role: api.Role } | { disabled: boolean };
};
export default function People() {
  const { user: actor } = useAuth();
  const [params, setParams] = useSearchParams();
  const [change, setChange] = useState<Change | null>(null);
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const query = {
    q: params.get("q") || undefined,
    role: api.roles.find((role) => role === params.get("role")),
    limit: 30,
    offset,
  };
  const users = useQuery({
    queryKey: ["users", query],
    queryFn: () => api.users(query),
  });
  const update = useAction(
    (value: Change) => api.updateUser(value.user.id, value.patch),
    "Account updated",
    () => setChange(null),
  );
  const propose = (next: Change) => {
    update.reset();
    setChange(next);
  };
  const setFilter = (key: string, value: string) =>
    setParams((old) => {
      const next = new URLSearchParams(old);
      next.set(key, value);
      next.delete("offset");
      return next;
    });
  return (
    <>
      <PageHeader
        title="People"
        description="Manage staff access and account status. Member applications and notes stay private."
      />
      <div className="filters">
        <Field
          label="Search people"
          type="search"
          placeholder="Name or email"
          value={query.q || ""}
          onChange={(e) => setFilter("q", e.target.value)}
        />
        <Field label="Role">
          <Select
            value={query.role || ""}
            onChange={(e) => setFilter("role", e.target.value)}
          >
            <option value="">All roles</option>
            {api.roles.map((role) => (
              <option key={role} value={role}>
                {role.charAt(0).toUpperCase() + role.slice(1)}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      {change && (
        <Confirm
          title={
            "role" in change.patch
              ? "Change this person's role?"
              : change.patch.disabled
                ? "Disable this account?"
                : "Enable this account?"
          }
          description={
            "role" in change.patch
              ? `${change.user.email} will become an ${change.patch.role}. This changes which tools and data they can access.`
              : `${change.user.email} ${change.patch.disabled ? "will lose access and their active sessions will stop working" : "will be able to sign in again"}.`
          }
          label={
            "role" in change.patch
              ? "Change role"
              : change.patch.disabled
                ? "Disable account"
                : "Enable account"
          }
          danger={"disabled" in change.patch && change.patch.disabled}
          busy={update.isPending}
          error={update.error}
          onCancel={() => {
            setChange(null);
            update.reset();
          }}
          onConfirm={() => update.mutate(change)}
        />
      )}
      {!change && <MutationError error={update.error} />}
      <QueryState query={users} empty={!users.data?.items.length}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Person</th>
                <th>Role</th>
                <th>Account</th>
                <th>Scans / 30 days</th>
                <th>Joined</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.data?.items.map((person) => (
                <tr key={person.id}>
                  <td>
                    <strong>{person.display_name || person.email}</strong>
                    {person.display_name && (
                      <span className="subline">{person.email}</span>
                    )}
                    {person.id === actor?.id && (
                      <span className="subline">Your account</span>
                    )}
                  </td>
                  <td>
                    <Select
                      aria-label={`Role for ${person.email}`}
                      value={person.role}
                      disabled={update.isPending || person.id === actor?.id}
                      onChange={(e) =>
                        propose({
                          user: person,
                          patch: { role: api.roleSchema(e.target.value) },
                        })
                      }
                    >
                      {api.roles.map((role) => (
                        <option key={role} value={role}>
                          {role.charAt(0).toUpperCase() + role.slice(1)}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td>
                    <div className="chip-stack">
                      <Chip tone={person.disabled ? "critical" : "forest"}>
                        {person.disabled ? "Disabled" : "Active"}
                      </Chip>
                      {!person.email_verified && (
                        <Chip tone="sun">Unverified email</Chip>
                      )}
                    </div>
                  </td>
                  <td>{person.scans_last_30_days}</td>
                  <td>{formatDate(person.created_at)}</td>
                  <td>
                    <Button
                      size="sm"
                      disabled={update.isPending || person.id === actor?.id}
                      onClick={() =>
                        propose({
                          user: person,
                          patch: { disabled: !person.disabled },
                        })
                      }
                    >
                      {person.disabled ? "Enable account" : "Disable account"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </QueryState>
      <Pagination
        offset={offset}
        limit={30}
        total={users.data?.total}
        count={users.data?.items.length || 0}
        onChange={(value) =>
          setParams((old) => {
            const next = new URLSearchParams(old);
            next.set("offset", String(value));
            return next;
          })
        }
      />
    </>
  );
}
