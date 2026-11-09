import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Chip, Field, Textarea } from "@blesser/ui";
import * as api from "../lib/api";
import {
  MutationError,
  PageHeader,
  Pagination,
  Panel,
  QueryState,
  formatDate,
  useAction,
} from "../components/shared";

export default function Scans() {
  const [offset, setOffset] = useState(0);
  const [starting, setStarting] = useState(false);
  const [selected, setSelected] = useState<api.Scan | null>(null);
  const scans = useQuery({
    queryKey: ["scans", offset],
    queryFn: () => api.scans({ limit: 30, offset }),
    refetchInterval: 10_000,
  });
  const current =
    scans.data?.find((scan) => scan.id === selected?.id) ?? selected;
  return (
    <>
      <PageHeader
        title="Scans"
        description="Follow discovery across all accounts and start a staff scan."
        action={
          <Button variant="primary" onClick={() => setStarting(true)}>
            Start a scan
          </Button>
        }
      />
      <QueryState query={scans} empty={!scans.data?.length}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Scan</th>
                <th>Owner</th>
                <th>Status</th>
                <th>Started</th>
                <th>Added</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {scans.data?.map((scan) => (
                <tr key={scan.id}>
                  <td>
                    <strong>{scan.categories.join(", ")}</strong>
                    <span className="subline">
                      {scan.region}
                      {scan.focus ? ` / ${scan.focus}` : ""}
                    </span>
                  </td>
                  <td>{scan.owner_email || "Owner not provided"}</td>
                  <td>
                    <Chip
                      tone={
                        scan.status === "running"
                          ? "sun"
                          : scan.status === "done"
                            ? "forest"
                            : "neutral"
                      }
                    >
                      {scan.status === "done"
                        ? "Finished"
                        : scan.status === "running"
                          ? "Running"
                          : scan.status === "cancelled"
                            ? "Stopped"
                            : scan.status}
                    </Chip>
                  </td>
                  <td>{formatDate(scan.created_at)}</td>
                  <td>{scan.opportunities_added}</td>
                  <td>
                    <Button size="sm" onClick={() => setSelected(scan)}>
                      View trace
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
        count={scans.data?.length || 0}
        onChange={setOffset}
      />
      {starting && <StartScan onClose={() => setStarting(false)} />}
      {current && (
        <Panel title="Scan trace" onClose={() => setSelected(null)}>
          <div className="section-stack">
            <h2>
              {current.categories.join(", ")} in {current.region}
            </h2>
            <p>
              {current.owner_email || "Owner not provided"} ·{" "}
              {formatDate(current.created_at)}
            </p>
            {current.tasks?.length ? (
              current.tasks.map((task) => (
                <section key={task.id} className="section-stack scan-task">
                  <h3>
                    {task.task_type}
                    {task.target ? ` / ${task.target}` : ""}
                  </h3>
                  <Chip>{task.status}</Chip>
                  {task.error && <p className="error">{task.error}</p>}
                  {task.final_text && (
                    <p className="whitespace-pre-wrap">{task.final_text}</p>
                  )}
                  <pre className="source-excerpt">
                    {JSON.stringify(task.log, null, 2)}
                  </pre>
                </section>
              ))
            ) : (
              <p className="text-ink-secondary">
                No trace was included in this scan. Running scans refresh every
                10 seconds.
              </p>
            )}
          </div>
        </Panel>
      )}
    </>
  );
}
function StartScan({ onClose }: { onClose: () => void }) {
  const [categories, setCategories] = useState([
    "startup",
    "research",
    "student",
  ]);
  const [region, setRegion] = useState("Ghana");
  const [focus, setFocus] = useState("");
  const start = useAction(api.startScan, "Scan started", onClose);
  return (
    <Panel
      title="Start a scan"
      onClose={() => {
        if (!start.isPending) onClose();
      }}
    >
      <form
        className="section-stack"
        onSubmit={(e) => {
          e.preventDefault();
          if (categories.length)
            start.mutate({
              categories,
              region: region.trim(),
              focus: focus.trim(),
            });
        }}
      >
        <p className="text-ink-secondary">
          The discovery agent will find and check opportunities for the
          audiences you choose.
        </p>
        <fieldset>
          <legend>Look for</legend>
          {[
            ["startup", "Startups"],
            ["research", "Researchers"],
            ["student", "Students"],
          ].map(([value, label]) => (
            <label className="checkbox-label" key={value}>
              <input
                type="checkbox"
                checked={categories.includes(value)}
                onChange={(e) =>
                  setCategories(
                    e.target.checked
                      ? [...categories, value]
                      : categories.filter((item) => item !== value),
                  )
                }
              />
              {label}
            </label>
          ))}
        </fieldset>
        <Field
          label="Region"
          required
          value={region}
          onChange={(e) => setRegion(e.target.value)}
        />
        <Field
          label="Focus"
          hint="Optional, such as climate grants or postgraduate funding."
        >
          <Textarea value={focus} onChange={(e) => setFocus(e.target.value)} />
        </Field>
        <MutationError error={start.error} />
        <Button
          type="submit"
          variant="brand"
          disabled={!categories.length || !region.trim() || start.isPending}
        >
          {start.isPending ? "Starting…" : "Start scan"}
        </Button>
      </form>
    </Panel>
  );
}
