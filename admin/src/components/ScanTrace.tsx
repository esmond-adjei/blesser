import { Chip } from "@blesser/ui";
import type { Scan } from "../lib/api";
import { describeLog, parseSummary, shortUrl, timeSpan, titleCase, type Step } from "../lib/scanTrace";
import { formatDate } from "./shared";

type Task = NonNullable<Scan["tasks"]>[number];

const AUDIENCE: Record<string, string> = { startup: "Startups", research: "Researchers", student: "Students" };

const statusTone = (status: string) =>
  status === "done" ? "forest" : status === "running" ? "sun" : status === "failed" ? "critical" : "neutral";

const clock = (at: string) =>
  at ? new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";

export function ScanTrace({ scan }: { scan: Scan }) {
  const tasks = scan.tasks ?? [];
  const steps = tasks.flatMap((task) => describeLog(task.log ?? []));
  const span = timeSpan(steps);
  return (
    <div className="trace">
      <header className="trace-head">
        <h2>
          {scan.categories.map((c) => AUDIENCE[c] ?? c).join(", ")} in {scan.region}
        </h2>
        <p className="subline">
          {scan.owner_email || "Owner not provided"}, {formatDate(scan.created_at)}
        </p>
        {scan.focus ? <p className="trace-focus">{scan.focus}</p> : null}
      </header>
      <dl className="trace-stats">
        <div>
          <dt>Status</dt>
          <dd>
            <Chip tone={statusTone(scan.status)}>{scan.status === "done" ? "Finished" : titleCase(scan.status)}</Chip>
          </dd>
        </div>
        <div>
          <dt>Added</dt>
          <dd>{scan.opportunities_added}</dd>
        </div>
        <div>
          <dt>Steps</dt>
          <dd>{steps.length}</dd>
        </div>
        {span ? (
          <div>
            <dt>Ran for</dt>
            <dd>{span}</dd>
          </div>
        ) : null}
      </dl>
      {tasks.length ? (
        tasks.map((task) => <TaskTrace key={task.id} task={task} />)
      ) : (
        <p className="text-ink-secondary">
          No trace was included in this scan. Running scans refresh every 10 seconds.
        </p>
      )}
    </div>
  );
}

function TaskTrace({ task }: { task: Task }) {
  const summary = parseSummary(task.final_text ?? "");
  const steps = describeLog(task.log ?? []);
  const target = task.target?.replace(/^category:/, "");
  return (
    <section className="trace-task">
      <div className="trace-task-head">
        <h3>{titleCase(task.task_type)}</h3>
        {target ? <Chip>{AUDIENCE[target] ?? titleCase(target)}</Chip> : null}
        {task.status === "done" ? null : <Chip tone={statusTone(task.status)}>{titleCase(task.status)}</Chip>}
      </div>
      {task.error ? <p className="error">{task.error}</p> : null}
      {summary.lead.map((line) => (
        <p key={line} className="trace-lead">
          {line}
        </p>
      ))}
      <div className="trace-saved">
        <h4>Saved</h4>
        {summary.saved.length ? (
          <ul>
            {summary.saved.map((title) => (
              <li key={title}>
                <Chip tone="forest">{title}</Chip>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-ink-tertiary">Nothing new was saved.</p>
        )}
      </div>
      {summary.skipped.length ? (
        <details className="trace-fold" open={summary.skipped.length <= 6}>
          <summary>Pages checked, {summary.skipped.length}</summary>
          <ul className="trace-skipped">
            {summary.skipped.map((item) => (
              <li key={item.url}>
                <div>
                  <strong>{item.title || shortUrl(item.url, 48)}</strong>
                  <a href={item.url} target="_blank" rel="noreferrer noopener" className="subline">
                    {shortUrl(item.url)}
                  </a>
                </div>
                <div className="trace-skipped-meta">
                  {item.outcome ? <OutcomeChip outcome={item.outcome} /> : null}
                  {item.deadline && item.deadline !== "none stated" ? (
                    <span className="subline">Deadline {item.deadline}</span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {steps.length ? (
        <details className="trace-fold">
          <summary>Steps, {steps.length}</summary>
          <ol className="trace-steps">
            {steps.map((step, index) => (
              <StepRow key={index} step={step} />
            ))}
          </ol>
        </details>
      ) : null}
      {task.log?.length ? (
        <details className="trace-fold">
          <summary>Raw log</summary>
          <pre className="source-excerpt">{JSON.stringify(task.log, null, 2)}</pre>
        </details>
      ) : null}
    </section>
  );
}

function OutcomeChip({ outcome }: { outcome: string }) {
  if (outcome.startsWith("saved")) return <Chip tone="forest">Saved</Chip>;
  return <Chip tone={outcome === "fetch failed" ? "critical" : "neutral"}>{titleCase(outcome)}</Chip>;
}

function StepRow({ step }: { step: Step }) {
  return (
    <li className={step.ok ? "" : "failed"}>
      <time>{clock(step.at)}</time>
      <div>
        <strong>{step.label}</strong>
        {step.ok ? null : <Chip tone="critical">Failed</Chip>}
        {step.detail ? (
          <span className="trace-detail">{step.detail.startsWith("http") ? shortUrl(step.detail, 80) : step.detail}</span>
        ) : null}
        {step.result ? (
          <details className="trace-result">
            <summary>Result</summary>
            <pre>{step.result}</pre>
          </details>
        ) : null}
      </div>
    </li>
  );
}
