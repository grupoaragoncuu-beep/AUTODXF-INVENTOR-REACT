import { useEffect, useMemo, useRef, useState } from "react"
import { FolderOpenIcon } from "lucide-react"
import { Badge } from "@/components/reui/badge"
import { Frame, FramePanel } from "@/components/reui/frame"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { toolbarApi, type ColorimetriaClass, type ColorimetriaCatalog, type ShapeRow, type StockRow } from "@/bridge"

const FAMILIES = ["SOLERA", "PTR", "TUBO", "VARILLA", "ANGULO", "CANAL", "VIGA"]
const PROCESSES = ["", "CORTE", "CORTE/MAQ", 'CORTE/MAQ, CORTAR EN 3"X3"']
const fieldClass = "border-border bg-background h-8 w-full rounded-lg border px-2 text-xs"

function isAssyClass(name: string) {
  return name.trim().toLowerCase().startsWith("assy")
}

const DEFAULT_CLASSES: ColorimetriaClass[] = [
  { id: "almacen", name: "Almacén", color: "#A3A3A3" },
  { id: "corte", name: "Corte", color: "#2563EB" },
  { id: "doblado", name: "Doblado", color: "#F97316" },
  { id: "maq_tank", name: "Maquinados Tank", color: "#7C3AED" },
  { id: "maq_accesorios", name: "Maquinados Accesorios Sueltos", color: "#059669" },
  { id: "accesorios", name: "Accesorios Sueltos", color: "#0891B2" },
  { id: "assy_tanks", name: "Assy Tanks", color: "#0F766E" },
  { id: "assy_loose", name: "Assy Loose Accesories", color: "#A16207" },
]

const SOURCE: Record<string, string> = {
  morfologia: "Morfología",
  aprendido: "Aprendido",
  ruta: "Esta pieza",
  nombre: "Estándar",
  iprop: "Clasificación",
}

