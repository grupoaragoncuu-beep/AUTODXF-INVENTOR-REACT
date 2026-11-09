# Corte — control (abierta)

Siguiente fase después de Cotas por referencia (cerrada).

Pieza **plana** (el IPT, no el tanque 3D). Un JPG por cota a orilla: X / Y / Ø / SLOT / CUT / LENGTH.

## Destino

`JPG/{job}/PIEZAS_ACOTADAS/{cara}/Corte/{tipo}/…jpg`

La `{cara}` debe ser el muro de las **6 placas** donde vive **esa instancia** (misma regla que referencia). No agrupar por nombre de `.ipt` si hay copias en varios muros.

## Código

- `python/acotacion_run.py`: `_jpg_cara`, `_jobs_tanque` fase CORTE, `_dir_tank_proceso`.
- Clases: Maquinados Tank, Corte, Maquinado, Accesorios Sueltos (ver `config/acotacion-jpg.json` flujo TANQUE).
- No se cotan las placas-ancla de muro aquí si van a Doblado.

## Hallazgo 261503 (primer arreglo)

`Tank-Base` salió bajo `PIEZAS_ACOTADAS/SEGM3/Corte` porque `mapa_ipt_cara` asigna **ruta de archivo → una cara**. Hay que clasificar por plano de instancia, como en referencia.

## Maquinado

Pieza clasificada Maquinado no usa el corte 2D (X/Y desde 0,0). `python/maquinado_geo.py` lee el sólido:

- Redonda: vista por el eje. Cada diámetro, el barreno que atraviesa (`PASADO`), el largo de cada escalón y el largo total. Si hay barrenos en círculo, `BCD` y `TYP`.
- Placa u otra forma: vista frontal. Ancho, alto, espesor, diámetro de barreno y distancia entre centros. Sin origen.
- Al lado de los JPG, el sólido en STEP (`python/step_inventor.py`).

## Doblado (en curso)

Las placas de segmento no se giran para poner el lado largo en horizontal. UV = Y mundo arriba, 0,0 = inferior izquierda de la placa en el tanque (`landscape=False` + `_basis_muro_part`).

La morfología de la cara no sale de los lazos COM ni de un rectángulo de bbox. Sale de la vista alámbrica del **.ipt de la lámina** (`python/doblado_geo.py`): `CalculateStrokes` + `CalculateFacets`, igual que Cotas por referencia, pero solo el sólido de la chapa. Los cuerpos chicos del mismo archivo (parche, base) no entran, y tampoco las ocurrencias ensambladas encima. Un lazo interno es hueco solo si la piel no tapa su interior; si sigue siendo metal, es marcaje. Junto a los JPG quedan `VISTA_ALAMBRICA.jpg` y el STEP de la pieza. Si el snapshot falla, se usa la cara COM de antes.

Un lazo interno es **un** hueco. Si el bbox del lazo es recorte 2D (ambos lados > 2.4×Ø de los arcos), esos arcos son radios de CUT, nunca barrenos. Cada barreno real es su propio lazo. Caso ancla: `261429_S2` ventana 27.50×6.00 (no 4×Ø1.00). La ventana chica de segmento (≈5.5×2.4) también es CUT: el filtro de “cortes ensamblados” la tiraba y el JPG quedaba en blanco. Pruebas: `python/test_huecos_lazo.py`, `python/test_doblado_geo.py`.

## Cotas del JPG (2026-11-03)

- El rótulo cabe entero en el JPG: la caja de texto usa la tinta real de la fuente y el margen crece con el rótulo.
- Rectángulo y slot: dos JPG, `LENGTH_…` y `WIDTH_…`. No va la vista con largo×ancho juntos.
- El nombre de una cota X/Y es la posición (`X_14.94`). No lleva el tamaño del hueco (`_C18.50x6.00`, `_D…`, `_S…`).

## Mientras se prueba referencia en el módulo

Publicar referencia sigue pendiente de contraseña. Este arreglo de Doblado no espera esa publicación.
