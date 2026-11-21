import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Chip, Field, Select } from "@blesser/ui";
import * as api from "../lib/api";
import {
  MutationError,
  PageHeader,
  formatDate,
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
      <ScanSchedules />
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
        <h2>Scheduled scan limits</h2>
        <p className="text-ink-secondary">
          Members can repeat their own scans weekly. Scheduled runs never use a
          member&apos;s scan quota, so these caps hold the cost. Set the token
          budget to zero for no daily cap.
        </p>
        <div className="form-grid">
          {(
            [
              ["member_max", "Weekly scans per member", 0, 20],
              ["runs_per_hour", "Runs started per hour", 0, 200],
              [
                "daily_token_budget",
                "Model tokens per day for scheduled runs",
                0,
                1000000000,
              ],
            ] as const
          ).map(([key, label, min, max]) => (
            <Field
              key={key}
              label={label}
              type="number"
              min={min}
              max={max}
              step={1}
              required
              value={draft.scheduled_scans[key]}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  scheduled_scans: {
                    ...draft.scheduled_scans,
                    [key]: Number(event.target.value),
                  },
                })
              }
            />
          ))}
        </div>
      </section>
      {draft.crawler && (
        <section className="section-stack">
          <h2>Crawler</h2>
          <p className="text-ink-secondary">
            Set hours to zero to pause scheduled crawls. Scans can still process
            queued candidates.
          </p>
          <div className="form-grid">
            {(
              [
                ["hours", "Hours between crawls", 0, 8760, 1],
                ["max_sources", "Sources per pass", 1, 100, 1],
                ["max_items_per_source", "Items per source", 1, 200, 1],
                [
                  "max_candidates_per_task",
                  "Pages to extract per category",
                  0,
                  100,
                  1,
                ],
                [
                  "host_interval_seconds",
                  "Seconds between requests to a host",
                  0.5,
                  60,
                  0.5,
                ],
                [
                  "page_cache_seconds",
                  "Page cache lifetime in seconds",
                  60,
                  604800,
                  1,
                ],
              ] as const
            ).map(([key, label, min, max, step]) => (
              <Field
                key={key}
                label={label}
                type="number"
                min={min}
                max={max}
                step={step}
                required
                value={draft.crawler?.[key]}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    crawler: draft.crawler && {
                      ...draft.crawler,
                      [key]: Number(event.target.value),
                    },
                  })
                }
              />
            ))}
          </div>
        </section>
      )}
      {draft.freshness && (
        <section className="section-stack">
          <h2>Listing checks</h2>
          <p className="text-ink-secondary">
            The worker re-reads listing pages on a schedule. Unchanged pages are
            confirmed without a model; changed pages get an agent check. Closed
            listings are watched for a new cycle.
          </p>
          <div className="form-grid">
            {(
              [
                [
                  "recheck_days",
                  "Days before rechecking undated listings",
                  1,
                  365,
                ],
                ["closing_days", "Days before a deadline to recheck", 0, 60],
                [
                  "closing_recheck_days",
                  "Recheck closing listings not confirmed for this many days",
                  1,
                  365,
                ],
                ["cycle_days", "Days between new-cycle checks", 1, 365],
                [
                  "stale_days",
                  "Archive undated listings not confirmed for this many days",
                  7,
                  1095,
                ],
                ["max_checks", "Pages to check every 15 minutes", 0, 200],
                ["max_agent_checks", "Agent checks per day", 0, 1000],
              ] as const
            ).map(([key, label, min, max]) => (
              <Field
                key={key}
                label={label}
                type="number"
                min={min}
                max={max}
                step={1}
                required
                value={draft.freshness?.[key]}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    freshness: draft.freshness && {
                      ...draft.freshness,
                      [key]: Number(event.target.value),
                    },
                  })
                }
              />
            ))}
          </div>
        </section>
      )}
      <MutationError error={update.error} />
      <Button type="submit" variant="primary" disabled={update.isPending}>
        {update.isPending ? "Saving…" : "Save settings"}
      </Button>
    </form>
  );
}

const CATEGORY_NAMES: Record<string, string> = {
  startup: "Startups",
  research: "Research",
  student: "Students",
};

function intervalLabel(hours: number): string {
  if (hours === 24) return "Daily";
  if (hours === 72) return "Every 3 days";
  if (hours === 168) return "Weekly";
  return `Every ${hours} hours`;
}

const emptySchedule: api.ScanScheduleInput = {
  name: "",
  categories: ["startup", "research", "student"],
  region: "",
  focus: "",
  interval_hours: 168,
};

