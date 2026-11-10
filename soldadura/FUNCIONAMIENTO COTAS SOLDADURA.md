# Cotas de soldadura — funcionamiento

Documento para otra conversación de Cursor. Leer esto junto con `soldadura/CONTROL.md` y `soldadura/control.json` antes de cambiar el módulo.

Nombre en la barra: **Weld Anotation**. El usuario lo llama Cotas de soldadura.

## Qué es

Publica la soldadura del tanque abierto en Inventor. No guarda el `.iam`. No abre plano, hoja, cajetín, DWG ni IDW. No usa el add-in de AWIS ni el de Inventor.

Inventor se queda abierto solo como fuente de geometría, igual que Acotación JPG. Python lee el ensamble por COM, dibuja los filetes 3D y, en un paso aparte, compone un JPG por cordón.

La cadena C# de la carpeta `Cotas de Soldadura` queda solo como referencia de las reglas (ISO, lado interno o externo, símbolo). No se vuelve a abrir un drawing para publicar la foto.

## Orden que el usuario aprobó

1. **Confirmar muros** en Acotación JPG, antes de generar. Sin esas caras el proceso se detiene con «Confirma los muros en Acotación JPG».
2. **Generar cordones 3D.** Primero el tanque pasa a gris. Después se crean los filetes: naranja en accesorio, azul en la costura hermética. En este paso no hay JPG.
3. **Nomenclatura y símbolo.** Se abre una ventana flotante, independiente del módulo, titulada `Nomenclatura`. Ahí se elige el cordón y se ajusta Hermético o Accesorio, cateto, paso, 2 lados y TYP.
4. Al cerrar esa ventana, el módulo lista cada cordón con clasificación, símbolo y longitud. La lista se refresca sola.
5. **Generar JPGs.** Un JPG por cordón. Si `DOSSIER FILES\JPGS` no existe, se crea. Dentro queda la carpeta `Weld`.

La ventana flotante también tiene **Generar JPGs** al fondo. Hay que cerrarla y volver a pulsar **Nomenclatura** si el código de la interfaz cambió: la ventana ya abierta no recarga sola.

## Destino de los JPG

```
{raiz}\{producto}\{cliente}\{job}\DOSSIER FILES\JPGS\Weld\{SEGM1|SEGM2|SEGM3|SEGM4|BASE|TOP}\{cordon}.jpg
```

Ejemplo usado en prueba:

```
X:\ARGA METALS CORPORATE SYSTEM\TANKS\PRUEBAS MODULO\TANK WELDS\DOSSIER FILES\JPGS\Weld
```

La ruta sale del job elegido en el dossier (`config/dossier_eleccion.json`), no de una carpeta local suelta. Función: `carpeta_weld` en `python/weld_anotation.py`. Si faltan `DOSSIER FILES`, `JPGS` o `Weld`, `ensure_dir` las crea. El job tiene que estar elegido; si no, el mensaje pide elegirlo.

Cada JPG lleva la cara, el detalle, la isométrica y el símbolo (cateto, largo-paso, TYP, uno o dos lados), en fondo blanco.

## Qué tiene que cumplir el modelo

