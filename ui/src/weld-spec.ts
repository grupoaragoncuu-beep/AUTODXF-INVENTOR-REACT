import type { WeldSpec } from "@/bridge"

export const VACIO: WeldSpec = { flecha: 6, otro: 0, dos_lados: false, typ: false, paso: "" }

function short(valor: number): string {
  return String(valor).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1")
}

export function formatSpec(spec: WeldSpec): string {
  const flecha = spec.flecha || 6
  const dos = spec.dos_lados
  const otro = dos ? spec.otro || flecha : 0
  let texto =
    dos && Math.abs(otro - flecha) > 0.05
      ? `FILLET ${short(flecha)}/${short(otro)} mm`
      : dos
        ? `FILLET ${short(flecha)} mm 2SIDES`
        : `FILLET ${short(flecha)} mm`
  if (spec.paso) texto += ` ${spec.paso}`
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