function ScanSchedules() {
  const schedules = useQuery({
    queryKey: ["scan-schedules"],
    queryFn: api.scanSchedules,
  });
  const [editing, setEditing] = useState<api.ScanSchedule | "new" | null>(null);
  const toggle = useAction(
    ({ id, paused }: { id: string; paused: boolean }) =>
      api.updateScanSchedule(id, { paused }),
    "Schedule updated",
  );
  const remove = useAction(api.deleteScanSchedule, "Schedule deleted");
  const data = schedules.data;
  return (
    <section className="section-stack">
      <div className="actions">
        <h2>Scheduled scans</h2>
        <Button size="sm" onClick={() => setEditing("new")}>
          Add schedule
        </Button>
      </div>
      <p className="text-ink-secondary">
        Staff schedules run the crawler first, then an agent with the
        schedule&apos;s focus. New finds follow the publishing defaults below.
        {data &&
          (data.run_as
            ? ` They run as ${data.run_as}.`
            : " Set OPPORTUNITY_SWEEP_EMAIL or add an admin so they can run.")}
      </p>
      {data && (
        <p className="text-ink-secondary">
          {data.member_schedules_active} of {data.member_schedules} member
          weekly scans active. {data.runs_last_7_days} scheduled runs in the
          last 7 days. {data.tokens_today.toLocaleString()} model tokens used
          today.
        </p>
      )}
      {editing && (
        <ScheduleForm
          key={editing === "new" ? "new" : editing.id}
          initial={editing === "new" ? emptySchedule : editing}
          id={editing === "new" ? undefined : editing.id}
          intervals={data?.intervals ?? [24, 72, 168]}
          close={() => setEditing(null)}
        />
      )}
      <MutationError error={toggle.error || remove.error} />
      <QueryState query={schedules} empty={!data?.schedules.length}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Schedule</th>
                <th>Repeats</th>
                <th>Status</th>
                <th>Last run</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.schedules.map((row) => (
                <tr key={row.id}>
                  <td>
                    {row.name ||
                      row.categories
                        .map((c) => CATEGORY_NAMES[c] ?? c)
                        .join(", ")}
                    <p>
                      {[
                        row.name &&
                          row.categories
                            .map((c) => CATEGORY_NAMES[c] ?? c)
                            .join(", "),
                        row.region || "Default region",
                        row.focus,
                      ]
                        .filter(Boolean)
                        .join(". ")}
                    </p>
                  </td>
                  <td>{intervalLabel(row.interval_hours)}</td>
                  <td>
                    <Chip tone={row.paused ? "neutral" : "forest"}>
                      {row.paused ? "Paused" : "Active"}
                    </Chip>
                    {!row.paused && <p>Next {formatDate(row.next_run_at)}</p>}
                  </td>
                  <td>
                    {row.last_run ? (
                      <>
                        {formatDate(row.last_run.created_at)}
                        <p>
                          {row.last_run.status === "running"
                            ? "Running"
                            : `${row.last_run.new} new, ${row.last_run.updated} updated`}
                        </p>
                      </>
                    ) : (
                      "Not run yet"
                    )}
                  </td>
                  <td>
                    <div className="actions">
                      <Button size="sm" onClick={() => setEditing(row)}>
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        disabled={toggle.isPending}
                        onClick={() =>
                          toggle.mutate({ id: row.id, paused: !row.paused })
                        }
                      >
                        {row.paused ? "Resume" : "Pause"}
                      </Button>
                      <Button
                        size="sm"
                        disabled={remove.isPending}
                        onClick={() => {
                          if (
                            window.confirm(
                              "Delete this schedule? Its past scans and what they found stay.",
                            )
                          )
                            remove.mutate(row.id);
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </QueryState>
    </section>
  );
}

function ScheduleForm({
  initial,
  id,
  intervals,
  close,
}: {
  initial: api.ScanScheduleInput;
  id?: string;
  intervals: number[];
  close: () => void;
}) {
  const [draft, setDraft] = useState<api.ScanScheduleInput>({
    name: initial.name,
    categories: initial.categories,
    region: initial.region,
    focus: initial.focus,
    interval_hours: initial.interval_hours,
  });
  const save = useAction(async (body: Partial<api.ScanScheduleInput>) => {
    const result = id
      ? await api.updateScanSchedule(id, body)
      : await api.createScanSchedule(body as api.ScanScheduleInput);
    close();
    return result;
  }, "Schedule saved");
  const options = intervals.includes(draft.interval_hours)
    ? intervals
    : [draft.interval_hours, ...intervals];
  return (
    <form
      className="section-stack"
      onSubmit={(event) => {
        event.preventDefault();
        // A migrated sweep can keep its old interval: send it only when changed.
        const { interval_hours, ...rest } = draft;
        save.mutate(intervals.includes(interval_hours) ? draft : { ...rest });
      }}
    >
      <h3>{id ? "Edit schedule" : "Add schedule"}</h3>
      <div className="form-grid">
        <Field
          label="Name"
          maxLength={80}
          value={draft.name}
          onChange={(event) => setDraft({ ...draft, name: event.target.value })}
        />
        <Field label="Repeats">
          <Select
            value={draft.interval_hours}
            onChange={(event) =>
              setDraft({ ...draft, interval_hours: Number(event.target.value) })
            }
          >
            {options.map((hours) => (
              <option key={hours} value={hours}>
                {intervalLabel(hours)}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Region"
          maxLength={120}
          placeholder="Default region"
          value={draft.region}
          onChange={(event) =>
            setDraft({ ...draft, region: event.target.value })
          }
        />
        <Field
          label="Focus"
          maxLength={2000}
          placeholder="Optional, e.g. climate research grants"
          value={draft.focus}
          onChange={(event) =>
            setDraft({ ...draft, focus: event.target.value })
          }
        />
      </div>
      <fieldset className="actions">
        <legend>Categories</legend>
        {Object.entries(CATEGORY_NAMES).map(([value, label]) => (
          <label key={value}>
            <input
              type="checkbox"
              checked={draft.categories.includes(value)}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  categories: event.target.checked
                    ? [...draft.categories, value]
                    : draft.categories.filter((c) => c !== value),
                })
              }
            />{" "}
            {label}
          </label>
        ))}
      </fieldset>
      <MutationError error={save.error} />
      <div className="actions">
        <Button
          type="submit"
          variant="primary"
          disabled={save.isPending || !draft.categories.length}
        >
          {save.isPending ? "Saving…" : "Save schedule"}
        </Button>
        <Button type="button" onClick={close}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
