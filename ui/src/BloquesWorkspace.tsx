import { useEffect, useRef, useState } from "react"
import { CheckIcon, EraserIcon, EyeIcon, FolderOpenIcon, LockIcon, MinusIcon, PaletteIcon, RefreshCwIcon } from "lucide-react"
import { Badge } from "@/components/reui/badge"
import { Frame, FramePanel } from "@/components/reui/frame"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { toolbarApi, type BlockItem, type BlockPending, type BlockStep, type BlocksSnapshot } from "@/bridge"

const LEVEL = { part: "Nivel componente (.ipt)", assembly: "Nivel ensamble (.iam)" }

export function BloquesWorkspace({
  disabled,
  exportRoot,
  jobName,
  onLog,
  onBusy,
  onChooseFolder,
}: {
  disabled: boolean
  exportRoot: string
  jobName: string
  onLog: (message: string) => void
  onBusy: (busy: boolean) => void
  onChooseFolder: () => void
}) {
  const [blocks, setBlocks] = useState<BlockStep[]>([])
  const [items, setItems] = useState<BlockItem[]>([])
  const [selected, setSelected] = useState("")
  const [complete, setComplete] = useState(false)
  const [assembly, setAssembly] = useState("")
  const [working, setWorking] = useState<string | null>(null)
  const [painted, setPainted] = useState("")
  const [picking, setPicking] = useState(false)
  const [pickedCount, setPickedCount] = useState(0)
  const [diagnostic, setDiagnostic] = useState<{ unclassified: BlockPending[]; conflicts: BlockPending[] } | null>(null)
  const pickingRef = useRef(false)
  const closingRef = useRef(false)

  const block = blocks.find((row) => row.id === selected)
  const open = Boolean(block && block.unlocked && !block.state)
  const rows = items.filter((item) => item.blocks.includes(selected))
  const names = Object.fromEntries(blocks.map((row) => [row.id, row.name]))
  const done = blocks.filter((row) => row.state).length
  const locked = disabled || working !== null

  function apply(result: BlocksSnapshot, focus?: string) {
    if (result.blocks) setBlocks(result.blocks)
    if (result.items) setItems(result.items)
    setComplete(Boolean(result.complete))
    if (result.assembly) setAssembly(result.assembly)
    if (focus !== undefined) setSelected(focus)
    if (result.message) onLog(result.message)
  }

  async function call(label: string, payload: Record<string, unknown>) {
    const api = toolbarApi()
    if (!api?.blocks_action) {
      onLog("Inicia la barra con Iniciar AutoDXF.bat.")
      return null
    }
    setWorking(label)
    onBusy(true)
    try {
      return await api.blocks_action(JSON.stringify(payload))
    } catch (error) {
      onLog(error instanceof Error ? error.message : "Inventor no respondió.")
      return null
    } finally {
      setWorking(null)
      onBusy(false)
    }
  }

  async function verify(blockId: string) {
    const result = await call("verify", { action: "verify", block: blockId })
    if (!result) return
    apply(result, blockId)
    setDiagnostic(null)
    if (result.ok) setPainted(blockId)
  }

  async function showFinal() {
    const result = await call("final", { action: "final" })
    if (!result) return
    apply(result)
    if (!result.ok || !result.diagnostic) return
    setDiagnostic(result.diagnostic)
    setPainted("final")
  }

  async function refresh() {
    const result = await call("status", { action: "status" })
    if (!result) return
    const focus = result.current || result.blocks?.[result.blocks.length - 1]?.id || ""
    apply(result)
    if (focus) await verify(focus)
    if (result.message) onLog(result.message)
  }

  async function step(action: "confirm" | "empty" | "reopen") {
    if (!block) return
    const result = await call(action, { action, block: block.id })
    if (!result) return
    apply(result)
    if (!result.ok) return
    const next = action === "reopen" ? block.id : result.current || block.id
    if (next !== painted) await verify(next)
  }

  async function unmark(paths: string[]) {
    if (!block) return
    const result = await call("unmark", { action: "unmark", block: block.id, paths })
    if (result) apply(result)
  }

  async function clearColors() {
    const result = await call("clear", { action: "clear" })
    if (!result) return
    apply(result)
    setPainted("")
    setDiagnostic(null)
  }

  async function exportCsv() {
    if (!exportRoot) {
      onLog("Elige la carpeta destino.")
      return
    }
    if (!jobName.trim()) {
      onLog("Elige el job del dossier antes de exportar.")
      return
    }
    const result = await call("export", { action: "export", folder: exportRoot, job: jobName })
    if (result) apply(result)
  }

  async function beginPick() {
    const api = toolbarApi()
    if (!api || !block) return
    if (painted !== block.id) await verify(block.id)
    const result = await api.start_pick(
      JSON.stringify({ mode: "accessories", className: block.name, color: block.color, block: block.id }),
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
      onLog(result.message || "Selección terminada.")
    } finally {
      onBusy(false)
      closingRef.current = false
    }
    const status = await call("status", { action: "status" })
    if (status) apply({ ...status, message: "" })
  }

  useEffect(() => {
    void refresh()
  }, [])

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

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <section className="flex flex-wrap items-center gap-2">
        <Button variant="outline" disabled={locked || picking} onClick={onChooseFolder}>
          <FolderOpenIcon />
          Carpeta
        </Button>
        <Button variant="outline" disabled={locked || picking} onClick={() => void refresh()}>
          {working === "status" ? <Spinner /> : <RefreshCwIcon />}
          Actualizar
        </Button>
        <Button variant="outline" disabled={locked || picking} onClick={() => void clearColors()}>
          <EraserIcon />
          Quitar colores
        </Button>
        <Button variant="outline" disabled={locked || picking || items.length === 0} onClick={() => void exportCsv()}>
          Exportar clasificación
        </Button>
        <Button disabled={locked || picking || !complete} onClick={() => void showFinal()}>
          {working === "final" ? <Spinner /> : <PaletteIcon />}
          Ver ensamble final
        </Button>
        <p className="text-muted-foreground min-w-0 flex-1 text-xs">
          {assembly ? `${assembly} · ${items.length} clasificados en el modelo · ` : ""}
          {complete
            ? "Flujo completo. «Ver ensamble final» colorea todo el ensamble y lista lo que quedó sin clasificar."
            : `${done} de ${blocks.length} bloques confirmados. Cada bloque se abre al confirmar el anterior.`}
        </p>
      </section>

      <ol className="flex flex-wrap gap-2">
        {blocks.map((row, index) => {
          const reachable = row.unlocked || Boolean(row.state)
          return (
            <li key={row.id}>
              <button
                type="button"
                disabled={locked || picking || !reachable}
                onClick={() => void verify(row.id)}
                className={`flex items-center gap-2 rounded-md border px-2 py-1 text-xs disabled:opacity-45 ${selected === row.id ? "border-foreground" : "border-border"}`}
              >
                <span className="text-muted-foreground">{index + 1}.</span>
                <span className="size-3 shrink-0 rounded-sm border border-black/20" style={{ backgroundColor: row.color }} />
                {row.name}
                {row.state === "hecho" ? (
                  <CheckIcon className="size-3.5" />
                ) : row.state === "no_aplica" ? (
                  <MinusIcon className="size-3.5" />
                ) : !row.unlocked ? (
                  <LockIcon className="size-3.5" />
                ) : null}
                <Badge variant="outline" size="sm">
                  {row.count}
                </Badge>
              </button>
            </li>
          )
        })}
      </ol>

      {diagnostic ? (
        <FinalReport blocks={blocks} diagnostic={diagnostic} />
      ) : block ? (
        <section className="border-border space-y-2 rounded-lg border px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="size-3 shrink-0 rounded-sm border border-black/20" style={{ backgroundColor: block.color }} />
            <p className="text-sm font-medium">{block.name}</p>
            <Badge variant="outline" size="sm">
              {LEVEL[block.level]}
            </Badge>
            <Badge variant={block.state ? "success-light" : open ? "info-light" : "outline"} size="sm">
              {block.state === "hecho" ? "Confirmado" : block.state === "no_aplica" ? "No aplica" : open ? "En proceso" : "Bloqueado"}
            </Badge>
            <span className="text-muted-foreground text-xs">iProperty «{block.prop}»</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {picking ? (
              <Button disabled={disabled} onClick={() => void endPick()}>
                Terminar
              </Button>
            ) : (
              <Button disabled={locked || !open} onClick={() => void beginPick()}>
                Iniciar selección
              </Button>
            )}
            {picking ? <p className="text-xs">{pickedCount} marcados en esta selección</p> : null}
            <Button variant="outline" disabled={locked || picking} onClick={() => void verify(block.id)}>
              {working === "verify" ? <Spinner /> : <EyeIcon />}
              Verificar mi selección «{block.name}»
            </Button>
            {block.state ? (
              <Button variant="outline" disabled={locked || picking} onClick={() => void step("reopen")}>
                Reabrir bloque
              </Button>
            ) : (
              <>
                <Button disabled={locked || picking || !open || block.count === 0} onClick={() => void step("confirm")}>
                  <CheckIcon />
                  Confirmar bloque
                </Button>
                <Button variant="outline" disabled={locked || picking || !open || block.count > 0} onClick={() => void step("empty")}>
                  Este bloque no aplica
                </Button>
              </>
            )}
          </div>
          <p className="text-muted-foreground text-xs">
            {picking
              ? block.level === "assembly"
                ? block.id === "assy_loose"
                  ? "Clic en cada subensamble .iam. Sus piezas también quedan en Accesorios Sueltos. Otro clic lo quita."
                  : "Clic en cada subensamble .iam. Otro clic lo quita. Esc o Terminar para salir."
                : "Clic en cada pieza .ipt; se marcan todas sus copias. Otro clic la quita. Esc o Terminar para salir."
              : open
                ? "Solo se ve en color lo marcado en este bloque. Una pieza puede estar en varios bloques: marcarla aquí no la quita de los demás."
                : block.state
                  ? "Bloque confirmado. Para corregirlo, pulsa Reabrir bloque; los demás bloques conservan su selección."
                  : "Confirma los bloques anteriores para abrir este."}
          </p>
        </section>
      ) : null}

      {diagnostic ? null : (
      <Frame spacing="xs" className="min-h-0 flex-1">
        <FramePanel className="h-full overflow-auto p-0!">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Componente</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Cant.</TableHead>
                <TableHead>También en</TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-muted-foreground text-center">
                    {blocks.length === 0
                      ? "Pulsa Actualizar con el ensamble abierto en Inventor."
                      : open
                        ? "Nada marcado en este bloque. Pulsa Iniciar selección o, si no aplica, «Este bloque no aplica»."
                        : "Este bloque no tiene componentes."}
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((item) => (
                  <TableRow key={item.path}>
                    <TableCell className="text-sm font-medium">{item.name}</TableCell>
                    <TableCell className="text-xs">{item.kind === "assembly" ? "Ensamble" : "Pieza"}</TableCell>
                    <TableCell>{item.qty}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {item.blocks
                          .filter((id) => id !== selected)
                          .map((id) => (
                            <Badge key={id} variant="outline" size="sm">
                              {names[id] || id}
                            </Badge>
                          ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Button size="sm" variant="outline" disabled={locked || picking || !open} onClick={() => void unmark([item.path])}>
                        Quitar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </FramePanel>
      </Frame>
      )}
    </div>
  )
}

function FinalReport({
  blocks,
  diagnostic,
}: {
  blocks: BlockStep[]
  diagnostic: { unclassified: BlockPending[]; conflicts: BlockPending[] }
}) {
  const names = Object.fromEntries(blocks.map((row) => [row.id, row.name]))
  const parts = diagnostic.unclassified.filter((row) => row.kind === "part").length
  const assemblies = diagnostic.unclassified.length - parts
  return (
    <>
      <section className="border-border space-y-2 rounded-lg border px-3 py-2">
        <p className="text-sm font-medium">Ensamble final</p>
        <div className="flex flex-wrap gap-3">
          {blocks.map((row) => (
            <span key={row.id} className="flex items-center gap-1.5 text-xs">
              <span className="size-3 shrink-0 rounded-sm border border-black/20" style={{ backgroundColor: row.color }} />
              {row.name} ({row.count})
            </span>
          ))}
        </div>
        <p className="text-muted-foreground text-xs">
          Cada pieza lleva el color de su proceso (Almacén, Corte o Doblado; si no tiene, Accesorios Sueltos). Las piezas de un
          kit Assy sin proceso propio llevan el color del kit. Lo que no tiene clasificación queda con su color original.
        </p>
        {diagnostic.conflicts.length > 0 ? (
          <p className="text-destructive text-xs">
            En más de un bloque de Almacén, Corte o Doblado:{" "}
            {diagnostic.conflicts.map((row) => `${row.name} (${(row.blocks || []).map((id) => names[id] || id).join(" + ")})`).join(", ")}.
            Reabre el bloque y quítalas de uno.
          </p>
        ) : null}
      </section>
      <Frame spacing="xs" className="min-h-0 flex-1">
        <FramePanel className="h-full overflow-auto p-0!">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>
                  Sin clasificación: {parts} pieza(s), {assemblies} ensamble(s)
                </TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Cant.</TableHead>
                <TableHead>Clasificación anterior</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {diagnostic.unclassified.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-muted-foreground text-center">
                    Todos los componentes pertenecen a alguna clasificación.
                  </TableCell>
                </TableRow>
              ) : (
                diagnostic.unclassified.map((row) => (
                  <TableRow key={row.path}>
                    <TableCell className="text-sm font-medium">{row.name}</TableCell>
                    <TableCell className="text-xs">{row.kind === "assembly" ? "Ensamble" : "Pieza"}</TableCell>
                    <TableCell>{row.qty}</TableCell>
                    <TableCell className="text-muted-foreground text-xs">{row.legacy || "—"}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </FramePanel>
      </Frame>
    </>
  )
}
