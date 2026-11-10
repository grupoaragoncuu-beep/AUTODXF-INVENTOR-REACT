import type { PhotoLayout } from "@/photo-layout"

export type PartRow = {
  name: string
  material: string
  canonical: string
  thickness: string
  qty: number
  flat: boolean
  classification: string
  path: string
  copper: boolean
  form: "" | "F" | "B"
  copperWhy: string
}

export type CatalogStatus = {
  connected: boolean
  source: string
  message: string
  materials: string[]
  herinoxConnected: boolean
  nestingConnected: boolean
}

export type Snapshot = {
  inventorConnected: boolean
  inventorVersion: string
  assemblyName: string
  assemblyPath: string
  jobName: string
  parts: PartRow[]
  message: string
  catalog: CatalogStatus
}

export type SheetRule = {
  id: string
  name: string
  min: number
  max: number
  unfold: "deduction" | "kfactor"
  bendDeduction: string
  kFactor: string
  bendRadius: string
  bendReliefShape: string
  bendReliefWidth: string
  bendReliefDepth: string
  minimumRemnant: string
  cornerReliefShape: string
  cornerReliefSize: string
  gapSize: string
  bendTransition: string
  bendTransitionArcRadius: string
  threeBendCornerReliefShape: string
  threeBendCornerReliefSize: string
}

export type SheetRuleCatalog = {
  unit: "in"
  rules: SheetRule[]
}

export type SheetRuleSave = {
  ok: boolean
  message: string
  catalog: SheetRuleCatalog
}

export type AwisResult = {
  ok: boolean
  message: string
  log: string
}

export type MultibodyFailure = {
  name: string
  message: string
}

export type MultibodyResult = {
  ok: boolean
  message: string
  folder?: string
  processed?: string[]
  failed?: MultibodyFailure[]
  replaced?: number
  inventorConnected?: boolean
  session?: Snapshot
}

export type SheetRulesResult = {
  ok: boolean
  withFlat: number
  missing: string[]
  message: string
  log: string
  catalog?: CatalogStatus
  session?: Snapshot
}

export type ExportResult = {
  ok: boolean
  exported: number
  csvPath: string
  message: string
  catalog?: CatalogStatus
  session?: Snapshot
}

export type ExportOptions = {
  exportRoot: string
  setASide: boolean
  writeCsv: boolean
  closeOpened: boolean
}

export type ShapeRow = {
  name: string
  path: string
  cara?: string
  removed?: boolean
  qty: number
  lengthIn: number
  widthIn: number
  thickIn: number
  fill: number
  family: string
  suggestedFamily: string
  source: string
  included: boolean
  accessory: boolean
  accessoryWhy: string
  process: string
  herinox: string
  signature: string
  hardware: boolean
  kind: string
  classification: string
}

export type StockRow = {
  code: string
  family: string
  material: string
  width: number
  thick: number
  text: string
}

export type ShapeScan = {
  ok: boolean
  message: string
  assemblyName?: string
  rows?: ShapeRow[]
  stock?: StockRow[]
}

export type ColorimetriaClass = {
  id: string
  name: string
  color: string
  appearances?: string[]
}

export type ColorimetriaCatalog = {
  classes: ColorimetriaClass[]
}

export type BlockStep = {
  id: string
  name: string
  prop: string
  level: "part" | "assembly"
  color: string
  count: number
  state: "" | "hecho" | "no_aplica"
  unlocked: boolean
}

export type BlockItem = {
  path: string
  name: string
  kind: "part" | "assembly"
  qty: number
  blocks: string[]
}

export type BlockPending = {
  path: string
  name: string
  kind: "part" | "assembly"
  qty: number
  legacy: string
  blocks?: string[]
}

export type BlocksSnapshot = {
  ok: boolean
  message: string
  assembly?: string
  blocks?: BlockStep[]
  items?: BlockItem[]
  current?: string
  complete?: boolean
  diagnostic?: { unclassified: BlockPending[]; conflicts: BlockPending[] } | null
}

