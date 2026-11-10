import type { WeldSpec } from "@/bridge"

export const VACIO: WeldSpec = { flecha: 6, otro: 0, dos_lados: false, typ: false, paso: "" }

function short(valor: number): string {
  return String(valor).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1")
}

const CATETO_IN: Record<string, string> = { "3": "1/8", "5": "3/16", "6": "1/4", "8": "5/16", "9.525": "3/8" }

export function etiquetaCateto(valor: string | number, unit?: string): string {
  const texto = String(valor)
  if (unit !== "in") return texto
  return CATETO_IN[texto] || texto
}

export function etiquetaPaso(valor: string, unit?: string): string {
  if (!valor) return "continuo"
  if (unit !== "in") return valor
  const partes = valor.split("-")
  if (partes.length !== 2) return valor
  const inicio = Number(partes[0])
  const fin = Number(partes[1])
  if (!Number.isFinite(inicio) || !Number.isFinite(fin) || inicio < 30) return valor
  return `${(inicio / 25.4).toFixed(2)}-${(fin / 25.4).toFixed(2)}`
}

export function formatSpec(spec: WeldSpec, unit?: string): string {
  const flecha = spec.flecha || 6
  const dos = spec.dos_lados
  const otro = dos ? spec.otro || flecha : 0
  const pulgadas = unit === "in"
  const marca = pulgadas ? "in" : "mm"
  const flechaTxt = pulgadas ? etiquetaCateto(flecha, "in") : short(flecha)
  const otroTxt = pulgadas ? etiquetaCateto(otro, "in") : short(otro)
  let texto =
    dos && Math.abs(otro - flecha) > 0.05
      ? `FILLET ${flechaTxt}/${otroTxt} ${marca}`
      : dos
        ? `FILLET ${flechaTxt} ${marca} 2SIDES`
        : `FILLET ${flechaTxt} ${marca}`
  if (spec.paso) texto += ` ${etiquetaPaso(spec.paso, unit)}`
  if (spec.typ) texto += " TYP"
  return texto
}

export function specFromText(texto: string): WeldSpec {
  let crudo = texto.toUpperCase()
  const spec: WeldSpec = { flecha: 6, otro: 0, dos_lados: /2\s*SIDE/.test(crudo), typ: crudo.includes("TYP"), paso: "" }
  const paso = crudo.match(/(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)/)
  if (paso) {
    spec.paso = `${short(Number(paso[1].replace(",", ".")))}-${short(Number(paso[2].replace(",", ".")))}`
    crudo = crudo.replace(paso[0], " ")
  }
  const desigual = crudo.match(/(\d+(?:[.,]\d+)?)\s*\/\s*(\d+(?:[.,]\d+)?)/)
  if (desigual) {
    spec.flecha = Number(desigual[1].replace(",", ".")) || 6
    spec.otro = Number(desigual[2].replace(",", ".")) || spec.flecha
    spec.dos_lados = true
    return spec
  }
  const tamano = crudo.match(/(\d+(?:[.,]\d+)?)/)
  if (tamano) spec.flecha = Number(tamano[1].replace(",", ".")) || 6
  if (spec.dos_lados) spec.otro = spec.flecha
  return spec
}
