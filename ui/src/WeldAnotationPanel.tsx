import { useEffect, useState } from "react"
import { FolderOpenIcon } from "lucide-react"
import { Badge } from "@/components/reui/badge"
import { Button } from "@/components/ui/button"
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress"
import { toolbarApi, type AcotacionProgress, type WeldNomList, type WeldScan } from "@/bridge"

export function WeldAnotationPanel({
  disabled,
  assemblyName,
  assemblyPath,
  jobName,
  onLog,
  onBusy,
}: {
  disabled: boolean
  assemblyName: string
  assemblyPath: string
  jobName: string
  onLog: (message: string) => void
  onBusy: (busy: boolean) => void
  onChooseFolder: () => Promise<string>
}) {
  const [scan, setScan] = useState<WeldScan | null>(null)
  const [progress, setProgress] = useState<AcotacionProgress | null>(null)
  const [summary, setSummary] = useState("")
  const [exporting, setExporting] = useState(false)
  const [tabla, setTabla] = useState<WeldNomList | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const api = toolbarApi()
      if (!api?.weld_scan) return
      void api.weld_scan(JSON.stringify({ assemblyName, assemblyPath, job: jobName })).then((next) => {
        if (next) setScan(next)
      })
    }, 250)
    return () => window.clearTimeout(timer)
  }, [assemblyName, assemblyPath, jobName])

  useEffect(() => {
    void refreshTabla(assemblyPath)
    const timer = window.setInterval(() => void refreshTabla(assemblyPath), 2000)
    return () => window.clearInterval(timer)
  }, [assemblyPath])

  async function refreshTabla(ruta: string) {
    const api = toolbarApi()
    if (!api?.weld_nom_list || !ruta) return
    const next = await api.weld_nom_list(JSON.stringify({ assemblyPath: ruta }))
    setTabla(next)
  }

  async function correr(fase: "cordon" | "foto") {
    const api = toolbarApi()
    if (!api?.weld_run) {
      onLog("Inicia la barra con Iniciar AutoDXF.bat.")
      return
    }
    if (!jobName.trim()) {
      onLog("Elige el job del dossier antes de continuar.")
      return
    }
    setExporting(true)
    onBusy(true)
    setSummary("")
    setProgress({
      running: true,
      done: false,
      current: 0,
      total: 0,
      piece: fase === "foto" ? "Preparando JPG…" : "Poniendo el tanque en gris…",
      percent: 0,
      photos: 0,
    })
    try {
      const started = await api.weld_run(JSON.stringify({ assemblyName, assemblyPath, job: jobName, fase }))
      if (!started.ok && !started.started) {
        const msg = started.message || "No arrancó."
        onLog(msg)
        setSummary(msg)
        setProgress((current) => ({ ...(current || {}), running: false, done: true, piece: "No arrancó", message: msg, percent: 100 }))
        return
      }
      for (;;) {
        const next = await api.weld_progress()
        setProgress(next)
        if (next.running === false && (next.done || next.result)) {
          const msg = String(next.result?.message || next.message || "")
          if (msg) onLog(msg)
          setSummary(msg)
          await refreshTabla(assemblyPath)
          if (fase === "cordon" && next.result?.ok !== false) await api.weld_tool_open?.()
          return
        }
        await new Promise((resolve) => window.setTimeout(resolve, 280))
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : "No se pudieron dibujar los cordones."
      onLog(msg)
      setSummary(msg)
    } finally {
      setExporting(false)
      onBusy(false)
    }
  }

  const folder = scan?.folder || ""
  const files = progress?.result?.files || []
  const cordones = tabla?.cordones || []
  const locked = disabled || exporting

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto">
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={locked} onClick={() => void correr("cordon")}>
            Generar cordones 3D
          </Button>
          <Button variant="outline" disabled={locked || cordones.length === 0} onClick={() => void toolbarApi()?.weld_tool_open?.()}>
            Nomenclatura
          </Button>
          <Button disabled={locked} onClick={() => void correr("foto")}>
            Generar JPGs
          </Button>
          <Button variant="outline" disabled={locked || !folder} onClick={() => void toolbarApi()?.acotacion_open(folder)}>
            <FolderOpenIcon />
            Abrir JPG
          </Button>
          {scan ? (
            <Badge variant="success-light" size="sm">
              Python · {scan.tank || "ensamble"}
            </Badge>
          ) : null}
        </div>
        <p className="text-muted-foreground text-xs">
          Confirma los muros, genera los cordones con el tanque en gris y ajusta el símbolo en la ventana Nomenclatura. Los JPG se publican al final, en DOSSIER FILES\JPGS\Weld del job.
        </p>
      </section>

      <section className="space-y-2 rounded-lg border p-3">
        <p className="text-xs font-medium">Desde el ensamble</p>
        <p className="text-xs">{scan?.message || "Leyendo el job…"}</p>
        <p className="text-muted-foreground text-xs">{assemblyName || "Abre el ensamble del tanque en Inventor."}</p>
      </section>

      {progress ? (
        <section className="w-full space-y-2 rounded-lg border p-3">
          <Progress value={progress.done ? 100 : Number(progress.percent || 0)}>
            <ProgressLabel>{progress.phase === "foto" ? "JPG" : "Cordones"}</ProgressLabel>
            <ProgressValue />
          </Progress>
          <p className="text-foreground truncate text-xs font-medium">{progress.piece || "Leyendo el ensamble…"}</p>
          <p className="text-muted-foreground text-xs">
            {progress.total ? `${progress.current || 0} de ${progress.total}` : "Leyendo caras…"}
            {progress.photos ? ` · ${progress.photos} JPG` : ""}
          </p>
        </section>
      ) : null}

      {summary ? (
        <section className="rounded-lg border p-3">
          <p className="text-xs font-medium">Resultado</p>
          <p className="text-foreground mt-1 text-xs break-words whitespace-pre-wrap">{summary}</p>
          {files.length > 0 ? (
            <ul className="mt-2 max-h-36 overflow-auto text-xs">
              {files.map((file) => (
                <li key={file}>{file}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      <section className="space-y-2 rounded-lg border p-3">
        <p className="text-xs font-medium">Cordones</p>
        <p className="text-muted-foreground text-xs">{tabla?.message || "Genera los cordones 3D para llenar la tabla."}</p>
        {cordones.length > 0 ? (
          <ul className="max-h-64 space-y-1 overflow-auto">
            {cordones.map((fila) => (
              <li key={fila.id} className="grid grid-cols-[auto_minmax(0,1.4fr)_auto_minmax(0,1fr)_auto] items-center gap-2 rounded-md border px-2 py-1 text-xs">
                <span
                  className="size-2.5 rounded-sm border border-black/20"
                  style={{ backgroundColor: fila.clasificacion === "hermetico" ? "#0F4BBE" : "#E66E0F" }}
                />
                <span className="truncate">{fila.titulo}</span>
                <span>{fila.clasificacion === "hermetico" ? "Hermético" : "Accesorio"}</span>
                <span className="text-muted-foreground truncate">{fila.texto}</span>
                <span className="text-muted-foreground">{fila.largo || "—"}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <p className="text-xs break-all">Carpeta: {folder || "Elige el job del dossier."}</p>
    </div>
  )
}
