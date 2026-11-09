using System;
using System.IO;
using System.Text;
using AutoDXF.Core;

namespace AutoDXF.Publicar
{
    internal static class Program
    {
        private static int Main(string[] args)
        {
            try
            {
                if (Has(args, "--selftest"))
                {
                    Console.WriteLine(Vault.SelfTest());
                    return 0;
                }
                Console.OutputEncoding = new UTF8Encoding(false);
                string destFile = Value(args, "--destino-archivo");
                string server = Value(args, "--destino");
                if (!string.IsNullOrWhiteSpace(destFile))
                    server = ReadDestino(destFile);
                if (string.IsNullOrWhiteSpace(server))
                {
                    Usage();
                    return 1;
                }
                server = Vault.ResolveServerDir(server);
                if (Has(args, "--list"))
                {
                    string manifest = Path.Combine(server, "version.json");
                    if (!File.Exists(manifest))
                    {
                        Console.WriteLine("Todavía no hay una versión en " + server);
                        return 0;
                    }
                    ReleaseInfo info = Vault.ReadManifest(manifest);
                    Console.WriteLine(info.Version + "  " + info.Published + "  " + info.File);
                    return 0;
                }
                string version = Value(args, "--version");
                string origin = Value(args, "--origen");
                if (string.IsNullOrWhiteSpace(origin))
                    origin = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "..", "..", ".."));
                if (string.IsNullOrWhiteSpace(version))
                {
                    Usage();
                    return 1;
                }
                string password = Value(args, "--password");
                if (string.IsNullOrWhiteSpace(password))
                    password = Environment.GetEnvironmentVariable("AUTODXF_PUBLISH_PASSWORD");
                if (string.IsNullOrWhiteSpace(password))
                {
                    password = ReadSecret("Contraseña de administrador para la versión " + version + ": ");
                    string confirm = ReadSecret("Repite la contraseña: ");
                    if (!string.Equals(password, confirm, StringComparison.Ordinal))
                    {
                        Console.WriteLine("No coincide.");
                        return 1;
                    }
                }
                Vault.Publish(origin, server, version, password);
                if (Has(args, "--guardar-llave"))
                {
                    ReleaseInfo info = Vault.ReadManifest(Path.Combine(server, "version.json"));
                    ReleaseKeys keys = Vault.Derive(password, Convert.FromBase64String(info.Salt), info.Iterations > 0 ? info.Iterations : Vault.Iterations);
                    Vault.StoreUnlock(info.Version, keys);
                    Console.WriteLine("Llave guardada en esta computadora.");
                }
                password = null;
                Console.WriteLine("Publicada la versión " + version + " en " + server);
                if (!Has(args, "--guardar-llave"))
                    Console.WriteLine("La contraseña no se guardó. Consérvala fuera de esta carpeta.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(ex.Message);
                return 1;
            }
        }

        private static string ReadDestino(string path)
        {
            foreach (string raw in File.ReadAllLines(path, Encoding.UTF8))
            {
                string line = raw.Trim().Trim('"');
                if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal)) continue;
                return line;
            }
            return "";
        }

        private static void Usage()
        {
            Console.WriteLine("Publicar:  AutoDXF.Publicar.exe --destino-archivo servidor.txt --version 1.0.0 --origen \"carpeta del proyecto\"");
            Console.WriteLine("Consultar: AutoDXF.Publicar.exe --destino-archivo servidor.txt --list");
        }

        private static bool Has(string[] args, string name)
        {
            foreach (string arg in args)
                if (string.Equals(arg, name, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        private static string Value(string[] args, string name)
        {
            for (int i = 0; i < args.Length - 1; i++)
                if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase)) return args[i + 1];
            return "";
        }

        private static string ReadSecret(string prompt)
        {
            Console.Write(prompt);
            var text = new StringBuilder();
            while (true)
            {
                ConsoleKeyInfo key = Console.ReadKey(true);
                if (key.Key == ConsoleKey.Enter)
                {
                    Console.WriteLine();
                    break;
                }
                if (key.Key == ConsoleKey.Backspace)
                {
                    if (text.Length > 0) text.Length -= 1;
                    continue;
                }
                if (!char.IsControl(key.KeyChar)) text.Append(key.KeyChar);
            }
            return text.ToString();
        }
    }
}
