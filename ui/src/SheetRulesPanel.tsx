import { useState } from "react"
import { Button } from "@/components/ui/button"
import { FieldLabel } from "@/components/ui/field"
import type { SheetRule, SheetRuleCatalog } from "@/bridge"
import { CORNER_SHAPES, nextRule, RELIEF_SHAPES, TRANSITIONS } from "@/sheet-rules"

const fieldClass = "border-border bg-background h-8 w-full rounded-lg border px-2 text-xs"

export function SheetRulesPanel({
  catalog,
  disabled,
  onChange,
  onSave,
}: {
  catalog: SheetRuleCatalog
  disabled: boolean
  onChange: (next: SheetRuleCatalog) => void
  onSave: () => void
}) {
  const [selectedId, setSelectedId] = useState(catalog.rules[0]?.id ?? "")
  const selected = catalog.rules.find((rule) => rule.id === selectedId) ?? catalog.rules[0]

  function update(patch: Partial<SheetRule>) {
    if (!selected) return
    onChange({
      ...catalog,
      rules: catalog.rules.map((rule) => (rule.id === selected.id ? { ...rule, ...patch } : rule)),
    })
  }

  function addRule() {
    const rule = nextRule(catalog)
    onChange({ ...catalog, rules: [...catalog.rules, rule] })
    setSelectedId(rule.id)
  }

  function removeRule() {
    if (!selected) return
    const rules = catalog.rules.filter((rule) => rule.id !== selected.id)
    onChange({ ...catalog, rules })
    setSelectedId(rules[0]?.id ?? "")
  }

  return (
    <div className="grid min-h-0 gap-3 rounded-lg border p-3 md:grid-cols-[220px_1fr]">
      <div className="flex min-h-0 flex-col gap-2">
        <FieldLabel>Rangos de espesor (in)</FieldLabel>
        <div className="max-h-72 overflow-auto rounded-lg border">
          {catalog.rules.map((rule) => (
            <button
              key={rule.id}
              type="button"
              disabled={disabled}
              className={`flex w-full items-center justify-between px-2 py-1.5 text-left text-xs ${
                rule.id === selected?.id ? "bg-muted" : "hover:bg-muted/60"
              }`}
              onClick={() => setSelectedId(rule.id)}
            >
              <span className="truncate font-medium">{rule.name}</span>
              <span className="text-muted-foreground shrink-0">
                {rule.min}–{rule.max}
              </span>
            </button>
          ))}
          {catalog.rules.length === 0 && (
            <p className="text-muted-foreground px-2 py-3 text-xs">Sin rangos. Cada pieza usará solo el espesor medido.</p>
          )}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={disabled} onClick={addRule}>
            Agregar
          </Button>
          <Button size="sm" variant="outline" disabled={disabled || !selected} onClick={removeRule}>
            Quitar
          </Button>
          <Button size="sm" disabled={disabled} onClick={onSave}>
            Guardar
          </Button>
        </div>
      </div>

      {selected ? (
        <div className="max-h-80 overflow-auto">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            <TextField label="Nombre de la regla" value={selected.name} disabled={disabled} onChange={(name) => update({ name })} />
            <NumberField label="Espesor mínimo (in)" value={selected.min} disabled={disabled} onChange={(min) => update({ min })} />
            <NumberField label="Espesor máximo (in)" value={selected.max} disabled={disabled} onChange={(max) => update({ max })} />
            <TextField
              label="Bend Deduction"
              value={selected.bendDeduction}
              disabled={disabled}
              onChange={(bendDeduction) => update({ bendDeduction, unfold: "deduction" })}
            />
            <TextField label="Radio de doblez" value={selected.bendRadius} disabled={disabled} onChange={(bendRadius) => update({ bendRadius })} />
            <SelectField
              label="Alivio de doblez"
              value={selected.bendReliefShape}
              disabled={disabled}
              options={RELIEF_SHAPES}
              onChange={(bendReliefShape) => update({ bendReliefShape })}
            />
            <TextField label="Ancho de alivio" value={selected.bendReliefWidth} disabled={disabled} onChange={(bendReliefWidth) => update({ bendReliefWidth })} />
            <TextField label="Fondo de alivio" value={selected.bendReliefDepth} disabled={disabled} onChange={(bendReliefDepth) => update({ bendReliefDepth })} />
            <TextField label="Remanente mínimo" value={selected.minimumRemnant} disabled={disabled} onChange={(minimumRemnant) => update({ minimumRemnant })} />
            <SelectField
              label="Alivio de esquina"
              value={selected.cornerReliefShape}
              disabled={disabled}
              options={CORNER_SHAPES}
              onChange={(cornerReliefShape) => update({ cornerReliefShape })}
            />
            <TextField label="Tamaño de esquina" value={selected.cornerReliefSize} disabled={disabled} onChange={(cornerReliefSize) => update({ cornerReliefSize })} />
            <TextField label="Separación (gap)" value={selected.gapSize} disabled={disabled} onChange={(gapSize) => update({ gapSize })} />
            <SelectField
              label="Transición de doblez"
              value={selected.bendTransition}
              disabled={disabled}
              options={TRANSITIONS}
              onChange={(bendTransition) => update({ bendTransition })}
            />
            <TextField
              label="Radio de transición"
              value={selected.bendTransitionArcRadius}
              disabled={disabled}
              onChange={(bendTransitionArcRadius) => update({ bendTransitionArcRadius })}
            />
            <SelectField
              label="Esquina de 3 dobleces"
              value={selected.threeBendCornerReliefShape}
              disabled={disabled}
              options={CORNER_SHAPES}
              onChange={(threeBendCornerReliefShape) => update({ threeBendCornerReliefShape })}
            />
            <TextField
              label="Tamaño de 3 dobleces"
              value={selected.threeBendCornerReliefSize}
              disabled={disabled}
              onChange={(threeBendCornerReliefSize) => update({ threeBendCornerReliefSize })}
            />
          </div>
          <p className="text-muted-foreground mt-2 text-xs">
            Un número suelto en Bend Deduction se toma en pulgadas. También puedes escribir 1.5 mm o Thickness. El espesor medido de la pieza se conserva: Usar grosor de regla queda desactivado.
          </p>
        </div>
      ) : (
        <p className="text-muted-foreground text-xs">Agrega un rango para definir su regla.</p>
      )}
    </div>
  )
}

function TextField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string
  value: string
  disabled: boolean
  onChange: (value: string) => void
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-muted-foreground text-[11px]">{label}</span>
      <input className={fieldClass} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
    </label>
  )
}

function NumberField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string
  value: number
  disabled: boolean
  onChange: (value: number) => void
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-muted-foreground text-[11px]">{label}</span>
      <input
        className={fieldClass}
        type="number"
        step="0.001"
        value={Number.isFinite(value) ? value : 0}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  )
}

function SelectField({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string
  value: string
  options: { id: string; label: string }[]
  disabled: boolean
  onChange: (value: string) => void
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-muted-foreground text-[11px]">{label}</span>
      <select className={fieldClass} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}
