export interface Skipped {
  url: string;
  title: string;
  deadline: string;
  outcome: string;
}

export interface TaskSummary {
  lead: string[];
  saved: string[];
  skipped: Skipped[];
}

export interface Step {
  turn: number;
  at: string;
  label: string;
  detail: string;
  ok: boolean;
  result: string;
}

const URL_START = /;\s+(?=https?:\/\/)/;

function parseSkipped(item: string): Skipped {
  const parts = item.split(" | ").map((part) => part.trim());
  const url = parts[0] ?? "";
  const outcome = parts.length > 1 ? (parts.at(-1) ?? "") : "";
  const deadline =
    parts.find((part) => part.startsWith("deadline:"))?.slice(9).trim() ?? "";
  const title =
    parts
      .slice(1, -1)
      .find((part) => part && !part.startsWith("deadline:") && !part.startsWith("[Could not")) ?? "";
  return { url, title, deadline, outcome };
}

export function parseSummary(text: string): TaskSummary {
  const summary: TaskSummary = { lead: [], saved: [], skipped: [] };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("Saved:")) {
      const value = line.slice(6).trim();
      if (value && value !== "None") summary.saved = value.split("; ").filter(Boolean);
    } else if (line.startsWith("Skipped:")) {
      const value = line.slice(8).trim();
      if (value && value !== "None") summary.skipped = value.split(URL_START).map(parseSkipped);
    } else {
      summary.lead.push(line);
    }
  }
  return summary;
}

const text = (value: unknown) => (typeof value === "string" ? value : "");

export function cleanResult(preview: string): string {
  return preview.replace(/\\n/g, "\n").replace(/\\"/g, '"').replace(/\\t/g, "  ").trim();
}

export function describeLog(log: Record<string, unknown>[]): Step[] {
  return log.map((entry) => {
    const input = (entry.input ?? {}) as Record<string, unknown>;
    const base = { turn: Number(entry.turn ?? 0), at: text(entry.at), ok: entry.ok !== false };
    const result = cleanResult(text(entry.result_preview));
    switch (entry.tool) {
      case "search_web":
        return { ...base, label: "Searched the web", detail: text(input.query), result };
      case "fetch_page":
        return { ...base, label: "Read a page", detail: text(input.url), result };
      case "crawl_candidate":
        return { ...base, label: "Checked a source", detail: text(input.url), result };
      case "save_opportunity":
        return { ...base, label: "Saved an opportunity", detail: text(input.title) || text(input.url), result };
      case "reject_candidate":
        return { ...base, label: "Rejected a candidate", detail: text(input.title) || text(input.url), result };
      default:
        if (entry.kind === "turn") return { ...base, label: "Note", detail: text(entry.note), result: "" };
        return { ...base, label: text(entry.tool) || "Step", detail: "", result };
    }
  });
}

export function shortUrl(value: string, max = 64): string {
  try {
    const url = new URL(value);
    const path = url.pathname === "/" ? "" : url.pathname;
    const text = `${url.host.replace(/^www\./, "")}${path}`;
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  } catch {
    return value.length > max ? `${value.slice(0, max - 1)}…` : value;
  }
}

export function timeSpan(steps: Step[]): string {
  const times = steps.map((step) => Date.parse(step.at)).filter(Number.isFinite);
  if (times.length < 2) return "";
  const seconds = Math.round((Math.max(...times) - Math.min(...times)) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60 ? `${minutes}m ${seconds % 60}s` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function titleCase(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
