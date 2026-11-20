import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Chip, Countdown, Field, Select } from "@blesser/ui";
import { Plus, ArrowUpRight } from "lucide-react";
import * as api from "../lib/api";
import {
  Confirm,
  MutationError,
  PageHeader,
  Pagination,
  Panel,
  QueryState,
  SafeLink,
  StatusChip,
  formatDate,
  statusLabels,
  useAction,
  Segmented,
} from "../components/shared";
import OpportunityEditor from "./OpportunityEditor";
import { AuditDiff } from "./Audit";

const limit = 30;
const bulkActions: { value: api.BulkAction; label: string }[] = [
  { value: "publish_public", label: "Publish to public" },
  { value: "publish_members", label: "Publish to members" },
  { value: "to_review", label: "Send to review" },
  { value: "archive", label: "Archive" },
  { value: "hide", label: "Hide" },
];
export default function Opportunities({
  review = false,
}: {
  review?: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<string[]>([]);
  const [bulkAction, setBulkAction] =
    useState<api.BulkAction>("publish_public");
  const [confirmHide, setConfirmHide] = useState<"single" | "bulk" | null>(
    null,
  );
  const [history, setHistory] = useState<api.AuditEntry | null>(null);
  const tab = params.get("queue") === "agent" ? "agent" : "review";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const id = params.get("id");
  const edit = params.get("edit") === "true" || id === "new";
  const query: api.OpportunityQuery = {
    q: params.get("q") || undefined,
    status: review
      ? tab === "review"
        ? "in_review"
        : undefined
      : api.statuses.find((s) => s === params.get("status")),
    audience: api.audiences.find((a) => a === params.get("audience")),
    category: params.get("category") || undefined,
    kind: params.get("kind") || undefined,
    source:
      review && tab === "agent" ? "agent" : params.get("source") || undefined,
    sort:
      review && tab === "agent"
        ? "created"
        : params.get("sort") === "deadline"
          ? "deadline"
          : params.get("sort") === "created"
            ? "created"
            : "updated",
    limit,
    offset,
  };
  const list = useQuery({
    queryKey: ["opportunities", query],
    queryFn: () => api.opportunities(query),
  });
  const counts = useQuery({ queryKey: ["counts"], queryFn: api.counts });
  const detail = useQuery({
    queryKey: ["opportunity", id],
    queryFn: () => api.opportunity(id || ""),
    enabled: !!id && id !== "new",
  });
  const items = list.data?.items ?? [];
  const selectionScope = JSON.stringify(query);
  useEffect(() => setSelected([]), [selectionScope, review]);
  useEffect(() => {
    if (list.data)
      setSelected((previous) =>
        previous.filter((value) =>
          list.data.items.some((item) => item.id === value),
        ),
      );
  }, [list.data]);
  const update = useAction(
    ({
      id: itemId,
      body,
    }: {
      id: string;
      body: Partial<api.OpportunityInput>;
    }) => api.updateOpportunity(itemId, body),
    "Opportunity updated",
    () => {
      setConfirmHide(null);
    },
  );
  const bulk = useAction(
    ({ ids, action }: { ids: string[]; action: api.BulkAction }) =>
      api.bulkOpportunities(ids, action),
    "Opportunities updated",
    () => {
      setSelected([]);
      setConfirmHide(null);
    },
  );
  const busy = update.isPending || bulk.isPending;
  const setFilter = (name: string, value: string) => {
    setSelected([]);
    setParams((old) => {
      const next = new URLSearchParams(old);
      if (value) next.set(name, value);
      else next.delete(name);
      next.delete("offset");
      next.delete("id");
      next.delete("edit");
      return next;
    });
  };
  const open = (itemId: string, editing = false) => {
    setConfirmHide(null);
    setHistory(null);
    setParams((old) => {
      const next = new URLSearchParams(old);
      next.set("id", itemId);
      if (editing) next.set("edit", "true");
      else next.delete("edit");
      return next;
    });
  };
  const close = () => {
    setConfirmHide(null);
    setHistory(null);
    setParams((old) => {
      const next = new URLSearchParams(old);
      next.delete("id");
      next.delete("edit");
      return next;
    });
  };
  const publish = (audience: api.Audience) => {
    if (id && id !== "new" && !busy)
      update.mutate({ id, body: { status: "published", audience } });
  };
  useEffect(() => {
    if (!review || edit) return;
    const handle = (event: KeyboardEvent) => {
      if (
        event.defaultPrevented ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        confirmHide ||
        busy
      )
        return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable || target.closest("input,textarea,select"))
      )
        return;
      const key = event.key.toLowerCase();
      if (!["j", "k", "p", "m", "h", "e"].includes(key)) return;
      event.preventDefault();
      if (key === "j" || key === "k") {
        const index = items.findIndex((item) => item.id === id);
        const item =
          items[
            index < 0
              ? key === "j"
                ? 0
                : items.length - 1
              : Math.max(
                  0,
                  Math.min(items.length - 1, index + (key === "j" ? 1 : -1)),
                )
          ];
        if (item) open(item.id);
      } else if (id && detail.data) {
        if (key === "p") publish("public");
        if (key === "m") publish("members");
        if (key === "h") setConfirmHide("single");
        if (key === "e") open(id, true);
      }
    };
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  });
  return (
    <>
      <PageHeader
        title={review ? "Review queue" : "Opportunities"}
        description={
          review
            ? "Check the source. Choose who sees the next good find."
            : "Find, edit and publish every opportunity in the catalogue."
        }
        action={
          <Button
            variant="primary"
            icon={<Plus />}
            onClick={() => open("new", true)}
          >
            Create opportunity
          </Button>
        }
      />
      <div className="counts-bar" aria-label="Catalogue counts">
        {counts.data ? (
          Object.entries(counts.data).map(([key, value]) => (
            <div key={key}>
              <strong>{value}</strong>
              <span>
                {
                  {
                    in_review: "In review",
                    members_only: "Members only",
                    published_public: "Published public",
                    archived: "Archived",
                    hidden: "Hidden",
                    draft: "Draft",
                  }[key]
                }
              </span>
            </div>
          ))
        ) : counts.isError ? (
          <Button
            size="sm"
            onClick={() => {
              void counts.refetch();
            }}
          >
            Retry counts
          </Button>
        ) : (
          <span role="status">Loading counts…</span>
        )}
      </div>
      {review && (
        <>
          <Segmented
            label="Review queues"
            value={tab}
            onChange={(next) => setFilter("queue", next)}
            options={[
              ["review", "Needs review"],
              ["agent", "Recent agent finds"],
            ]}
            aside={
              <span className="text-footnote text-ink-secondary">
                {tab === "agent"
                  ? "Newest discoveries first"
                  : "Waiting for an editorial decision"}
              </span>
            }
          />
          <div className="shortcut-legend" aria-label="Keyboard shortcuts">
            {[
              ["j / k", "Next / previous"],
              ["p", "Approve public"],
              ["m", "Approve members"],
              ["h", "Hide"],
              ["e", "Edit"],
            ].map(([key, label]) => (
              <span key={key}>
                <kbd>{key}</kbd> {label}
              </span>
            ))}
          </div>
        </>
      )}
      <div className="filters">
        <Field
          label="Search"
          type="search"
          placeholder="Title or organization"
          value={params.get("q") || ""}
          onChange={(e) => setFilter("q", e.target.value)}
        />
        {!review && (
          <Field label="Status">
            <Select
              value={params.get("status") || ""}
              onChange={(e) => setFilter("status", e.target.value)}
            >
              <option value="">All statuses</option>
              {api.statuses.map((s) => (
                <option key={s} value={s}>
                  {statusLabels[s]}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Field label="Audience">
          <Select
            value={params.get("audience") || ""}
            onChange={(e) => setFilter("audience", e.target.value)}
          >
            <option value="">All audiences</option>
            <option value="public">Public</option>
            <option value="members">Members only</option>
          </Select>
        </Field>
        <Field
          label="Category"
          placeholder="Any category"
          value={params.get("category") || ""}
          onChange={(e) => setFilter("category", e.target.value)}
        />
        <Field
          label="Kind"
          placeholder="Any kind"
          value={params.get("kind") || ""}
          onChange={(e) => setFilter("kind", e.target.value)}
        />
        {(!review || tab !== "agent") && (
          <Field
            label="Source"
            placeholder="Any source"
            value={params.get("source") || ""}
            onChange={(e) => setFilter("source", e.target.value)}
          />
        )}
        <Field label="Sort by">
          <Select
            value={query.sort}
            disabled={review && tab === "agent"}
            onChange={(e) => setFilter("sort", e.target.value)}
          >
            <option value="updated">Last updated</option>
            <option value="deadline">Deadline</option>
            <option value="created">Newest first</option>
          </Select>
        </Field>
      </div>
      {!!selected.length && (
        <div className="bulk-bar">
          <strong>{selected.length} selected</strong>
          <Select
            aria-label="Bulk action"
            value={bulkAction}
            onChange={(e) => {
              const action = bulkActions.find(
                (a) => a.value === e.target.value,
              );
              if (action) setBulkAction(action.value);
            }}
          >
            {bulkActions.map((a) => (
              <option value={a.value} key={a.value}>
                {a.label}
              </option>
            ))}
          </Select>
          <Button
            variant="brand"
            disabled={busy}
            onClick={() => {
              if (bulkAction === "hide") setConfirmHide("bulk");
              else bulk.mutate({ ids: selected, action: bulkAction });
            }}
          >
            Apply action
          </Button>
          <Button variant="quiet" onClick={() => setSelected([])}>
            Clear selection
          </Button>
        </div>
      )}
      {confirmHide === "bulk" && (
        <Confirm
          title={`Hide ${selected.length} opportunities?`}
          description="These listings will disappear from the public site and member catalogue. Existing tracked copies stay in applications."
          label="Hide opportunities"
          danger
          busy={bulk.isPending}
          error={bulk.error}
          onCancel={() => setConfirmHide(null)}
          onConfirm={() => bulk.mutate({ ids: selected, action: "hide" })}
        />
      )}
      <MutationError error={bulk.error} />
      <QueryState query={list} empty={!items.length}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="check-cell">
                  <input
                    type="checkbox"
                    aria-label="Select this page"
                    checked={
                      items.length > 0 &&
                      items.every((item) => selected.includes(item.id))
                    }
                    onChange={(e) =>
                      setSelected(
                        e.target.checked ? items.map((item) => item.id) : [],
                      )
                    }
                  />
                </th>
                <th>Opportunity</th>
                <th>Status / audience</th>
                <th>Category / kind</th>
                <th>Deadline</th>
                <th>Source</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.id}
                  className={id === item.id ? "selected-row" : ""}
                >
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Select ${item.title}`}
                      checked={selected.includes(item.id)}
                      onChange={(e) =>
                        setSelected((old) =>
                          e.target.checked
                            ? [...old, item.id]
                            : old.filter((value) => value !== item.id),
                        )
                      }
                    />
                  </td>
                  <td className="title-cell">
                    <button
                      className="table-title"
                      onClick={() => open(item.id)}
                    >
                      {item.title}
                      <ArrowUpRight size={14} />
                    </button>
                    <span className="subline">{item.organization}</span>
                    {review && item.review_reason && (
                      <span className="subline">
                        {item.review_reason.replaceAll("_", " ")}
                      </span>
                    )}
                  </td>
                  <td>
                    <div className="chip-stack">
                      <StatusChip status={item.status} />
                      {item.audience === "members" && (
                        <Chip tone="info">Members only</Chip>
                      )}
                    </div>
                  </td>
                  <td>
                    {item.category}
                    <span className="subline">
                      {item.kind.replaceAll("_", " ")}
                    </span>
                  </td>
                  <td>
                    <Countdown
                      date={item.deadline_date}
                      daysLeft={item.days_left}
                      rolling={item.rolling}
                      label={item.deadline}
                    />
                  </td>
                  <td>{item.source}</td>
                  <td className="nowrap">{formatDate(item.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </QueryState>
      <Pagination
        offset={offset}
        limit={limit}
        total={list.data?.total}
        count={items.length}
        onChange={(value) => {
          setSelected([]);
          setParams((old) => {
            const next = new URLSearchParams(old);
            next.set("offset", String(value));
            return next;
          });
        }}
      />
      {id &&
        (edit ? (
          <OpportunityEditor
            key={id}
            id={id}
            detail={detail}
            onClose={close}
            onSaved={(item) => open(item.id)}
          />
        ) : (
          <Panel title="Review opportunity" onClose={close}>
            <QueryState query={detail} empty={false}>
              {detail.data && (
                <>
                  <div className="detail-heading">
                    <StatusChip status={detail.data.status} />
                    {detail.data.audience === "members" && (
                      <Chip tone="info">Members only</Chip>
                    )}
                    <h2>{detail.data.title}</h2>
                    <p>{detail.data.organization}</p>
                    <Countdown
                      date={detail.data.deadline_date}
                      daysLeft={detail.data.days_left}
                      rolling={detail.data.rolling}
                      label={detail.data.deadline}
                    />
                  </div>
                  <div className="actions">
                    <Button
                      variant="brand"
                      disabled={busy}
                      onClick={() => publish("public")}
                    >
                      Approve to public
                    </Button>
                    <Button disabled={busy} onClick={() => publish("members")}>
                      Approve to members
                    </Button>
                    <Button disabled={busy} onClick={() => open(id, true)}>
                      Edit
                    </Button>
                    <Button
                      disabled={busy}
                      variant="quiet"
                      onClick={() => setConfirmHide("single")}
                    >
                      Hide
                    </Button>
                  </div>
                  <MutationError error={update.error} />
                  {confirmHide === "single" && (
                    <Confirm
                      title="Hide this opportunity?"
                      description="It will disappear from the public site and member catalogue. Existing tracked copies stay in applications."
                      label="Hide opportunity"
                      danger
                      busy={update.isPending}
                      error={update.error}
                      onCancel={() => setConfirmHide(null)}
                      onConfirm={() =>
                        update.mutate({ id, body: { status: "hidden" } })
                      }
                    />
                  )}
                  <section className="section-stack">
                    <h3>Source and agent checks</h3>
                    <SafeLink href={detail.data.source_url}>
                      Open source
                    </SafeLink>
                    <SafeLink href={detail.data.link}>
                      Open application page
                    </SafeLink>
                    <p className="text-footnote text-ink-secondary">
                      Verified {formatDate(detail.data.verified_at)}. Source:{" "}
                      {detail.data.source}
                    </p>
                    <pre className="source-excerpt">
                      {detail.data.trace_excerpt ||
                        "No agent excerpt was recorded. Check the original source before publishing."}
                    </pre>
                  </section>
                  <dl className="detail-list">
                    {[
                      ["Summary", detail.data.summary],
                      ["Eligibility", detail.data.eligibility],
                      ["Benefits", detail.data.benefits],
                      ["Requirements", detail.data.requirements.join("\n")],
                      ["Location", detail.data.location],
                      ["Countries", detail.data.countries.join(", ")],
                      ["Category", detail.data.category],
                      ["Kind", detail.data.kind],
                      ["Tags", detail.data.tags.join(", ")],
                      ["Slug", detail.data.slug],
                      ["Editor note", detail.data.editor_note],
                      ["Review reason", detail.data.review_reason || "None"],
                      [
                        "Featured rank",
                        detail.data.featured_rank?.toString() || "Not featured",
                      ],
                      ["Published", formatDate(detail.data.published_at)],
                      ["Created", formatDate(detail.data.created_at)],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd>{value || "Not provided"}</dd>
                      </div>
                    ))}
                  </dl>
                  <details className="full-record">
                    <summary>View full record</summary>
                    <pre className="source-excerpt">
                      {JSON.stringify(detail.data, null, 2)}
                    </pre>
                  </details>
                  <section className="section-stack">
                    <h3>History</h3>
                    {detail.data.history.length ? (
                      detail.data.history.map((entry) => (
                        <button
                          className="history-row"
                          key={entry.id}
                          onClick={() =>
                            setHistory(history?.id === entry.id ? null : entry)
                          }
                        >
                          <strong>{entry.action}</strong>
                          <span>
                            {entry.actor_email}, {formatDate(entry.at)}
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
            </QueryState>
          </Panel>
        ))}
    </>
  );
}
