export type PhotoFolder = {
  name: string
  children: string[]
}

export type PhotoSlots = {
  F: string
  B: string
  ISO: string
}

export type PhotoLayout = {
  rootName: string
  items: Record<string, PhotoFolder>
  slots: PhotoSlots
}

/** Árbol de `cotas_dossier` / `_RAMAS_DOSSIER_JPGS` (PIEZAS_ACOTADAS). */
export const defaultPhotoLayout = (): PhotoLayout => ({
  rootName: "PIEZAS_ACOTADAS",
  items: {
    root: {
      name: "PIEZAS_ACOTADAS",
      children: ["corte", "doblado", "armado", "estanado_busbar", "sin"],
    },
    corte: { name: "Corte", children: ["plasma", "maquinado"] },
    plasma: { name: "Plasma y Laser", children: ["plasma_metal", "plasma_busbar"] },
    plasma_metal: { name: "Corte metal", children: [] },
    plasma_busbar: { name: "Corte Busbar", children: [] },
    maquinado: {
      name: "Maquinado",
      children: [
        "maquinados_metal",
        "corte_busbar",
        "piezas_soldadas",
        "accesorios_sueltos",
        "inspeccion_visual",
        "accesorios_por_pieza",
      ],
    },
    maquinados_metal: { name: "Maquinados metal", children: [] },
    corte_busbar: { name: "Corte Busbar", children: [] },
    piezas_soldadas: { name: "Piezas Soldadas", children: [] },
    accesorios_sueltos: { name: "Accesorios Sueltos", children: [] },
    inspeccion_visual: { name: "Inspeccion Visual", children: [] },
    accesorios_por_pieza: { name: "Accesorios Sueltos por pieza", children: [] },
    doblado: { name: "Doblado", children: ["metal", "busbar"] },
    metal: { name: "Metal", children: [] },
    busbar: { name: "Busbar", children: [] },
    armado: { name: "Armado", children: ["assy_tanks", "assy_loose"] },
    assy_tanks: { name: "Assy Tanks", children: [] },
    assy_loose: { name: "Assy Loose Accesories", children: [] },
    estanado_busbar: { name: "Estañado Busbar", children: [] },
    sin: { name: "SIN CLASIFICACION", children: [] },
  },
  slots: { F: "corte_busbar", B: "busbar", ISO: "estanado_busbar" },
})

export function normalizePhotoLayout(raw: unknown): PhotoLayout {
  const fallback = defaultPhotoLayout()
  if (!raw || typeof raw !== "object") return fallback
  const data = raw as Partial<PhotoLayout>
  const items = { ...fallback.items, ...(data.items && typeof data.items === "object" ? data.items : {}) }
  if (!items.root) items.root = fallback.items.root
  const rootKids = new Set(items.root.children || [])
  for (const id of fallback.items.root.children) rootKids.add(id)
  items.root = { ...items.root, children: [...rootKids], name: String(data.rootName || items.root.name || "PIEZAS_ACOTADAS") }
  const slots = data.slots && typeof data.slots === "object" ? data.slots : fallback.slots
  return {
    rootName: String(data.rootName || items.root?.name || "PIEZAS_ACOTADAS").trim() || "PIEZAS_ACOTADAS",
    items,
    slots: {
      F: String(slots.F || "corte_busbar"),
      B: String(slots.B || "busbar"),
      ISO: String(slots.ISO || "estanado_busbar"),
    },
  }
}

export function folderPath(layout: PhotoLayout, folderId: string): string {
  const parent: Record<string, string> = {}
  for (const [id, node] of Object.entries(layout.items)) {
    for (const child of node.children || []) parent[child] = id
  }
  const parts: string[] = []
  let cur = folderId
  while (cur && cur !== "root") {
    const node = layout.items[cur]
    if (!node) break
    parts.unshift(node.name)
    cur = parent[cur]
  }
  return [layout.rootName, ...parts].join("/")
}

export function safeFolderName(name: string): string {
  const cleaned = name.replace(/[<>:"/\\|?*]/g, "_").replace(/[. ]+$/g, "").trim()
  return cleaned || "carpeta"
}
