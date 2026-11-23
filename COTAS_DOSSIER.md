# Cotas en `public.cotas_dossier`

Una fila por JPG. La base es NestingPro (`nestingpro_db`). La fila se actualiza cuando coinciden `job` y `ruta`; si esa pareja no existe, se inserta una nueva.

El share del job es:

```text
{PRODUCTO}\{CLIENTE}\{JOB}\DOSSIER FILES\JPGS\
```

`ruta` se guarda en UNC:

```text
\\192.168.2.80\Users\Administrator\Desktop\Grupo Arga Metals\ARGA METALS CORPORATE SYSTEM\{PRODUCTO}\{CLIENTE}\{JOB}\DOSSIER FILES\JPGS\...
```

Cliente y producto salen del job elegido en el dossier. Sin esa elección, `cliente` queda `SIN_CLIENTE`.

## Quién escribe la fila

| Origen | Función | Cuándo |
| --- | --- | --- |
| Corte, doblado, maquinado, armado, cotas por referencia | `alimentar_bd` en `python/cotas_dossier.py` | Al cerrar Acotación JPG |
| Soldadura | `alimentar_weld` | Al publicar los JPG de `JPGS\Weld` |

Acotación JPG prefiere el registro de Planos (`paths.cotasProject` → `cotas_dossier_registro.publicar_y_sincronizar_dossier`). Si ese proyecto no está, este repo copia el árbol a `DOSSIER FILES\JPGS` y escribe la fila.

Los `.stp` no entran. Una carpeta de Almacén tampoco.

Una corrida completa de soldadura deja las filas de los cordones publicados y quita las de `clasificacion = 'Weld'` de ese job cuya ruta apunta a la misma carpeta y cuyo archivo ya no está.

## Columnas

| Columna | Valor |
| --- | --- |
| `cliente` | Cliente del job elegido |
| `producto` | Producto del job elegido |
| `job` | Número de job |
| `type` | `TYP` en todas las filas |
| `cantidad_spoteos` | `1` |
| `nombre_archivo` | Nombre del JPG, con extensión |
| `ruta` | UNC canónica del JPG |
| `clasificacion` | Proceso, según la carpeta (tabla de abajo) |
| `seleccionadas` | `si` o `no`. El VSM de TANKS muestra la fila solo con `si` |
| `valores` | Vacío en estas escrituras |

`type = TYP` es la columna de la fila. El texto `TYP` dentro del nombre de un JPG de referencia es otra cosa: varias piezas comparten esa cota.

## Nombre del JPG

Los caracteres `<>:"/\|?*` del nombre se cambian por `_`.

### Pieza (corte, doblado, cara de maquinado)

```text
{job}__{stem del .ipt}__{marca}.jpg
```

Carpeta:

```text
PIEZAS_ACOTADAS\{cara}\{proceso}\{stem}\
```

`{cara}` es el muro de esa instancia (`SEGM1`–`SEGM4`, `TOP`, `BASE`, y el resto de las seis placas). `{proceso}` es `Corte`, `Doblado`, `Maquinado` o `Armado`.

La marca sale de la cota, con dos decimales:

| Marca | Cota |
| --- | --- |
| `X_1.25` | Orilla en X |
| `Y_3.50` | Orilla en Y |
| `HOLE_0.50` | Diámetro |
| `LENGTH_4.00` y `WIDTH_1.00` | Largo y ancho de un slot o un corte. Van en dos JPG |
| `LENGTH_24.00` | Largo de la placa |

Si dos cotas de la misma pieza producen el mismo nombre, la segunda queda `…_2`, la tercera `…_3`.

Doblado agrega, en la misma carpeta de la pieza:

| Marca | Cota |
| --- | --- |
| `ID_8.00` | Alto del perfil |
| `THK_0.13` | Espesor |
| `LEG_1.50` | Largo de pata |

Maquinado de sólido, cuando hay morfología:

| Marca | Cota |
| --- | --- |
| `D_1.00` | Diámetro |
| `D_1.00_PASADO` | Diámetro pasante |
| `D_0.50_TYP` | Mismo diámetro en varios centros |
| `STEP_0.25_D1.00` | Alto del escalón y su diámetro |
| `L_6.00` | Largo de revolución |
| `W_4.00`, `H_2.00`, `THK_0.25` | Placa: ancho, alto, espesor |

Ejemplo:

```text
PIEZAS_ACOTADAS\SEGM1\Corte\261079_Tank-Wall\261079__261079_Tank-Wall__X_1.25.jpg
```

En un board de cobre el tramo del medio no es el stem: es `{código del board}-{F o B}-{cola de la pieza}`.

### Cotas por referencia

```text
COTAS_POR_REFERENCIA\{cara}\{tipo}\{job}__{tipo}__{marca}.jpg
```

`{cara}` es `TOP`, `SEGM1`, `SEGM2`, `SEGM3`, `SEGM4` o `BASE`. `{tipo}` es el tipo de hijo en esa cara.

