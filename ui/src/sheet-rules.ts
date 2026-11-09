import type { SheetRule, SheetRuleCatalog } from "@/bridge"

export const RELIEF_SHAPES = [
  { id: "round", label: "Redondo" },
  { id: "straight", label: "Recto" },
  { id: "tear", label: "Rasgado" },
]

export const CORNER_SHAPES = [
  { id: "round", label: "Redondo" },
  { id: "square", label: "Cuadrado" },
  { id: "tear", label: "Rasgado" },
  { id: "intersection", label: "Intersección" },
  { id: "trim", label: "Recortar al doblez" },
  { id: "none", label: "Sin reemplazo" },
]

export const TRANSITIONS = [
  { id: "none", label: "Ninguna" },
  { id: "intersection", label: "Intersección" },
  { id: "straight", label: "Recta" },
  { id: "arc", label: "Arco" },
  { id: "trim", label: "Recortar" },
]

const blank: Omit<SheetRule, "id" | "name" | "min" | "max"> = {
  unfold: "deduction",
  bendDeduction: "0 in",
  kFactor: "0.44",
  bendRadius: "Thickness",
  bendReliefShape: "round",
  bendReliefWidth: "Thickness",
  bendReliefDepth: "Thickness / 2",
  minimumRemnant: "Thickness * 2",
  cornerReliefShape: "round",
  cornerReliefSize: "Thickness",
  gapSize: "Thickness",
  bendTransition: "none",
  bendTransitionArcRadius: "Thickness",
  threeBendCornerReliefShape: "intersection",
  threeBendCornerReliefSize: "Thickness",
}

function rule(name: string, min: number, max: number): SheetRule {
  return { id: name.toLowerCase().replace(/\s+/g, "-"), name, min, max, ...blank }
}

export const defaultRuleCatalog: SheetRuleCatalog = {
  unit: "in",
  rules: [
    rule("Cal 0.125", 0.11, 0.15),
    rule("Cal 0.1875", 0.16, 0.21),
    rule("Cal 0.25", 0.22, 0.28),
    rule("Cal 0.375", 0.34, 0.41),
    rule("Cal 0.50", 0.46, 0.54),
  ],
}

export function nextRule(catalog: SheetRuleCatalog): SheetRule {
  const top = catalog.rules.reduce((max, item) => Math.max(max, item.max), 0)
  const min = Math.round((top + 0.01) * 1000) / 1000
  const max = Math.round((min + 0.05) * 1000) / 1000
  return {
    ...blank,
    id: `rango-${Date.now()}`,
    name: "Nuevo rango",
    min,
    max,
  }
}
