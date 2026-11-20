import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Chip, Field } from "@blesser/ui";
import * as api from "../lib/api";
import {
  MutationError,
  PageHeader,
  QueryState,
  StatusChip,
  formatDate,
  useAction,
} from "../components/shared";

const reasons: Record<api.DuplicatePair["reason"], string> = {
  similar_title: "Similar title",
  same_page: "Same source page",
};

function Listing({ item }: { item: api.AdminOpportunity }) {
  return (
    <div className="section-stack">
      <Link
        className="text-link underline"
        to={`/opportunities?id=${encodeURIComponent(item.id)}`}
      >
        {item.title}
      </Link>
      <p>{item.organization || "No organization"}</p>
      <div className="actions">
        <StatusChip status={item.status} />
        <span className="text-ink-secondary">
          {item.deadline_date
            ? `Closes ${item.deadline_date}`
            : item.rolling
              ? "Rolling"
              : "No deadline"}
        </span>
      </div>
      <p className="text-ink-secondary">
        Last confirmed {formatDate(item.verified_at)}
      </p>
    </div>
  );
}

export default function Duplicates() {
  const pairs = useQuery({
    queryKey: ["duplicates"],
    queryFn: api.duplicates,
  });
  const merge = useAction(
    ({ from, into }: { from: string; into: string }) =>
      api.mergeOpportunity(from, into),
    "Duplicate merged",
  );
  const dismiss = useAction(api.dismissDuplicate, "Marked as different");
  const busy = merge.isPending || dismiss.isPending;
  return (
    <>
      <PageHeader
        title="Duplicates"
        description="Listings that look like the same opportunity. Keep one and the other is hidden, with its tracking and links moved over."
      />
      <MutationError error={merge.error || dismiss.error} />
      <QueryState query={pairs} empty={!pairs.data?.length}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>First listing</th>
                <th>Second listing</th>
                <th>Match</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {pairs.data?.map(({ first, second, score, reason }) => (
                <tr key={`${first.id}:${second.id}`}>
                  <td>
                    <Listing item={first} />
                  </td>
                  <td>
                    <Listing item={second} />
                  </td>
                  <td>
                    <Chip tone="sun">{reasons[reason]}</Chip>
                    <p>{Math.round(score * 100)}% alike</p>
                  </td>
                  <td>
                    <div className="actions">
                      <Button
                        size="sm"
                        disabled={busy || first.status === "hidden"}
                        onClick={() =>
                          merge.mutate({ from: second.id, into: first.id })
                        }
                      >
                        Keep first
                      </Button>
                      <Button
                        size="sm"
                        disabled={busy || second.status === "hidden"}
                        onClick={() =>
                          merge.mutate({ from: first.id, into: second.id })
                        }
                      >
                        Keep second
                      </Button>
                      <Button
                        size="sm"
                        variant="quiet"
                        disabled={busy}
                        onClick={() =>
                          dismiss.mutate({
                            first_id: first.id,
                            second_id: second.id,
                          })
                        }
                      >
                        Not duplicates
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </QueryState>
      <Aliases />
    </>
  );
}

function Aliases() {
  const aliases = useQuery({
    queryKey: ["organization-aliases"],
    queryFn: api.organizationAliases,
  });
  const [draft, setDraft] = useState<api.OrganizationAlias>({
    alias: "",
    canonical: "",
  });
  const save = useAction(api.saveOrganizationAlias, "Alias saved", () =>
    setDraft({ alias: "", canonical: "" }),
  );
  const remove = useAction(api.deleteOrganizationAlias, "Alias removed");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(draft);
  };
  return (
    <section className="section-stack">
      <h2>Organization names</h2>
      <p className="text-ink-secondary">
        Treat two names as one organization when checking for duplicates, for
        example German Academic Exchange Service and DAAD. Words such as
        Foundation and Trust at the end of a name are already ignored.
      </p>
      <form className="form-grid" onSubmit={submit}>
        <Field
          label="Other name"
          required
          value={draft.alias}
          onChange={(e) => setDraft({ ...draft, alias: e.target.value })}
        />
        <Field
          label="Name to use"
          required
          value={draft.canonical}
          onChange={(e) => setDraft({ ...draft, canonical: e.target.value })}
        />
        <Button type="submit" disabled={save.isPending}>
          Add name
        </Button>
      </form>
      <MutationError error={save.error || remove.error} />
      <QueryState query={aliases} empty={!aliases.data?.length}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Other name</th>
                <th>Name to use</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {aliases.data?.map((row) => (
                <tr key={row.alias}>
                  <td>{row.alias}</td>
                  <td>{row.canonical}</td>
                  <td>
                    <Button
                      size="sm"
                      variant="quiet"
                      disabled={remove.isPending}
                      onClick={() => remove.mutate(row.alias)}
                    >
                      Remove
                    </Button>
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
