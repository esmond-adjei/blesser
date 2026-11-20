import type { ExportField, FormExport } from "../shared/types"
import { zip } from "./zip"

// Builds a .docx of the form so the member can draft answers offline. Plain WordprocessingML that opens in Word, Google Docs and LibreOffice.

const MAX_LISTED_OPTIONS = 15
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
const INK = "1F1F1F"
const MUTED = "5C5C5C"
const RULE = "B9B5AC"

// XML 1.0 forbids most control characters; pages sometimes carry them.
// eslint-disable-next-line no-control-regex
const INVALID = /[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/g
const esc = (text: string) =>
  text.replace(INVALID, "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")

export const formatDate = (date: Date) => `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`

interface RunStyle {
  bold?: boolean
  color?: string
  size?: number
  font?: string
}

function run(text: string, style: RunStyle = {}): string {
  const props = [
    style.font ? `<w:rFonts w:ascii="${style.font}" w:hAnsi="${style.font}" w:eastAsia="${style.font}" w:cs="${style.font}"/>` : "",
    style.bold ? "<w:b/>" : "",
    style.color ? `<w:color w:val="${style.color}"/>` : "",
    style.size ? `<w:sz w:val="${style.size}"/><w:szCs w:val="${style.size}"/>` : "",
  ].join("")
  const lines = text.split(/\r?\n/)
  const body = lines.map((line, i) => `${i ? "<w:br/>" : ""}<w:t xml:space="preserve">${esc(line)}</w:t>`).join("")
  return `<w:r>${props ? `<w:rPr>${props}</w:rPr>` : ""}${body}</w:r>`
}

interface ParaStyle {
  style?: string
  keepNext?: boolean
  after?: number
  before?: number
  indent?: number
}

function para(runs: string, p: ParaStyle = {}): string {
  const props = [
    p.style ? `<w:pStyle w:val="${p.style}"/>` : "",
    p.keepNext ? "<w:keepNext/>" : "",
    p.after !== undefined || p.before !== undefined ? `<w:spacing${p.before !== undefined ? ` w:before="${p.before}"` : ""}${p.after !== undefined ? ` w:after="${p.after}"` : ""}/>` : "",
    p.indent ? `<w:ind w:left="${p.indent}"/>` : "",
  ].join("")
  return `<w:p>${props ? `<w:pPr>${props}</w:pPr>` : ""}${runs}</w:p>`
}

/** A bordered box to write in; taller for long answers. */
function answerBox(value: string, minHeight: number): string {
  const border = (side: string) => `<w:${side} w:val="single" w:sz="6" w:space="0" w:color="${RULE}"/>`
  return [
    "<w:tbl>",
    `<w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>${["top", "left", "bottom", "right"].map(border).join("")}</w:tblBorders>`,
    '<w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tblCellMar>',
    '<w:tblLook w:val="0000"/></w:tblPr>',
    '<w:tblGrid><w:gridCol w:w="9360"/></w:tblGrid>',
    `<w:tr><w:trPr><w:cantSplit/><w:trHeight w:val="${minHeight}" w:hRule="atLeast"/></w:trPr>`,
    `<w:tc><w:tcPr><w:tcW w:w="5000" w:type="pct"/></w:tcPr>${para(value ? run(value, { color: INK }) : "", { after: 0 })}</w:tc></w:tr>`,
    "</w:tbl>",
    // A short spacer: Word needs a paragraph between consecutive tables.
    '<w:p><w:pPr><w:spacing w:after="0" w:line="160" w:lineRule="exact"/></w:pPr></w:p>',
  ].join("")
}

const box = (picked: boolean) => run(picked ? "☒" : "☐", { font: "Segoe UI Symbol", color: INK })

const asList = (value: ExportField["value"]) => (value === null ? [] : Array.isArray(value) ? value : [value])

function isPicked(field: ExportField, option: { value: string; label: string }): boolean {
  const chosen = asList(field.value).map((v) => v.trim().toLowerCase())
  return chosen.includes(option.label.trim().toLowerCase()) || chosen.includes(option.value.trim().toLowerCase())
}

const label = (field: ExportField) => field.label || field.placeholder || field.name || "Unlabelled field"

function labelPara(text: string, required: boolean): string {
  return para(run(text, { bold: true, color: INK }) + (required ? run(" (required)", { color: MUTED }) : ""), { keepNext: true, before: 200, after: 60 })
}

const hint = (text: string) => para(run(text, { color: MUTED, size: 18 }), { keepNext: true, after: 80 })

function fieldXml(field: ExportField): string {
  const parts: string[] = []
  const single = field.type === "checkbox" && field.options.length <= 1
  if (single) {
    const option = field.options[0] ?? { value: "on", label: label(field) }
    const picked = asList(field.value).some((v) => v === "Yes" || v === option.value || v === option.label)
    parts.push(para(box(picked) + run(`  ${option.label || label(field)}`, { color: INK }) + (field.required ? run(" (required)", { color: MUTED }) : ""), { before: 200, after: 60 }))
    if (field.help_text) parts.push(hint(field.help_text))
    return parts.join("")
  }

  parts.push(labelPara(label(field), field.required))
  if (field.help_text) parts.push(hint(field.help_text))

  const choice = ["radio", "checkbox", "select", "select-multiple"].includes(field.type) && field.options.length > 0
  const many = field.type === "checkbox" || field.type === "select-multiple"
  if (choice && field.options.length <= MAX_LISTED_OPTIONS) {
    parts.push(hint(many ? "Tick all that apply." : "Tick one."))
    field.options.forEach((option, i) => {
      const last = i === field.options.length - 1
      parts.push(para(box(isPicked(field, option)) + run(`  ${option.label || option.value}`, { color: INK }), { indent: 120, after: last ? 160 : 40, keepNext: !last }))
    })
    return parts.join("")
  }
  if (choice) {
    const shown = field.options.map((o) => o.label || o.value).join(", ")
    parts.push(hint(`${many ? "Choose any of" : "Choose one of"}: ${shown}`))
    parts.push(answerBox(asList(field.value).join(", "), 480))
    return parts.join("")
  }
  if (field.type === "file") {
    const types = field.accept.split(",").map((t) => t.trim()).filter(Boolean)
    parts.push(hint(types.length ? `Attach a file (${types.join(", ")}).` : "Attach a file."))
    parts.push(answerBox(asList(field.value).join(", "), 480))
    return parts.join("")
  }
  const long = field.tag === "textarea" || field.tag === "contenteditable"
  parts.push(answerBox(asList(field.value).join(", "), long ? 2400 : 480))
  return parts.join("")
}

export function documentXml(form: FormExport, date: Date): string {
  const filled = form.fields.filter((f) => f.value !== null).length
  const body: string[] = [
    para(run(form.title || "Application form"), { style: "Title" }),
    para(run(`Saved ${formatDate(date)} from ${form.url}`, { color: MUTED, size: 18 }), { after: 60 }),
    para(
      run(`${filled} of ${form.fields.length} ${form.fields.length === 1 ? "field has" : "fields have"} an answer. Write yours in the boxes, then copy them into the online form.`, { color: INK }),
      { after: 240 },
    ),
  ]
  let section: string | null = null
  for (const field of form.fields) {
    const next = field.section.trim()
    if (next && next !== section) body.push(para(run(next), { style: "Heading1" }))
    section = next || section
    body.push(fieldXml(field))
  }
  return [
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
    "<w:body>",
    ...body,
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>',
    "</w:body></w:document>",
  ].join("")
}

const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="80"/></w:pPr><w:rPr><w:b/><w:color w:val="${INK}"/><w:sz w:val="40"/><w:szCs w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="360" w:after="80"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="${INK}"/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr></w:style>
<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>`

const CONTENT_TYPES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>`

const ROOT_RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>`

const DOCUMENT_RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`

function coreXml(title: string, date: Date): string {
  const at = date.toISOString().replace(/\.\d{3}Z$/, "Z")
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>${esc(title)}</dc:title><dc:creator>Blesser</dc:creator>
<dcterms:created xsi:type="dcterms:W3CDTF">${at}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">${at}</dcterms:modified>
</cp:coreProperties>`
}

export const DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

export function buildFormDocx(form: FormExport, date = new Date()): Uint8Array {
  return zip(
    [
      { name: "[Content_Types].xml", data: CONTENT_TYPES },
      { name: "_rels/.rels", data: ROOT_RELS },
      { name: "word/document.xml", data: documentXml(form, date) },
      { name: "word/_rels/document.xml.rels", data: DOCUMENT_RELS },
      { name: "word/styles.xml", data: STYLES },
      { name: "docProps/core.xml", data: coreXml(form.title || "Application form", date) },
    ],
    date,
  )
}

/** A safe, readable file name from the page title. */
export function docxName(title: string): string {
  const slug = title
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase()
    .slice(0, 80)
    .replace(/-+$/, "")
  return `${slug || "application-form"}.docx`
}
