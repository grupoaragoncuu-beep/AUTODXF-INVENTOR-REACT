# Selector de roles L2 — guía para reimplementar

Este archivo describe **toda la lógica que hace funcionar el selector** de Planos Universales / Fase 2: listas por rol, propuesta automática de Segmento 1–4 + Top Cover + Base, confirmación y autoaprendizaje.

No incluye generación de planos, OCC ni el visor. El selector solo **asigna piezas a roles** y publica un JSON. El otro proyecto debe aportar su CAD (Inventor, SolidWorks, etc.) detrás de la interfaz de más abajo.

Fuentes originales (si tienes el repo GIGA / Planos Universales):

| Pieza | Archivo |
| --- | --- |
| Sesión, Pick 3D, bolsas | `fase 2/flat_part_roles.py`, `fase 2/interactive_selector.py` |
| Propuesta de muros | `fase 2/auto_muros.py` |
| Memoria incluir/excluir | `fase 2/aprendizaje_roles.py` |
| Panel (confirmar, proponer, vaciar) | `Modulo Planos Universales/escritorio/planos_ui/views/componentes.py` |
| Resaltado morado/azul | `planos_ui/seleccion_cara.py` |
| Lista alternativa por sub-IAM | `fase 2/l2_list_selector.py` |

---

## 1. Qué resuelve

El usuario mira un ensamble (tanque) y dice qué piezas son cada muro. Eso se guarda como `roles_seleccionados` + árbol `estructura`.

Hay tres caminos, en este orden de preferencia:

1. **Propuesta automática** (cara frontal + geometría) → llena las 6 bolsas.
2. **Aprendizaje** (JSON local) → quita lo que el usuario ya rechazó y recupera lo que ya confirmó, si en *este* modelo la pieza toca la placa de ese rol.
3. **Pick manual** sobre el modelo (y vaciar / quitar).

La propuesta es opcional. Si el usuario dice que no, el Pick sigue igual.

---

## 2. Claves de rol (no traducir en el JSON)

```
Segmento_1   # frente (normal hacia el espectador)
Segmento_2   # izquierda de quien mira el frente
Segmento_3   # posterior
Segmento_4   # derecha
Top_Cover    # tapa superior
Base         # piso
```

Opcionales (no los propone `auto_muros`):

```
Lifting_Lug
Jacking_Pad
Componentes      # gabinetes: una bolsa, sin muros
__extra__        # estructuras extras (padre + Extra_N)
```

Etiquetas de UI por producto (mismas claves, otro nombre en pantalla):

| Producto | Segmento_1 | Segmento_2 | Segmento_3 | Segmento_4 |
| --- | --- | --- | --- | --- |
| Tank | Segmento 1 | Segmento 2 | Segmento 3 | Segmento 4 |
| Compartment | Puertas | Panel izquierdo | Barrera interna | Panel derecho |
| LV-HV Throat / ATC | (no se usa) | Componente izquierdo | (no se usa) | Componente derecho |

Gabinetes **no** llama a la propuesta de muros.

---

## 3. Modelo de sesión

El selector es un objeto con este contrato mínimo:

```python
sesion.producto          # str, p.ej. "tank"  → clave del JSON de aprendizaje
sesion.rol               # rol activo en la UI
sesion.bolsas            # dict[str, list[dict]]  una lista por rol
sesion.sugerencia_tokens # dict[str, list[str]]   foto al proponer (para el delta)
sesion.inventor          # API CAD o None
sesion.tank              # documento / ocurrencia raíz del ensamble
```

Cada miembro de una bolsa:

```json
{
  "nombre_ocurrencia": "261427_SEG 1:1",
  "ruta_archivo": "C:\\cache\\261427_SEG 1.ipt",
  "ruta_ocurrencia_tanque": "Tanque:1/SEG 1:1",
  "es_chapa": true,
  "has_flat_pattern": true,
  "placa_rol": true,
  "sugerido": true,
  "objeto_com": null
}
```

| Campo | Uso |
| --- | --- |
| `placa_rol` | Es la placa del muro (no un accesorio). No se mueve al aplicar aprendizaje. |
| `sugerido` | Morado = propuesta aún no confirmada. Al confirmar pasa a `false` (azul). |
| `ruta_ocurrencia_tanque` | Identidad estable en *este* ensamble. Mejor que el nombre. |
| `objeto_com` | Handle CAD. No serializar al JSON publicado. |

