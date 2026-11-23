import { useState } from "react"
import { FolderOpenIcon } from "lucide-react"
import { Badge } from "@/components/reui/badge"
import { Button } from "@/components/ui/button"
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress"
import { Switch } from "@/components/ui/switch"
import { toolbarApi, type AcotacionProgress } from "@/bridge"

export function EspesorPinturaPanel({
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
}) {
  const [otc, setOtc] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [progress, setProgress] = useState<AcotacionProgress | null>(null)
  const [summary, setSummary] = useState("")
  const [folder, setFolder] = useState("")
  const [avisos, setAvisos] = useState<string[]>([])

  async function correr(muestra: boolean) {
    const api = toolbarApi()
    if (!api?.espesor_run) {
      onLog("Cierra la barra y ábrela con Iniciar AutoDXF.bat para cargar esta prueba.")
      return
    }
    setExporting(true)
    onBusy(true)
    setSummary("")
    setAvisos([])
    setProgress({ running: true, done: false, current: 0, total: 0, piece: muestra ? "Dibujando la muestra…" : "Leyendo el ensamble…", percent: 0 })
    try {
      const payload = JSON.stringify({
        otc,
        muestra,
        assemblyName,
        assemblyPath,
        job: jobName,
      })
      const started = await api.espesor_run(payload)
      if (muestra || started.folder) {
        const msg = started.message || (started.ok ? "Listo." : "No se generó la prueba.")
        onLog(msg)
        setSummary(msg)
        setFolder(started.folder || "")
        setAvisos(started.avisos || [])
        setProgress({ running: false, done: true, percent: 100, piece: "Listo", message: msg, result: started })
        return
      }
      if (!started.ok && !started.started) {
        const msg = started.message || "No arrancó."
        onLog(msg)
        setSummary(msg)
        setProgress({ running: false, done: true, percent: 100, piece: "No arrancó", message: msg })
        return
      }
      for (;;) {
        const next = await api.espesor_progress()
        setProgress(next)
        if (next.running === false && (next.done || next.result)) {
          const msg = String(next.result?.message || next.message || "")
          if (msg) onLog(msg)
          setSummary(msg)
          setFolder(next.result?.folder || "")
          setAvisos(next.result?.avisos || [])
          return
        }
        await new Promise((resolve) => window.setTimeout(resolve, 280))
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : "No se pudo dibujar el espesor."
      onLog(msg)
      setSummary(msg)
    } finally {
      setExporting(false)
      onBusy(false)
    }
  }

  const locked = disabled || exporting

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto">
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={locked || !assemblyPath} onClick={() => void correr(false)}>
            Generar las cuatro
          </Button>
          <Button variant="outline" disabled={locked} onClick={() => void correr(true)}>
            Muestra de 4 segmentos
          </Button>
          <Button variant="outline" disabled={locked || !folder} onClick={() => void toolbarApi()?.espesor_open(folder)}>
            <FolderOpenIcon />
            Abrir JPG
          </Button>
          <Badge variant="outline" size="sm">
            Cotas dossier
          </Badge>
        </div>
        <label className="flex items-center gap-2 text-xs">
          <Switch checked={otc} disabled={locked} onCheckedChange={setOtc} />
          Tanque OTC: en Poliuretano el esquema incluye Zinc. Los puntos no se duplican.
        </label>
        <p className="text-muted-foreground text-xs">
          Un clic saca las cuatro señalaciones, cada una en su carpeta: Thermox, Zinc y Macro, Poliuretano, y shot blast. Shot blast marca igual que Poliuretano. Con el job del dossier elegido, los JPG se copian a DOSSIER FILES\JPGS\Espesor pintura y entran a cotas_dossier.
        </p>
      </section>

      <section className="space-y-1 rounded-lg border p-3">
        <p className="text-xs font-medium">Ensamble abierto</p>
        <p className="text-muted-foreground text-xs">{assemblyName || "Abre el tanque en Inventor y pulsa Generar con el ensamble."}</p>
      </section>

      {progress ? (
        <section className="w-full space-y-2 rounded-lg border p-3">
          <Progress value={progress.done ? 100 : Number(progress.percent || 0)}>
            <ProgressLabel>Espesor</ProgressLabel>
            <ProgressValue />
          </Progress>
          <p className="truncate text-xs font-medium">{progress.piece || "Preparando…"}</p>
        </section>
      ) : null}

      {summary ? (
        <section className="rounded-lg border p-3">
          <p className="text-xs font-medium">Resultado</p>
          <p className="mt-1 text-xs break-words whitespace-pre-wrap">{summary}</p>
          {avisos.length > 0 ? (
            <ul className="text-muted-foreground mt-2 max-h-36 list-disc overflow-auto pl-4 text-xs">
              {avisos.map((aviso) => (
                <li key={aviso}>{aviso}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
