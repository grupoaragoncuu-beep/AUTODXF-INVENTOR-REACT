import { useEffect, useRef, useState } from "react"
import { FolderOpenIcon } from "lucide-react"
import { Badge } from "@/components/reui/badge"
import { Button } from "@/components/ui/button"
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress"
import {
  toolbarApi,
  type AcotacionCatalog,
  type AcotacionClassify,
  type AcotacionProgress,
  type RolesSnapshot,
} from "@/bridge"
import { boardCode } from "@/materials"
import { PhotoLayoutTree } from "@/PhotoLayoutTree"
import { defaultPhotoLayout, normalizePhotoLayout } from "@/photo-layout"

const fieldClass = "border-border bg-background h-8 w-full rounded-lg border px-2 text-xs"
const CARAS_MURO = ["TOP", "SEGM1", "SEGM2", "SEGM3", "SEGM4", "BASE"] as const
const COLORES_MURO: Record<string, string> = {
  TOP: "#EAB308",
  SEGM1: "#7C3AED",
  SEGM2: "#2563EB",
  SEGM3: "#06B6D4",
  SEGM4: "#EA580C",
  BASE: "#F97316",
}

function clockLabel(seconds?: number) {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—"
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = total % 60
  if (hours > 0) return `${hours} h ${minutes} min ${rest} s`
  if (minutes > 0) return `${minutes} min ${rest} s`
  return `${rest} s`
}
const emptyCatalog = (): AcotacionCatalog => ({
  paths: {
    corporateRoot: "",
    cotasProject: "",
    machote: "",
    localJpg: "",
    dossierFolder: "DOSSIER FILES",
    jpgsFolder: "JPGS",
  },
  classify: [],
  defaultTipo: "TANQUE",
  flows: {
    BOARD: {
      label: "Gabinete",
      dossierProduct: "ENCLOSURES NEMA 1",
      unit: "mm",
      picks: [],
      views: ["FRONT", "BACK", "TOP", "BOTTOM", "RIGHT", "LEFT"],
      omit: ["Almacén"],
      despliegue: true,
      copperPrefixes: ["ABB", "GENE", "RLG"],
    },
    TANQUE: {
      label: "Tank",
      dossierProduct: "TANKS",
      unit: "in",
      picks: ["TOP COVER", "SEGM1", "SEGM2", "SEGM3", "SEGM4", "BASE"],
      views: [],
      omit: ["Almacén"],
      despliegue: false,
      copperPrefixes: [],
      corte: {
        classes: [
          "Maquinados Tank",
          "Maquinados Accesorios Sueltos",
          "Corte",
          "Maquinado",
          "Accesorios Sueltos",
        ],
        holeAnchor: "edge",
        measureWalls: false,
      },
      doblado: { classes: ["Doblado"], holeAnchor: "edge", measureWalls: true },
      armado: { classes: ["Assy Tanks", "Assy Loose Accesories"] },
      referencia: {
        faces: {
          TOP: ["top cover", "tapa superior", "tank lid", "tank-lid", "tapa"],
          SEGM1: ["segmento 1", "segmento #1", "segm1", "s1"],
          SEGM2: ["segmento 2", "segmento #2", "segm2", "s2"],
          SEGM3: ["segmento 3", "segmento #3", "segm3", "s3"],
          SEGM4: ["segmento 4", "segmento #4", "segm4", "s4"],
          BASE: ["base de soleras", "cuadro base", "base plate", "tank base", "tank-base"],
        },
      },
    },
  },
  measures: [],
  photoLayout: defaultPhotoLayout(),
})