Una pieza **no puede vivir en dos segmentos**. Si toca dos placas, se queda en la primera bolsa que la reclamó por contacto.

---

## 4. Flujo de la UI

```
Abrir ensamble (.iam)
        │
        ▼
¿Capturar cara FRONTAL?  ──No──► Pick manual (sin propuesta)
        │ Sí
        ▼
Guardar normal + punto de la cara (y cámara si existe)
        │
        ▼
¿Proponer muros?  ──No──► Pick manual
        │ Sí
        ▼
clasificar_placas + contactos + aplicar_aprendizaje
        │
        ▼
Usuario corrige (quitar / vaciar / Pick)
        │
        ▼
Confirmar sugerencia  → registrar_sesion (incluir / excluir)
        │
        ▼
Listo — publicar  → estructura.json + roles_seleccionados
```

Botones que debe tener el otro proyecto:

- **Selección sobre modelo** — Pick de cara/ocurrencia hacia la bolsa activa.
- **Proponer muros** — recalcula Segmento/Base/Top Cover; no borra extras.
- **Confirmar sugerencia** — `sugerido=false` + escribe aprendizaje del rol activo.
- **Quitar seleccionado / Vaciar rol**
- **Listo — publicar**

Colores: **morado** = `sugerido`, **azul** = confirmado. Tras confirmar, refrescar el resaltado.

Si el rol ya se confirmó en esta sesión y el usuario vuelve a confirmar, preguntar si **reemplaza** la iteración (`reemplazar=True`) o deja la memoria anterior.

---

## 5. Propuesta de muros (geometría)

Unidades del motor original: **centímetros** (Inventor). Si tu CAD está en mm, escala holguras ×10.

Constantes:

```
HOLGURA_CM            = 1.5     # soldadura: las placas no se intersecan
TOLERANCIA_CONTACTO   = 0.005   # 0,05 mm — accesorio “toca” la placa
UMBRAL_HORIZONTAL     = 0.35    # |n·up| alto → tapa/base; bajo → muro
UMBRAL_ALINEACION     = 0.72    # la normal debe alinearse con el eje del rol
ARRIBA_DE_PIE         = (0, 1, 0)   # +Y = arriba del modelo
```

### 5.1 Entrada

- Cara frontal capturada: `front_face_normal` (hacia el espectador o se corrige) y `face_point`.
- Hasta ~12 piezas más grandes por área de caja.
- De cada una: caja AABB, centro, normal de la cara plana más grande, área.

Las normales se **orientan hacia afuera** del centroide del conjunto de placas. El eje frente se aplana contra +Y y se snap al eje mundo más cercano (X/Y/Z).

Si el punto de la cara queda *detrás* del centroide, se invierte el frente.

### 5.2 Clasificación (`clasificar_placas`)

1. Separar **muros** (normal casi horizontal) y **tapas** (normal casi vertical).
2. Quedarse con placas grandes (≥ 18 % del área máxima; si hay menos de 4, las 6 mayores).
3. **Segmento_1** = muro cuya normal apunta más al frente (`dot ≥ 0.72`).
4. **Segmento_3** = muro opuesto (`dot` con el frente `< -0.72`), el más atrás a lo largo de ese eje.
5. **Segmento_2** = mejor alineado con `izquierda = normalize(frente × arriba)`.
   En este producto, con frente hacia el espectador y +Y arriba, **izquierda es la izquierda de quien mira**.
6. **Segmento_4** = derecha (`-izquierda`).
7. Validar que 2 y 4 estén cerca (AABB + holgura) del 1; si no, se descartan. Igual 2 y 4 respecto del 3.
8. **Base** = tapa más baja a lo largo de +Y; **Top_Cover** = la más alta, si hay al menos dos.

Si no hay 4 muros coherentes, no se cierra el rectángulo: el usuario sigue a mano. Pueden faltar roles; se avisa.

### 5.3 Accesorios por contacto

Para cada rol que sí cerró:

