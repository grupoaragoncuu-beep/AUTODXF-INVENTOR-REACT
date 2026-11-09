using System.IO;
using System.Text.Json;

namespace AWIS.InventorBridge.FacePreview
{
    public static class FacePreviewExporter
    {
        public static void Export(
            FacePreviewPackage package,
            string outputPath)
        {
            var options = new JsonSerializerOptions
            {
                WriteIndented = true
            };

            string json =
                JsonSerializer.Serialize(package, options);

            File.WriteAllText(outputPath, json);
        }
    }
}