import type { PartRow } from "@/bridge"

export const COPPER = "CU"

export function partKey(part: PartRow) {
  return part.path || part.name
}

const STEEL_GRADE = new Set(["A 36", "A 36 GALV", "SSTL 304", "Aluminio"])

function isGenericMaterial(name: string) {
  const key = name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]/gi, "")
    .toLowerCase()
  return key === "" || key === "generic" || key === "generico"
}

export function detectedMaterial(part: PartRow) {
  const grade = (part.canonical || part.material || "").trim()
  if (STEEL_GRADE.has(grade)) return grade
  if (part.copper) return COPPER
  if (isGenericMaterial(grade)) return "A 36"
  return grade || "A 36"
}

export function effectiveMaterial(part: PartRow, overrides: Record<string, string>) {
  const chosen = overrides[partKey(part)]
  if (chosen && chosen.trim()) return chosen.trim()
  return detectedMaterial(part)
}

const INVALID_FILE = /[<>:"/\\|?*\u0000-\u001f]/g

export function boardCode(value: string) {
  const text = value
    .replace(INVALID_FILE, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[.\s]+$/g, "")
  if (!text) return "B1"
  return text.slice(0, 48).trim() || "B1"
}

function isTextToken(token: string) {
  return /^[A-Za-z]+$/.test(token)
}

function pieceTail(name: string) {
  const chunks = name.split("-").map((chunk) => chunk.trim()).filter(Boolean)
  const numbered = chunks.filter((chunk) => !isTextToken(chunk))
  const source = numbered.length > 0 ? numbered : chunks
  return source.join("-") || name
}

export function copperFileName(part: PartRow, material: string, board = "B1") {
  if (material !== COPPER || !part.copper || (part.form !== "F" && part.form !== "B")) return ""
  return `${boardCode(board)}-${part.form}-${pieceTail(part.name)}`
}

export function materialChoices(catalog: string[] | undefined, parts: PartRow[], current: string) {
  const values = new Set<string>([COPPER, "Genérico"])
  for (const name of catalog ?? []) {
    const text = name.trim()
    if (text) values.add(text)
  }
  for (const part of parts) values.add(detectedMaterial(part))
  const chosen = current.trim()
  if (chosen) values.add(chosen)
  return [...values].sort((a, b) => {
    if (a === COPPER) return -1
    if (b === COPPER) return 1
    return a.localeCompare(b, "es")
  })
}

export function choiceLabel(part: PartRow, choice: string) {
  if (choice === COPPER && part.copper && (part.form === "F" || part.form === "B")) return `Cu ${part.form}`
  return choice
}

const HARDWARE_NAME =
  /(?:^|[^a-z0-9])(?:washers?|arandelas?|nuts?|tuercas?|bolts?|screws?|tornillos?|pernos?|hex|handles?|manijas?|asas?|jaladeras?|manerales?|hw)(?:[^a-z0-9]|$)/i

export function isHardware(name: string) {
  return HARDWARE_NAME.test(name)
}

export function uniqueText(values: string[]) {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))]
}

export function sortCalibres(values: string[]) {
  return uniqueText(values).sort((a, b) => Number(a) - Number(b) || a.localeCompare(b, "es"))
}