export type AcotacionFlow = {
  label: string
  dossierProduct: string
  unit: string
  picks: string[]
  views: string[]
  omit: string[]
  despliegue: boolean
  copperPrefixes: string[]
  corte?: {
    classes: string[]
    holeAnchor: "center" | "edge"
    measureWalls: boolean
  }
  doblado?: {
    classes?: string[]
    holeAnchor: "center" | "edge"
    measureWalls: boolean
  }
  armado?: {
    classes: string[]
  }
  referencia?: {
    faces?: Record<string, string[]>
  }
}

export type AcotacionCatalog = {
  paths: {
    corporateRoot: string
    cotasProject: string
    machote: string
    localJpg: string
    dossierFolder: string
    jpgsFolder: string
  }
  classify: Array<{
    id: string
    field: "nombre" | "ruta"
    pattern: string
    tipo: "BOARD" | "TANQUE"
    familia: string
    enabled: boolean
  }>
  defaultTipo: "BOARD" | "TANQUE"
  flows: { BOARD: AcotacionFlow; TANQUE: AcotacionFlow }
  measures: Array<{ id: string; label: string; enabled: boolean }>
  photoLayout: PhotoLayout
}

export type AcotacionProgress = {
  running?: boolean
  done?: boolean
  current?: number
  total?: number
  piece?: string
  marca?: string
  photos?: number
  phase?: string
  elapsed?: number
  eta?: number
  percent?: number
  message?: string
  result?: { ok?: boolean; message?: string; folder?: string; count?: number; files?: string[] }
}

export type WeldScan = {
  ok: boolean
  message: string
  kind?: "face" | "dims" | "open" | string
  tank?: string
  drawingPath?: string
  folder?: string
}

export type WeldSpec = {
  flecha: number
  otro: number
  dos_lados: boolean
  typ: boolean
  paso: string
}

export type WeldCordon = {
  id: string
  titulo: string
  largo?: string
  clasificacion: "hermetico" | "accesorio" | string
  spec: WeldSpec
  texto: string
  cuerpos?: string[]
  editado?: boolean
}

export type WeldNomList = {
  ok: boolean
  message: string
  assembly?: string
  cordones?: WeldCordon[]
  presets?: string[]
  sizes?: string[]
  pitches?: string[]
  unit?: string
  id?: string
}

export type AcotacionClassify = {
  ok: boolean
  message: string
  tipo?: "BOARD" | "TANQUE"
  label?: string
  unit?: string
  dossier?: string
  picks?: string[]
  views?: string[]
}

type ToolbarApi = {
  snapshot: () => Promise<Snapshot>
  parts: () => Promise<Snapshot>
  job_save: (payload: string) => Promise<{ ok: boolean; job?: string; message: string }>
  pick_folder: () => Promise<string>
  export_dxf: (payload: string) => Promise<ExportResult>
  sheet_rules_load: () => Promise<SheetRuleCatalog>
  sheet_rules_save: (payload: string) => Promise<SheetRuleSave>
  sheet_rules: (payload?: string) => Promise<SheetRulesResult>
  multibody?: () => Promise<MultibodyResult>
  awis_run?: (payload: string) => Promise<AwisResult>
  scan_shapes: () => Promise<ShapeScan>
  start_pick: (mode: string) => Promise<{ ok: boolean; message: string }>
  update_pick: (payload: string) => Promise<{ ok: boolean; message: string }>
  pick_status: () => Promise<{ running?: boolean; count?: number; names?: string[] }>
  stop_pick: () => Promise<ShapeScan>
  paint_shapes: (payload: string) => Promise<{ ok: boolean; message: string; painted?: number }>
  colorimetria_load: () => Promise<ColorimetriaCatalog>
  colorimetria_save: (payload: string) => Promise<{ ok: boolean; message: string; catalog?: ColorimetriaCatalog }>
  shape_stock: () => Promise<{ stock: StockRow[] }>
  remember_shapes: (payload: string) => Promise<{ ok: boolean; message: string }>
  export_shapes: (payload: string) => Promise<{ ok: boolean; message: string }>
  acotacion_load: () => Promise<AcotacionCatalog>
  acotacion_save: (payload: string) => Promise<{ ok: boolean; message: string }>
  acotacion_classify: (payload: string) => Promise<AcotacionClassify>
  acotacion_run: (payload: string) => Promise<{ ok: boolean; started?: boolean; message: string; folder?: string; count?: number }>
  acotacion_progress: () => Promise<AcotacionProgress>
  acotacion_open: (folder?: string) => Promise<{ ok: boolean; message: string; folder?: string }>
  weld_scan: (payload: string) => Promise<WeldScan>
  weld_run: (payload: string) => Promise<{ ok: boolean; started?: boolean; message: string; folder?: string; count?: number }>
  weld_progress: () => Promise<AcotacionProgress>
  weld_nom_list: (payload: string) => Promise<WeldNomList>
  weld_nom_apply: (payload: string) => Promise<WeldNomList>
  weld_nom_select: (payload: string) => Promise<{ ok: boolean; message: string }>
  weld_nom_pick: () => Promise<WeldNomList>
  weld_nom_mira?: () => Promise<WeldNomList>
  weld_nom_armar?: () => Promise<{ ok: boolean; message: string }>
  weld_nom_soltar?: () => Promise<{ ok: boolean; message: string }>
  weld_nom_drop?: (payload: string) => Promise<WeldNomList>
  weld_tool_open?: () => Promise<{ ok: boolean; message: string }>
  roles_action: (payload: string) => Promise<RolesSnapshot>
  blocks_action: (payload: string) => Promise<BlocksSnapshot>
  dossier_consulta?: (payload: string) => Promise<DossierConsulta>
}

