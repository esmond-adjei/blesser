import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Field } from "@blesser/ui";
import * as api from "../lib/api";
import {
  PageHeader,
  Pagination,
  Panel,
  QueryState,
  formatDate,
} from "../components/shared";

function stable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stable);
  if (typeof value === "object" && value !== null)
    return Object.fromEntries(
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, v]) => [key, stable(v)]),
    );
  return value;
}
export function AuditDiff({ entry }: { entry: api.AuditEntry }) {
  const before = entry.before ?? {};
  const after = entry.after ?? {};
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])];
  return (
    <section className="audit-diff">
      <h3>Before and after</h3>
      <p className="text-footnote text-ink-secondary">
        Changed fields are highlighted.
      </p>
      {keys.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Field</th>
                <th>Before</th>
                <th>After</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => {
                const changed =
                  JSON.stringify(stable(before[key])) !==
                  JSON.stringify(stable(after[key]));
                return (
                  <tr key={key} className={changed ? "diff-changed" : ""}>
                    <th>
                      {key}
                      {changed && <span className="subline">Changed</span>}
                    </th>
                    <td>
                      <pre>
                        {key in before
                          ? JSON.stringify(before[key], null, 2)
                          : "(absent)"}
                      </pre>
                    </td>
                    <td>
                      <pre>
                        {key in after
                          ? JSON.stringify(after[key], null, 2)
                          : "(absent)"}
                      </pre>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No before or after values were recorded.</p>
      )}
    </section>
  );
}
export default function Audit() {
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<api.AuditEntry | null>(null);
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const filters = {
    actor_id: params.get("actor_id") || undefined,
    entity_type: params.get("entity_type") || undefined,
    entity_id: params.get("entity_id") || undefined,
    action: params.get("action") || undefined,
    offset,
    limit: 30,
  };
  const audit = useQuery({
    queryKey: ["audit", filters],
    queryFn: () => api.audit(filters),
  });
  return (
    <>
      <PageHeader
        title="Audit log"
        description="See who changed what, and inspect the recorded values."
      />
      <div className="filters">
        {[
          ["actor_id", "Actor ID"],
          ["entity_type", "Entity type"],
          ["entity_id", "Entity ID"],
          ["action", "Action"],
        ].map(([key, label]) => (
          <Field
            key={key}
            label={label}
            value={params.get(key) || ""}
            onChange={(e) =>
              setParams((old) => {
                const next = new URLSearchParams(old);
                next.set(key, e.target.value);
                next.delete("offset");
                return next;
              })
            }
          />
        ))}
      </div>
      <QueryState query={audit} empty={!audit.data?.items.length}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Entity</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              {audit.data?.items.map((entry) => (
                <tr key={entry.id}>
                  <td className="nowrap">{formatDate(entry.at)}</td>
                  <td>{entry.actor_email}</td>
                  <td>{entry.action}</td>
                  <td>
                    {entry.entity_type}
                    <span className="subline mono">{entry.entity_id}</span>
                  </td>
                  <td>
                    <button
                      className="table-title"
                      onClick={() => setSelected(entry)}
                    >
                      View changes
                    </button>
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
        total={audit.data?.total}
        count={audit.data?.items.length || 0}
        onChange={(value) =>
          setParams((old) => {
            const next = new URLSearchParams(old);
            next.set("offset", String(value));
            return next;
          })
        }
      />
      {selected && (
        <Panel title="Recorded change" onClose={() => setSelected(null)} wide>
          <div className="section-stack">
            <h2>{selected.action}</h2>
            <p>
              {selected.actor_email}, {formatDate(selected.at)}
            </p>
            <AuditDiff entry={selected} />
          </div>
        </Panel>
      )}
    </>
  );
}
