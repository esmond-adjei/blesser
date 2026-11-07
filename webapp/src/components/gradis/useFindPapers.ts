import { useGradis } from "./GradisProvider"

/** Has Gradis find a professor's papers on OpenAlex and save them, in a
 * chat it opens for the purpose. Without papers there's nothing to match. */
export function useFindPapers() {
  const { ask, sending } = useGradis()
  function findPapers(p: { id: string; name: string; program?: string | null; school?: string | null; openalex_id?: string | null }) {
    const where = [p.program, p.school].filter(Boolean).join(", ")
    ask(
      `Find the papers of professor ${p.name} (professor_id ${p.id})${where ? ` at ${where}` : ""}` +
        `${p.openalex_id ? `; their OpenAlex id may be ${p.openalex_id}` : ""}. ` +
        "Look them up on OpenAlex, make sure the author is at that institution, then save their recent papers " +
        "to their record with save_professor_papers.",
    )
  }
  return { findPapers, sending }
}
