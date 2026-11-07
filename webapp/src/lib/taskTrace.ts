import type { TaskLogEvent } from "./types"

/** Swap the clipped note of the last turn for the task's full final text
 * when the note is a prefix of it; the trace stores at most a preview. */
export function withFinalText(logs: TaskLogEvent[], finalText: string | null | undefined): TaskLogEvent[] {
  const full = finalText?.trim()
  const last = logs.at(-1)
  if (!full || last?.kind !== "turn" || !last.note) return logs
  const shown = last.note.replace(/\.\.\.$/, "").trim()
  if (shown === full || !full.startsWith(shown)) return logs
  return [...logs.slice(0, -1), { ...last, note: full }]
}

/** A task's human title: what it researches or drafts, for whom. */
export function taskLabel(type: string, name: string | null): string {
  switch (type) {
    case "discover_programs": {
      const tier = name?.replace(/^tier:/, "");

      return tier
        ? `Research ${tier} tier schools`
        : "Research schools";
    }

    case "research_professor":
      return name ? `Faculties at ${name}` : "Research faculties";

    case "research_one_professor": {
      if (!name) return "Match professor";

      const [last, ...firstParts] = name.split(",").map((part) => part.trim());
      const fullName = firstParts.length
        ? `${firstParts.join(" ")} ${last}`
        : last;

      return `Match with ${fullName}`;
    }

    case "draft_email": {
      const recipient = name?.split(",")[0].trim();

      return recipient ? `Draft email to ${recipient}` : "Draft email";
    }

    case "discover_opportunities": {
      const category = name?.replace(/^category:/, "");
      const audience: Record<string, string> = { startup: "startups", research: "researchers", student: "students" };
      return category ? `Find opportunities for ${audience[category] ?? category}` : "Find opportunities";
    }

    default:
      return name ? `${type}: ${name}` : type;
  }
}
