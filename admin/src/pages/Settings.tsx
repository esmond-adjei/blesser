import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Field, Select } from "@blesser/ui";
import * as api from "../lib/api";
import {
  MutationError,
  PageHeader,
  QueryState,
  statusLabels,
  useAction,
} from "../components/shared";

export default function Settings() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  return (
    <>
      <PageHeader
        title="Settings"
        description="Set publishing defaults and the limits discovery agents work within."
      />
      <QueryState query={settings} empty={false}>
        {settings.data && <SettingsForm initial={settings.data} />}
      </QueryState>
    </>
  );
}
function SettingsForm({ initial }: { initial: api.Settings }) {
  const [draft, setDraft] = useState(initial);
  const update = useAction(api.updateSettings, "Settings saved");
  return (
    <form
      className="settings-form section-stack"
      onSubmit={(e) => {
        e.preventDefault();
        update.mutate(draft);
      }}
    >
      <section className="section-stack">
        <h2>Publishing defaults</h2>
        <p className="text-ink-secondary">
          These apply to new finds and submissions.
        </p>
        <div className="form-grid">
          <Field label="Agent find status">
            <Select
              value={draft.agent_default.status}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  agent_default: {
                    ...draft.agent_default,
                    status: api.statusSchema(e.target.value),
                  },
                })
              }
            >
              {api.statuses.map((status) => (
                <option key={status} value={status}>
                  {statusLabels[status]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Agent find audience">
            <Select
              value={draft.agent_default.audience}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  agent_default: {
                    ...draft.agent_default,
                    audience: api.audienceSchema(e.target.value),
                  },
                })
              }
            >
              <option value="public">Public</option>
              <option value="members">Members only</option>
            </Select>
          </Field>
          <Field label="Community submission status">
            <Select
              value={draft.community_default.status}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  community_default: {
                    status: api.statusSchema(e.target.value),
                  },
                })
              }
            >
              {api.statuses.map((status) => (
                <option key={status} value={status}>
                  {statusLabels[status]}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </section>
      <section className="section-stack">
        <h2>Archive closed opportunities</h2>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={draft.auto_archive}
            onChange={(e) =>
              setDraft({ ...draft, auto_archive: e.target.checked })
            }
          />{" "}
          Archive the day after the deadline
        </label>
        <p className="text-ink-secondary">Rolling opportunities stay open.</p>
      </section>
      <section className="section-stack">
        <h2>Member scan limits</h2>
        <div className="form-grid">
          <Field
            label="Scans per hour"
            type="number"
            min="0"
            step="1"
            required
            value={draft.member_scan_limits.per_hour}
            onChange={(e) =>
              setDraft({
                ...draft,
                member_scan_limits: {
                  ...draft.member_scan_limits,
                  per_hour: Number(e.target.value),
                },
              })
            }
          />
          <Field
            label="Scans per day"
            type="number"
            min="0"
            step="1"
            required
            value={draft.member_scan_limits.per_day}
            onChange={(e) =>
              setDraft({
                ...draft,
                member_scan_limits: {
                  ...draft.member_scan_limits,
                  per_day: Number(e.target.value),
                },
              })
            }
          />
        </div>
      </section>
      <section className="section-stack">
        <h2>Discovery sweep</h2>
        <Field
          label="Hours between sweeps"
          type="number"
          min="1"
          step="1"
          required
          value={draft.sweep_hours}
          onChange={(e) =>
            setDraft({ ...draft, sweep_hours: Number(e.target.value) })
          }
        />
      </section>
      <MutationError error={update.error} />
      <Button type="submit" variant="primary" disabled={update.isPending}>
        {update.isPending ? "Saving…" : "Save settings"}
      </Button>
    </form>
  );
}
