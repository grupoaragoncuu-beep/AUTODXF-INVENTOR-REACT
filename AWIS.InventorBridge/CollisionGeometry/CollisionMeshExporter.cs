using System.IO;
using System.Text.Json;
using AWIS.InventorBridge.Services;

namespace AWIS.InventorBridge.CollisionGeometry
{
    public static class CollisionMeshExporter
    {
        public static string Export(
            CollisionGeometryPackage geometryPackage,
            string outputDirectory)
        {
            Directory.CreateDirectory(
                outputDirectory);


            string outputPath =
                AwisOutputNaming.BuildPath(
                    outputDirectory,
                    "AWIS_COLLISION_MESHES",
                    geometryPackage.TankName);


            string fileName =
                Path.GetFileName(
                    outputPath);


            CollisionMeshPackage meshPackage =
                new CollisionMeshPackage
                {
                    TankName = geometryPackage.TankName,
                    DocumentName = geometryPackage.DocumentName,
                    ExportTime = geometryPackage.ExportTime,
                    Policy =
                        new CollisionMeshPolicy
                        {
                            RequestedChordToleranceMm =
                                geometryPackage.RepresentationPolicy.MeshChordToleranceMm,

                            ExportScope =
                                geometryPackage.RepresentationPolicy.MeshExportScope
                        }
                };


            foreach (CollisionComponentRecord component
                     in geometryPackage.Components)
            {
                foreach (CollisionBodyRecord body
                         in component.Bodies)
                {
                    if (body.MeshReference != null &&
                        body.MeshReference.Status == "EXPORTED")
                    {
                        body.MeshReference.CompanionFileName =
                            fileName;
                    }


                    if (body.MeshData == null)
                    {
                        continue;
                    }


                    meshPackage.Meshes.Add(
                        body.MeshData);


                    meshPackage.Statistics.MeshCount++;
                    meshPackage.Statistics.TotalVertexCount +=
                        body.MeshData.VertexCount;
                    meshPackage.Statistics.TotalTriangleCount +=
                        body.MeshData.TriangleCount;
                }
            }


            JsonSerializerOptions options =
                new JsonSerializerOptions
                {
                    // Mesh arrays can become very large. Keep this companion
                    // compact; the human-readable index remains indented.
                    WriteIndented = false
                };


            using (FileStream stream =
                   File.Create(
                       outputPath))
            {
                JsonSerializer.Serialize(
                    stream,
                    meshPackage,
                    options);
            }


            return outputPath;
        }
    }
}