- La ventana activa de Inventor es el `.iam` del tanque, ya guardado. Una pieza, un plano o un subensamble de fondo no sirven. Si no hay ensamble: «Abre el ensamble del tanque en Inventor.»
- Job elegido en el dossier de la barra. Sin job no arranca. Con el job de otro tanque, las fotos caen en la carpeta de ese otro job.
- Seis muros confirmados para **ese** archivo, en `config/roles_sesion.json`: `BASE`, `TOP`, `SEGM1`, `SEGM2`, `SEGM3`, `SEGM4`. Cada cara lleva una placa (`placa_rol`) que sigue existiendo en el ensamble, con el mismo nombre de ocurrencia.
- Las cuatro paredes van en circuito: `SEGM1`–`SEGM2`–`SEGM3`–`SEGM4`–`SEGM1`. `BASE` cierra contra las cuatro. Dos caras opuestas con nombres seguidos no forman costura. Si la tapa se llama lid, cover o tapa y no es cellar, no lleva cordón. Una tapa con cellar, o sin ese nombre, sí cierra contra las cuatro. El filete de un accesorio va en la cara de la placa que la pieza toca, la que queda expuesta para la cota. En un cáncamo solo entra el borde exterior que apoya en el segmento: la ranura de la cadena y la horquilla no. En la base, una pieza apoyada encima no suelda la cara que iría al piso. Una solera colgada debajo se suelda en la esquina donde toca la placa; el canto de esa solera que iría al piso queda fuera. Si la pieza pintada ahora es un ensamble, cuenta como una sola pieza: el cordón es el borde donde ese ensamble toca su segmento. No se suelda placa interna con placa interna, ni un accesorio con otro accesorio. El azul queda entre muros. La esquina vertical se acota en SEGM2 o en SEGM4, así cada uno lleva sus dos esquinas más el cordón de la base. SEGM1 y SEGM3 no se quedan esas esquinas. El cordón azul con la base sigue en su propio segmento. El naranja es accesorio contra su segmento.
- Dos muros que se sueldan se miran cerca de 90° (el producto de las normales no pasa de 0.5), se acercan a menos de 80 mm y comparten al menos 20 mm de arista.
- Cada accesorio está en la cara donde va montado, no suprimido, y el apoyo mide al menos 8 mm. Si no, ese cordón no nace.
- La placa del muro tiene una cara plana grande (área mayor a 200 mm²). Si no la hay, se usa la caja de la pieza.

Los pares herméticos están fijos en `PARES` de `python/weld_juntas.py`. El generador llama `armar_juntas(..., holgura_mm=80)`.

## Símbolo automático

Hasta que el usuario lo edite, `simbolo()` en `python/weld_juntas.py` propone:

- Hermético contra `BASE` o `TOP`: `FILLET 6/8 mm 100-300 TYP` (dos lados).
- Hermético entre paredes: `FILLET 6 mm 100-300 TYP` (el otro cateto también es 6, dos lados).
- Accesorio corto, menos de 80 mm: `FILLET 3 mm 2SIDES TYP`.
- Accesorio medio, menos de 160 mm: `FILLET 5 mm 2SIDES`.
- Accesorio largo: `FILLET 6 mm TYP` (un lado).

Presets de la herramienta: 3 mm 2 lados TYP, 5 mm 2 lados, 6 mm TYP, 8 mm TYP, 6/8 mm 100-300, 6 mm 2 lados 100-300, 3 mm 2 lados 10-60. Catetos de taller: 3, 5, 6, 8. Pasos: continuo, 10-60, 100-300.

En un tanque (pulgadas) esa tabla no se publica. `aplicar_pauta_vantran` usa los dos planos Vantran: unión de paredes y de pared con base a 1/4" continuo; brida, niple, oil boss y tierra a 1/4"; cáncamo a 3/8"; marco de base a la placa a 5/16" completo por fuera y 5/16" 4-20 por dentro. Lo que el plano no nombra sigue con el cateto de taller. Un gabinete en milímetros no entra en esta pauta.

Lo editado queda en `config/weld_nomenclatura.json`, por ruta de ensamble. Un pase nuevo no pisa la clasificación ni el símbolo marcados como editados. El JPG usa el símbolo editado; si nadie lo editó, usa la pauta vigente.

## Cordones 3D

`python/weld_solido.py`.

- `descolorear`: pinta las piezas del tanque de gris `(188, 188, 188)`, aspecto `TanqueNeutro`, para que el naranja y el azul se lean. No pinta las ocurrencias `WELD_ANOTATION`.
- `construir`: borra los filetes del pase anterior y crea dos piezas insertadas en el ensamble, sin guardar:
  - `WELD_ANOTATION_NARANJA` — accesorios.
  - `WELD_ANOTATION_AZUL` — herméticos.
