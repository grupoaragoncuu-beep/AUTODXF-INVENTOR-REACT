using System.IO;

namespace AWIS.InventorBridge.Services
{
    /// <summary>
    /// Carpeta de salida de AWIS: la que el operador eligió en el módulo,
    /// más "Efort Weld Files". No usa Documentos\AWIS.
    /// </summary>
    public static class EfortWeldDirectory
    {
        public const string FolderName = "Efort Weld Files";
        public const string EnvVar = "AUTODXF_EFORT_WELD";

        public static bool TryGet(out string directory)
        {
            string? found = FirstUsable(Environment.GetEnvironmentVariable(EnvVar))
                ?? FirstUsable(ReadPointer());
            if (found == null)
            {
                directory = "";
                return false;
            }

            Directory.CreateDirectory(found);
            directory = found;
            return true;
        }

        public static string Require()
        {
            if (TryGet(out string directory))
            {
                return directory;
            }

            throw new InvalidOperationException(
                "Elige producto, cliente y job en el módulo antes de AWIS. " +
                "Los archivos van a la carpeta Efort Weld Files de ese job.");
        }

        private static string PointerFile()
        {
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "AutoDXF",
                "efort_weld_dir.txt");
        }

        private static string? ReadPointer()
        {
            try
            {
                string file = PointerFile();
                if (!File.Exists(file))
                {
                    return null;
                }

                return File.ReadAllText(file).Trim();
            }
            catch (IOException)
            {
                return null;
            }
            catch (UnauthorizedAccessException)
            {
                return null;
            }
        }

        private static string? FirstUsable(string? raw)
        {
            if (string.IsNullOrWhiteSpace(raw))
            {
                return null;
            }

            string full;
            try
            {
                full = Path.GetFullPath(raw.Trim());
            }
            catch (Exception)
            {
                return null;
            }

            if (!string.Equals(
                    Path.GetFileName(full.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)),
                    FolderName,
                    StringComparison.OrdinalIgnoreCase))
            {
                return null;
            }

            string? parent = Path.GetDirectoryName(full);
            if (string.IsNullOrWhiteSpace(parent) || !Directory.Exists(parent))
            {
                return null;
            }

            string documentsAwis = Path.GetFullPath(Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                "AWIS"));
            if (IsUnder(full, documentsAwis))
            {
                return null;
            }

            return full;
        }

        private static bool IsUnder(string path, string root)
        {
            string full = Path.GetFullPath(path)
                .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            string baseDir = Path.GetFullPath(root)
                .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            return full.Equals(baseDir, StringComparison.OrdinalIgnoreCase)
                || full.StartsWith(
                    baseDir + Path.DirectorySeparatorChar,
                    StringComparison.OrdinalIgnoreCase);
        }
    }
}
