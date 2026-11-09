import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Frame, FramePanel } from "@/components/reui/frame"
import { Spinner } from "@/components/ui/spinner"
import { toolbarApi, type AwisResult } from "@/bridge"

const PASOS = [
  {
    id: "solids",
    numero: "01",
    titulo: "Sólidos de soldadura",
    detalle: "Coloca los cuerpos de soldadura en las uniones del tanque.",
  },
  {
    id: "classify",
    numero: "02",
    titulo: "Clasificar soldaduras",
    detalle: "Abre la ventana para editar tipo, tamaño y símbolo. El módulo espera a que la cierres.",
  },
  {
    id: "drawings",
    numero: "03",
    titulo: "Cotas de soldadura",
    detalle: "Genera una foto por cordón.",
  },
] as const

export function AwisPanel({
  disabled,
  onLog,
  onBusy,
}: {
  disabled: boolean
  onLog: (message: string) => void
  onBusy: (busy: boolean) => void
}) {
  const [paso, setPaso] = useState<string | null>(null)
  const [resultado, setResultado] = useState<AwisResult | null>(null)

  async function correr(id: (typeof PASOS)[number]["id"]) {
    const api = toolbarApi()
    if (!api?.awis_run) {
      onLog("Abre el módulo con Iniciar AutoDXF.bat para correr AWIS.")
      return
    }
    setPaso(id)
    setResultado(null)
    onBusy(true)
    try {
      const next = await api.awis_run(JSON.stringify({ paso: id }))
      setResultado(next)
      onLog(next?.message || "AWIS terminó.")
    } catch (error) {
      const message = error instanceof Error ? error.message : "AWIS no pudo iniciar."
      setResultado({ ok: false, message, log: "" })
      onLog(message)
    } finally {
      setPaso(null)
      onBusy(false)
    }
  }

  return (
    <Frame>
      <FramePanel className="flex flex-col gap-4">
        <div>
          <h2 className="text-sm font-medium">AWIS</h2>
          <p className="text-muted-foreground text-xs">
            Inventor debe estar abierto con el ensamble del tanque. Estos son los tres pasos del plugin de soldadura.
          </p>
        </div>
        <div className="flex flex-col gap-2">
          {PASOS.map((item) => (
            <div key={item.id} className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2">
              <span className="text-muted-foreground w-8 text-xs">{item.numero}</span>
              <div className="min-w-64 flex-1">
                <p className="text-sm">{item.titulo}</p>
                <p className="text-muted-foreground text-xs">{item.detalle}</p>
              </div>
              <Button
                variant="outline"
                disabled={disabled || paso !== null}
                onClick={() => void correr(item.id)}
              >
                {paso === item.id ? <Spinner /> : "Correr"}
              </Button>
            </div>
          ))}
        </div>
        {resultado && (
          <pre className="bg-muted max-h-64 overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap">
            {resultado.message}
            {resultado.log ? `\n\n${resultado.log}` : ""}
          </pre>
        )}
      </FramePanel>
    </Frame>
  )
}