export type DossierJob = {
  nombre: string
  dias: number
}

export type DossierConsulta = {
  ok: boolean
  message?: string
  raiz?: string
  nombres?: string[]
  jobs?: DossierJob[]
  producto?: string
  cliente?: string
  job?: string
  dossier?: string
}

export type RolesMember = {
  nombre_ocurrencia?: string
  ruta_archivo?: string
  ruta_ocurrencia?: string
  placa_rol?: boolean
  sugerido?: boolean
}

export type RolesSnapshot = {
  ok: boolean
  message: string
  bags?: Record<string, RolesMember[]>
  colors?: Record<string, string>
  confirmed?: boolean
  assembly?: string
  count?: number
}

declare global {
  interface Window {
    pywebview?: { api: ToolbarApi }
  }
}

export function toolbarApi(): ToolbarApi | null {
  return window.pywebview?.api ?? null
}

export const previewSnapshot: Snapshot = {
  inventorConnected: false,
  inventorVersion: "",
  assemblyName: "assy prueba.iam",
  assemblyPath: "",
  jobName: "assy prueba",
  message: "Vista de la barra. Ábrela con Iniciar AutoDXF.bat para conectar Inventor.",
  parts: [
    {
      name: "ABB-42-BCK-728",
      material: "Genérico",
      canonical: "Genérico",
      thickness: "0.25",
      qty: 1,
      flat: true,
      classification: "Chapa",
      path: "",
      copper: true,
      form: "B",
      copperWhy: "ABB + BCK + solera doblada",
    },
    {
      name: "GENE-FCU-5-102",
      material: "Genérico",
      canonical: "Genérico",
      thickness: "0.25",
      qty: 1,
      flat: true,
      classification: "Busbar",
      path: "",
      copper: true,
      form: "F",
      copperWhy: "GENE + solera",
    },
    {
      name: "HW-FW-SS-M10-A Washer",
      material: "Steel",
      canonical: "Steel",
      thickness: "0.106",
      qty: 8,
      flat: true,
      classification: "Tornillería",
      path: "",
      copper: false,
      form: "",
      copperWhy: "",
    },
    {
      name: "PANEL-LAT-01",
      material: "A 36",
      canonical: "A 36",
      thickness: "0.25",
      qty: 1,
      flat: true,
      classification: "Tanque",
      path: "",
      copper: false,
      form: "",
      copperWhy: "A36",
    },
  ],
  catalog: {
    connected: false,
    source: "VISTA",
    message: "La consulta en vivo aparece al abrir la ventana de Inventor.",
    materials: ["A 36", "A 36 GALV", "SSTL 304", "Aluminio"],
    herinoxConnected: false,
    nestingConnected: false,
  },
}
