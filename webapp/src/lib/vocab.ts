/** Vocabularies for the new-run composer: canonical names plus the
 * aliases people type, so "US", "USA" and "United States" are one value. */

export interface VocabEntry {
  /** Canonical value sent to the server. */
  value: string
  /** Lower-case alternatives matched in typeahead and in the interest text. */
  aliases: string[]
  group?: string
}

export const DEGREE_VOCAB: VocabEntry[] = [
  { value: "phd", aliases: ["phd", "ph.d", "ph.d.", "doctorate", "doctoral", "dphil"] },
  { value: "masters", aliases: ["masters", "master's", "master", "msc", "m.sc", "ms", "ma", "meng", "mres", "mphil"] },
  { value: "mba", aliases: ["mba"] },
  { value: "jd", aliases: ["jd", "law school", "juris doctor"] },
  { value: "md", aliases: ["md", "medical school", "medicine degree"] },
  { value: "pharmd", aliases: ["pharmd", "pharm.d", "doctor of pharmacy"] },
  { value: "mph", aliases: ["mph", "public health masters", "master of public health"] },
  { value: "dds", aliases: ["dds", "dental school", "dmd"] },
]

export const DEGREE_LABELS: Record<string, string> = {
  phd: "PhD",
  masters: "Master's",
  mba: "MBA",
  jd: "JD, Law",
  md: "MD, Medicine",
  pharmd: "PharmD",
  mph: "MPH",
  dds: "DDS, Dental",
}

export const ANYWHERE = "Anywhere"

export const PLACE_VOCAB: VocabEntry[] = [
  { value: "North America", aliases: ["north america"], group: "Regions" },
  { value: "Europe", aliases: ["europe", "european"], group: "Regions" },
  { value: "Asia", aliases: ["asia", "asian"], group: "Regions" },
  { value: "East Asia", aliases: ["east asia"], group: "Regions" },
  { value: "Southeast Asia", aliases: ["southeast asia", "south-east asia"], group: "Regions" },
  { value: "Middle East", aliases: ["middle east"], group: "Regions" },
  { value: "Africa", aliases: ["africa", "african"], group: "Regions" },
  { value: "Latin America", aliases: ["latin america", "south america"], group: "Regions" },
  { value: "Oceania", aliases: ["oceania"], group: "Regions" },
  { value: "Scandinavia", aliases: ["scandinavia", "nordics", "nordic countries"], group: "Regions" },
  { value: "United States", aliases: ["united states", "usa", "us", "u.s.", "u.s.a.", "america", "the states"], group: "Countries" },
  { value: "Canada", aliases: ["canada", "canadian"], group: "Countries" },
  { value: "United Kingdom", aliases: ["united kingdom", "uk", "u.k.", "britain", "great britain", "england", "scotland", "wales"], group: "Countries" },
  { value: "Ireland", aliases: ["ireland"], group: "Countries" },
  { value: "Germany", aliases: ["germany", "german"], group: "Countries" },
  { value: "France", aliases: ["france", "french"], group: "Countries" },
  { value: "Netherlands", aliases: ["netherlands", "holland", "dutch"], group: "Countries" },
  { value: "Switzerland", aliases: ["switzerland", "swiss"], group: "Countries" },
  { value: "Sweden", aliases: ["sweden", "swedish"], group: "Countries" },
  { value: "Denmark", aliases: ["denmark", "danish"], group: "Countries" },
  { value: "Norway", aliases: ["norway", "norwegian"], group: "Countries" },
  { value: "Finland", aliases: ["finland", "finnish"], group: "Countries" },
  { value: "Belgium", aliases: ["belgium"], group: "Countries" },
  { value: "Austria", aliases: ["austria"], group: "Countries" },
  { value: "Italy", aliases: ["italy", "italian"], group: "Countries" },
  { value: "Spain", aliases: ["spain", "spanish"], group: "Countries" },
  { value: "Portugal", aliases: ["portugal"], group: "Countries" },
  { value: "Australia", aliases: ["australia", "australian"], group: "Countries" },
  { value: "New Zealand", aliases: ["new zealand"], group: "Countries" },
  { value: "Japan", aliases: ["japan", "japanese"], group: "Countries" },
  { value: "South Korea", aliases: ["south korea", "korea", "korean"], group: "Countries" },
  { value: "China", aliases: ["china", "chinese", "mainland china"], group: "Countries" },
  { value: "Hong Kong", aliases: ["hong kong"], group: "Countries" },
  { value: "Taiwan", aliases: ["taiwan"], group: "Countries" },
  { value: "Singapore", aliases: ["singapore"], group: "Countries" },
  { value: "India", aliases: ["india", "indian"], group: "Countries" },
  { value: "Israel", aliases: ["israel"], group: "Countries" },
  { value: "United Arab Emirates", aliases: ["united arab emirates", "uae"], group: "Countries" },
  { value: "Saudi Arabia", aliases: ["saudi arabia"], group: "Countries" },
  { value: "South Africa", aliases: ["south africa"], group: "Countries" },
  { value: "Ghana", aliases: ["ghana"], group: "Countries" },
  { value: "Nigeria", aliases: ["nigeria"], group: "Countries" },
  { value: "Kenya", aliases: ["kenya"], group: "Countries" },
  { value: "Brazil", aliases: ["brazil"], group: "Countries" },
  { value: "Mexico", aliases: ["mexico"], group: "Countries" },
  { value: "Chile", aliases: ["chile"], group: "Countries" },
  { value: "Argentina", aliases: ["argentina"], group: "Countries" },
]