1. La placa entra con `placa_rol=true`.
2. Toda pieza que esté a ≤ 0,05 mm de esa placa entra en la bolsa, **excepto**:
   - otra placa de muro/tapa (`es_placa_muro` por nombre: `SEG 1`, `Segmento 2`, `Base`, `Top Cover`, `Tapa`, …);
   - una placa ya asignada a otro rol;
   - una pieza ya reclamada por otro segmento.
3. Distancia preferida: `MeasureTools.GetMinimumDistance`. Si falla, AABB con la misma tolerancia.
4. Todos los miembros de la propuesta llevan `sugerido=true`.

Después, `_dejar_en_un_segmento`: si un accesorio toca la placa de un rol, se quita de los demás.

### 5.4 Nombres que son placa, no accesorio

Normalizar: quitar ruta, `:\\`, prefijo de job (`261427_`), y comparar:

```
^(seg(mento)?|segment)[ _-]*[1-4]$
^base$
^(top[ _-]*cover|tapa( superior)?|cubierta)$
```

Si esas placas se tratan como “contacto”, el segmento 2 y el 4 se cuelan dentro del 1 y del 3 solo porque se tocan en las esquinas.

---

## 6. Autoaprendizaje

Archivo (Windows):

```
%LOCALAPPDATA%\VisorPlanos\aprendizaje\roles.json
```

Si no hay `LOCALAPPDATA`: `~/.visor_planos/aprendizaje/roles.json`.

Puedes cambiar la ruta; el esquema no.

### 6.1 Token de pieza

No se guarda la ruta completa. Se guarda un **token** del stem:

1. Si el texto es ruta (`\` `/` o `C:`), usar solo el nombre de archivo.
2. Cortar en el primer `:` *después* de quitar la ruta (`SEG 1:1` → `SEG 1`).
3. Quitar prefijo de job `^\d+[_\- ]+`.
4. `casefold`, no alfanumérico → `_`, recortar `_`.
5. Descartar tokens de menos de 3 caracteres.

Así `C:\...\261427_SEG 1.ipt` y `SEG 1:1` dan el mismo token `seg_1`.

### 6.2 Esquema

```json
{
  "tank": {
    "Segmento_1": {
      "incluir": ["seg_1", "brace_front"],
      "excluir": ["nameplate"]
    },
    "Base": {
      "incluir": ["base_plate"],
      "excluir": []
    }
  }
}
```

La clave de primer nivel es `sesion.producto` en minúsculas (`tank`, `compartment`, `gabinetes`, …). Cada producto tiene su memoria.

### 6.3 Al confirmar (`registrar_sesion`)

Se compara la bolsa **actual** con `sugerencia_tokens` (foto al proponer):

- Quedó en la bolsa → va a `incluir`; si estaba en `excluir`, se saca.
- Estaba en la propuesta y el usuario la quitó → va a `excluir`; si estaba en `incluir`, se saca.

`solo_rol`: el botón Confirmar guarda solo el rol activo.  
`reemplazar=True`: tira incluir/excluir de esos roles y escribe solo la selección de ahora.

No se escribe nada si no hay tokens actuales ni propuestos.

### 6.4 Al volver a proponer (`aplicar_a_sesion`)

1. **Excluir:** se quitan de la bolsa los miembros cuyo token está en `excluir` de ese rol.
2. **Incluir:** se buscan en el ensamble actual piezas con ese token y se meten en la bolsa *si*:
   - no están ya;
   - `en_contacto(rol, ocurrencia)` es verdadero (tocan la placa de *este* modelo);
   - no están ya en otro rol (salvo que el otro ítem sea `placa_rol`).

Un nombre confirmado en el Segmento 2 **no** se sugiere ahí si en este tanque la pieza está en otro muro.

Tras aplicar, se recalcula `sugerencia_tokens = foto_bolsas(sesion)` para el próximo delta.

---

## 7. Publicación (contrato con el generador de planos)

`roles_seleccionados` (un objeto por rol ocupado):

```json
{
  "Segmento_1": {
    "nombre_ocurrencia": "SEG 1:1",
    "ruta_archivo": "C:\\modelos\\SEG 1.iam",
    "miembros": [ { "nombre_ocurrencia": "...", "ruta_archivo": "..." } ]
  }
}
```

Extras: `Extra_2`, `rol_padre`: `"Segmento_1"`.

El árbol `estructura` replica ocurrencias con `rol`, `path`, `accesorios`. El generador de DWG **no vuelve a preguntar**; consume este JSON.

---

## 8. Interfaz CAD que debe implementar el otro proyecto

La lógica de este archivo no llama a Inventor. El host debe dar:

```python
class HostCAD(Protocol):
    def piezas_del_ensamble(self) -> list[Any]: ...
    def caja(self, pieza) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None: ...
    def cara_plana_mayor(self, pieza) -> tuple[Any, float] | None: ...  # (cara, área)
    def normal_cara(self, cara) -> tuple[float, float, float] | None: ...
    def distancia(self, a, b) -> float | None: ...
    def miembro_desde_pieza(self, pieza) -> dict: ...
    def resaltar(self, bolsas: dict, rol_activo: str) -> None: ...
    def pick_ocurrencia(self) -> Any | None: ...
```

`caja` = AABB en espacio de ensamble.  
`distancia` = mínimo entre cuerpos; si no hay, usar AABB + tolerancia.

---

## 9. Código portable (copiar a tu proyecto)

Independiente de Inventor. Entrada: placas `{normal, centro, caja, area}` y vectores frente/arriba.

```python
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

ROLES_MURO = (
    "Segmento_1",
    "Segmento_2",
    "Segmento_3",
    "Segmento_4",
    "Base",
    "Top_Cover",
)
ROLES_PUBLICAR = ROLES_MURO + ("Lifting_Lug", "Jacking_Pad", "Componentes")

HOLGURA = 1.5
TOLERANCIA_CONTACTO = 0.005
UMBRAL_HORIZONTAL = 0.35
UMBRAL_ALINEACION = 0.72
_PREFIJO_JOB = re.compile(r"^\d+[_\- ]+")
_NOMBRE_MURO = re.compile(
    r"^(?:seg(?:mento)?|segment)[\s_\-]*[1-4]$"
    r"|^(?:base)$"
    r"|^(?:top[\s_\-]*cover|tapa(?:[\s_\-]*superior)?|cubierta)$",
    re.IGNORECASE,
)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v):
    length = math.sqrt(_dot(v, v))
    if length < 1e-9:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)


