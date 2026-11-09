import { useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Button, Chip, Field, Select, Textarea } from "@blesser/ui";
import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import * as api from "../lib/api";
import { parseFilter } from "../lib/schema";
import {
  Confirm,
  MutationError,
  PageHeader,
  Panel,
  QueryState,
  useAction,
} from "../components/shared";

const emptyCollection: api.CollectionInput = {
  title: "",
  slug: "",
  intro: "",
  audience: "public",
  filter: null,
  item_ids: [],
  position: 0,
  published: false,
};
export default function Curation() {
  const [tab, setTab] = useState("collections");
  const [editing, setEditing] = useState<api.Collection | "new" | null>(null);
  const collections = useQuery({
    queryKey: ["collections"],
    queryFn: api.collections,
  });
  const site = useQuery({ queryKey: ["site"], queryFn: api.site });
  return (
    <>
      <PageHeader
        title="Curation"
        description="Choose the collections, featured order and words people see first."
        action={
          tab === "collections" ? (
            <Button
              variant="primary"
              icon={<Plus />}
              onClick={() => setEditing("new")}
            >
              Create collection
            </Button>
          ) : undefined
        }
      />
      <div className="tabs" role="group" aria-label="Curation sections">
        {[
          ["collections", "Collections"],
          ["featured", "Featured order"],
          ["homepage", "Homepage content"],
        ].map(([key, label]) => (
          <Button
            key={key}
            variant={tab === key ? "brand" : "quiet"}
            aria-pressed={tab === key}
            onClick={() => setTab(key)}
          >
            {label}
          </Button>
        ))}
      </div>
      {tab === "collections" && (
        <QueryState query={collections} empty={!collections.data?.length}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Collection</th>
                  <th>Audience</th>
                  <th>Selection</th>
                  <th>Position</th>
                  <th>Visibility</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {collections.data
                  ?.slice()
                  .sort((a, b) => a.position - b.position)
                  .map((collection) => (
                    <tr key={collection.id}>
                      <td>
                        <button
                          className="table-title"
                          onClick={() => setEditing(collection)}
                        >
                          {collection.title}
                        </button>
                        <span className="subline">/{collection.slug}</span>
                      </td>
                      <td>
                        <Chip
                          tone={
                            collection.audience === "members"
                              ? "info"
                              : "neutral"
                          }
                        >
                          {collection.audience === "members"
                            ? "Members only"
                            : "Public"}
                        </Chip>
                      </td>
                      <td>
                        {collection.filter
                          ? "Saved filter"
                          : `${collection.item_ids.length} hand-picked`}
                      </td>
                      <td>{collection.position}</td>
                      <td>
                        <Chip
                          tone={collection.published ? "forest" : "neutral"}
                        >
                          {collection.published ? "Published" : "Draft"}
                        </Chip>
                      </td>
                      <td>
                        <Button
                          size="sm"
                          onClick={() => setEditing(collection)}
                        >
                          Edit
                        </Button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </QueryState>
      )}
      {tab === "featured" && <Featured />}
      {tab === "homepage" && (
        <QueryState query={site} empty={false}>
          {site.data && <Homepage initial={site.data} />}
        </QueryState>
      )}
      {editing && (
        <CollectionEditor
          initial={editing === "new" ? emptyCollection : editing}
          id={editing === "new" ? undefined : editing.id}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}
function CollectionEditor({
  initial,
  id,
  onClose,
}: {
  initial: api.CollectionInput;
  id?: string;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [mode, setMode] = useState<"hand" | "filter">(
    initial.filter ? "filter" : "hand",
  );
  const [filter, setFilter] = useState(
    initial.filter ? JSON.stringify(initial.filter, null, 2) : "{}",
  );
  const [validation, setValidation] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [confirm, setConfirm] = useState<"delete" | "discard" | null>(null);
  const candidates = useQuery({
    queryKey: ["opportunities", "collection", search],
    queryFn: () => api.opportunities({ q: search, limit: 20 }),
    enabled: mode === "hand",
  });
  const picked = useQueries({
    queries: draft.item_ids.map((itemId) => ({
      queryKey: ["opportunity", itemId],
      queryFn: () => api.opportunity(itemId),
    })),
  });
  const save = useAction(
    (body: api.CollectionInput) =>
      id ? api.updateCollection(id, body) : api.createCollection(body),
    "Collection saved",
    onClose,
  );
  const remove = useAction(
    () => api.deleteCollection(id || ""),
    "Collection deleted",
    onClose,
  );
  const busy = save.isPending || remove.isPending;
  const dirty =
    JSON.stringify(draft) !== JSON.stringify(initial) ||
    mode !== (initial.filter ? "filter" : "hand") ||
    filter !==
      (initial.filter ? JSON.stringify(initial.filter, null, 2) : "{}");
  const requestClose = () => {
    if (busy) return;
    if (dirty) setConfirm("discard");
    else onClose();
  };
  const move = (index: number, step: number) => {
    const ids = [...draft.item_ids];
    const next = index + step;
    const value = ids[index];
    if (next < 0 || next >= ids.length || !value) return;
    ids.splice(index, 1);
    ids.splice(next, 0, value);
    setDraft({ ...draft, item_ids: ids });
  };
  return (
    <Panel
      title={id ? "Edit collection" : "Create collection"}
      onClose={requestClose}
    >
      <form
        className="section-stack"
        onSubmit={(e) => {
          e.preventDefault();
          try {
            const savedFilter = mode === "filter" ? parseFilter(filter) : null;
            if (mode === "filter" && !savedFilter)
              throw new Error("Enter a JSON filter object before saving.");
            const { id: ignored, ...body } = { id, ...draft };
            void ignored;
            setValidation(null);
            save.mutate({
              ...body,
              filter: savedFilter,
              item_ids: mode === "hand" ? draft.item_ids : [],
            });
          } catch (error) {
            setValidation(api.errorMessage(error));
          }
        }}
      >
        <Field
          label="Title"
          required
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
        />
        <Field
          label="Slug"
          required
          pattern="[a-z0-9]+(-[a-z0-9]+)*"
          value={draft.slug}
          onChange={(e) => setDraft({ ...draft, slug: e.target.value })}
        />
        <Field label="Introduction">
          <Textarea
            value={draft.intro}
            onChange={(e) => setDraft({ ...draft, intro: e.target.value })}
          />
        </Field>
        <div className="form-grid">
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
            label="Position"
            type="number"
            min="0"
            step="1"
            required
            value={draft.position}
            onChange={(e) =>
              setDraft({ ...draft, position: Number(e.target.value) })
            }
          />
        </div>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={draft.published}
            onChange={(e) =>
              setDraft({ ...draft, published: e.target.checked })
            }
          />{" "}
          Publish collection
        </label>
        <Field label="Choose opportunities">
          <Select
            value={mode}
            onChange={(e) =>
              setMode(e.target.value === "filter" ? "filter" : "hand")
            }
          >
            <option value="hand">Hand-picked opportunities</option>
            <option value="filter">Saved filter</option>
          </Select>
        </Field>
        {mode === "filter" ? (
          <Field
            label="Saved filter"
            hint={
              'Use a JSON object, for example {"category":"student","kind":"scholarship"}.'
            }
          >
            <Textarea
              className="mono"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </Field>
        ) : (
          <>
            <section className="section-stack">
              <h3>Selected opportunities</h3>
              {draft.item_ids.length ? (
                draft.item_ids.map((itemId, index) => (
                  <div className="ordered-row" key={itemId}>
                    <span>{index + 1}</span>
                    <div className="grow">
                      <strong>
                        {picked[index]?.data?.title ||
                          (picked[index]?.isError
                            ? "Listing unavailable. Remove it or try again."
                            : "Loading listing…")}
                      </strong>
                      <span className="subline">
                        {picked[index]?.data?.organization}
                      </span>
                    </div>
                    <Button
                      size="sm"
                      icon={<ArrowUp />}
                      aria-label={`Move item ${index + 1} up`}
                      disabled={index === 0}
                      onClick={() => move(index, -1)}
                    />
                    <Button
                      size="sm"
                      icon={<ArrowDown />}
                      aria-label={`Move item ${index + 1} down`}
                      disabled={index === draft.item_ids.length - 1}
                      onClick={() => move(index, 1)}
                    />
                    <Button
                      size="sm"
                      icon={<X />}
                      aria-label={`Remove item ${index + 1}`}
                      onClick={() =>
                        setDraft({
                          ...draft,
                          item_ids: draft.item_ids.filter(
                            (value) => value !== itemId,
                          ),
                        })
                      }
                    />
                  </div>
                ))
              ) : (
                <p className="text-ink-secondary">Choose listings below.</p>
              )}
            </section>
            <Field
              label="Find opportunities"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <QueryState
              query={candidates}
              empty={!candidates.data?.items.length}
            >
              <ul className="choice-list">
                {candidates.data?.items.map((item) => (
                  <li key={item.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={draft.item_ids.includes(item.id)}
                        onChange={(e) =>
                          setDraft({
                            ...draft,
                            item_ids: e.target.checked
                              ? [...draft.item_ids, item.id]
                              : draft.item_ids.filter(
                                  (value) => value !== item.id,
                                ),
                          })
                        }
                      />
                      {item.title}
                      <span className="subline">{item.organization}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </QueryState>
          </>
        )}
        {validation && (
          <p className="error" role="alert">
            {validation}
          </p>
        )}
        <MutationError error={save.error} />
        <div className="actions">
          <Button type="submit" variant="brand" disabled={busy}>
            {save.isPending ? "Saving…" : "Save collection"}
          </Button>
          {id && (
            <Button
              variant="quiet"
              disabled={busy}
              onClick={() => setConfirm("delete")}
            >
              Delete collection
            </Button>
          )}
        </div>
      </form>
      {confirm && (
        <Confirm
          title={
            confirm === "delete"
              ? "Delete this collection?"
              : "Discard your changes?"
          }
          description={
            confirm === "delete"
              ? "The collection will be removed. Its opportunities will stay in the catalogue."
              : "Your collection edits have not been saved."
          }
          label={confirm === "delete" ? "Delete collection" : "Discard changes"}
          danger
          busy={busy}
          error={remove.error}
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            if (confirm === "delete") remove.mutate();
            else onClose();
          }}
        />
      )}
    </Panel>
  );
}
async function allPublished() {
  const first = await api.opportunities({
    status: "published",
    audience: "public",
    limit: 100,
    offset: 0,
  });
  const items = [...first.items];
  for (let offset = first.items.length; offset < first.total; offset += 100) {
    const page = await api.opportunities({
      status: "published",
      audience: "public",
      limit: 100,
      offset,
    });
    items.push(...page.items);
    if (!page.items.length) break;
  }
  return items;
}
function Featured() {
  const list = useQuery({
    queryKey: ["opportunities", "featured-candidates"],
    queryFn: allPublished,
  });
  return (
    <QueryState query={list} empty={!list.data?.length}>
      {list.data && (
        <FeaturedOrder
          key={list.data
            .filter((item) => item.featured_rank !== null)
            .sort((a, b) => (a.featured_rank ?? 0) - (b.featured_rank ?? 0))
            .map((item) => `${item.id}:${item.featured_rank}`)
            .join(",")}
          items={list.data}
        />
      )}
    </QueryState>
  );
}
function FeaturedOrder({ items }: { items: api.AdminOpportunity[] }) {
  const initial = items
    .filter((item) => item.featured_rank !== null)
    .sort((a, b) => (a.featured_rank ?? 0) - (b.featured_rank ?? 0));
  const [order, setOrder] = useState(initial);
  const [search, setSearch] = useState("");
  const [partial, setPartial] = useState(false);
  const save = useAction(async () => {
    setPartial(false);
    try {
      for (const item of initial.filter(
        (item) => !order.some((next) => next.id === item.id),
      ))
        await api.updateOpportunity(item.id, { featured_rank: null });
      for (const [rank, item] of order.entries())
        await api.updateOpportunity(item.id, { featured_rank: rank });
    } catch (error) {
      setPartial(true);
      throw error;
    }
  }, "Featured order saved");
  const move = (index: number, step: number) => {
    const next = [...order];
    const item = next[index];
    if (!item) return;
    next.splice(index, 1);
    next.splice(index + step, 0, item);
    setOrder(next);
  };
  const dirty =
    initial.map((i) => i.id).join(",") !== order.map((i) => i.id).join(",");
  return (
    <div className="section-stack">
      <p className="text-ink-secondary">
        Only published public opportunities appear on the homepage. Move them
        into the order you want.
      </p>
      {order.length ? (
        order.map((item, index) => (
          <div className="ordered-row" key={item.id}>
            <span className="rank">{index + 1}</span>
            <div className="grow">
              <strong>{item.title}</strong>
              <span className="subline">{item.organization}</span>
            </div>
            <Button
              icon={<ArrowUp />}
              aria-label={`Move ${item.title} up`}
              disabled={save.isPending || index === 0}
              onClick={() => move(index, -1)}
            />
            <Button
              icon={<ArrowDown />}
              aria-label={`Move ${item.title} down`}
              disabled={save.isPending || index === order.length - 1}
              onClick={() => move(index, 1)}
            />
            <Button
              icon={<X />}
              aria-label={`Remove ${item.title} from featured`}
              disabled={save.isPending}
              onClick={() =>
                setOrder(order.filter((value) => value.id !== item.id))
              }
            />
          </div>
        ))
      ) : (
        <p>No featured opportunities yet. Add one below.</p>
      )}
      <Field
        label="Find a published opportunity"
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <ul className="choice-list">
        {items
          .filter(
            (item) =>
              !order.some((value) => value.id === item.id) &&
              `${item.title} ${item.organization}`
                .toLowerCase()
                .includes(search.toLowerCase()),
          )
          .slice(0, 20)
          .map((item) => (
            <li key={item.id}>
              <Button
                variant="quiet"
                disabled={save.isPending}
                onClick={() => setOrder([...order, item])}
              >
                Add {item.title}
              </Button>
            </li>
          ))}
      </ul>
      <MutationError error={save.error} />
      {partial && (
        <p className="error" role="alert">
          Part of the order may have been saved. Retry saving to apply the
          complete order.
        </p>
      )}
      <Button
        variant="primary"
        disabled={save.isPending || (!dirty && !partial)}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "Saving…" : "Save featured order"}
      </Button>
    </div>
  );
}
function Homepage({ initial }: { initial: api.SiteContent }) {
  const [draft, setDraft] = useState(initial);
  const [enabled, setEnabled] = useState(!!initial.announcement);
  const [validation, setValidation] = useState<string | null>(null);
  const save = useAction(api.updateSite, "Homepage saved");
  const announcement = draft.announcement ?? {
    text: "",
    link: "",
    starts_on: null,
    ends_on: null,
  };
  return (
    <form
      className="homepage-form section-stack"
      onSubmit={(e) => {
        e.preventDefault();
        if (
          enabled &&
          announcement.starts_on &&
          announcement.ends_on &&
          announcement.starts_on > announcement.ends_on
        ) {
          setValidation("Choose an end date on or after the start date.");
          return;
        }
        setValidation(null);
        save.mutate({ ...draft, announcement: enabled ? announcement : null });
      }}
    >
      <Field
        label="Hero title"
        required
        value={draft.hero_title}
        onChange={(e) => setDraft({ ...draft, hero_title: e.target.value })}
      />
      <Field label="Hero subtitle">
        <Textarea
          value={draft.hero_subtitle}
          onChange={(e) =>
            setDraft({ ...draft, hero_subtitle: e.target.value })
          }
        />
      </Field>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />{" "}
        Show an announcement
      </label>
      {enabled && (
        <>
          <Field
            label="Announcement text"
            required
            value={announcement.text}
            onChange={(e) =>
              setDraft({
                ...draft,
                announcement: { ...announcement, text: e.target.value },
              })
            }
          />
          <Field
            label="Announcement link"
            type="url"
            required
            value={announcement.link}
            onChange={(e) =>
              setDraft({
                ...draft,
                announcement: { ...announcement, link: e.target.value },
              })
            }
          />
          <div className="form-grid">
            <Field
              label="Starts on"
              type="date"
              value={announcement.starts_on || ""}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  announcement: {
                    ...announcement,
                    starts_on: e.target.value || null,
                  },
                })
              }
            />
            <Field
              label="Ends on"
              type="date"
              min={announcement.starts_on || undefined}
              value={announcement.ends_on || ""}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  announcement: {
                    ...announcement,
                    ends_on: e.target.value || null,
                  },
                })
              }
            />
          </div>
        </>
      )}
      {validation && (
        <p className="error" role="alert">
          {validation}
        </p>
      )}
      <MutationError error={save.error} />
      <Button type="submit" variant="primary" disabled={save.isPending}>
        {save.isPending ? "Saving…" : "Save homepage"}
      </Button>
      <section className="homepage-preview">
        <p className="eyebrow">Homepage preview</p>
        {enabled && (
          <div className="announcement-preview">{announcement.text}</div>
        )}
        <h2>{draft.hero_title || "Your hero title"}</h2>
        <p>{draft.hero_subtitle}</p>
      </section>
    </form>
  );
}