const f = (value: string, ...aliases: string[]): VocabEntry => ({ value, aliases: [value.toLowerCase(), ...aliases] })

export const FIELD_VOCAB: VocabEntry[] = [
  f("Robotics", "robot", "robots", "robotic"),
  f("Machine Learning", "ml", "deep learning", "reinforcement learning", "neural networks"),
  f("Artificial Intelligence", "ai"),
  f("Computer Vision", "image recognition", "visual perception"),
  f("Natural Language Processing", "nlp", "computational linguistics", "language models"),
  f("Computer Science", "cs", "computing"),
  f("Human-Computer Interaction", "hci", "human computer interaction"),
  f("Computer Security", "cybersecurity", "security", "cryptography"),
  f("Data Science", "data analytics"),
  f("Statistics", "statistical", "biostatistics"),
  f("Mathematics", "math", "maths", "applied mathematics"),
  f("Operations Research", "optimization", "optimisation"),
  f("Electrical Engineering", "ee", "signal processing", "circuits"),
  f("Mechanical Engineering", "mechanical", "mechatronics"),
  f("Aerospace Engineering", "aerospace", "aeronautics", "astronautics"),
  f("Civil Engineering", "civil", "structural engineering"),
  f("Chemical Engineering", "process engineering"),
  f("Biomedical Engineering", "bioengineering", "medical devices"),
  f("Materials Science", "materials", "nanomaterials", "metallurgy"),
  f("Environmental Engineering", "water resources"),
  f("Physics", "condensed matter", "quantum", "optics", "photonics"),
  f("Astronomy", "astrophysics", "cosmology"),
  f("Chemistry", "organic chemistry", "inorganic chemistry", "physical chemistry"),
  f("Biology", "molecular biology", "cell biology"),
  f("Neuroscience", "neuro", "brain", "cognitive neuroscience"),
  f("Computational Biology", "bioinformatics", "systems biology"),
  f("Genetics", "genomics"),
  f("Ecology", "evolution", "conservation"),
  f("Earth Sciences", "geology", "geoscience", "climate science", "climate"),
  f("Public Health", "epidemiology", "global health"),
  f("Medicine", "clinical research"),
  f("Pharmacology", "pharmaceutical sciences", "drug discovery"),
  f("Psychology", "cognitive science", "behavioral science", "behavioural science"),
  f("Economics", "econometrics", "development economics"),
  f("Finance", "financial economics"),
  f("Business", "management", "strategy", "marketing"),
  f("Political Science", "politics", "international relations", "public policy"),
  f("Sociology", "social science"),
  f("Anthropology"),
  f("Education", "learning sciences"),
  f("Law", "legal studies"),
  f("History"),
  f("Philosophy", "ethics"),
  f("Linguistics"),
  f("Literature", "english literature", "comparative literature"),
  f("Architecture", "urban planning", "urban design"),
  f("Design", "industrial design"),
  f("Agriculture", "agronomy", "food science"),
  f("Energy Systems", "renewable energy", "power systems", "batteries"),
]

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/** Short aliases that are ordinary words in lower case ("help us", "ma"):
 * these only count written as capitals (US, MA, AI). */
const CAPS_ONLY = new Set(["us", "ma", "ms", "md", "ai", "ee", "cs", "ml", "jd", "uk"])

/** Entries named in `text`, each once, in the order they appear. A match
 * inside a longer one ("america" in "North America") doesn't count. */
export function findInText(text: string, vocab: VocabEntry[]): string[] {
  const hits: { value: string; start: number; end: number }[] = []
  for (const entry of vocab) {
    let best: { start: number; end: number } | null = null
    for (const alias of entry.aliases) {
      const caps = CAPS_ONLY.has(alias)
      const re = new RegExp(
        `(^|[^A-Za-z])(${escapeRe(caps ? alias.toUpperCase() : alias)})(?=[^A-Za-z]|$)`,
        caps ? "" : "i",
      )
      const m = re.exec(text)
      if (!m) continue
      const start = m.index + m[1].length
      const span = { start, end: start + m[2].length }
      if (!best || span.start < best.start || (span.start === best.start && span.end > best.end)) best = span
    }
    if (best) hits.push({ value: entry.value, ...best })
  }
  return hits
    .filter((h) => !hits.some((o) => o !== h && o.start <= h.start && o.end >= h.end && o.end - o.start > h.end - h.start))
    .sort((a, b) => a.start - b.start)
    .map((h) => h.value)
}

/** Vocabulary entries matching a typeahead query (prefix of any alias first). */
export function searchVocab(query: string, vocab: VocabEntry[], limit = 8): VocabEntry[] {
  const q = query.trim().toLowerCase()
  if (!q) return vocab.slice(0, limit)
  const prefix = vocab.filter((e) => e.aliases.some((a) => a.startsWith(q)))
  const inner = vocab.filter((e) => !prefix.includes(e) && e.aliases.some((a) => a.includes(q)))
  return [...prefix, ...inner].slice(0, limit)
}

/** The canonical value for something typed, or the text itself. */
export function canonical(input: string, vocab: VocabEntry[]): string {
  const q = input.trim().toLowerCase()
  return vocab.find((e) => e.aliases.includes(q) || e.value.toLowerCase() === q)?.value ?? input.trim()
}
