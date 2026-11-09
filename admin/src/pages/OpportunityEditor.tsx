import { useState } from "react";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  Button,
  Field,
  OpportunityCard,
  Select,
  Textarea,
  daysUntil,
} from "@blesser/ui";
import * as api from "../lib/api";
import { AuditDiff } from "./Audit";
import {
  Confirm,
  MutationError,
  Panel,
  QueryState,
  formatDate,
  statusLabels,
  useAction,
} from "../components/shared";

const blank: api.OpportunityInput = {
  title: "",
  slug: "",
  organization: "",
  category: "startup",
  kind: "grant",
  summary: "",
  eligibility: "",
  benefits: "",
  location: "",
  countries: [],
  requirements: [],
  tags: [],
  deadline: "",
  deadline_date: null,
  rolling: false,
  link: "",
  source_url: "",
  verified_at: null,
  status: "draft",
  audience: "members",
  featured_rank: null,
  editor_note: "",
  review_reason: null,
};
function editable(item: api.AdminOpportunity): api.OpportunityInput {
  return {
    title: item.title,
    slug: item.slug,
    organization: item.organization,
    category: item.category,
    kind: item.kind,
    summary: item.summary,
    eligibility: item.eligibility,
    benefits: item.benefits,
    location: item.location,
    countries: item.countries,
    requirements: item.requirements,
    tags: item.tags,
    deadline: item.deadline,
    deadline_date: item.deadline_date,
    rolling: item.rolling,
    link: item.link,
    source_url: item.source_url,
    verified_at: item.verified_at,
    status: item.status,
    audience: item.audience,
    featured_rank: item.featured_rank,
    editor_note: item.editor_note,
    review_reason: item.review_reason,
  };
}
export default function OpportunityEditor({
  id,
  detail,
  onClose,
  onSaved,
}: {
  id: string;
  detail: UseQueryResult<api.OpportunityDetail>;
  onClose: () => void;
  onSaved: (item: api.AdminOpportunity) => void;
}) {
  if (id === "new")
    return <EditorForm initial={blank} onClose={onClose} onSaved={onSaved} />;
  if (detail.data)
    return (
      <EditorForm
        initial={editable(detail.data)}
        item={detail.data}
        onClose={onClose}
        onSaved={onSaved}
      />
    );
  return (
    <Panel title="Edit opportunity" onClose={onClose}>
      <QueryState query={detail} empty={false}>
        {null}
      </QueryState>
    </Panel>
  );
}
function EditorForm({
  initial,
  item,
  onClose,
  onSaved,
}: {
  initial: api.OpportunityInput;
  item?: api.OpportunityDetail;
  onClose: () => void;
  onSaved: (item: api.AdminOpportunity) => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [confirm, setConfirm] = useState<
    "hide" | "merge" | "reverify" | "discard" | null
  >(null);
  const [targetSearch, setTargetSearch] = useState("");
  const [target, setTarget] = useState<api.AdminOpportunity | null>(null);
  const [history, setHistory] = useState<api.AuditEntry | null>(null);
  const dirty = JSON.stringify(initial) !== JSON.stringify(draft);
  const targets = useQuery({
    queryKey: ["opportunities", "merge", targetSearch],
    queryFn: () => api.opportunities({ q: targetSearch, limit: 15, offset: 0 }),
    enabled: !!item && targetSearch.trim().length > 1,
  });
  const save = useAction(
    (value: api.OpportunityInput) =>
      item
        ? api.updateOpportunity(item.id, value)
        : api.createOpportunity(value),
    item ? "Opportunity saved" : "Opportunity created",
    onSaved,
  );
  const merge = useAction(
    (into: string) => api.mergeOpportunity(item?.id || "", into),
    "Opportunities merged",
    onSaved,
  );
  const reverify = useAction(
    () => api.reverifyOpportunity(item?.id || ""),
    "Verification queued",
    () => setConfirm(null),
  );
  const busy = save.isPending || merge.isPending || reverify.isPending;
  const requestClose = () => {
    if (busy) return;
    if (dirty) setConfirm("discard");
    else onClose();
  };
  const saveDraft = () =>
    save.mutate({
      ...draft,
      requirements: draft.requirements.map((v) => v.trim()).filter(Boolean),
      countries: draft.countries.map((v) => v.trim()).filter(Boolean),
      tags: draft.tags.map((v) => v.trim()).filter(Boolean),
    });
  const scalarFields = [
    ["title", "Title"],
    ["slug", "Slug"],
    ["organization", "Organization"],
    ["category", "Category"],
    ["kind", "Kind"],
    ["location", "Location"],
    ["link", "Application link"],
    ["source_url", "Source link"],
    ["deadline", "Deadline wording"],
  ] satisfies [
    keyof Pick<
      api.OpportunityInput,
      | "title"
      | "slug"
      | "organization"
      | "category"
      | "kind"
      | "location"
      | "link"
      | "source_url"
      | "deadline"
    >,
    string,
  ][];
  const largeFields = [
    ["summary", "Summary"],
    ["eligibility", "Eligibility"],
    ["benefits", "Benefits"],
    ["editor_note", "Editor note"],
  ] satisfies [
    "summary" | "eligibility" | "benefits" | "editor_note",
    string,
  ][];
  return (
    <Panel
      title={item ? "Edit opportunity" : "Create opportunity"}
      onClose={requestClose}
      wide
    >
      <div className="editor-grid">
        <div className="section-stack">
          <form
            className="section-stack"
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.status === "hidden" && item?.status !== "hidden")
                setConfirm("hide");
              else saveDraft();
            }}
          >
            <div className="form-grid">
              {scalarFields.map(([key, label]) => (
                <Field
                  key={key}
                  label={label}
                  required={[
                    "title",
                    "slug",
                    "organization",
                    "category",
                    "kind",
                    "link",
                    "source_url",
                  ].includes(key)}
                  type={key === "link" || key === "source_url" ? "url" : "text"}
                  pattern={
                    key === "slug" ? "[a-z0-9]+(-[a-z0-9]+)*" : undefined
                  }
                  value={draft[key]}
                  onChange={(e) =>
                    setDraft({ ...draft, [key]: e.target.value })
                  }
                />
              ))}
              <Field
                label="Deadline date"
                type="date"
                value={draft.deadline_date || ""}
                onChange={(e) =>
                  setDraft({ ...draft, deadline_date: e.target.value || null })
                }
              />
              <Field
                label="Verified at"
                type="datetime-local"
                value={draft.verified_at ? draft.verified_at.slice(0, 16) : ""}
                hint="UTC"
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    verified_at: e.target.value
                      ? `${e.target.value}:00Z`
                      : null,
                  })
                }
              />
              <Field label="Status">
                <Select
                  value={draft.status}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      status: api.statusSchema(e.target.value),
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
              <Field label="Audience">
                <Select
                  value={draft.audience}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      audience: api.audienceSchema(e.target.value),
                    })
                  }
                >
                  <option value="public">Public</option>
                  <option value="members">Members only</option>
                </Select>
              </Field>
              <Field
                label="Review reason"
                hint="Leave empty when no review is needed."
                value={draft.review_reason || ""}
                onChange={(e) =>
                  setDraft({ ...draft, review_reason: e.target.value || null })
                }
              />
              <Field
                label="Featured rank"
                type="number"
                min="0"
                step="1"
                value={draft.featured_rank ?? ""}
                hint="Leave empty to remove from featured."
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    featured_rank:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={draft.rolling}
                  onChange={(e) =>
                    setDraft({ ...draft, rolling: e.target.checked })
                  }
                />{" "}
                Accept applications year round
              </label>
            </div>
            {largeFields.map(([key, label]) => (
              <Field key={key} label={label}>
                <Textarea
                  value={draft[key]}
                  onChange={(e) =>
                    setDraft({ ...draft, [key]: e.target.value })
                  }
                />
              </Field>
            ))}
            <Field label="Requirements" hint="One requirement per line">
              <Textarea
                value={draft.requirements.join("\n")}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    requirements: e.target.value.split("\n"),
                  })
                }
              />
            </Field>
            <Field
              label="Countries"
              hint="Separate countries with commas"
              value={draft.countries.join(",")}
              onChange={(e) =>
                setDraft({ ...draft, countries: e.target.value.split(",") })
              }
            />
            <Field
              label="Tags"
              hint="Separate tags with commas"
              value={draft.tags.join(",")}
              onChange={(e) =>
                setDraft({ ...draft, tags: e.target.value.split(",") })
              }
            />
            <MutationError error={save.error} />
            <div className="actions sticky-actions">
              <Button variant="brand" type="submit" disabled={busy}>
                {save.isPending
                  ? "Saving…"
                  : item
                    ? "Save opportunity"
                    : "Create opportunity"}
              </Button>
              <Button onClick={requestClose} disabled={busy}>
                Cancel
              </Button>
              {dirty && (
                <span className="text-footnote text-ink-secondary">
                  Unsaved changes
                </span>
              )}
            </div>
          </form>
          {confirm === "hide" && (
            <Confirm
              title="Save and hide this opportunity?"
              description="These changes will be saved and the listing removed from the public site and member catalogue."
              label="Save and hide"
              danger
              busy={save.isPending}
              error={save.error}
              onCancel={() => setConfirm(null)}
              onConfirm={saveDraft}
            />
          )}
          {confirm === "discard" && (
            <Confirm
              title="Discard your changes?"
              description="Your edits have not been saved."
              label="Discard changes"
              danger
              busy={false}
              error={null}
              onCancel={() => setConfirm(null)}
              onConfirm={onClose}
            />
          )}
          {item && (
            <>
              <section className="section-stack maintenance">
                <h3>Check or merge</h3>
                <p className="text-ink-secondary">
                  Save your edits before starting either action.
                </p>
                <Button
                  disabled={busy || dirty}
                  onClick={() => setConfirm("reverify")}
                >
                  Re-verify source
                </Button>
                {confirm === "reverify" && (
                  <Confirm
                    title="Re-verify this opportunity?"
                    description="A new agent scan will check this source. The listing stays as it is until the check finishes."
                    label="Queue verification"
                    busy={reverify.isPending}
                    error={reverify.error}
                    onCancel={() => setConfirm(null)}
                    onConfirm={() => reverify.mutate()}
                  />
                )}
                <Field
                  label="Find a duplicate to keep"
                  type="search"
                  placeholder="Search by title"
                  value={targetSearch}
                  disabled={busy || dirty}
                  onChange={(e) => {
                    setTargetSearch(e.target.value);
                    setTarget(null);
                    setConfirm(null);
                  }}
                />
                {targetSearch.trim().length > 1 && (
                  <QueryState
                    query={targets}
                    empty={
                      !targets.data?.items.filter(
                        (candidate) => candidate.id !== item.id,
                      ).length
                    }
                  >
                    <ul className="choice-list">
                      {targets.data?.items
                        .filter((candidate) => candidate.id !== item.id)
                        .map((candidate) => (
                          <li key={candidate.id}>
                            <label>
                              <input
                                type="radio"
                                name="merge-target"
                                checked={target?.id === candidate.id}
                                onChange={() => {
                                  setTarget(candidate);
                                  setConfirm(null);
                                }}
                              />
                              {candidate.title}
                              <span className="subline">
                                {candidate.organization} / {candidate.slug}
                              </span>
                            </label>
                          </li>
                        ))}
                    </ul>
                  </QueryState>
                )}
                <Button
                  disabled={!target || busy || dirty}
                  onClick={() => setConfirm("merge")}
                >
                  Merge duplicate
                </Button>
                {confirm === "merge" && target && (
                  <Confirm
                    title="Merge these opportunities?"
                    description={`Keep "${target.title}" (${target.slug}). Hide "${item.title}" and move its tracked applications to the kept listing.`}
                    label="Merge opportunities"
                    danger
                    busy={merge.isPending}
                    error={merge.error}
                    onCancel={() => setConfirm(null)}
                    onConfirm={() => merge.mutate(target.id)}
                  />
                )}
              </section>
              <section className="section-stack">
                <h3>History</h3>
                {item.history.length ? (
                  item.history.map((entry) => (
                    <button
                      key={entry.id}
                      className="history-row"
                      onClick={() =>
                        setHistory(history?.id === entry.id ? null : entry)
                      }
                    >
                      <strong>{entry.action}</strong>
                      <span>
                        {entry.actor_email} · {formatDate(entry.at)}
                      </span>
                    </button>
                  ))
                ) : (
                  <p>No changes have been recorded.</p>
                )}
                {history && <AuditDiff entry={history} />}
              </section>
            </>
          )}
        </div>
        <aside className="preview">
          <p className="eyebrow">Live card preview</p>
          <OpportunityCard
            organization={draft.organization}
            title={draft.title || "Opportunity title"}
            kind={draft.kind}
            audiences={draft.audience === "members" ? ["Members only"] : []}
            countdown={{
              date: draft.deadline_date,
              daysLeft: draft.deadline_date
                ? daysUntil(draft.deadline_date)
                : null,
              rolling: draft.rolling,
              label: draft.deadline,
            }}
            trackDisabled
          >
            <p>{draft.summary || "Your summary will appear here."}</p>
          </OpportunityCard>
          <section className="page-preview section-stack">
            <p className="eyebrow">Live page preview</p>
            <h2>{draft.title || "Opportunity title"}</h2>
            <p>{draft.summary}</p>
            {[
              ["Eligibility", draft.eligibility],
              ["Benefits", draft.benefits],
              ["Requirements", draft.requirements.filter(Boolean).join("\n")],
              [
                "Location",
                [draft.location, ...draft.countries.filter(Boolean)]
                  .filter(Boolean)
                  .join(", "),
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <h3>{label}</h3>
                <p className="whitespace-pre-wrap">{value || "Not provided"}</p>
              </div>
            ))}
          </section>
        </aside>
      </div>
    </Panel>
  );
}
