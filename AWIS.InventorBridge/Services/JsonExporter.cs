using System.Text.Json;
using AWIS.InventorBridge.Models;

namespace AWIS.InventorBridge.Services
{
    public static class JsonExporter
    {
        private static string GetAwisDirectory()
        {
            return EfortWeldDirectory.Require();
        }


        private static JsonSerializerOptions
            GetJsonOptions()
        {
            return new JsonSerializerOptions
            {
                WriteIndented = true
            };
        }


        public static string ExportGeometryScan(
            GeometryScanResult result)
        {
            string outputPath =
                Path.Combine(
                    GetAwisDirectory(),
                    "AWIS_GEOMETRY_SCAN.json");


            string json =
                JsonSerializer.Serialize(
                    result,
                    GetJsonOptions());


            File.WriteAllText(
                outputPath,
                json);


            return outputPath;
        }


        public static string ExportTankDetection(
            TankDetectionResult result)
        {
            string json =
                JsonSerializer.Serialize(
                    result,
                    GetJsonOptions());


            string safeTankName =
                SanitizeFileName(
                    result.TankName);


            // ========================================================
            // IDENTIFIED FILE
            // ========================================================

            string namedOutputPath =
                Path.Combine(
                    GetAwisDirectory(),
                    $"AWIS_TANK_DETECTION_{safeTankName}.json");


            File.WriteAllText(
                namedOutputPath,
                json);


            // ========================================================
            // LATEST SNAPSHOT
            //
            // Se conserva por compatibilidad con el flujo anterior.
            // ========================================================

            string latestOutputPath =
                Path.Combine(
                    GetAwisDirectory(),
                    "AWIS_TANK_DETECTION.json");


            File.WriteAllText(
                latestOutputPath,
                json);


            return namedOutputPath;
        }


        private static string SanitizeFileName(
            string value)
        {
            if (string.IsNullOrWhiteSpace(
                    value))
            {
                return "UNKNOWN_TANK";
            }


            char[] invalidChars =
                Path.GetInvalidFileNameChars();


            string cleaned =
                new string(
                    value
                    .Select(
                        character =>
                            invalidChars.Contains(
                                character)
                                ? '_'
                                : character)
                    .ToArray());


            cleaned =
                cleaned
                .Trim()
                .Replace(
                    ' ',
                    '_');


            if (string.IsNullOrWhiteSpace(
                    cleaned))
            {
                return "UNKNOWN_TANK";
            }


            return cleaned;
        }
    }
}