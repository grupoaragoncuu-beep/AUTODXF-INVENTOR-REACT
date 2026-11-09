import { useEffect, useMemo, useRef, useState } from "react"
import { hotkeysCoreFeature, selectionFeature, syncDataLoaderFeature } from "@headless-tree/core"
import { useTree } from "@headless-tree/react"
import { FolderIcon, FolderOpenIcon } from "lucide-react"
import { Tree, TreeItem, TreeItemLabel } from "@/components/reui/tree"
import { Button } from "@/components/ui/button"
import {
  folderPath,
  normalizePhotoLayout,
  safeFolderName,
  type PhotoFolder,
  type PhotoLayout,
} from "@/photo-layout"

const indent = 16
const fieldClass = "border-border bg-background h-8 rounded-lg border px-2 text-xs"

export function PhotoLayoutTree({
  layout,
  disabled,
  onChange,
}: {
  layout: PhotoLayout
  disabled: boolean
  onChange: (next: PhotoLayout) => void
}) {
  const data = normalizePhotoLayout(layout)
  const itemsRef = useRef(data.items)
  itemsRef.current = data.items
  const [draft, setDraft] = useState("")
  const tree = useTree<PhotoFolder>({
    initialState: {
      expandedItems: ["root", "corte", "maquinado", "plasma", "doblado"],
      selectedItems: ["root"],
    },
    indent,
    rootItemId: "root",
    getItemName: (item) => item.getItemData()?.name || item.getId(),
    isItemFolder: () => true,
    dataLoader: {
      getItem: (itemId) => itemsRef.current[itemId] || { name: itemId, children: [] },
      getChildren: (itemId) => itemsRef.current[itemId]?.children ?? [],
    },
    features: [syncDataLoaderFeature, selectionFeature, hotkeysCoreFeature],
  })
  const stamp = JSON.stringify({
    root: data.rootName,
    slots: data.slots,
    items: Object.fromEntries(
      Object.entries(data.items).map(([id, node]) => [id, { name: node.name, children: node.children || [] }]),
    ),
  })
  useEffect(() => {
    tree.rebuildTree()
  }, [stamp])

  const selected = tree.getSelectedItems()[0]
  const selectedId = selected?.getId() || "root"
  const selectedPath = folderPath(data, selectedId)
  const labels = useMemo(
    () => ({
      F: folderPath(data, data.slots.F),
      B: folderPath(data, data.slots.B),
      ISO: folderPath(data, data.slots.ISO),
    }),
    [data],
  )

  function commit(next: PhotoLayout) {
    onChange(normalizePhotoLayout({ ...next, rootName: next.items.root?.name || next.rootName }))
  }

  function addFolder() {
    const parentId = selectedId
    const id = `f-${Date.now()}`
    const name = safeFolderName(draft || "Nueva carpeta")
    const parent = data.items[parentId]
    if (!parent) return
    commit({
      ...data,
      items: {
        ...data.items,
        [parentId]: { ...parent, children: [...(parent.children || []), id] },
        [id]: { name, children: [] },
      },
    })
    setDraft("")
  }

  function renameFolder() {
    const name = safeFolderName(draft)
    if (!name || selectedId === "root") {
      if (selectedId === "root" && name) {
        commit({
          ...data,
          rootName: name,
          items: { ...data.items, root: { ...data.items.root, name } },
        })
        setDraft("")
      }
      return
    }
    commit({
      ...data,
      items: { ...data.items, [selectedId]: { ...data.items[selectedId], name } },
    })
    setDraft("")
  }

  function deleteFolder() {
    if (selectedId === "root") return
    const parentId = Object.keys(data.items).find((id) => (data.items[id].children || []).includes(selectedId))
    if (!parentId) return
    const drop = new Set<string>()
    const walk = (id: string) => {
      drop.add(id)
      for (const child of data.items[id]?.children || []) walk(child)
    }
    walk(selectedId)
    const items = { ...data.items }
    items[parentId] = {
      ...items[parentId],
      children: (items[parentId].children || []).filter((id) => id !== selectedId),
    }
    for (const id of drop) delete items[id]
    const slots = { ...data.slots }
    for (const key of ["F", "B", "ISO"] as const) {
      if (drop.has(slots[key])) slots[key] = "root"
    }
    commit({ ...data, items, slots })
  }

  function assign(kind: "F" | "B" | "ISO") {
    commit({ ...data, slots: { ...data.slots, [kind]: selectedId } })
  }

  return (
    <section className="grid gap-2 rounded-lg border p-3">
      <p className="text-sm font-medium">Dónde se guardan las fotos</p>
      <p className="text-muted-foreground text-xs">
        Árbol bajo JPG / JOB. Se guarda solo. F y B: una carpeta por pieza con su JPG. ISO: todos los JPG juntos.
      </p>
      <Tree indent={indent} tree={tree} className="border-border max-h-56 overflow-auto rounded-md border p-1">
        {tree.getItems().map((item) => {
          const id = item.getId()
          const marks = (
            [
              data.slots.F === id ? "F" : "",
              data.slots.B === id ? "B" : "",
              data.slots.ISO === id ? "ISO" : "",
            ] as const
          ).filter(Boolean)
          return (
            <TreeItem key={id} item={item}>
              <TreeItemLabel>
                <span className="flex min-w-0 items-center gap-2">
                  {item.isExpanded() ? (
                    <FolderOpenIcon className="size-4 shrink-0 text-amber-500" />
                  ) : (
                    <FolderIcon className="size-4 shrink-0 text-amber-500" />
                  )}
                  <span className="truncate">{item.getItemName()}</span>
                  {marks.length ? (
                    <span className="text-muted-foreground shrink-0 text-[10px]">{marks.join(" · ")}</span>
                  ) : null}
                </span>
              </TreeItemLabel>
            </TreeItem>
          )
        })}
      </Tree>
      <p className="text-muted-foreground text-[11px] break-all">Selección: {selectedPath}</p>
      <div className="flex flex-wrap gap-2">
        <input
          className={`${fieldClass} min-w-40 flex-1`}
          placeholder="Nombre de carpeta"
          value={draft}
          disabled={disabled}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") addFolder()
          }}
        />
        <Button size="sm" variant="outline" disabled={disabled} onClick={addFolder}>
          Nueva carpeta
        </Button>
        <Button size="sm" variant="outline" disabled={disabled} onClick={renameFolder}>
          Renombrar
        </Button>
        <Button size="sm" variant="outline" disabled={disabled || selectedId === "root"} onClick={deleteFolder}>
          Eliminar
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={disabled} onClick={() => assign("F")}>
          F aquí
        </Button>
        <Button size="sm" disabled={disabled} onClick={() => assign("B")}>
          B aquí
        </Button>
        <Button size="sm" disabled={disabled} onClick={() => assign("ISO")}>
          ISO aquí
        </Button>
      </div>
      <div className="text-muted-foreground grid gap-0.5 text-[11px]">
        <p>F → {labels.F} / «pieza» / JPG</p>
        <p>B → {labels.B} / «pieza» / JPG</p>
        <p>ISO → {labels.ISO} / todos los JPG</p>
      </div>
    </section>
  )
}