| Marca | Cota |
| --- | --- |
| `XMIN_12` / `YMIN_4.5` | Esquina del hijo respecto al origen IL |
| `XCENTRO_6` / `YCENTRO_3` | Centro, cuando el hijo es circular |
| `XMIN_TYP_12` | Varios hijos comparten ese valor |

El número sale entero cuando cae en entero; si no, hasta tres decimales. Cada cara publica además `VISTA_ALAMBRICA.jpg`, sin el prefijo del job.

### Armado

Un solo `_` entre tramos, dentro de `PIEZAS_ACOTADAS\Armado\...`:

```text
{job}_{kit}_{vista}_{X o Y}_{valor}.jpg
{job}_{hijo}_{marca de maquinado}.jpg
```

La posición de cada hijo respecto al ancla usa `X_1.25` o `Y_3.50`. El sólido de cada hijo usa las marcas de maquinado (`D_`, `STEP_`, `L_`, `W_`, `H_`, `THK_`).

### Soldadura

```text
JPGS\Weld\{cara}\{titulo}.jpg
```

El título `SEGM1 / BASE` queda `SEGM1_BASE.jpg`. `{cara}` es `SEGM1`–`SEGM4`, `BASE` o `TOP`; si el cordón no trae una de esas, el JPG cae en la carpeta `Weld`. Un título repetido queda `SEGM1_BASE_2.jpg`.

## Qué queda en `clasificacion`

Se ignora la cara y se lee la carpeta de proceso.

| La ruta contiene | `clasificacion` |
| --- | --- |
| `\COTAS_POR_REFERENCIA\` | `COTAS_POR_REFERENCIA` |
| `\ENSAMBLES_INDEPENDIENTES\` | `ENSAMBLES_INDEPENDIENTES` |
| `\Weld\` (publicación de soldadura) | `Weld` |
| `Doblado` y `Busbar` | `Doblado/Busbar` |
| `Doblado` | `Doblado/Metal` |
| `Maquinado` y `Busbar` | `Corte/Maquinado/Corte Busbar` |
| `Maquinado` | `Maquinado` |
| `Corte` o `Armado` de tanque | `Corte` |
| El árbol largo de gabinete (`Corte/Plasma y Laser/Corte metal`, `Estañado Busbar`, `SIN CLASIFICACION`, …) | Ese mismo texto |

En un tanque la carpeta es `PIEZAS_ACOTADAS\{cara}\Corte`. La clasificación que se guarda es `Corte`.

## Qué muestra el VSM (`seleccionadas`)

| Condición | `seleccionadas` | Sección |
| --- | --- | --- |
| Referencia | `si` | Final Dimensions |
| `clasificacion = Corte` | `si` | Tank Assembly |
| Doblado de metal | `si` | Bending |
| Maquinado de metal | `si` | Tank Machining |
| Soldadura | `si` | — |
| Bajo `Corte`, y la carpeta siguiente no es `Plasma y Laser` ni `Maquinado` | `no` | — |
| El resto del árbol de gabinete | `si` | — |

## Cómo rastrear una cota

La pareja que identifica la fila es `job` + `ruta`. Volver a publicar el mismo JPG actualiza esa fila. Mover el JPG de carpeta cambia la ruta y deja una fila nueva.

Todo el job:

```sql
SELECT id, clasificacion, seleccionadas, nombre_archivo, ruta
FROM public.cotas_dossier
WHERE job = '261079'
ORDER BY clasificacion, nombre_archivo;
```

Una pieza. El stem va entre los dos `__`:

```sql
SELECT nombre_archivo, clasificacion, ruta
FROM public.cotas_dossier
WHERE job = '261079'
  AND nombre_archivo ILIKE '261079__261079_Tank-Wall__%';
```

Una marca. El tercer tramo es la cota:

```sql
SELECT nombre_archivo, ruta
FROM public.cotas_dossier
WHERE job = '261079'
  AND nombre_archivo ILIKE '%__X_1.25.jpg';
```

Una cara de tanque. La cara está en la ruta, no en el nombre:

```sql
SELECT nombre_archivo, clasificacion
FROM public.cotas_dossier
WHERE job = '261079'
  AND replace(ruta, '/', '\') ILIKE '%\PIEZAS_ACOTADAS\SEGM1\Corte\%';
```

Referencia de una cara:

```sql
SELECT nombre_archivo, ruta
FROM public.cotas_dossier
WHERE job = '261079'
  AND clasificacion = 'COTAS_POR_REFERENCIA'
  AND replace(ruta, '/', '\') ILIKE '%\COTAS_POR_REFERENCIA\TOP\%';
```

Soldadura del job:

```sql
SELECT nombre_archivo, ruta
FROM public.cotas_dossier
WHERE job = '261079'
  AND clasificacion = 'Weld'
ORDER BY nombre_archivo;
```

Lo que el VSM de TANKS enseña:

```sql
SELECT clasificacion, nombre_archivo, ruta
FROM public.cotas_dossier
WHERE job = '261079'
  AND seleccionadas = 'si'
ORDER BY clasificacion, nombre_archivo;
```

`dossier_arbol.borrar_filas` quita las filas de un producto, cliente y job por la ruta, junto con el vaciado de `DOSSIER FILES\JPGS`.
