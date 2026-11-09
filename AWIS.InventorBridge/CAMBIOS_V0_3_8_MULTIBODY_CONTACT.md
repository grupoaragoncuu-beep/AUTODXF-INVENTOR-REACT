# Bridge V0.3.8 — Contactos entre cuerpos de una misma pieza

## Instalación y comprobación

1. Extraer en una carpeta nueva. Abrir AWIS.InventorBridge.csproj en Visual Studio y compilar con la misma configuración del proyecto activo. Se conserva el framework y la referencia Interop originales; si su ruta local de Inventor difiere, usar la misma referencia que ya funcionaba.
2. Cerrar Inventor antes de sustituir la DLL activa. Instalar/deplegar esta compilación en la ruta que realmente carga el complemento. Una compilación exitosa no demuestra que Inventor haya cargado la DLL nueva.
3. Abrir MODELO VANTRAN 261198.iam y volver a exportar desde el complemento. No editar ni reutilizar los JSON de interfaces anteriores para probar la corrección. Conservar juntos todos los archivos de la nueva exportación.
4. En AWIS_WELD_INTERFACES verificar Version=0.3.8 y GeneratorVersion=Inventor Weld Interface Companion V0.3.8-MULTIBODY_CONTACT. Revisar Sources y hashes de detección/preview.
5. Revisar AXIS_2_NEGATIVE y AXIS_2_POSITIVE: debe existir una interfaz adicional con ComponentOccurrencePath=PUREBA:1/S2,S3,S4:1 y un path longitudinal cercano a 1638.3 mm proveniente del Body 1. Debe conservarse el cierre de S1:1 y los accesorios anteriores. Verificar también las variantes EXTERIOR/INTERIOR que se utilicen.
6. En Statistics se agregan OwnWallBodiesSkippedExact, OwnWallBodiesSkippedSection y SameOccurrenceBodyInterfacesEvaluated. En Evidence se registra same_occurrence_other_body_contact_evaluated y same_occurrence_boundary_uses_contact_tolerance_preserves_model3d.
7. Cargar los JSON nuevos en AWIS y comprobar los dos cierres paralelos y sus coordenadas. El cierre definitivo requiere esta nueva exportación y validación visual en Inventor/AWIS.

## Qué cambió y dónde

- WeldInterfaces/WeldWallBodyScope.cs (nuevo): identifica los cuerpos de pared por occurrence path + índice. Incluye el cuerpo ancla y los cuerpos de segmentos de PhysicalWall. Comparación sin distinguir mayúsculas. Si no existe una identificación válida del cuerpo, se conserva la exclusión previa.
- WeldInterfaces/WeldInterfaceBroadPhase.cs, FindCandidatesForWall / condición que incrementa OwnWallPairsSkipped: ya no descarta toda la occurrence si contiene otros cuerpos además de los de pared.
- WeldInterfaces/WeldInterfaceExactDetector.cs, bucle bodyIndex: excluye el cuerpo propio antes de recorrer caras y aristas. En ClipPaths aplica el override local de recorte solamente a la occurrence que aporta la pared y registra evidencia.
- WeldInterfaces/WeldInterfaceSectionBuilder.cs, BuildSections / bucle bodyIndex: excluye esos mismos cuerpos antes de copiar, transformar e intersectar B-Rep.
- WeldInterfaces/WeldInterfaceEnvelopeClipper.cs, ClipPaths y ClipPath: reciben un parámetro opcional boundaryToleranceMm. Si no se proporciona, conservan la tolerancia original de 0.01 mm.
- WeldInterfaces/WeldInterfaceModels.cs: versión, identificación explícita de generador y contadores diagnósticos nuevos.

## Tolerancias y geometría

La tolerancia de contacto permanece en 0.25 mm. Para interfaces entre cuerpos de la misma occurrence se usa max(EnvelopeClipToleranceMm, ContactToleranceMm) como tolerancia local de borde. La causa inicial era la exclusión de toda la occurrence; había además un filtro posterior de recorte de 0.01 mm que rechaza el gap de aproximadamente 0.0127 mm de este tanque. El recorte para otros componentes conserva 0.01 mm. No se cambian posiciones de los cuerpos ni se hace clamp de los puntos. La interpolación UV/XYZ del recorte se conserva.

Esta corrección permite tolerar la pequeña separación del modelo, no la elimina ni certifica su aceptación por ingeniería. Deben conservarse las tolerancias dimensionales de diseño/fabricación.

## Verificaciones ejecutadas y límites

- Parser C# tree-sitter: 42 archivos sin errores sintácticos. Esto no verifica tipos, referencias COM ni compilación.
- Alcance por cuerpos contrastado con los JSON reales: AXIS_2_NEGATIVE excluye Body 2 y permite 1/3; AXIS_2_POSITIVE excluye Body 3 y permite 1/2. Los cuerpos de pared propios siguen excluidos.
- STEP mediante OCCT: sección del Body 1 en los planos físicos de ambas caras produce líneas longitudinales de 1638.3 mm. La línea cercana tiene gap UV de 0.0125/0.0131 mm (incluye redondeo del JSON): fuera de 0.01 mm, dentro de 0.25 mm. La línea lejana a 4.775/4.7756 mm continúa fuera.
- Los sólidos involucrados son válidos; gap 3D 0.0127 mm, sin volumen de interferencia entre esos pares.
- No se dispone aquí de .NET/Autodesk Inventor para compilar ni ejecutar COM. No se entregan DLL ni JSON regenerados simulando una ejecución real. Compilar y exportar en Inventor son pruebas pendientes.
