import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { toolbarApi, type DossierJob } from "@/bridge"

type Props = {
  open: boolean
  onConfirm: (choice: { producto: string; cliente: string; job: string }) => void
}

function edad(dias: number) {
  if (dias <= 0) return "hoy"
  if (dias === 1) return "hace 1 día"
  return `hace ${dias} días`
}

export function DossierPicker({ open, onConfirm }: Props) {
  const [productos, setProductos] = useState<string[]>([])
  const [clientes, setClientes] = useState<string[]>([])
  const [jobs, setJobs] = useState<DossierJob[]>([])
  const [producto, setProducto] = useState("")
  const [cliente, setCliente] = useState("")
  const [job, setJob] = useState("")
  const [raiz, setRaiz] = useState("")
  const [mensaje, setMensaje] = useState("")
  const [cargando, setCargando] = useState(false)
  const [confirmarBorrado, setConfirmarBorrado] = useState(false)

  useEffect(() => {
    if (!open) return
    const consultar = toolbarApi()?.dossier_consulta
    if (!consultar) {
      setMensaje("Abre el módulo con Iniciar AutoDXF.bat para leer las carpetas del dossier.")
      return
    }
    let vivo = true
    setCargando(true)
    setMensaje("")
    void (async () => {
      const [arbol, actual] = await Promise.all([
        consultar(JSON.stringify({ accion: "productos" })),
        consultar(JSON.stringify({ accion: "actual" })),
      ])
      if (!vivo) return
      setProductos(arbol.nombres || [])
      setRaiz(arbol.raiz || "")
      if (!arbol.ok) setMensaje(arbol.message || "No se leyeron los productos.")
      const productoInicial = actual.producto && (arbol.nombres || []).includes(actual.producto) ? actual.producto : ""
      setProducto(productoInicial)
      setCliente("")
      setJob("")
      setClientes([])
      setJobs([])
      if (productoInicial && actual.cliente) {
        const lista = await consultar(JSON.stringify({ accion: "clientes", producto: productoInicial }))
        if (!vivo) return
        setClientes(lista.nombres || [])
        if ((lista.nombres || []).includes(actual.cliente)) {
          setCliente(actual.cliente)
          const trabajos = await consultar(
            JSON.stringify({ accion: "jobs", producto: productoInicial, cliente: actual.cliente }),
          )
          if (!vivo) return
          const filas = trabajos.jobs || []
          setJobs(filas)
          if (actual.job && filas.some((fila) => fila.nombre === actual.job)) setJob(actual.job)
        }
      }
      setCargando(false)
    })()
    return () => {
      vivo = false
    }
  }, [open])

  async function elegirProducto(value: string) {
    setProducto(value)
    setCliente("")
    setJob("")
    setConfirmarBorrado(false)
    setClientes([])
    setJobs([])
    setMensaje("")
    const consultar = toolbarApi()?.dossier_consulta
    if (!consultar || !value) return
    const lista = await consultar(JSON.stringify({ accion: "clientes", producto: value }))
    setClientes(lista.nombres || [])
    if (!lista.ok) setMensaje(lista.message || "No se leyeron los clientes.")
  }

  async function elegirCliente(value: string) {
    setCliente(value)
    setJob("")
    setJobs([])
    setConfirmarBorrado(false)
    setMensaje("")
    const consultar = toolbarApi()?.dossier_consulta
    if (!consultar || !producto || !value) return
    const trabajos = await consultar(JSON.stringify({ accion: "jobs", producto, cliente: value }))
    setJobs(trabajos.jobs || [])
    if (!trabajos.ok) setMensaje(trabajos.message || "No se leyeron los jobs.")
    else if ((trabajos.jobs || []).length === 0) setMensaje("No hay jobs de los últimos 15 días para este cliente.")
  }

  async function confirmar() {
    const consultar = toolbarApi()?.dossier_consulta
    if (!consultar || !producto || !cliente || !job) return
    const result = await consultar(JSON.stringify({ accion: "elegir", producto, cliente, job }))
    if (!result.ok) {
      setMensaje(result.message || "No se pudo usar esa carpeta.")
      return
    }
    onConfirm({ producto, cliente, job })
  }

  async function quitar() {
    const consultar = toolbarApi()?.dossier_consulta
    if (!consultar || !producto || !cliente || !job) return
    if (!confirmarBorrado) {
      setConfirmarBorrado(true)
      setMensaje("Se borran los JPG de este job y sus filas en la base. El modelo y el resto del dossier se quedan.")
      return
    }
    setCargando(true)
    const result = await consultar(JSON.stringify({ accion: "quitar", producto, cliente, job }))
    setMensaje(result.message || "No se pudo quitar la exportación.")
    setConfirmarBorrado(false)
    setCargando(false)
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-background flex max-h-[85svh] w-full max-w-md flex-col gap-3 rounded-lg border p-4 shadow-lg">
        <div>
          <h2 className="text-base font-medium">Dossier del job</h2>
          <p className="text-muted-foreground mt-1 text-xs">
            Elige la carpeta del producto, luego la del cliente y después el job. El nombre que se exporta es el de esa carpeta. Los jobs con más de 15 días no aparecen.
          </p>
        </div>
        <label className="flex flex-col gap-1 text-xs">
          Producto
          <select
            aria-label="Producto"
            className="border-border bg-background h-8 rounded-md border px-2 text-sm"
            value={producto}
            disabled={cargando || productos.length === 0}
            onChange={(event) => void elegirProducto(event.target.value)}
          >
            <option value="">Selecciona un producto</option>
            {productos.map((nombre) => (
              <option key={nombre} value={nombre}>
                {nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Cliente
          <select
            aria-label="Cliente"
            className="border-border bg-background h-8 rounded-md border px-2 text-sm"
            value={cliente}
            disabled={!producto || clientes.length === 0}
            onChange={(event) => void elegirCliente(event.target.value)}
          >
            <option value="">Selecciona un cliente</option>
            {clientes.map((nombre) => (
              <option key={nombre} value={nombre}>
                {nombre}
              </option>
            ))}
          </select>
        </label>
        <div className="flex min-h-0 flex-1 flex-col gap-1 text-xs">
          <span>Job</span>
          <div className="border-border max-h-48 overflow-auto rounded-md border">
            {jobs.map((fila) => (
              <button
                key={fila.nombre}
                type="button"
                className={`hover:bg-muted flex w-full items-center justify-between gap-3 px-2 py-1.5 text-left text-sm ${job === fila.nombre ? "bg-muted" : ""}`}
                onClick={() => {
                  setConfirmarBorrado(false)
                  setJob(fila.nombre)
                }}
              >
                <span className="truncate">{fila.nombre}</span>
                <span className="text-muted-foreground shrink-0 text-[10px]">{edad(fila.dias)}</span>
              </button>
            ))}
            {producto && cliente && jobs.length === 0 ? (
              <p className="text-muted-foreground px-2 py-3">Sin jobs recientes en esta carpeta.</p>
            ) : null}
          </div>
        </div>
        {job ? (
          <p className="text-muted-foreground truncate text-[10px]">
            {(raiz || "X:\\ARGA METALS CORPORATE SYSTEM") + `\\${producto}\\${cliente}\\${job}\\DOSSIER FILES\\JPGS`}
            <br />
            {(raiz || "X:\\ARGA METALS CORPORATE SYSTEM") + `\\${producto}\\${cliente}\\${job}\\Efort Weld Files`}
          </p>
        ) : null}
        {mensaje ? <p className="text-xs">{mensaje}</p> : null}
        <div className="flex gap-2">
          <Button
            type="button"
            variant={confirmarBorrado ? "destructive" : "outline"}
            className="flex-1"
            disabled={!job || cargando}
            onClick={() => void quitar()}
          >
            {confirmarBorrado ? "Sí, borrar esta exportación" : "Quitar exportación"}
          </Button>
          <Button type="button" className="flex-1" disabled={!job || cargando} onClick={() => void confirmar()}>
            Usar esta carpeta
          </Button>
        </div>
      </div>
    </div>
  )
}
