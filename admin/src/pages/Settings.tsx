import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Field, Select, Textarea } from "@blesser/ui";
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
      {draft.aggregators && (
        <section className="section-stack">
          <h2>Aggregator sites</h2>
          <p className="text-ink-secondary">
            Sites that repost other funders' calls. Finds on them are followed
            to the official page, and that page is stored instead. Finds with no
            official page are held for review.
          </p>
          <Field label="Sites, one per line">
            <Textarea
              rows={8}
              value={draft.aggregators.join("\n")}
              onChange={(e) =>
                setDraft({ ...draft, aggregators: e.target.value.split("\n") })
              }
            />
          </Field>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={Boolean(draft.official_backfill)}
              onChange={(e) =>
                setDraft({ ...draft, official_backfill: e.target.checked })
              }
            />{" "}
            Move existing listings off aggregator pages every hour
          </label>
          <p className="text-ink-secondary">
            Ten listings a pass. Published listings with no official page go to
            review.
          </p>
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
