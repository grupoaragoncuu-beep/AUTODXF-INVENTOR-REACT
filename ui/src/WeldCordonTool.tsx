import { useEffect, useRef, useState } from "react"
import { Badge } from "@/components/reui/badge"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Switch } from "@/components/ui/switch"
import { toolbarApi, type WeldCordon, type WeldNomList, type WeldSpec } from "@/bridge"
import { VACIO, etiquetaCateto, etiquetaPaso, formatSpec, specFromText } from "@/weld-spec"

export function WeldCordonTool() {
  const [tabla, setTabla] = useState<WeldNomList | null>(null)
  const [elegido, setElegido] = useState("")
  const [clasificacion, setClasificacion] = useState("accesorio")
  const [spec, setSpec] = useState<WeldSpec>(VACIO)
  const [ruta, setRuta] = useState("")
  const [job, setJob] = useState("")
  const [aviso, setAviso] = useState("")
  const [ocupado, setOcupado] = useState(false)
  const [generando, setGenerando] = useState(false)
  const elegidoRef = useRef("")
  const ocupadoRef = useRef(false)
  const tablaRef = useRef<WeldNomList | null>(null)
  elegidoRef.current = elegido
  ocupadoRef.current = ocupado
  tablaRef.current = tabla

  useEffect(() => {
    const cargar = () => {
      const api = toolbarApi()
      if (!api?.snapshot) return
      void api.snapshot().then((foto) => {
        const ensamble = String(foto?.assemblyPath || "")
        setRuta(ensamble)
        setJob(String(foto?.jobName || ""))
        void refrescar(ensamble)
      })
    }
    window.addEventListener("pywebviewready", cargar)
    cargar()
    const api = toolbarApi()
    void api?.weld_nom_armar?.()
    const timer = window.setInterval(() => {
      if (ocupadoRef.current) return
      const puente = toolbarApi()
      if (!puente?.weld_nom_mira) return
      void puente.weld_nom_mira().then((next) => {
        if (!next?.id || next.id === elegidoRef.current) return
        const fila = (tablaRef.current?.cordones || []).find((item) => item.id === next.id)
        if (fila) abrir(fila, false)
      })
    }, 700)
    const salir = () => {
      void toolbarApi()?.weld_nom_soltar?.()
    }
    window.addEventListener("beforeunload", salir)
    return () => {
      window.removeEventListener("pywebviewready", cargar)
      window.removeEventListener("beforeunload", salir)
      window.clearInterval(timer)
      void toolbarApi()?.weld_nom_soltar?.()
    }
  }, [])

  async function refrescar(ensamble: string, keepId?: string) {
    const api = toolbarApi()
    if (!api?.weld_nom_list || !ensamble) return
    const next = await api.weld_nom_list(JSON.stringify({ assemblyPath: ensamble }))
    setTabla(next)
    const filas = next.cordones || []
    const actual = filas.find((fila) => fila.id === (keepId || elegido)) || filas[0]
    if (actual) abrir(actual, false)
    else {
      setElegido("")
      setSpec(VACIO)
    }
  }

  function abrir(fila: WeldCordon, iluminar: boolean) {
    setElegido(fila.id)
    setClasificacion(fila.clasificacion === "hermetico" ? "hermetico" : "accesorio")
    setSpec({ ...VACIO, ...fila.spec })
    if (iluminar) void marcar(fila.cuerpos || [])
  }

  async function marcar(cuerpos: string[]) {
    const api = toolbarApi()
    if (!api?.weld_nom_select || cuerpos.length === 0) return
    const next = await api.weld_nom_select(JSON.stringify({ cuerpos }))
    if (next.message) setAviso(next.message)
  }

  async function aplicar() {
    const api = toolbarApi()
    if (!api?.weld_nom_apply || !elegido) return
    setOcupado(true)
    try {
      const next = await api.weld_nom_apply(JSON.stringify({ assemblyPath: ruta, id: elegido, clasificacion, spec }))
      if (next.message) setAviso(next.message)
      if (next.ok) {
        setTabla(next)
        const fila = (next.cordones || []).find((item) => item.id === elegido)
        if (fila) abrir(fila, false)
      }
    } finally {
      setOcupado(false)
    }
  }

  async function quitar() {
    const api = toolbarApi()
    const filaActual = (tabla?.cordones || []).find((item) => item.id === elegido)
    if (!api?.weld_nom_drop || !filaActual) return
    if (!window.confirm(`Quitar ${filaActual.titulo}. El siguiente pase no lo vuelve a proponer.`)) return
    setOcupado(true)
    try {
      const next = await api.weld_nom_drop(JSON.stringify({ assemblyPath: ruta, id: filaActual.id }))
      if (next.message) setAviso(next.message)
      if (next.ok) {
        setTabla(next)
        const filas = next.cordones || []
        if (filas[0]) abrir(filas[0], false)
        else setElegido("")
      }
    } finally {
      setOcupado(false)
    }
  }

  async function borrarTodos() {
    const api = toolbarApi()
    if (!api?.weld_run) {
      setAviso("Cierra la barra y ábrela de nuevo.")
      return
    }
    if (!window.confirm("Borra todos los cordones de este tanque. No genera otros.")) return
    setGenerando(true)
    setAviso("Borrando cordones…")
    try {
      const started = await api.weld_run(JSON.stringify({ assemblyPath: ruta, job, fase: "borrar" }))
      if (!started.ok && !started.started) {
        setAviso(started.message || "No arrancó.")
        return
      }
      for (;;) {
        const next = await api.weld_progress()
        const texto = String(next.piece || next.message || "")
        if (texto) setAviso(texto)
        if (next.running === false && (next.done || next.result)) {
          setAviso(String(next.result?.message || next.message || "Cordones borrados."))
          setElegido("")
          await refrescar(ruta)
          return
        }
        await new Promise((resolve) => window.setTimeout(resolve, 280))
      }
    } catch (error) {
      setAviso(error instanceof Error ? error.message : "No se pudieron borrar los cordones.")
    } finally {
      setGenerando(false)
    }
  }

  async function generarJpg() {
    const api = toolbarApi()
    if (!api?.weld_run) {
      setAviso("Cierra la barra y ábrela de nuevo.")
      return
    }
    setGenerando(true)
    setAviso("Generando JPG…")
    try {
      const started = await api.weld_run(JSON.stringify({ assemblyPath: ruta, job, fase: "foto" }))
      if (!started.ok && !started.started) {
        setAviso(started.message || "No arrancó.")
        return
      }
      for (;;) {
        const next = await api.weld_progress()
        const texto = String(next.piece || next.message || "")
        if (texto) setAviso(texto)
        if (next.running === false && (next.done || next.result)) {
          setAviso(String(next.result?.message || next.message || "Listo"))
          return
        }
        await new Promise((resolve) => window.setTimeout(resolve, 280))
      }
    } catch (error) {
      setAviso(error instanceof Error ? error.message : "No se pudieron generar los JPG.")
    } finally {
      setGenerando(false)
    }
  }

  const cordones = tabla?.cordones || []
  const presets = tabla?.presets || []
  const sizes = tabla?.sizes || ["3", "5", "6", "8"]
  const pitches = tabla?.pitches || ["", "10-60", "100-300"]
  const unit = tabla?.unit
  const texto = formatSpec(spec)
  const visible = formatSpec(spec, unit)
  const fila = cordones.find((item) => item.id === elegido)

  return (
    <main className="flex h-svh flex-col gap-2 bg-background p-3">
      <header className="space-y-1">
        <p className="text-sm font-medium">Nomenclatura</p>
        <p className="text-muted-foreground text-xs">Clic en un filete del modelo: ese cordón queda elegido aquí. Cierra esta ventana al terminar.</p>
      </header>
      <p className="text-muted-foreground text-xs">{aviso || tabla?.message || "Genera los cordones 3D en el módulo."}</p>
      {cordones.length > 0 ? (
        <ul className="max-h-28 space-y-1 overflow-auto">
          {cordones.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                disabled={ocupado}
                onClick={() => abrir(item, true)}
                className={`flex w-full items-center gap-2 rounded-md border px-2 py-1 text-left text-xs ${elegido === item.id ? "border-foreground" : "border-border"}`}
              >
                <span
                  className="size-2.5 shrink-0 rounded-sm border border-black/20"
                  style={{ backgroundColor: item.clasificacion === "hermetico" ? "#0F4BBE" : "#E66E0F" }}
                />
                <span className="min-w-0 flex-1 truncate">{item.titulo}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {elegido ? (
        <section className="space-y-2 border-t pt-2">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant={clasificacion === "hermetico" ? "default" : "outline"} disabled={ocupado} onClick={() => setClasificacion("hermetico")}>
              Hermético
            </Button>
            <Button size="sm" variant={clasificacion === "accesorio" ? "default" : "outline"} disabled={ocupado} onClick={() => setClasificacion("accesorio")}>
              Accesorio
            </Button>
          </div>
          {presets.length > 0 ? (
            <label className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
              Preset
              <select
                className="border-border bg-background h-7 min-w-40 flex-1 rounded-md border px-2 text-xs"
                value={presets.includes(texto) ? texto : ""}
                disabled={ocupado}
                onChange={(event) => {
                  if (event.target.value) setSpec(specFromText(event.target.value))
                }}
              >
                <option value="">Personalizado</option>
                {presets.map((preset) => (
                  <option key={preset} value={preset}>
                    {formatSpec(specFromText(preset), unit)}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-muted-foreground flex items-center gap-1 text-xs">
              Cateto
              <select
                className="border-border bg-background h-7 w-16 rounded-md border px-1 text-xs"
                value={String(spec.flecha)}
                disabled={ocupado}
                onChange={(event) => {
                  const flecha = Number(event.target.value) || 6
                  setSpec((actual) => ({ ...actual, flecha, otro: actual.dos_lados && !actual.otro ? flecha : actual.otro }))
                }}
              >
                {sizes.map((size) => (
                  <option key={size} value={size}>
                    {etiquetaCateto(size, unit)}
                  </option>
                ))}
              </select>
            </label>
            {spec.dos_lados ? (
              <label className="text-muted-foreground flex items-center gap-1 text-xs">
                Otro
                <select
                  className="border-border bg-background h-7 w-16 rounded-md border px-1 text-xs"
                  value={String(spec.otro || spec.flecha)}
                  disabled={ocupado}
                  onChange={(event) => setSpec((actual) => ({ ...actual, otro: Number(event.target.value) || actual.flecha }))}
                >
                  {sizes.map((size) => (
                    <option key={`otro-${size}`} value={size}>
                      {etiquetaCateto(size, unit)}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <label className="text-muted-foreground flex items-center gap-1 text-xs">
              Paso
              <select
                className="border-border bg-background h-7 w-24 rounded-md border px-1 text-xs"
                value={spec.paso}
                disabled={ocupado}
                onChange={(event) => setSpec((actual) => ({ ...actual, paso: event.target.value }))}
              >
                {pitches.map((pitch) => (
                  <option key={pitch || "continuo"} value={pitch}>
                    {etiquetaPaso(pitch, unit)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Field orientation="horizontal" className="w-auto">
              <Switch
                id="weld-2sides"
                size="sm"
                checked={spec.dos_lados}
                disabled={ocupado}
                onCheckedChange={(checked) =>
                  setSpec((actual) => ({ ...actual, dos_lados: Boolean(checked), otro: Boolean(checked) ? actual.otro || actual.flecha : 0 }))
                }
              />
              <FieldLabel htmlFor="weld-2sides">2 lados</FieldLabel>
            </Field>
            <Field orientation="horizontal" className="w-auto">
              <Switch
                id="weld-typ"
                size="sm"
                checked={spec.typ}
                disabled={ocupado}
                onCheckedChange={(checked) => setSpec((actual) => ({ ...actual, typ: Boolean(checked) }))}
              />
              <FieldLabel htmlFor="weld-typ">TYP</FieldLabel>
            </Field>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium">{visible}</p>
            {fila?.largo ? <Badge variant="outline" size="sm">{fila.largo}</Badge> : null}
            <Button size="sm" disabled={ocupado} onClick={() => void aplicar()}>
              Aplicar
            </Button>
            <Button size="sm" variant="outline" disabled={ocupado} onClick={() => void quitar()}>
              Quitar
            </Button>
          </div>
        </section>
      ) : null}
      <div className="mt-auto space-y-2 border-t pt-2">
        <Button className="w-full" variant="outline" disabled={ocupado || generando || !ruta} onClick={() => void borrarTodos()}>
          Borrar cordones
        </Button>
        <Button className="w-full" disabled={ocupado || generando || cordones.length === 0} onClick={() => void generarJpg()}>
          Generar JPGs
        </Button>
      </div>
    </main>
  )
}
