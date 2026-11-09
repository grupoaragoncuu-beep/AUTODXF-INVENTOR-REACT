import { useEffect, useRef, useState } from "react"
import { Popover } from "@base-ui/react/popover"
import { CheckIcon, FolderOpenIcon, ListFilterIcon, MinusIcon, PlayIcon, RefreshCwIcon, RulerIcon } from "lucide-react"
import { Badge, badgeVariants } from "@/components/reui/badge"
import { IconStack } from "@/components/reui/icon-stack"
import { Frame, FramePanel } from "@/components/reui/frame"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "cn"
import {
  previewSnapshot,
  toolbarApi,
  type ExportResult,
  type SheetRuleCatalog,
  type SheetRulesResult,
  type Snapshot,
} from "@/bridge"
import { AcotacionJpgPanel } from "@/AcotacionJpgPanel"
import { AwisPanel } from "@/AwisPanel"
import { DossierPicker } from "@/DossierPicker"
import { WeldAnotationPanel } from "@/WeldAnotationPanel"
import { BloquesWorkspace } from "@/BloquesWorkspace"
import { SheetRulesPanel } from "@/SheetRulesPanel"
import { ShapesWorkspace } from "@/ShapesWorkspace"
import { defaultRuleCatalog } from "@/sheet-rules"
import {
  choiceLabel,
  boardCode,
  copperFileName,
  effectiveMaterial,
  isHardware,
  materialChoices,
  partKey,
  sortCalibres,
  uniqueText,
} from "@/materials"

function initials(name: string) {
  const parts = name.split(/[^A-Za-z0-9]+/).filter(Boolean)
  return (parts[0]?.slice(0, 2) || "DX").toUpperCase()
}

function toggleValue(list: string[], value: string) {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
}

