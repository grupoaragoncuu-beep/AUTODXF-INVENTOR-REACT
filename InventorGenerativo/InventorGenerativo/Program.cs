using System;
using System.Runtime.InteropServices;
using Inventor;

namespace InventorGenerativo
{
    class Program
    {
        // --- INICIO P/INVOKE: Conexión nativa para .NET 10 ---
        [DllImport("ole32.dll")]
        private static extern int CLSIDFromProgIDEx([MarshalAs(UnmanagedType.LPWStr)] string lpszProgID, out Guid lpclsid);

        [DllImport("oleaut32.dll")]
        private static extern int GetActiveObject([MarshalAs(UnmanagedType.LPStruct)] Guid rclsid, IntPtr pvReserved, [MarshalAs(UnmanagedType.IUnknown)] out object ppunk);

        public static object ObtenerInventorActivo(string progId)
        {
            Guid clsid;
            CLSIDFromProgIDEx(progId, out clsid);
            
            object obj;
            GetActiveObject(clsid, IntPtr.Zero, out obj);
            
            if (obj == null) throw new Exception("No se encontró la aplicación en ejecución.");
            return obj;
        }
        // --- FIN P/INVOKE ---

        static void Main(string[] args)
        {
            Console.WriteLine("Iniciando conexión con Inventor...");
            Inventor.Application invApp = null;

            try
            {
                invApp = (Inventor.Application)ObtenerInventorActivo("Inventor.Application");
                Console.WriteLine("¡Conexión exitosa! Tomando el control...");
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error: " + ex.Message);
                return; // Detenemos el programa si no hay conexión
            }

            // 1. Crear el Contenedor
            Console.WriteLine("Creando nuevo archivo de pieza...");
            PartDocument partDoc = (PartDocument)invApp.Documents.Add(
                DocumentTypeEnum.kPartDocumentObject, 
                invApp.FileManager.GetTemplateFile(DocumentTypeEnum.kPartDocumentObject), 
                true);

            PartComponentDefinition compDef = partDoc.ComponentDefinition;

            // 2. Matemáticas y Boceto
            Console.WriteLine("Trazando geometría matemática...");
            TransientGeometry transGeom = invApp.TransientGeometry;
            
            // Accedemos al plano XY (índice 3)
            WorkPlane xyPlane = compDef.WorkPlanes[3];
            PlanarSketch sketch = compDef.Sketches.Add(xyPlane, false);

            // Coordenadas: Origen (0,0) a (10, 5) centímetros
            Point2d puntoInicio = transGeom.CreatePoint2d(0, 0);
            Point2d puntoFin = transGeom.CreatePoint2d(10, 5);
            
            sketch.SketchLines.AddAsTwoPointRectangle(puntoInicio, puntoFin);

            // 3. El Volumen
            Console.WriteLine("Calculando perfil y extruyendo...");
            Profile perfil = sketch.Profiles.AddForSolid();

            // Definimos cómo será la extrusión (Unión, 2.5 cm, dirección positiva)
            ExtrudeDefinition extrudeDef = compDef.Features.ExtrudeFeatures.CreateExtrudeDefinition(perfil, PartFeatureOperationEnum.kJoinOperation);
            extrudeDef.SetDistanceExtent(2.5, PartFeatureExtentDirectionEnum.kPositiveExtentDirection);

            // Ejecutamos la extrusión en el modelo
            ExtrudeFeature extrudeFeature = compDef.Features.ExtrudeFeatures.Add(extrudeDef);

            // Ajustamos la cámara para ver la pieza completa
            invApp.ActiveView.Fit();
            
            Console.WriteLine("¡Misión cumplida! Revisa la ventana de Inventor.");
        }
    }
}