export function AcotacionJpgPanel({
  disabled,
  assemblyName,
  assemblyPath,
  jobName,
  onLog,
  onBusy,
  onChooseFolder,
}: {
  disabled: boolean
  assemblyName: string
  assemblyPath: string
  jobName: string
  onLog: (message: string) => void
  onBusy: (busy: boolean) => void
  onChooseFolder: () => Promise<string>
}) {
  const [catalog, setCatalog] = useState<AcotacionCatalog>(emptyCatalog)
  const [hit, setHit] = useState<AcotacionClassify | null>(null)
  const [dossier, setDossier] = useState("")
  const [lastFolder, setLastFolder] = useState("")
  const [flowKey, setFlowKey] = useState<"BOARD" | "TANQUE">("BOARD")
  const [layoutReady, setLayoutReady] = useState(false)
  const [progress, setProgress] = useState<AcotacionProgress | null>(null)
  const [summary, setSummary] = useState("")
  const [exporting, setExporting] = useState(false)
  const [roles, setRoles] = useState<RolesSnapshot | null>(null)
  const [activeCara, setActiveCara] = useState("SEGM1")
  const [pickingRoles, setPickingRoles] = useState(false)
  const [pickedRoleCount, setPickedRoleCount] = useState(0)
  const [smartPick, setSmartPick] = useState(true)
  const catalogReady = useRef(false)
  const pickingRolesRef = useRef(false)
  const catalogRef = useRef(catalog)
  catalogRef.current = catalog

  useEffect(() => {
    const load = () => {
      const api = toolbarApi()
      if (!api) return
      void api.acotacion_load().then((next) => {
        if (!next || !next.paths) return
        const blank = emptyCatalog()
        setCatalog({
          ...blank,
          ...next,
          paths: { ...blank.paths, ...next.paths },
          flows: { ...blank.flows, ...next.flows },
          photoLayout: normalizePhotoLayout(next.photoLayout),
        })
        catalogReady.current = true
        setLayoutReady(true)
      })
    }
    window.addEventListener("pywebviewready", load)
    load()
    return () => window.removeEventListener("pywebviewready", load)
  }, [])

  useEffect(() => {
    const api = toolbarApi()
    if (!api?.roles_action || !assemblyPath) return
    void api.roles_action(JSON.stringify({ action: "restore" })).then((next) => {
      if (next?.bags) setRoles(next)
    })
  }, [assemblyPath])

  useEffect(() => {
    if (!pickingRoles) return
    const timer = window.setInterval(() => {
      const api = toolbarApi()
      if (!api || !pickingRolesRef.current) return
      void api.pick_status().then((status) => {
        setPickedRoleCount(status.count || 0)
        if (pickingRolesRef.current && status.running === false) void endRolePick()
      })
    }, 700)
    return () => window.clearInterval(timer)
  }, [pickingRoles])

  useEffect(() => {
    if (!pickingRoles) return
    const api = toolbarApi()
    const color = roles?.colors?.[activeCara] || COLORES_MURO[activeCara] || "#7C3AED"
    void api?.update_pick(JSON.stringify({ className: activeCara, color }))
  }, [activeCara, pickingRoles, roles?.colors])

  useEffect(() => {
    if (!catalogReady.current) return
    const api = toolbarApi()
    if (!api) return
    const timer = window.setTimeout(() => {
      void api.acotacion_save(JSON.stringify(catalogRef.current))
    }, 400)
    return () => window.clearTimeout(timer)
  }, [catalog.photoLayout])

  const flow = catalog.flows[flowKey]

  function patchPaths(key: keyof AcotacionCatalog["paths"], value: string) {
    setCatalog((current) => ({ ...current, paths: { ...current.paths, [key]: value } }))
  }

  function patchFlow(patch: Partial<AcotacionCatalog["flows"]["BOARD"]>) {
    setCatalog((current) => ({
      ...current,
      flows: { ...current.flows, [flowKey]: { ...current.flows[flowKey], ...patch } },
    }))
  }

  async function choose(key: keyof AcotacionCatalog["paths"]) {
    const folder = await onChooseFolder()
    if (folder) patchPaths(key, folder)
  }

  async function save() {
    const api = toolbarApi()
    if (!api) {
      onLog("Inicia la barra con Iniciar AutoDXF.bat.")
      return
    }
    const result = await api.acotacion_save(JSON.stringify(catalog))
    onLog(result.message)
  }

  async function classify() {
    const api = toolbarApi()
    if (!api) {
      onLog("Inicia la barra con Iniciar AutoDXF.bat.")
      return
    }
    const result = await api.acotacion_classify(
      JSON.stringify({ name: assemblyName, path: assemblyPath, config: catalog, job: jobName }),
    )
    setHit(result)
    setDossier(result.dossier || "")
    if (result.tipo === "BOARD" || result.tipo === "TANQUE") setFlowKey(result.tipo)
    onLog(result.message)
  }

  async function run(mode: "BOARD" | "TANQUE", limit: number, phase?: "CORTE" | "DOBLADO" | "ARMADO" | "ALL") {
    const api = toolbarApi()
    if (!api) {
      onLog("Inicia la barra con Iniciar AutoDXF.bat.")
      return "Inicia la barra con Iniciar AutoDXF.bat."
    }
    if (!jobName.trim()) {
      onLog("Elige el job del dossier antes de generar los JPG.")
      return "Elige el job del dossier antes de generar los JPG."
    }
    setProgress({
      running: true,
      done: false,
      current: 0,
      total: 0,
      piece: phase ? `Iniciando ${phase}…` : "Iniciando…",
      percent: 0,
      eta: 0,
      elapsed: 0,
      photos: 0,
      marca: "",
    })
    try {
      await save()
      const board = boardCode(localStorage.getItem("autodxf-board") || "B1")
      const started = await api.acotacion_run(
        JSON.stringify({ mode, limit, config: catalog, board, job: jobName, phase }),
      )
      if (!started.ok && !started.started) {
        const msg = started.message || "No arrancó la exportación."
        onLog(msg)
        setProgress((current) => ({
          ...(current || {}),
          running: false,
          done: true,
          piece: "No arrancó",
          message: msg,
          percent: 100,
        }))
        return msg
      }
      onLog(started.message)
      for (;;) {
        const next = await api.acotacion_progress()
        setProgress(next)
        if (next.running === false && (next.done || next.result)) {
          const result = next.result
          if (result?.folder) setLastFolder(result.folder)
          const msg = String(result?.message || next.message || "")
          if (msg) onLog(msg)
          return msg
        }
        await new Promise((resolve) => window.setTimeout(resolve, 280))
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : "No se pudo ejecutar la acotación."
      onLog(msg)
      setProgress((current) => ({
        ...(current || {}),
        running: false,
        done: true,
        piece: "Error",
        message: msg,
        percent: 100,
      }))
      return msg
    }
  }

  async function runBoard() {
    setExporting(true)
    onBusy(true)
    setSummary("")
    try {
      await classify()
      const msg = await run("BOARD", 0)
      setSummary(msg || "Gabinete terminado.")
    } finally {
      setExporting(false)
      onBusy(false)
    }
  }

  function applyRoles(next: RolesSnapshot) {
    setRoles(next)
    if (next.message) onLog(next.message)
  }

  async function rolesAction(action: string, extra?: Record<string, unknown>) {
    const api = toolbarApi()
    if (!api?.roles_action) {
      onLog("Inicia la barra con Iniciar AutoDXF.bat.")
      return null
    }
    const next = await api.roles_action(JSON.stringify({ action, ...extra }))
    applyRoles(next)
    return next
  }

  async function proposeRoles() {
    onBusy(true)
    try {
      await rolesAction("propose")
    } finally {
      onBusy(false)
    }
  }

  async function confirmRoles() {
    onBusy(true)
    try {
      if (pickingRolesRef.current) await endRolePick()
      else if (!Number(roles?.count || 0)) await rolesAction("ingest", { cara: activeCara })
      await rolesAction("confirm")
    } finally {
      onBusy(false)
    }
  }

  async function startRolePick() {
    const api = toolbarApi()
    if (!api) return
    const color = roles?.colors?.[activeCara] || COLORES_MURO[activeCara] || "#7C3AED"
    const started = await api.start_pick(
      JSON.stringify({ mode: "roles", className: activeCara, color, smart: smartPick }),
    )
    onLog(started.message || "Selector de muros activo.")
    if (started.ok !== false) {
      pickingRolesRef.current = true
      setPickingRoles(true)
    }
  }

  async function endRolePick() {
    const api = toolbarApi()
    if (!api || !pickingRolesRef.current) return
    pickingRolesRef.current = false
    setPickingRoles(false)
    const stopped = await api.stop_pick()
    const rows = (stopped.rows || [])
      .filter((row) => String(row.path || "").trim())
      .map((row) => ({
        path: String(row.path).trim(),
        cara: String(row.cara || activeCara).toUpperCase(),
        removed: Boolean(row.removed),
      }))
    // Inventor ya pintó la placa con lo montado en el clic; aquí solo se guarda lo pintado.
    if (rows.length) {
      await rolesAction("pick", { rows, smart: false })
      return
    }
    await rolesAction("ingest", { cara: activeCara, smart: false })
  }

  async function runTank() {
    setExporting(true)
    onBusy(true)
    setSummary("")
    try {
      if (pickingRolesRef.current) await endRolePick()
      let next = roles
      if (!Number(next?.count || 0)) {
        next = await rolesAction("ingest", { cara: activeCara })
      }
      const count = Number(next?.count || 0)
      if (!count) {
        setSummary(
          "No hay muros en la lista. Inicia el selector, clica cada cara y pulsa Terminar selector. Luego Confirmar y acotar.",
        )
        return
      }
      if (!next?.confirmed) await rolesAction("confirm")
      await classify()
      onLog("Tank · CORTE + DOBLADO + REFERENCIA")
      const msg = await run("TANQUE", 0, "ALL")
      setSummary(msg || "Tank terminado.")
    } finally {
      setExporting(false)
      onBusy(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto">
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={disabled || exporting} onClick={() => void runTank()}>
            Confirmar y acotar
          </Button>
          <Button variant="outline" disabled={disabled || exporting} onClick={() => void runBoard()}>
            Ejecutar gabinete
          </Button>
          <Button
            variant="outline"
            disabled={disabled}
            onClick={() => void toolbarApi()?.acotacion_open(lastFolder || catalog.paths.localJpg)}
          >
            <FolderOpenIcon />
            Abrir JPG
          </Button>
          {hit ? (
            <Badge variant={hit.tipo === "BOARD" ? "success-light" : "warning-light"} size="sm">
              {hit.label} · {hit.unit}
            </Badge>
          ) : (
            <p className="text-muted-foreground text-xs">{assemblyName || "Abre un ensamble en Inventor."}</p>
          )}
        </div>
        <p className="text-muted-foreground text-xs">
          Elige un color de cara, pulsa <strong className="text-foreground font-medium">Iniciar selector</strong> y
          haz clic en las piezas del modelo. Luego confirma y acota.
        </p>
      </section>
      <section className="space-y-2 rounded-lg border p-3">
        <p className="text-xs font-medium">Color de cara (clic en el modelo)</p>
        <div className="flex flex-wrap gap-2">
          {CARAS_MURO.map((cara) => {
            const color = roles?.colors?.[cara] || COLORES_MURO[cara]
            const n = (roles?.bags?.[cara] || []).length
            return (
              <button
                key={cara}
                type="button"
                className={`flex items-center gap-2 rounded-md border px-2 py-1 text-xs ${activeCara === cara ? "border-foreground" : "border-border"}`}
                onClick={() => {
                  setActiveCara(cara)
                  if (!pickingRolesRef.current) return
                  void toolbarApi()?.update_pick(JSON.stringify({ className: cara, color }))
                }}
              >
                <span className="size-3 shrink-0 rounded-sm border border-black/20" style={{ backgroundColor: color }} />
                {cara}
                {n ? ` · ${n}` : ""}
              </button>
            )
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {pickingRoles ? (
            <Button disabled={disabled} onClick={() => void endRolePick()}>
              Terminar selector
            </Button>
          ) : (
            <Button disabled={disabled || exporting} onClick={() => void startRolePick()}>
              Iniciar selector · {activeCara}
            </Button>
          )}
          <Button variant="outline" disabled={disabled || exporting} onClick={() => void proposeRoles()}>
            Proponer muros
          </Button>
          <Button variant="outline" disabled={disabled || exporting || !roles?.count} onClick={() => void confirmRoles()}>
            Confirmar muros
          </Button>
          <Button variant="outline" disabled={disabled || exporting} onClick={() => void rolesAction("clear", { cara: activeCara })}>
            Vaciar {activeCara}
          </Button>
          {pickingRoles ? <p className="text-xs">{pickedRoleCount} clic(s) en {activeCara}</p> : null}
        </div>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={smartPick}
            onChange={(event) => {
              const smart = event.target.checked
              setSmartPick(smart)
              if (!pickingRolesRef.current) return
              const color = roles?.colors?.[activeCara] || COLORES_MURO[activeCara] || "#7C3AED"
              void toolbarApi()?.update_pick(JSON.stringify({ className: activeCara, color, smart }))
            }}
          />
          Selección inteligente: clic en una placa suma la placa y todo lo montado en ella
        </label>
        <p className="text-muted-foreground text-xs">
          {pickingRoles
            ? `Selector activo: cada clic pinta de ${activeCara}; otro clic sobre la misma pieza la quita. Cambia de color arriba sin Terminar. Al Terminar se suma lo montado en las placas.`
            : "Elige SEGM1–4 / TOP / BASE e Iniciar. Lo que eliges a mano se guarda por ensamble y Proponer muros no lo cambia."}
        </p>
        <ul className="max-h-40 overflow-auto text-xs">
          {(roles?.bags?.[activeCara] || []).length === 0 ? (
            <li className="text-muted-foreground">Nada en {activeCara}. Inicia el selector y clica piezas.</li>
          ) : (
            (roles?.bags?.[activeCara] || []).map((item) => (
              <li
                key={item.ruta_ocurrencia || item.ruta_archivo || item.nombre_ocurrencia}
                className="flex items-center justify-between gap-2 py-0.5"
              >
                <span className="truncate" title={item.ruta_ocurrencia || item.ruta_archivo}>
                  {item.placa_rol ? "Placa · " : ""}
                  {item.nombre_ocurrencia}
                  {item.sugerido ? " · propuesta" : ""}
                </span>
                {item.placa_rol ? null : (
                  <button
                    type="button"
                    className="text-muted-foreground shrink-0 underline"
                    onClick={() =>
                      void rolesAction("remove", {
                        ocurrencia: item.ruta_ocurrencia,
                        ruta: item.ruta_archivo,
                        cara: activeCara,
                      })
                    }
                  >
                    Quitar
                  </button>
                )}
              </li>
            ))
          )}
        </ul>
      </section>

      {progress ? (
        <section className="w-full space-y-2 rounded-lg border p-3">
          <Progress value={progress.done ? 100 : Number(progress.percent || 0)}>
            <ProgressLabel>Exportar JPG</ProgressLabel>
            <ProgressValue />
          </Progress>
          <div className="text-muted-foreground grid gap-0.5 text-xs">
            <p className="text-foreground truncate font-medium">
              {progress.piece || "Preparando…"}
              {progress.marca ? ` · ${progress.marca}` : ""}
            </p>
            <p>
              {progress.total
                ? `${progress.current || 0} de ${progress.total} piezas`
                : "Calculando piezas…"}
              {progress.photos ? ` · ${progress.photos} fotos` : ""}
            </p>
            <p>
              Transcurrido {clockLabel(progress.elapsed)}
              {progress.done
                ? progress.result?.ok === false || /no hay|no arranc/i.test(progress.message || "")
                  ? " · terminó sin fotos"
                  : " · listo"
                : ` · resta aprox. ${clockLabel(progress.current ? progress.eta : undefined)}`}
            </p>
            {progress.done && progress.message ? (
              <p className="text-foreground whitespace-pre-wrap break-words">{progress.message}</p>
            ) : null}
          </div>
        </section>
      ) : null}
      {summary ? (
        <section className="rounded-lg border p-3">
          <p className="text-xs font-medium">Resultado</p>
          <p className="text-foreground mt-1 whitespace-pre-wrap text-xs break-words">{summary}</p>
        </section>
      ) : null}

      <p className="text-xs break-all">
        Fotos locales: {lastFolder || catalog.paths.localJpg || "AUTODXF INVENTOR REACT\\JPG"}
      </p>
      {dossier ? <p className="text-muted-foreground text-xs break-all">Dossier: {dossier}</p> : null}

      <PhotoLayoutTree
        layout={catalog.photoLayout || defaultPhotoLayout()}
        disabled={disabled || !layoutReady || exporting}
        onChange={(photoLayout) => setCatalog((current) => ({ ...current, photoLayout }))}
      />

      <section className="grid gap-2 rounded-lg border p-3">
        <p className="text-sm font-medium">Rutas</p>
        <PathRow
          label="Raíz corporativa"
          value={catalog.paths.corporateRoot}
          disabled={disabled}
          onChange={(value) => patchPaths("corporateRoot", value)}
          onPick={() => void choose("corporateRoot")}
        />
        <PathRow
          label="Proyecto Cotas Dossier"
          value={catalog.paths.cotasProject}
          disabled={disabled}
          onChange={(value) => patchPaths("cotasProject", value)}
          onPick={() => void choose("cotasProject")}
        />
        <PathRow
          label="JPG locales (opcional)"
          value={catalog.paths.localJpg}
          disabled={disabled}
          onChange={(value) => patchPaths("localJpg", value)}
          onPick={() => void choose("localJpg")}
        />
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs">
            Carpeta dossier
            <input
              className={`${fieldClass} mt-1`}
              value={catalog.paths.dossierFolder}
              disabled={disabled}
              onChange={(event) => patchPaths("dossierFolder", event.target.value)}
            />
          </label>
          <label className="text-xs">
            Carpeta fotos
            <input
              className={`${fieldClass} mt-1`}
              value={catalog.paths.jpgsFolder}
              disabled={disabled}
              onChange={(event) => patchPaths("jpgsFolder", event.target.value)}
            />
          </label>
        </div>
      </section>

      <section className="grid gap-2 rounded-lg border p-3">
        <p className="text-sm font-medium">Cómo se reconoce el producto</p>
        <p className="text-muted-foreground text-xs">
          Primera regla que coincida gana. Gabinete = BOARD. Tank = TANQUE. Sin tocar código.
        </p>
        <div className="overflow-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left">
                <th className="p-1">On</th>
                <th className="p-1">Busca en</th>
                <th className="p-1">Patrón</th>
                <th className="p-1">Resultado</th>
                <th className="p-1" />
              </tr>
            </thead>
            <tbody>
              {catalog.classify.map((rule, index) => (
                <tr key={rule.id}>
                  <td className="p-1">
                    <input
                      type="checkbox"
                      checked={rule.enabled !== false}
                      disabled={disabled}
                      onChange={(event) => {
                        const classify = catalog.classify.map((item, i) =>
                          i === index ? { ...item, enabled: event.target.checked } : item,
                        )
                        setCatalog({ ...catalog, classify })
                      }}
                    />
                  </td>
                  <td className="p-1">
                    <select
                      className={fieldClass}
                      value={rule.field}
                      disabled={disabled}
                      onChange={(event) => {
                        const classify = catalog.classify.map((item, i) =>
                          i === index ? { ...item, field: event.target.value as "nombre" | "ruta" } : item,
                        )
                        setCatalog({ ...catalog, classify })
                      }}
                    >
                      <option value="nombre">Nombre</option>
                      <option value="ruta">Ruta</option>
                    </select>
                  </td>
                  <td className="p-1">
                    <input
                      className={fieldClass}
                      value={rule.pattern}
                      disabled={disabled}
                      onChange={(event) => {
                        const classify = catalog.classify.map((item, i) =>
                          i === index ? { ...item, pattern: event.target.value } : item,
                        )
                        setCatalog({ ...catalog, classify })
                      }}
                    />
                  </td>
                  <td className="p-1">
                    <select
                      className={fieldClass}
                      value={rule.tipo}
                      disabled={disabled}
                      onChange={(event) => {
                        const tipo = event.target.value as "BOARD" | "TANQUE"
                        const classify = catalog.classify.map((item, i) =>
                          i === index ? { ...item, tipo, familia: tipo } : item,
                        )
                        setCatalog({ ...catalog, classify })
                      }}
                    >
                      <option value="BOARD">Gabinete</option>
                      <option value="TANQUE">Tank</option>
                    </select>
                  </td>
                  <td className="p-1">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={disabled}
                      onClick={() =>
                        setCatalog({ ...catalog, classify: catalog.classify.filter((_, i) => i !== index) })
                      }
                    >
                      Quitar
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={disabled}
          onClick={() =>
            setCatalog({
              ...catalog,
              classify: [
                ...catalog.classify,
                {
                  id: `regla-${Date.now()}`,
                  field: "nombre",
                  pattern: "",
                  tipo: "BOARD",
                  familia: "BOARD",
                  enabled: true,
                },
              ],
            })
          }
        >
          Agregar regla
        </Button>
      </section>

      <section className="grid gap-2 rounded-lg border p-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium">Cómo se obtienen las cotas</p>
          <select
            className={`${fieldClass} max-w-40`}
            value={flowKey}
            disabled={disabled}
            onChange={(event) => setFlowKey(event.target.value as "BOARD" | "TANQUE")}
          >
            <option value="BOARD">Gabinete</option>
            <option value="TANQUE">Tank</option>
          </select>
        </div>
        <label className="text-xs">
          Producto en el dossier
          <input
            className={`${fieldClass} mt-1`}
            value={flow.dossierProduct}
            disabled={disabled}
            onChange={(event) => patchFlow({ dossierProduct: event.target.value })}
          />
        </label>
        <label className="text-xs">
          Selecciones en el modelo (vacío = no pide caras; es el caso gabinete)
          <input
            className={`${fieldClass} mt-1`}
            value={flow.picks.join(", ")}
            disabled={disabled}
            onChange={(event) =>
              patchFlow({
                picks: event.target.value
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean),
              })
            }
          />
        </label>
        <label className="text-xs">
          Vistas de kit
          <input
            className={`${fieldClass} mt-1`}
            value={flow.views.join(", ")}
            disabled={disabled}
            onChange={(event) =>
              patchFlow({
                views: event.target.value
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean),
              })
            }
          />
        </label>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={flow.despliegue}
            disabled={disabled}
            onChange={(event) => patchFlow({ despliegue: event.target.checked })}
          />
          DESPLIEGUE / flat
        </label>
        <p className="text-muted-foreground text-xs">
          Gabinete: _F en flat, coincidencias al centro (busbar). Tank Corte: solo Maquinados Tank / Maquinados Accesorios
          Sueltos, orilla de barreno/slot, sin paredes de segmento.           Tank Doblado: la lámina sola, vista alámbrica y STEP, sin las piezas que van montadas
          encima. Cobre doblado: además _B e _ISO.
        </p>
        <div className="flex flex-wrap gap-3">
          {catalog.measures.map((item, index) => (
            <label key={item.id} className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={item.enabled}
                disabled={disabled}
                onChange={(event) => {
                  const measures = catalog.measures.map((row, i) =>
                    i === index ? { ...row, enabled: event.target.checked } : row,
                  )
                  setCatalog({ ...catalog, measures })
                }}
              />
              {item.label}
            </label>
          ))}
        </div>
      </section>
    </div>
  )
}

function PathRow({
  label,
  value,
  disabled,
  onChange,
  onPick,
}: {
  label: string
  value: string
  disabled: boolean
  onChange: (value: string) => void
  onPick: () => void
}) {
  return (
    <label className="text-xs">
      {label}
      <span className="mt-1 flex gap-2">
        <input className={fieldClass} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
        <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={onPick}>
          <FolderOpenIcon />
        </Button>
      </span>
    </label>
  )
}