export function ShapesWorkspace({
  mode,
  disabled,
  exportRoot,
  jobName,
  onLog,
  onBusy,
  onChooseFolder,
}: {
  mode: "lengths" | "accessories"
  disabled: boolean
  exportRoot: string
  jobName: string
  onLog: (message: string) => void
  onBusy: (busy: boolean) => void
  onChooseFolder: () => void
}) {
  const [rows, setRows] = useState<ShapeRow[]>([])
  const [stock, setStock] = useState<StockRow[]>([])
  const [query, setQuery] = useState("")
  const [picking, setPicking] = useState(false)
  const [pickedCount, setPickedCount] = useState(0)
  const [colorOn, setColorOn] = useState(true)
  const [classes, setClasses] = useState<ColorimetriaClass[]>(DEFAULT_CLASSES)
  const [activeClass, setActiveClass] = useState(DEFAULT_CLASSES[0].id)
  const painted = useRef<string[]>([])
  const paintQueue = useRef(Promise.resolve())
  const pickingRef = useRef(false)
  const closingRef = useRef(false)
  const active = classes.find((item) => item.id === activeClass) || classes[0]

  const lengths = rows.filter((row) => row.included)
  const accessories = rows.filter((row) => row.accessory)
  const visible =
    mode === "lengths"
      ? rows.filter((row) => row.included || row.family || row.suggestedFamily)
      : rows.filter((row) => row.accessory || row.accessoryWhy)
  const pool = rows.filter((row) => {
    if (mode === "lengths") return !row.included
    return !row.accessory
  })
  const matches = useMemo(() => {
    const text = query.trim().toLowerCase()
    return pool.filter((row) => !text || row.name.toLowerCase().includes(text)).slice(0, 12)
  }, [pool, query])

  function patch(path: string, next: Partial<ShapeRow>) {
    setRows((current) => current.map((row) => (row.path === path ? { ...row, ...next } : row)))
    const marked = mode === "lengths" ? next.included : next.accessory
    if (colorOn && marked !== undefined) {
      const cls = classes.find((item) => item.name === next.classification) || active
      void colorPaths(marked ? [path] : [], marked ? [] : [path], cls)
    } else if (mode === "accessories" && next.classification && colorOn) {
      const cls = classes.find((item) => item.name === next.classification) || active
      void colorPaths([path], [], cls)
    }
  }

  function colorPaths(mark: string[], clear: string[], cls?: ColorimetriaClass) {
    const api = toolbarApi()
    if (!api || (mark.length === 0 && clear.length === 0)) return Promise.resolve()
    painted.current = [...new Set([...painted.current.filter((path) => !clear.includes(path)), ...mark])]
    const chosen = cls || active
    const job = paintQueue.current.then(async () => {
      const result = await api.paint_shapes(
        JSON.stringify({
          paths: mark,
          clear,
          role: mode,
          className: chosen?.name || "",
          color: chosen?.color || "",
        }),
      )
      if (!result.ok) onLog(result.message)
    })
    paintQueue.current = job.catch(() => undefined)
    return job
  }

  async function beginPick() {
    const api = toolbarApi()
    if (!api) {
      onLog("Inicia la barra con Iniciar AutoDXF.bat.")
      return
    }
    const result = await api.start_pick(
      JSON.stringify({
        mode,
        className: active?.name || "",
        color: active?.color || "",
      }),
    )
    if (!result.ok) {
      onLog(result.message)
      return
    }
    pickingRef.current = true
    setPicking(true)
    setPickedCount(0)
    onLog(result.message)
  }

  async function endPick() {
    if (closingRef.current) return
    closingRef.current = true
    const api = toolbarApi()
    if (!api) {
      closingRef.current = false
      return
    }
    onBusy(true)
    try {
      const result = await api.stop_pick()
      pickingRef.current = false
      setPicking(false)
      if (result.stock) setStock(result.stock)
      const incoming = result.rows ?? []
      if (incoming.length > 0) {
        setRows((current) => {
          const byPath = new Map(current.map((row) => [row.path, row]))
          for (const row of incoming) {
            const previous = byPath.get(row.path)
            byPath.set(row.path, previous ? { ...previous, ...row } : row)
          }
          return [...byPath.values()]
        })
        const marked = incoming.map((row) => row.path)
        if (mode === "lengths") {
          if (colorOn) await colorPaths(marked, [])
          else await colorPaths([], marked)
        }
      }
      onLog(result.message || "Selección terminada.")
    } catch (error) {
      onLog(error instanceof Error ? error.message : "No se pudo cerrar la selección.")
    } finally {
      onBusy(false)
      closingRef.current = false
    }
  }

  useEffect(() => {
    if (!picking) return
    const timer = window.setInterval(() => {
      const api = toolbarApi()
      if (!api || closingRef.current) return
      void api.pick_status().then((status) => {
        setPickedCount(status.count || 0)
        if (pickingRef.current && status.running === false) void endPick()
      })
    }, 700)
    return () => window.clearInterval(timer)
  }, [picking])

  useEffect(() => {
    return () => {
      if (!pickingRef.current) return
      pickingRef.current = false
      void toolbarApi()?.stop_pick()
    }
  }, [])

  useEffect(() => {
    if (mode !== "accessories") return
    const api = toolbarApi()
    if (!api?.colorimetria_load) return
    void api.colorimetria_load().then((catalog: ColorimetriaCatalog) => {
      const next = catalog?.classes?.length ? catalog.classes : DEFAULT_CLASSES
      setClasses(next)
      setActiveClass((current) => (next.some((item) => item.id === current) ? current : next[0].id))
    })
  }, [mode])

  async function persistClasses(next: ColorimetriaClass[]) {
    setClasses(next)
    if (!next.some((item) => item.id === activeClass)) setActiveClass(next[0]?.id || "")
    const api = toolbarApi()
    if (!api?.colorimetria_save) return
    const result = await api.colorimetria_save(JSON.stringify({ classes: next }))
    if (result.catalog?.classes) setClasses(result.catalog.classes)
    if (result.ok === false && result.message) onLog(result.message)
  }

  async function remember() {
    const api = toolbarApi()
    if (!api) return
    const result = await api.remember_shapes(JSON.stringify({ rows }))
    onLog(result.message)
  }

  async function exportLists() {
    const api = toolbarApi()
    if (!api) return
    if (!exportRoot) {
      onLog("Elige la carpeta destino.")
      return
    }
    if (!jobName.trim()) {
      onLog("Elige el job del dossier antes de exportar.")
      return
    }
    onBusy(true)
    try {
      const result = await api.export_shapes(JSON.stringify({ folder: exportRoot, rows, job: jobName }))
      onLog(result.message)
    } catch (error) {
      onLog(error instanceof Error ? error.message : "No se pudo exportar.")
    } finally {
      onBusy(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <section className="flex flex-wrap items-center gap-2">
        <Button variant="outline" disabled={disabled} onClick={onChooseFolder}>
          <FolderOpenIcon />
          Carpeta
        </Button>
        {picking ? (
          <Button disabled={disabled} onClick={() => void endPick()}>
            Terminar
          </Button>
        ) : (
          <Button disabled={disabled} onClick={() => void beginPick()}>
            Iniciar
          </Button>
        )}
        {picking ? (
          <p className="text-xs">
            {pickedCount} en el modelo
          </p>
        ) : null}
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            className="accent-foreground size-3.5"
            checked={colorOn}
            disabled={disabled}
            onChange={(event) => {
              const next = event.target.checked
              setColorOn(next)
              const marked = rows
                .filter((row) => (mode === "lengths" ? row.included : row.accessory))
                .map((row) => row.path)
              void colorPaths(next ? marked : [], next ? [] : marked)
            }}
          />
          {mode === "lengths" ? "Transparencia 75%" : "Aplicar color"}
        </label>
        <Button variant="outline" disabled={disabled || rows.length === 0} onClick={() => void remember()}>
          Guardar aprendizaje
        </Button>
        <Button variant="outline" disabled={disabled || rows.length === 0} onClick={() => void exportLists()}>
          {mode === "lengths" ? `Exportar ${lengths.length} largos` : `Exportar ${accessories.length} clasificados`}
        </Button>
        <p className="text-muted-foreground min-w-0 flex-1 text-xs">
          {picking
            ? isAssyClass(active?.name || "")
              ? active?.name.toLowerCase().includes("loose")
                ? "Assy Loose: clic en el .iam. El ensamble queda Assy Loose Accesories y cada pieza Accesorios Sueltos."
                : `Assy: clic en un subensamble .iam (o en una pieza del kit). ${active?.name} se escribe en el .iam, no en partes.`
              : "Clic en cada pieza .ipt. Puedes cambiar la clasificación sin Terminar. Esc o Terminar para salir."
            : mode === "lengths"
              ? "Iniciar abre el selector. Las piezas marcadas quedan al 75% de opacidad, sin cambiar el color."
              : "Elige la clasificación y pulsa Iniciar. Assy Tanks y Assy Loose Accesories aplican solo a ensambles .iam."}
        </p>
      </section>
      {mode === "lengths" ? (
        <p className="text-muted-foreground text-xs">
          Lista de largos ya no asigna color: el componente se ve un poco más transparente (opacidad 75%), da igual su clasificación.
        </p>
      ) : (
        <section className="border-border space-y-2 rounded-lg border px-3 py-2">
          <p className="text-xs font-medium">Clasificación a aplicar</p>
          <div className="flex flex-wrap gap-2">
            {classes.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`flex items-center gap-2 rounded-md border px-2 py-1 text-xs ${activeClass === item.id ? "border-foreground" : "border-border"}`}
                onClick={() => {
                  setActiveClass(item.id)
                  if (!pickingRef.current) return
                  const api = toolbarApi()
                  if (!api?.update_pick) return
                  void api.update_pick(JSON.stringify({ className: item.name, color: item.color }))
                }}
              >
                <span className="size-3 shrink-0 rounded-sm border border-black/20" style={{ backgroundColor: item.color }} />
                {item.name}
              </button>
            ))}
          </div>
          <p className="text-muted-foreground text-xs">Nombres y colores editables. Se guardan solos.</p>
          <div className="flex flex-col gap-1">
            {classes.map((item) => (
              <div key={item.id} className="flex flex-wrap items-center gap-2">
                <input
                  type="color"
                  className="size-7 cursor-pointer rounded border bg-transparent"
                  value={item.color}
                  aria-label={`Color de ${item.name}`}
                  onChange={(event) => {
                    void persistClasses(classes.map((row) => (row.id === item.id ? { ...row, color: event.target.value } : row)))
                  }}
                />
                <input
                  className={`${fieldClass} max-w-72`}
                  defaultValue={item.name}
                  key={`${item.id}-${item.name}`}
                  aria-label={`Nombre de ${item.name}`}
                  onBlur={(event) => {
                    const name = event.target.value.trim() || item.name
                    if (name === item.name) return
                    void persistClasses(classes.map((row) => (row.id === item.id ? { ...row, name } : row)))
                  }}
                />
                <Button
                  size="sm"
                  variant="outline"
                  disabled={classes.length <= 1}
                  onClick={() => void persistClasses(classes.filter((row) => row.id !== item.id))}
                >
                  Quitar
                </Button>
              </div>
            ))}
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              const id = `clase_${Date.now().toString(36)}`
              void persistClasses([...classes, { id, name: "Nueva clasificación", color: "#64748B" }])
            }}
          >
            Añadir clasificación
          </Button>
        </section>
      )}

      <Frame spacing="xs" className="min-h-0 flex-1">
        <FramePanel className="h-full overflow-auto p-0!">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">{mode === "lengths" ? "Corte" : "Clase"}</TableHead>
                <TableHead>Pieza</TableHead>
                <TableHead>Morfología</TableHead>
                <TableHead>Sección</TableHead>
                <TableHead>Largo</TableHead>
                <TableHead>Cant.</TableHead>
                {mode === "lengths" ? <TableHead>Proceso</TableHead> : <TableHead>Clasificación</TableHead>}
                {mode === "lengths" ? <TableHead>Herinox</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={mode === "lengths" ? 8 : 7} className="text-muted-foreground text-center">
                    {rows.length === 0 ? "Pulsa Iniciar y selecciona los componentes en el modelo." : "Nada en esta lista. Agrega una pieza abajo."}
                  </TableCell>
                </TableRow>
              ) : (
                visible.map((row) => (
                  <ShapeLine
                    key={row.path || row.name}
                    row={row}
                    mode={mode}
                    stock={stock}
                    classes={classes}
                    disabled={disabled}
                    onChange={(next) => patch(row.path, next)}
                  />
                ))
              )}
            </TableBody>
          </Table>
        </FramePanel>
      </Frame>

      <div className="flex flex-wrap items-center gap-2">
        <input
          className={`${fieldClass} max-w-64`}
          placeholder="Agregar pieza que no detectó"
          value={query}
          disabled={disabled || rows.length === 0}
          onChange={(event) => setQuery(event.target.value)}
        />
        {matches.map((row) => (
          <Button
            key={row.path || row.name}
            size="sm"
            variant="outline"
            disabled={disabled}
            onClick={() => {
              if (mode === "accessories" && isAssyClass(active?.name || "") && row.kind !== "assembly") {
                onLog("Assy Tanks y Assy Loose Accesories solo aplican a ensambles .iam.")
                return
              }
              if (mode === "accessories" && !isAssyClass(active?.name || "") && row.kind === "assembly") {
                onLog("Las clases de pieza no aplican a un .iam. Usa Assy Tanks o Assy Loose Accesories.")
                return
              }
              patch(
                row.path,
                mode === "lengths"
                  ? { included: true, family: row.family || row.suggestedFamily || "SOLERA", process: row.process || "CORTE" }
                  : { accessory: true, accessoryWhy: active?.name || "Marcado por ingeniería", classification: active?.name || "" },
              )
              setQuery("")
            }}
          >
            {row.name}
          </Button>
        ))}
      </div>
    </div>
  )
}

