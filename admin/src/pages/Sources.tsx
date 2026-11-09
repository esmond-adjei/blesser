import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Chip, Field, Select } from "@blesser/ui";
import * as api from "../lib/api";
import {
  MutationError,
  PageHeader,
  QueryState,
  formatDate,
  useAction,
} from "../components/shared";

const emptySource: api.SourceInput = {
  url: "",
  kind: "listing",
  category_hints: [],
  enabled: true,
};

export default function Sources() {
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: api.sources,
    refetchInterval: 15000,
  });
  const [editing, setEditing] = useState<api.Source | "new" | null>(null);
  const toggle = useAction(
    ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.updateSource(id, { enabled }),
    "Source updated",
  );
  const crawl = useAction(api.crawlSource, "Crawl queued");
  const remove = useAction(api.deleteSource, "Source deleted");
  return (
    <>
      <PageHeader
        title="Sources"
        description="Manage the feeds and pages the crawler checks for new opportunities."
        action={<Button onClick={() => setEditing("new")}>Add source</Button>}
      />
      {editing && (
        <SourceForm
          key={editing === "new" ? "new" : editing.id}
          initial={editing === "new" ? emptySource : editing}
          id={editing === "new" ? undefined : editing.id}
          close={() => setEditing(null)}
        />
      )}
      <MutationError error={toggle.error || crawl.error || remove.error} />
      <QueryState query={sources} empty={!sources.data?.length}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Categories</th>
                <th>Status</th>
                <th>Yield</th>
                <th>Last crawl</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.data?.map((source) => (
                <tr key={source.id}>
                  <td>
                    <a
                      className="text-link"
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {source.url}
                    </a>
                    <p>
                      {source.kind}
                      {source.proposed ? ", proposed by agent" : ""}
                    </p>
                    {source.last_error && (
                      <p role="status">
                        {source.last_error} ({source.consecutive_failures}{" "}
                        failures)
                      </p>
                    )}
                  </td>
                  <td>
                    {source.category_hints.join(", ") || "All categories"}
                  </td>
                  <td>
                    <Chip tone={source.enabled ? "forest" : "neutral"}>
                      {source.enabled ? "Enabled" : "Disabled"}
                    </Chip>
                    {source.crawl_requested && <p>Crawl queued</p>}
                  </td>
                  <td>
                    {source.candidates_found} candidates
                    <br />
                    {source.opportunities_saved} saved
                  </td>
                  <td>
                    {formatDate(source.last_crawled_at)}
                    <p>{source.last_candidates} new last crawl</p>
                  </td>
                  <td>
                    <div className="actions">
                      <Button size="sm" onClick={() => setEditing(source)}>
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        disabled={toggle.isPending}
                        onClick={() =>
                          toggle.mutate({
                            id: source.id,
                            enabled: !source.enabled,
                          })
                        }
                      >
                        {source.enabled ? "Disable" : "Enable"}
                      </Button>
                      <Button
                        size="sm"
                        disabled={
                          !source.enabled ||
                          crawl.isPending ||
                          source.crawl_requested
                        }
                        onClick={() => crawl.mutate(source.id)}
                      >
                        Crawl now
                      </Button>
                      <Button
                        size="sm"
                        disabled={remove.isPending}
                        onClick={() => {
                          if (
                            window.confirm(
                              `Delete ${source.url}? Candidates and saved opportunities will stay.`,
                            )
                          )
                            remove.mutate(source.id);
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
    </>
  );
}

function SourceForm({
  initial,
  id,
  close,
}: {
  initial: api.SourceInput;
  id?: string;
  close: () => void;
}) {
  const [draft, setDraft] = useState<api.SourceInput>({
    url: initial.url,
    kind: initial.kind,
    category_hints: initial.category_hints,
    enabled: initial.enabled,
  });
  const save = useAction(async (body: api.SourceInput) => {
    const result = id
      ? await api.updateSource(id, body)
      : await api.createSource(body);
    close();
    return result;
  }, "Source saved");
  return (
    <form
      className="section-stack"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(draft);
      }}
    >
      <h2>{id ? "Edit source" : "Add source"}</h2>
      <div className="form-grid">
        <Field
          label="URL"
          type="url"
          required
          maxLength={2000}
          value={draft.url}
          onChange={(event) => setDraft({ ...draft, url: event.target.value })}
        />
        <Field label="Kind">
          <Select
            value={draft.kind}
            onChange={(event) =>
              setDraft({
                ...draft,
                kind: api.sourceKindSchema(event.target.value),
              })
            }
          >
            <option value="listing">Listing page</option>
            <option value="rss">RSS or Atom feed</option>
            <option value="sitemap">Sitemap</option>
          </Select>
        </Field>
      </div>
      <fieldset>
        <legend>Category hints</legend>
        {["startup", "research", "student"].map((category) => (
          <label className="checkbox-label" key={category}>
            <input
              type="checkbox"
              checked={draft.category_hints.includes(category)}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  category_hints: event.target.checked
                    ? [...draft.category_hints, category]
                    : draft.category_hints.filter((item) => item !== category),
                })
              }
            />{" "}
            {category}
          </label>
        ))}
      </fieldset>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={draft.enabled}
          onChange={(event) =>
            setDraft({ ...draft, enabled: event.target.checked })
          }
        />{" "}
        Enabled
      </label>
      <MutationError error={save.error} />
      <div className="actions">
        <Button type="submit" variant="primary" disabled={save.isPending}>
          Save source
        </Button>
        <Button type="button" onClick={close}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