def _aplanar(v, arriba):
    return _norm(_sub(v, _scale(arriba, _dot(v, arriba))))


def es_placa_muro(texto: str) -> bool:
    cola = str(texto or "").replace("\\", "/").split("/")[-1].split(":")[0].strip()
    cola = _PREFIJO_JOB.sub("", cola)
    return bool(_NOMBRE_MURO.match(cola))


def cajas_cerca(a, b, holgura=HOLGURA) -> bool:
    for eje in range(3):
        if b[1][eje] < a[0][eje] - holgura or b[0][eje] > a[1][eje] + holgura:
            return False
    return True


def clasificar_placas(placas: list[dict], frente, arriba) -> dict[str, dict]:
    """Asigna placas grandes a Segmento_1..4, Base y Top_Cover."""
    frente_n = _aplanar(frente, arriba)
    arriba_n = _norm(arriba)
    if frente_n is None or arriba_n is None or not placas:
        return {}
    izquierda = _norm(_cross(frente_n, arriba_n))
    if izquierda is None:
        return {}
    derecha = _scale(izquierda, -1.0)

    muros, tapas = [], []
    for placa in placas:
        normal = _norm(tuple(placa["normal"]))
        if normal is None:
            continue
        vertical = abs(_dot(normal, arriba_n))
        if vertical >= 1.0 - UMBRAL_HORIZONTAL:
            tapas.append(placa)
        elif vertical <= UMBRAL_HORIZONTAL:
            muros.append(placa)
    if not muros:
        return {}

    area_max = max(float(item["area"]) for item in muros)
    grandes = [item for item in muros if float(item["area"]) >= area_max * 0.18]
    if len(grandes) < 4:
        grandes = sorted(muros, key=lambda item: float(item["area"]), reverse=True)[:6]

    def mejor(eje, signo):
        orden = sorted(
            grandes,
            key=lambda item: signo * _dot(_norm(tuple(item["normal"])) or (0, 0, 0), eje),
            reverse=True,
        )
        if not orden:
            return None
        ganador = orden[0]
        normal = _norm(tuple(ganador["normal"])) or (0, 0, 0)
        if signo * _dot(normal, eje) < UMBRAL_ALINEACION:
            return None
        return ganador

    roles: dict[str, dict] = {}
    frente_placa = mejor(frente_n, 1.0)
    if frente_placa is None:
        return roles
    roles["Segmento_1"] = frente_placa
    usados = {id(frente_placa)}
    atras = [
        item
        for item in grandes
        if id(item) not in usados
        and _dot(_norm(tuple(item["normal"])) or (0, 0, 0), frente_n) < -UMBRAL_ALINEACION
    ]
    if atras:
        centro_1 = tuple(frente_placa["centro"])
        atras.sort(key=lambda item: _dot(_sub(tuple(item["centro"]), centro_1), frente_n))
        roles["Segmento_3"] = atras[0]
        usados.add(id(atras[0]))

    lateral = [item for item in grandes if id(item) not in usados]
    derecha_placa = izquierda_placa = None
    mejor_der = mejor_izq = -1.0
    for item in lateral:
        normal = _norm(tuple(item["normal"])) or (0, 0, 0)
        izq, der = _dot(normal, izquierda), _dot(normal, derecha)
        if der > mejor_der:
            mejor_der, derecha_placa = der, item
        if izq > mejor_izq:
            mejor_izq, izquierda_placa = izq, item
    if izquierda_placa is not None and mejor_izq >= UMBRAL_ALINEACION:
        roles["Segmento_2"] = izquierda_placa
    if (
        derecha_placa is not None
        and derecha_placa is not izquierda_placa
        and mejor_der >= UMBRAL_ALINEACION
    ):
        roles["Segmento_4"] = derecha_placa

    if "Segmento_1" in roles and "Segmento_2" in roles and "Segmento_4" in roles:
        caja_1 = roles["Segmento_1"]["caja"]
        if not (
            cajas_cerca(caja_1, roles["Segmento_2"]["caja"])
            and cajas_cerca(caja_1, roles["Segmento_4"]["caja"])
        ):
            roles.pop("Segmento_2", None)
            roles.pop("Segmento_4", None)
    if "Segmento_3" in roles and "Segmento_2" in roles and "Segmento_4" in roles:
        caja_3 = roles["Segmento_3"]["caja"]
        if not (
            cajas_cerca(caja_3, roles["Segmento_2"]["caja"])
            and cajas_cerca(caja_3, roles["Segmento_4"]["caja"])
        ):
            roles.pop("Segmento_3", None)

    if tapas:
        area_tapa = max(float(item["area"]) for item in tapas)
        candidatas = [item for item in tapas if float(item["area"]) >= area_tapa * 0.25]
        candidatas.sort(key=lambda item: _dot(tuple(item["centro"]), arriba_n))
        if candidatas:
            roles["Base"] = candidatas[0]
            if len(candidatas) > 1 and candidatas[-1] is not candidatas[0]:
                roles["Top_Cover"] = candidatas[-1]
    return roles