function ShapeLine({
  row,
  mode,
  stock,
  classes,
  disabled,
  onChange,
}: {
  row: ShapeRow
  mode: "lengths" | "accessories"
  stock: StockRow[]
  classes: ColorimetriaClass[]
  disabled: boolean
  onChange: (next: Partial<ShapeRow>) => void
}) {
  const options = stock.filter((item) => item.family === row.family)
  const knownStock = options.some((item) => item.text === row.herinox)
  const checked = mode === "lengths" ? row.included : row.accessory
  const classChoices =
    row.kind === "assembly" ? classes.filter((item) => isAssyClass(item.name)) : classes.filter((item) => !isAssyClass(item.name))
  return (
    <TableRow className={checked ? undefined : "opacity-45"}>
      <TableCell>
        <input
          type="checkbox"
          className="accent-foreground size-3.5"
          checked={checked}
          disabled={disabled}
          aria-label={row.name}
          onChange={(event) => {
            if (mode === "lengths") {
              onChange({
                included: event.target.checked,
                family: event.target.checked ? row.family || row.suggestedFamily || "SOLERA" : row.family,
                process: event.target.checked ? row.process || "CORTE" : row.process,
              })
            } else {
              const name = row.classification || classes[0]?.name || "Accesorios Sueltos"
              onChange({
                accessory: event.target.checked,
                accessoryWhy: name,
                classification: name,
              })
            }
          }}
        />
      </TableCell>
      <TableCell>
        <div className="flex flex-col">
          <span className="text-sm font-medium">{row.name}</span>
          <span className="text-muted-foreground text-xs">{SOURCE[row.source] || row.kind}</span>
        </div>
      </TableCell>
      <TableCell>
        {mode === "lengths" ? (
          <select
            className={fieldClass}
            value={row.family}
            disabled={disabled}
            aria-label={`Morfología de ${row.name}`}
            onChange={(event) => onChange({ family: event.target.value, included: true, process: row.process || "CORTE" })}
          >
            <option value="">Sin familia</option>
            {FAMILIES.map((family) => (
              <option key={family} value={family}>
                {family}
              </option>
            ))}
          </select>
        ) : (
          <Badge variant="outline" size="sm">
            {row.family || row.kind}
          </Badge>
        )}
      </TableCell>
      <TableCell className="text-xs">
        {row.kind === "assembly" ? "Ensamble" : `${row.widthIn} x ${row.thickIn}`}
      </TableCell>
      <TableCell className="text-xs">{row.lengthIn > 0 ? `${row.lengthIn} in` : "—"}</TableCell>
      <TableCell>{row.qty}</TableCell>
      {mode === "lengths" ? (
        <TableCell>
          <select
            className={fieldClass}
            value={row.process}
            disabled={disabled}
            aria-label={`Proceso de ${row.name}`}
            onChange={(event) => onChange({ process: event.target.value })}
          >
            {PROCESSES.map((process) => (
              <option key={process || "none"} value={process}>
                {process || "Sin proceso"}
              </option>
            ))}
          </select>
        </TableCell>
      ) : (
        <TableCell>
          <select
            className={fieldClass}
            value={row.classification || classes[0]?.name || ""}
            disabled={disabled}
            aria-label={`Clasificación de ${row.name}`}
            onChange={(event) =>
              onChange({
                accessory: true,
                classification: event.target.value,
                accessoryWhy: event.target.value,
              })
            }
          >
            {classChoices.map((item) => (
              <option key={item.id} value={item.name}>
                {item.name}
              </option>
            ))}
            {row.classification && !classes.some((item) => item.name === row.classification) ? (
              <option value={row.classification}>{row.classification}</option>
            ) : null}
          </select>
        </TableCell>
      )}
      {mode === "lengths" ? (
        <TableCell className="min-w-56">
          <select
            className={fieldClass}
            value={row.herinox}
            disabled={disabled}
            aria-label={`Herinox de ${row.name}`}
            onChange={(event) => onChange({ herinox: event.target.value })}
          >
            <option value="">Sin código</option>
            {row.herinox && !knownStock ? <option value={row.herinox}>{row.herinox}</option> : null}
            {options.map((item) => (
              <option key={item.text} value={item.text}>
                {item.code} · {item.material}
              </option>
            ))}
          </select>
        </TableCell>
      ) : null}
    </TableRow>
  )
}
