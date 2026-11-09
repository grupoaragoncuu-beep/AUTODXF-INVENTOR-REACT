using System;
using System.IO;
using System.Text.RegularExpressions;

namespace AWIS.InventorBridge.Services
{
    /// <summary>
    /// Nombres trazables para los outputs companion que consume AWIS.
    /// No modifica el contenido de los JSON ni la lógica de detección.
    /// </summary>
    public static class AwisOutputNaming
    {
        public static string SafeTankToken(string? tankName)
        {
            string value = string.IsNullOrWhiteSpace(tankName)
                ? "UNKNOWN_TANK"
                : tankName.Trim();

            value = Regex.Replace(value, @"[^\p{L}\p{Nd}._-]+", "_");
            value = Regex.Replace(value, @"_+", "_");
            value = value.Trim('_', '.', ' ');

            return string.IsNullOrWhiteSpace(value)
                ? "UNKNOWN_TANK"
                : value;
        }

        public static string BuildPath(
            string outputDirectory,
            string prefix,
            string? tankName)
        {
            return Path.Combine(
                outputDirectory,
                $"{prefix}_{SafeTankToken(tankName)}.json");
        }

        /// <summary>
        /// Conserva el archivo generado por el módulo original y garantiza
        /// además una copia trazable con identificador de tanque. Si el
        /// archivo ya tiene el nombre esperado, no hace nada.
        /// </summary>
        public static string EnsureTankSpecificCopy(
            string currentPath,
            string prefix,
            string? tankName)
        {
            string? directory = Path.GetDirectoryName(currentPath);
            if (string.IsNullOrWhiteSpace(directory))
            {
                throw new InvalidOperationException(
                    "El JSON de AWIS no tiene carpeta. Elige el job en el módulo.");
            }

            string desiredPath = BuildPath(directory, prefix, tankName);

            if (string.Equals(
                    Path.GetFullPath(currentPath),
                    Path.GetFullPath(desiredPath),
                    StringComparison.OrdinalIgnoreCase))
            {
                return currentPath;
            }

            File.Copy(currentPath, desiredPath, overwrite: true);
            return desiredPath;
        }
    }
}
