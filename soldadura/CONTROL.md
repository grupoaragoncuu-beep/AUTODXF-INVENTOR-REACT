# Weld Anotation — control

El funcionamiento completo, para otra conversación, está en `soldadura/FUNCIONAMIENTO.md`.

El módulo de ingeniería publica la soldadura en JPG. No se guarda un plano de Inventor (ni DWG ni IDW) y no se usa el add-in.

Inventor permanece abierto con el ensamble. De ahí salen tres vistas sombreadas, por COM: la cara frontal (solo la pieza del cordón), un detalle y una isométrica. Python compone la hoja en fondo blanco, con el largo y el símbolo de filete.

## Foto

Un JPG por cordón, en `{job}\DOSSIER FILES\JPGS\Weld\{cordon}.jpg`.

La misma carpeta de cotas del job elegido en el dossier. Código: `python/weld_vista.py` y `python/weld_jpg.py`.

## Orden

1. Muros confirmados en Acotación JPG, antes de generar.
2. Cordones 3D: el tanque pasa a gris y después se dibujan los filetes (naranja accesorio, azul hermético). No se guardan JPG en este paso. Código: `python/weld_solido.py`. No se guarda el iam.
3. Nomenclatura y símbolo: ventana flotante, aparte del módulo. El clic en un filete elige ese cordón, no el grupo del mismo color. Ahí se elige Hermético o Accesorio, cateto, paso, dos lados y TYP. Quitar un cordón borra su sólido y esa unión no se vuelve a proponer.
4. Al cerrar esa ventana, el módulo lista cada cordón con clasificación, símbolo y longitud.
5. Generar JPGs. Van a `DOSSIER FILES\JPGS\Weld` del job. Cada JPG queda en `public.cotas_dossier` con clasificación `Weld`, la misma tabla de las cotas de pieza. Una corrida completa actualiza esas filas y quita los cordones que ya no están.

La cadena C# de `Cotas de Soldadura` queda de referencia de las reglas (ISO, lado interno o externo, símbolo). No se vuelve a abrir un drawing para publicar la foto.
