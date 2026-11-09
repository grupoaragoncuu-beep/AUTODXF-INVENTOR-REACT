using System;
using System.IO;
using System.Text.Json;

namespace AWIS.InventorBridge.WeldInterfaces
{
    public static class WeldInterfaceExporter
    {
        public static string Export(
            WeldInterfacePackage package,
            string outputDirectory)
        {
            Directory.CreateDirectory(
                outputDirectory);


            string tank =
                SanitizeFileName(
                    package.TankName);


            if (string.IsNullOrWhiteSpace(
                    tank))
            {
                tank =
                    "UNKNOWN_TANK";
            }


            string outputPath =
                Path.Combine(
                    outputDirectory,
                    $"AWIS_WELD_INTERFACES_{tank}.json");


            JsonSerializerOptions options =
                new JsonSerializerOptions
                {
                    WriteIndented =
                        true,

                    PropertyNamingPolicy =
                        null
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


        private static string SanitizeFileName(
            string value)
        {
            if (string.IsNullOrWhiteSpace(
                    value))
            {
                return "";
            }


            foreach (char invalid
                     in Path.GetInvalidFileNameChars())
            {
                value =
                    value.Replace(
                        invalid,
                        '_');
            }


            value =
                value
                    .Trim()
                    .Replace(
                        ' ',
                        '_');


            while (value.Contains(
                       "__",
                       StringComparison.Ordinal))
            {
                value =
                    value.Replace(
                        "__",
                        "_",
                        StringComparison.Ordinal);
            }


            return value;
        }
    }
}
