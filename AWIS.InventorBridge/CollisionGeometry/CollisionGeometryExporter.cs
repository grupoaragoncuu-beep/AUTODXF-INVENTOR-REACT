using System;
using System.IO;
using System.Text.Json;
using AWIS.InventorBridge.Services;

namespace AWIS.InventorBridge.CollisionGeometry
{
    public static class CollisionGeometryExporter
    {
        public static string Export(
            CollisionGeometryPackage package,
            string outputDirectory)
        {
            Directory.CreateDirectory(
                outputDirectory);


            string outputPath =
                AwisOutputNaming.BuildPath(
                    outputDirectory,
                    "AWIS_COLLISION_GEOMETRY",
                    package.TankName);


            JsonSerializerOptions options =
                new JsonSerializerOptions
                {
                    WriteIndented = true
                };


            string json =
                JsonSerializer.Serialize(
                    package,
                    options);


            File.WriteAllText(
                outputPath,
                json);


            return outputPath;
        }
    }
}