def token_de_miembro(miembro: dict | str) -> str:
    if isinstance(miembro, dict):
        bruto = str(miembro.get("ruta_archivo") or miembro.get("nombre_ocurrencia") or "")
    else:
        bruto = str(miembro or "")
    texto = bruto.strip().strip('"')
    if re.search(r"[\\/]", texto) or re.match(r"^[A-Za-z]:", texto):
        texto = Path(texto).name
    stem = Path(texto.split(":", 1)[0]).stem
    stem = _PREFIJO_JOB.sub("", stem)
    return re.sub(r"[^a-z0-9]+", "_", stem.casefold()).strip("_")


def ruta_aprendizaje() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    raiz = Path(local) / "VisorPlanos" / "aprendizaje" if local else Path.home() / ".visor_planos" / "aprendizaje"
    return raiz / "roles.json"


def cargar_aprendizaje() -> dict:
    path = ruta_aprendizaje()
    if not path.is_file():
        return {}
    try:
        datos = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def guardar_aprendizaje(datos: dict) -> Path:
    path = ruta_aprendizaje()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def foto_bolsas(bolsas: dict, roles=None) -> dict[str, list[str]]:
    foto = {}
    for rol in roles or ROLES_MURO:
        tokens = []
        for miembro in bolsas.get(rol) or []:
            if not isinstance(miembro, dict):
                continue
            token = token_de_miembro(miembro)
            if len(token) < 3 or token in tokens:
                continue
            tokens.append(token)
        foto[rol] = tokens
    return foto