export default function App() {
  const [linked, setLinked] = useState(false)
  const [snapshot, setSnapshot] = useState<Snapshot>(previewSnapshot)
  const [exportRoot, setExportRoot] = useState(() => localStorage.getItem("autodxf-export-root") || "")
  const [board, setBoard] = useState(() => boardCode(localStorage.getItem("autodxf-board") || "B1"))
  const [setASide, setSetASide] = useState(true)
  const [writeCsv, setWriteCsv] = useState(true)
  const [closeOpened, setCloseOpened] = useState(true)
  const [busy, setBusy] = useState<"refresh" | "export" | "rules" | null>(null)
  const [partsLoading, setPartsLoading] = useState(false)
  const [log, setLog] = useState(previewSnapshot.message)
  const [missingFlats, setMissingFlats] = useState<string[]>([])
  const [ruleCatalog, setRuleCatalog] = useState<SheetRuleCatalog>(defaultRuleCatalog)
  const [rulesOpen, setRulesOpen] = useState(false)
  const [view, setView] = useState<"dxf" | "lengths" | "accessories" | "cotas" | "weld" | "awis">("dxf")
  const [shapesBusy, setShapesBusy] = useState(false)
  const [offMaterials, setOffMaterials] = useState<string[]>([])
  const [offCalibres, setOffCalibres] = useState<string[]>([])
  const [overrides, setOverrides] = useState<Record<string, string>>({})
  const [excludedKeys, setExcludedKeys] = useState<string[]>([])
  const [jobName, setJobName] = useState("")
  const [producto, setProducto] = useState("")
  const [cliente, setCliente] = useState("")
  const [dossierOpen, setDossierOpen] = useState(false)
  const dossierAsked = useRef(false)

  async function refresh() {
    const api = toolbarApi()
    if (!api) return
    setBusy("refresh")
    try {
      const next = await api.snapshot()
      setSnapshot((current) => ({
        ...next,
        parts: Array.isArray(next.parts) && next.parts.length ? next.parts : current.assemblyPath === next.assemblyPath ? current.parts : [],
        catalog: Array.isArray(next.catalog?.materials) ? next.catalog : current.catalog,
      }))
      setLog(next.message || next.catalog?.message || "")
      if (next.inventorConnected && next.assemblyPath && api.parts) {
        setPartsLoading(true)
        setLog("Leyendo piezas de chapa…")
        try {
          const bom = await api.parts()
          setSnapshot((current) => ({
            ...current,
            inventorConnected: bom.inventorConnected !== false,
            assemblyName: bom.assemblyName || current.assemblyName,
            assemblyPath: bom.assemblyPath || current.assemblyPath,
            parts: Array.isArray(bom.parts) ? bom.parts : [],
            message: bom.message || current.message,
          }))
          setLog(bom.message || "")
        } catch (error) {
          setLog(error instanceof Error ? error.message : "No se pudieron leer las piezas.")
        } finally {
          setPartsLoading(false)
        }
      }
    } catch (error) {
      setLog(error instanceof Error ? error.message : "No se pudo consultar Inventor.")
    } finally {
      setBusy(null)
    }
  }

  useEffect(() => {
    localStorage.setItem("autodxf-export-root", exportRoot)
  }, [exportRoot])

  useEffect(() => {
    localStorage.setItem("autodxf-board", board)
  }, [board])

  useEffect(() => {
    setOffMaterials([])
    setOffCalibres([])
    setOverrides({})
    setExcludedKeys([])
  }, [snapshot.assemblyPath])

  useEffect(() => {
    const connect = () => {
      const api = toolbarApi()
      if (!api) return
      setLinked(true)
      if (!dossierAsked.current && api.dossier_consulta) {
        dossierAsked.current = true
        setDossierOpen(true)
      }
      void refresh()
      void api.sheet_rules_load().then((catalog) => {
        if (catalog?.rules) setRuleCatalog(catalog)
      })
    }
    window.addEventListener("pywebviewready", connect)
    connect()
    return () => window.removeEventListener("pywebviewready", connect)
  }, [])

  async function persistJob(value: string) {
    const api = toolbarApi()
    if (!api?.job_save) return
    try {
      const result = await api.job_save(
        JSON.stringify({
          job: value,
          assemblyPath: snapshot.assemblyPath,
          assemblyName: snapshot.assemblyName,
        }),
      )
      if (result.job) setJobName(result.job)
    } catch {
      /* el JOB sigue en pantalla; se reintenta al exportar */
    }
  }

  async function chooseFolder() {
    const api = toolbarApi()
    if (!api) {
      setLog("La carpeta se elige desde la ventana de AutoDXF, no desde el navegador.")
      return
    }
    const folder = await api.pick_folder()
    if (folder) setExportRoot(folder)
    return folder || ""
  }

  async function pickAnyFolder() {
    const api = toolbarApi()
    if (!api) {
      setLog("La carpeta se elige desde la ventana de AutoDXF, no desde el navegador.")
      return ""
    }
    return (await api.pick_folder()) || ""
  }

  async function runSheetRules() {
    const api = toolbarApi()
    if (!api) {
      setLog("Inicia la barra con Iniciar AutoDXF.bat. Esta vista no aplica reglas sola.")
      return
    }
    setBusy("rules")
    setMissingFlats([])
    setLog("Midiendo espesor, clasificando rangos y creando reglas de chapa. Inventor queda ocupado hasta que termine.")
    try {
      const result: SheetRulesResult = await api.sheet_rules(JSON.stringify(ruleCatalog))
      if (result.catalog) {
        setSnapshot((current) => ({ ...current, catalog: result.catalog! }))
      }
      if (result.session) {
        setSnapshot((current) => ({
          ...current,
          ...result.session!,
          parts: result.session!.parts?.length ? result.session!.parts : current.parts,
          catalog: result.catalog ?? current.catalog,
        }))
      }
      setMissingFlats(result.missing || [])
      setLog(result.message || (result.ok ? "Reglas de chapa listas." : "Quedaron piezas sin flat."))
    } catch (error) {
      setLog(error instanceof Error ? error.message : "Error al aplicar las reglas de chapa.")
    } finally {
      setBusy(null)
    }
  }

  async function saveRules() {
    const api = toolbarApi()
    if (!api) {
      setLog("Inicia la barra con Iniciar AutoDXF.bat para guardar las reglas.")
      return
    }
    try {
      const saved = await api.sheet_rules_save(JSON.stringify(ruleCatalog))
      if (saved.catalog?.rules) setRuleCatalog(saved.catalog)
      setLog(saved.message)
    } catch (error) {
      setLog(error instanceof Error ? error.message : "No se pudieron guardar las reglas.")
    }
  }

  async function runExport() {
    const api = toolbarApi()
    if (!api) {
      setLog("Inicia la barra con Iniciar AutoDXF.bat. Esta vista no exporta sola.")
      return
    }
    if (!jobName.trim()) {
      setDossierOpen(true)
      setLog("Elige el job del dossier antes de exportar.")
      return
    }
    if (selected.length === 0) {
      setLog("No hay piezas marcadas para exportar.")
      return
    }
    setBusy("export")
    try {
      const result: ExportResult = await api.export_dxf(
        JSON.stringify({
          exportRoot,
          setASide,
          writeCsv,
          closeOpened,
          usePartPlan: true,
          board: boardCode(board),
          job: jobName,
          parts: selected.map((part) => {
            const material = effectiveMaterial(part, overrides)
            return {
              path: part.path,
              material,
              dxfName: copperFileName(part, material, board) || part.name,
            }
          }),
        }),
      )
      if (result.catalog) {
        setSnapshot((current) => ({ ...current, catalog: result.catalog! }))
      }
      if (result.session) {
        setSnapshot((current) => ({
          ...current,
          ...result.session!,
          parts: result.session!.parts?.length ? result.session!.parts : current.parts,
          catalog: result.catalog ?? current.catalog,
        }))
      }
      setLog(result.message || (result.ok ? "Exportación terminada." : "La exportación no terminó."))
    } catch (error) {
      setLog(error instanceof Error ? error.message : "Error al exportar.")
    } finally {
      setBusy(null)
    }
  }

  const sheetParts = snapshot.parts.filter((part) => !isHardware(part.name))
  const flatCount = sheetParts.filter((part) => part.flat).length
  const materials = uniqueText(sheetParts.map((part) => effectiveMaterial(part, overrides))).sort((a, b) =>
    a.localeCompare(b, "es"),
  )
  const calibres = sortCalibres(sheetParts.map((part) => part.thickness || "—"))
  const visible = sheetParts.filter((part) => {
    const material = effectiveMaterial(part, overrides)
    const calibre = part.thickness || "—"
    return !offMaterials.includes(material) && !offCalibres.includes(calibre)
  })
  const materialCounts = new Map<string, number>()
  const calibreCounts = new Map<string, number>()
  for (const part of sheetParts) {
    const material = effectiveMaterial(part, overrides)
    const calibre = part.thickness || "—"
    materialCounts.set(material, (materialCounts.get(material) || 0) + 1)
    calibreCounts.set(calibre, (calibreCounts.get(calibre) || 0) + 1)
  }
  const selected = visible.filter((part) => !excludedKeys.includes(partKey(part)))
  const visibleKeys = visible.map((part) => partKey(part))
  const allVisibleChecked = visibleKeys.length > 0 && visibleKeys.every((key) => !excludedKeys.includes(key))
  const someVisibleChecked = visibleKeys.some((key) => !excludedKeys.includes(key))
  const missing = !exportRoot || !snapshot.assemblyName
  const nothingVisible = sheetParts.length > 0 && visible.length === 0
  const nothingSelected = visible.length > 0 && selected.length === 0
  const exporting = busy === "export"

  function setVisibleIncluded(include: boolean) {
    setExcludedKeys((current) => {
      if (include) return current.filter((key) => !visibleKeys.includes(key))
      return [...new Set([...current, ...visibleKeys])]
    })
  }

  return (
    <main className="flex h-svh flex-col gap-3 overflow-hidden bg-background p-3">
      <header className="flex items-center gap-4">
        <IconStack aria-hidden="true" className="text-primary h-16 w-14 shrink-0">
          <span className="bg-background text-primary flex size-7 items-center justify-center rounded-full border shadow-xs">
            <CheckIcon className="size-3.5" />
          </span>
        </IconStack>
        <div className="min-w-0 flex-1">
          <p className="text-muted-foreground text-xs tracking-wide uppercase">Grupo Arga</p>
          <h1 className="truncate text-lg font-medium">AutoDXF</h1>
          <p className="text-muted-foreground truncate text-xs">
            {snapshot.inventorConnected
              ? `${snapshot.inventorVersion} · ${snapshot.assemblyName || "sin ensamble"}`
              : linked
                ? "Ventana conectada. Inventor no responde."
                : "Barra flotante para Inventor"}
          </p>
        </div>
        <button
          type="button"
          className="border-border hover:bg-muted flex max-w-72 min-w-40 shrink-0 flex-col rounded-md border px-2 py-1 text-left"
          disabled={busy !== null}
          onClick={() => setDossierOpen(true)}
        >
          <span className="text-muted-foreground text-[10px] tracking-wide uppercase">Dossier</span>
          <span className="truncate text-sm">{jobName || "Elegir job"}</span>
          <span className="text-muted-foreground truncate text-[10px]">
            {producto && cliente ? `${producto} \\ ${cliente}` : "Producto y cliente"}
          </span>
        </button>
        <div className="hidden items-end gap-4 sm:flex">
          <StatusStack
            label="Inventor"
            ok={snapshot.inventorConnected}
            detail={snapshot.inventorConnected ? "Activo" : "Espera"}
          />
          <StatusStack
            label="Base"
            ok={snapshot.catalog.connected}
            detail={snapshot.catalog.source}
          />
          <StatusStack
            label="Flat"
            ok={sheetParts.length > 0 && flatCount === sheetParts.length}
            detail={`${flatCount}/${sheetParts.length}`}
          />
        </div>
      </header>

      <DossierPicker
        open={dossierOpen}
        onConfirm={(choice) => {
          setProducto(choice.producto)
          setCliente(choice.cliente)
          setJobName(choice.job)
          setDossierOpen(false)
          void persistJob(choice.job)
          setLog(`${choice.producto} \\ ${choice.cliente} \\ ${choice.job}`)
        }}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["dxf", "Chapa DXF"],
            ["lengths", "Lista de largos"],
            ["accessories", "Clasificación por bloques"],
            ["cotas", "Acotación JPG"],
            ["weld", "Weld Anotation"],
            ["awis", "AWIS"],
          ] as const
        ).map(([id, label]) => (
          <Button key={id} variant={view === id ? "default" : "outline"} disabled={busy !== null || shapesBusy} onClick={() => setView(id)}>
            {label}
          </Button>
        ))}
      </div>

      {view === "dxf" ? (
      <>
      <section className="flex flex-wrap items-center gap-2">
        <Button variant="outline" disabled={busy !== null} onClick={() => void runSheetRules()}>
          {busy === "rules" ? <Spinner /> : <RulerIcon />}
          Reglas de chapa
        </Button>
        <Button variant="outline" disabled={busy !== null} onClick={() => setRulesOpen((open) => !open)}>
          {rulesOpen ? "Cerrar reglas" : "Editar reglas"}
        </Button>
        <p className="text-muted-foreground min-w-0 flex-1 text-xs">
          {ruleCatalog.rules.length} rangos. El espesor medido se conserva.
        </p>
      </section>
      {rulesOpen && (
        <SheetRulesPanel
          catalog={ruleCatalog}
          disabled={busy !== null}
          onChange={setRuleCatalog}
          onSave={() => void saveRules()}
        />
      )}
      {missingFlats.length > 0 && (
        <ul className="max-h-24 overflow-auto rounded-md border px-3 py-2 text-xs">
          {missingFlats.map((name) => (
            <li key={name}>Sin flat: {name}</li>
          ))}
        </ul>
      )}

      <section className="flex flex-wrap items-center gap-2">
        <Button
          size="icon-lg"
          variant="outline"
          aria-label="Actualizar ensamble"
          disabled={busy !== null}
          onClick={() => void refresh()}
        >
          {busy === "refresh" ? <Spinner /> : <RefreshCwIcon />}
        </Button>
        <Button variant="outline" disabled={busy !== null} onClick={() => void chooseFolder()}>
          <FolderOpenIcon />
          Carpeta
        </Button>
        {exporting ? (
          <Button disabled>
            <Spinner aria-hidden="true" />
            Exportando
          </Button>
        ) : missing || nothingVisible || nothingSelected ? (
          <Button aria-invalid="true" onClick={() => void runExport()}>
            {nothingVisible ? "Nada con estos filtros" : nothingSelected ? "Nada seleccionado" : "Falta ensamble o carpeta"}
          </Button>
        ) : (
          <Button
            className="group/fab relative flex h-10 w-10 items-center overflow-hidden rounded-full px-3 transition-[width] duration-300 ease-in-out hover:w-44"
            aria-label={`Exportar ${selected.length} DXF`}
            onClick={() => void runExport()}
          >
            <PlayIcon
              aria-hidden="true"
              className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 transition-transform duration-300 group-hover/fab:left-3 group-hover/fab:translate-x-0"
            />
            <span className="ml-8 pr-2 whitespace-nowrap opacity-0 transition-opacity duration-300 group-hover/fab:opacity-100">
              Exportar {selected.length}
            </span>
          </Button>
        )}
        <p className="text-muted-foreground min-w-0 flex-1 truncate text-xs">
          {exportRoot || "Sin carpeta destino"}
        </p>
      </section>

      <Field className="w-auto">
        <FieldLabel>Opciones de exportación</FieldLabel>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <Field orientation="horizontal" className="w-auto">
            <Switch id="opt-aside" checked={setASide} onCheckedChange={setSetASide} />
            <FieldLabel htmlFor="opt-aside">Cara A-Side</FieldLabel>
          </Field>
          <Field orientation="horizontal" className="w-auto">
            <Switch id="opt-csv" checked={writeCsv} onCheckedChange={setWriteCsv} />
            <FieldLabel htmlFor="opt-csv">CSV de clasificación</FieldLabel>
          </Field>
          <Field orientation="horizontal" className="w-auto">
            <Switch id="opt-close" checked={closeOpened} onCheckedChange={setCloseOpened} />
            <FieldLabel htmlFor="opt-close">Cerrar piezas abiertas</FieldLabel>
          </Field>
          <Field orientation="horizontal" className="w-auto">
            <FieldLabel htmlFor="opt-board">Board</FieldLabel>
            <input
              id="opt-board"
              aria-label="Board"
              className="border-border bg-background h-7 w-40 rounded-md border px-2 text-sm"
              value={board}
              placeholder="B1"
              title="Código del ensamble. Se usa en el nombre del DXF y de las fotos."
              disabled={busy !== null}
              onChange={(event) => setBoard(event.target.value)}
              onBlur={(event) => setBoard(boardCode(event.target.value))}
            />
          </Field>
        </div>
      </Field>

      <Frame spacing="xs" className="min-h-0 flex-1">
        <FramePanel className="h-full overflow-auto p-0!">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <RowCheck
                    checked={allVisibleChecked}
                    indeterminate={!allVisibleChecked && someVisibleChecked}
                    disabled={busy !== null || visible.length === 0}
                    label="Incluir las piezas visibles"
                    onChange={() => setVisibleIncluded(!allVisibleChecked)}
                  />
                </TableHead>
                <TableHead>Pieza</TableHead>
                <TableHead>
                  <ColumnFilter
                    label="Material"
                    options={materials}
                    counts={materialCounts}
                    excluded={offMaterials}
                    disabled={busy !== null}
                    onChange={setOffMaterials}
                  />
                </TableHead>
                <TableHead>
                  <ColumnFilter
                    label="Calibre"
                    options={calibres}
                    counts={calibreCounts}
                    excluded={offCalibres}
                    disabled={busy !== null}
                    format={(value) => `Cal ${value}`}
                    onChange={setOffCalibres}
                  />
                </TableHead>
                <TableHead>Cant.</TableHead>
                <TableHead>Flat</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sheetParts.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-muted-foreground text-center">
                    {partsLoading ? "Leyendo piezas de chapa…" : "No hay chapa en el ensamble activo."}
                  </TableCell>
                </TableRow>
              ) : visible.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-muted-foreground text-center">
                    Ninguna pieza con estos filtros.
                  </TableCell>
                </TableRow>
              ) : (
                visible.map((part) => {
                  const key = partKey(part)
                  const included = !excludedKeys.includes(key)
                  const material = effectiveMaterial(part, overrides)
                  const dxfName = copperFileName(part, material, board)
                  const choices = materialChoices(snapshot.catalog.materials, sheetParts, material)
                  return (
                    <TableRow key={key} className={included ? undefined : "opacity-45"}>
                      <TableCell>
                        <RowCheck
                          checked={included}
                          disabled={busy !== null}
                          label={`Incluir ${part.name}`}
                          onChange={() => setExcludedKeys((current) => toggleValue(current, key))}
                        />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <Avatar size="sm">
                            <AvatarFallback>{initials(part.name)}</AvatarFallback>
                          </Avatar>
                          <div className="flex flex-col">
                            <span className="text-sm font-medium">{part.name}</span>
                            {dxfName ? (
                              <span className="text-muted-foreground text-xs">{dxfName}</span>
                            ) : null}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <select
                          aria-label={`Material de ${part.name}`}
                          className={cn(
                            badgeVariants({
                              variant: material === "CU" && part.copper ? "warning-light" : "default",
                              size: "lg",
                              radius: "full",
                            }),
                            "max-w-36 cursor-pointer pr-1",
                            material === "CU" && part.copper && "text-black!",
                          )}
                          value={material}
                          style={material === "CU" && part.copper ? { color: "#000" } : undefined}
                          disabled={busy !== null}
                          onChange={(event) =>
                            setOverrides((current) => ({ ...current, [partKey(part)]: event.target.value }))
                          }
                        >
                          {choices.map((choice) => (
                            <option key={choice} value={choice}>
                              {choiceLabel(part, choice)}
                            </option>
                          ))}
                        </select>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" size="sm">
                          Cal {part.thickness || "—"}
                        </Badge>
                      </TableCell>
                      <TableCell>{part.qty}</TableCell>
                      <TableCell>
                        <Badge variant={part.flat ? "success-light" : "warning-light"} size="sm">
                          {part.flat ? "Flat" : "Sin flat"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        </FramePanel>
      </Frame>
      </>
      ) : view === "cotas" ? (
        <AcotacionJpgPanel
          disabled={busy !== null || shapesBusy}
          assemblyName={snapshot.assemblyName}
          assemblyPath={snapshot.assemblyPath}
          jobName={jobName}
          onLog={setLog}
          onBusy={setShapesBusy}
          onChooseFolder={pickAnyFolder}
        />
      ) : view === "awis" ? (
        <AwisPanel
          disabled={busy !== null || shapesBusy}
          onLog={setLog}
          onBusy={setShapesBusy}
        />
      ) : view === "weld" ? (
        <WeldAnotationPanel
          disabled={busy !== null || shapesBusy}
          assemblyName={snapshot.assemblyName}
          assemblyPath={snapshot.assemblyPath}
          jobName={jobName}
          onLog={setLog}
          onBusy={setShapesBusy}
          onChooseFolder={pickAnyFolder}
        />
      ) : view === "accessories" ? (
        <BloquesWorkspace
          key={snapshot.assemblyPath}
          disabled={busy !== null || shapesBusy}
          exportRoot={exportRoot}
          jobName={jobName}
          onLog={setLog}
          onBusy={setShapesBusy}
          onChooseFolder={() => void chooseFolder()}
        />
      ) : (
        <ShapesWorkspace
          mode={view}
          disabled={busy !== null || shapesBusy}
          exportRoot={exportRoot}
          jobName={jobName}
          onLog={setLog}
          onBusy={setShapesBusy}
          onChooseFolder={() => void chooseFolder()}
        />
      )}

      <p className="text-muted-foreground line-clamp-3 text-xs whitespace-pre-wrap">{log}</p>
    </main>
  )
}

function ColumnFilter({
  label,
  options,
  counts,
  excluded,
  disabled,
  format,
  onChange,
}: {
  label: string
  options: string[]
  counts: Map<string, number>
  excluded: string[]
  disabled: boolean
  format?: (value: string) => string
  onChange: (next: string[]) => void
}) {
  const active = excluded.length > 0
  return (
    <Popover.Root>
      <Popover.Trigger
        disabled={disabled}
        className={cn(
          "inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-left font-medium hover:bg-muted",
          active && "text-primary",
        )}
      >
        {label}
        <ListFilterIcon className={cn("size-3.5", active ? "text-primary" : "text-muted-foreground")} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="bottom" align="start" sideOffset={6} className="z-50">
          <Popover.Popup className="bg-popover text-popover-foreground max-h-72 w-56 overflow-auto rounded-lg border p-1.5 shadow-md">
            <button
              type="button"
              className="hover:bg-muted w-full rounded-md px-2 py-1.5 text-left text-xs font-medium"
              onClick={() => onChange([])}
            >
              Todos
            </button>
            {options.map((option) => {
              const checked = !excluded.includes(option)
              return (
                <label key={option} className="hover:bg-muted flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm">
                  <input
                    type="checkbox"
                    className="accent-foreground size-3.5"
                    checked={checked}
                    onChange={() => onChange(toggleValue(excluded, option))}
                  />
                  <span className="min-w-0 flex-1 truncate">{format ? format(option) : option}</span>
                  <span className="text-muted-foreground text-xs">{counts.get(option) || 0}</span>
                </label>
              )
            })}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}

function RowCheck({
  checked,
  indeterminate = false,
  disabled,
  label,
  onChange,
}: {
  checked: boolean
  indeterminate?: boolean
  disabled: boolean
  label: string
  onChange: () => void
}) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate
  }, [indeterminate])
  return (
    <input
      ref={ref}
      type="checkbox"
      className="accent-foreground size-3.5"
      checked={checked}
      disabled={disabled}
      aria-label={label}
      onChange={onChange}
    />
  )
}

function StatusStack({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <IconStack aria-hidden="true" className={ok ? "text-success h-12 w-11" : "text-warning h-12 w-11"}>
        {ok ? <CheckIcon className="text-success size-3.5" /> : <MinusIcon className="text-warning size-3.5" />}
      </IconStack>
      <span className="text-muted-foreground text-[10px]">{label}</span>
      <span className="max-w-20 truncate text-[10px]">{detail}</span>
    </div>
  )
}