- Un cordón puede ser varios cuerpos (dos lados, tramos). El conteo de filetes es de cuerpos, no de filas de la tabla.
- El archivo del tanque queda sucio a propósito. No se guarda.

## Fotos

`python/weld_vista.py` toma tres vistas sombreadas del ensamble (cara, detalle, isométrica). Oculta el resto de las piezas y enciende solo el cordón de esa junta. `python/weld_jpg.py` compone el JPG.

Al cerrar la tanda, `mostrar_todos()` vuelve a encender **todos** los cuerpos de soldadura. Si no se hace, el ensamble se queda como la última foto: casi todos los filetes invisibles aunque las ocurrencias sigan ahí. Eso ya pasó y se corrigió.

## Interfaz

- Módulo: `ui/src/WeldAnotationPanel.tsx`, pestaña Weld Anotation.
  - **Generar cordones 3D** envía `fase: "cordon"`.
  - **Nomenclatura** abre la ventana flotante.
  - **Generar JPGs** envía `fase: "foto"`.
  - La tabla es de lectura: título, Hermético o Accesorio, símbolo, longitud.
- Ventana flotante: `ui/src/WeldCordonTool.tsx`, hash `#cordon`, título `Nomenclatura`. La abre `weld_tool_open` en `python/host.py`. Trae leer cordón, lista, clasificación, símbolo y **Generar JPGs**.
- El puente COM no puede vivir en el proceso de la ventana (WebView2 deja `GetActiveObject` inútil). `python/inventor_worker.py` con comando `weld` hace el trabajo. Progreso: `config/weld_anotation_progress.json`.

La barra que el usuario abre desde el proyecto carga `ui/dist`. Un cambio de interfaz no se ve hasta `pnpm build` en `ui/` y volver a abrir la ventana. Un cambio solo de Python sí entra en el siguiente clic, porque el worker arranca de nuevo.

## Archivos

| Pieza | Dónde |
| --- | --- |
| Orquestación, carpeta Weld, fases | `python/weld_anotation.py` |
| Juntas y símbolo automático | `python/weld_juntas.py` |
| Filetes 3D y gris del tanque | `python/weld_solido.py` |
| Tres vistas | `python/weld_vista.py` |
| Hoja JPG | `python/weld_jpg.py` |
| Tabla de nomenclatura | `python/weld_nomenclatura.py` |
| API de la barra | `python/host.py` (`weld_run`, `weld_scan`, `weld_progress`, `weld_nom_*`, `weld_tool_open`) |
| Muros confirmados | `config/roles_sesion.json` |
| Símbolos editados | `config/weld_nomenclatura.json` |
| Job del dossier | `config/dossier_eleccion.json` |
| Pruebas sin Inventor | `python/test_weld_anotation.py` |

## Errores que ya ocurrieron

- «Abre el ensamble del tanque en Inventor» con el tanque ya abierto: el clic no vio la ventana activa. Reintentar cuando el `.iam` está al frente.
- La barra instalada en `AppData\Local\AutoDXF\runtime\` no ve los muros del proyecto. La sesión vive en el `config` de la copia que está corriendo. Hoy el usuario arranca el host del proyecto (`python\host.py`).
- Tras los JPG el 3D parecía sin cordones: los cuerpos quedaron ocultos. `mostrar_todos` los enciende al cerrar las fotos.
- «No está la carpeta de JPG del job»: `JPGS` no existía. Ahora se crea, con `Weld` dentro.

## Qué no hacer

- No abrir ni crear un plano de Inventor para esta foto.
- No guardar el `.iam` al terminar cordones o JPG.
- No usar el add-in de AWIS.
- No volver a mezclar cordones 3D y JPG en un solo botón.
- No publicar en `JPG/{job}/WELD_ANOTATION/`. Esa ruta quedó vieja. El destino es `DOSSIER FILES\JPGS\Weld`.
- No pintar de gris las ocurrencias `WELD_ANOTATION`.
- No dar por cerrada la fase. `soldadura/control.json` sigue en `cordon_3d` hasta que el usuario apruebe los JPG de un tanque y pida liberar el proceso.