def registrar_sesion(producto: str, bolsas: dict, propuesto: dict, solo_rol=None, reemplazar=False):
    """Delta bolsa vs propuesta → incluir / excluir. Devuelve la ruta o None."""
    roles = [solo_rol] if solo_rol else [rol for rol in ROLES_PUBLICAR if rol in bolsas]
    if not roles:
        return None
    actual = foto_bolsas(bolsas, roles)
    if not any(actual.values()) and not any(propuesto.get(rol) for rol in roles):
        return None
    datos = cargar_aprendizaje()
    bucket = datos.setdefault(producto.casefold() or "default", {})
    if not isinstance(bucket, dict):
        bucket = {}
        datos[producto.casefold() or "default"] = bucket
    for rol in roles:
        info = bucket.get(rol) if isinstance(bucket.get(rol), dict) else {}
        incluir = [] if reemplazar else [str(x) for x in info.get("incluir") or [] if str(x)]
        excluir = [] if reemplazar else [str(x) for x in info.get("excluir") or [] if str(x)]
        quedaron = set(actual.get(rol) or [])
        estaban = set(propuesto.get(rol) or [])
        for token in quedaron:
            if token not in incluir:
                incluir.append(token)
            if token in excluir:
                excluir.remove(token)
        for token in estaban - quedaron:
            if token not in excluir:
                excluir.append(token)
            if token in incluir:
                incluir.remove(token)
        bucket[rol] = {"incluir": incluir, "excluir": excluir}
    return guardar_aprendizaje(datos)


def aplicar_exclusiones(producto: str, bolsas: dict) -> list[str]:
    memoria = cargar_aprendizaje().get(producto.casefold() or "default")
    if not isinstance(memoria, dict):
        return []
    notas = []
    for rol, bolsa in list(bolsas.items()):
        info = memoria.get(rol) if isinstance(memoria.get(rol), dict) else {}
        excluir = set(info.get("excluir") or [])
        if not excluir:
            continue
        antes = len(bolsa)
        bolsas[rol] = [
            m for m in bolsa
            if not isinstance(m, dict) or token_de_miembro(m) not in excluir
        ]
        if len(bolsas[rol]) != antes:
            notas.append(f"{rol}: se omitieron piezas que quitaste antes")
    return notas
```

Para **recuperar inclusiones** necesitas el host CAD: recorrer piezas del ensamble, fabricar el dict miembro y exigir `en_contacto(rol, pieza)`. La regla está en la sección 6.4.

---

## 10. Cómo cablearlo en el otro proyecto (checklist)

1. Crear `bolsas` vacías para los roles del producto.
2. Capturar cara frontal (normal + punto). Sin eso no hay propuesta.
3. Recolectar piezas → cajas → placas (cara plana mayor).
4. Orientar normales hacia afuera; clasificar; llenar bolsas + contactos.
5. `aplicar_exclusiones` y luego inclusiones con contacto.
6. Guardar `sugerencia_tokens = foto_bolsas(bolsas)`.
7. Pintar listas; morado / azul.
8. Al confirmar: quitar `sugerido` y `registrar_sesion(...)`.
9. Al publicar: serializar bolsas a `roles_seleccionados` (sin `objeto_com`).

Prueba mínima sin CAD: arma 6 placas en un prisma (frente/atrás/izq/der/piso/techo) y comprueba que `clasificar_placas` devuelva los 6 roles. Luego confirma, quita una pieza, vuelve a proponer y verifica que el aprendizaje la excluya.

---

## 11. Lo que no debes copiar a ciegas

- `interactive_selector.py` / `flat_part_roles.py` están atados a COM de Inventor (`CommandManager.Pick`, `HighlightSet`, proxies `*_FLAT_L2_PROXY.iam`).
- El generador DWG (`drawing_engine`) **consume** el JSON; no selecciona.
- El aprendizaje de *hojas* del visor (`sheet_learning.py`, escalas y cotas) es **otro** módulo. Este archivo es solo el selector de listas L2.
