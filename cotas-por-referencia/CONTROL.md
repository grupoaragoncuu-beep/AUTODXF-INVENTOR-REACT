# Cotas por referencia — CERRADA (2026-10-20) · motor geometría (2026-10-23)

Aceptada en VANTRAN 261503. El Módulo de Ingeniería genera las 6 caras con esta lógica.
Desde 2026-10-23 el motor por defecto es **geometría exacta** (`motor_vista: "geometria"`):
ya no se captura la pantalla de Inventor. El 8711 queda como respaldo (`motor_vista: "inventor_8711"`
o automático si el motor de geometría falla o no encuentra caras).

## Contrato visual (igual para ambos motores)

1. Carpetas `COTAS_POR_REFERENCIA / {SEGM1|SEGM2|SEGM3|SEGM4|TOP|BASE} / {tipo} / JPG` + `VISTA_ALAMBRICA.jpg` + `_camara.json`.
2. Vista de líneas sin ocultas. **No** malla Phong/gris 3D.
3. Cada placa de **frente** (eje del espesor). Y mundo arriba. No girar 90° por el lado largo.
4. Vista **desde fuera del tanque** (normal de la placa hacia afuera del centro del tanque).
5. Origen 0,0 = inferior izquierda (IL) de la piel exterior de la placa (si el muro tiene varias placas coplanares, de su unión).
6. Un JPG por cota: `XMIN`/`YMIN` (cajas) o `XCENTRO`/`YCENTRO` (círculos). TYP A/B/C si hay varias iguales.
7. No se cota la placa madre.

## Motor geometría

1. **Captura** (`python/referencia_snapshot.py`, único paso con Inventor). Por `.ipt` único:
   `CalculateStrokes` (aristas) + `CalculateFacets` (facetas) en cm de pieza, en caché por ruta+fecha
   (`%LOCALAPPDATA%/AutoDXF/geo_cache`). Por instancia: matriz, muro y placa desde la sesión de
   **Confirmar muros** (cruda, por `ruta_ocurrencia`). Se guarda en `COTAS_POR_REFERENCIA/_geometria.json.gz`.
2. **Cálculo** (`python/referencia_geo.py`, Python puro, sin Inventor):
   - Aristas = trazos encadenados, cortados en vértices de grado ≠ 2. Círculos/arcos por ajuste exacto
     (los vértices del trazo están sobre la curva). Un cuadrado no es círculo (paso angular ≤ 50°).
   - Marco: cara plana mayor de la placa (planos desde facetas), normal afuera, Y mundo arriba,
     plano exterior = cara paralela más externa, IL desde la piel exterior (sin pestañas).
   - Ancla del muro: placa confirmada de mayor área; sin placa confirmada, la lámina grande que más
     miembros de la bolsa tocan; TOP/BASE sin bolsa, lámina libre con normal ±Y.
   - Accesorio: huella exacta delante de la piel. Redondo si el círculo mayor paralelo a la placa llena
     ≥ 85 % y la huella es cuadrada (±15 %) → centro exacto; si no, mínimos X/Y exactos.
   - Barrera de muro por instancia: dueño = |altura| + 3×fuera del rectángulo (6 placas).
   - Piezas sin bolsa cuentan en la cara de la que son dueñas si tocan o cruzan la piel
     (su geometría llega a ≤ 0.3 cm) y caen dentro del rectángulo, aunque esa cara ya
     tenga otros accesorios confirmados. Una bolsa parcial no las esconde.
   - Vista: z-buffer de facetas + aristas visibles; cotas con el mismo dibujo que el 8711.
3. Fase REFERENCIA sola no republica `PIEZAS_ACOTADAS` ni repinta muros (el motor no toca el modelo).

Medido en 10000-1246 (636 instancias, 153 `.ipt`): fase REFERENCIA completa 34 s, 273 JPG, 6 muros.

## Barrera de muro (instancia, no .ipt)

El mismo archivo `.ipt` puede existir en varios segmentos. Cada **ocurrencia** va a **una** de las 6 placas:

- Distancia al plano de la placa + penalización si el centro cae **fuera del rectángulo** de esa cara.
- No basta el par de enfrente (S1↔S3, S2↔S4): un flange de S1 en la arista no se cota en S4.
- Piezas completamente detrás de la piel (dentro del tanque) no se cotan.

Ejemplo 261503: `Pipe Flange 1` y nipples viven en **SEGM1**, no en SEGM4.

## Código

| Qué | Dónde |
| --- | --- |
| Captura snapshot (Inventor) | `python/referencia_snapshot.py` |
| Marco, IL, rasgos, vista, JPG | `python/referencia_geo.py` |
| Dibujo de cotas / origen IL (compartido) | `python/caras_referencia.py` |
| Respaldo 8711 | `python/vista_hlr.py` + `python/caras_referencia.exportar_cara` |
| Bolsas / sesión | `python/roles_inventor.py` |
| El módulo llama | `acotacion_run.py` → `_motor_referencia()` → `JPG/{job}/COTAS_POR_REFERENCIA` |
| Pruebas | `python/test_referencia_geo.py` |

## Regenerar local

Inventor con el `.iam` del tanque activo:

```
python cotas-por-referencia/exportar_vista.py
```

Sin Inventor, desde un snapshot guardado:

```
python cotas-por-referencia/exportar_vista.py "JPG/{job}/COTAS_POR_REFERENCIA/_geometria.json.gz"
```

Salida de laboratorio: `cotas-por-referencia/salidas/`.

## No regresar

- No volver a malla `mesh_view` para estos JPG.
- No clasificar por nombre de archivo ni por "más cerca del par opuesto" solamente.
- No mirar desde adentro del tanque (se mezclan S1 y S3).
- No medir cotas sobre píxeles: siempre desde la geometría del snapshot.
