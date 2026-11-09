using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AutoDXF.Core
{
    public sealed class ReleaseInfo
    {
        [JsonPropertyName("version")] public string Version { get; set; }
        [JsonPropertyName("file")] public string File { get; set; }
        [JsonPropertyName("sha256")] public string Sha256 { get; set; }
        [JsonPropertyName("iterations")] public int Iterations { get; set; }
        [JsonPropertyName("salt")] public string Salt { get; set; }
        [JsonPropertyName("verify")] public string Verify { get; set; }
        [JsonPropertyName("published")] public string Published { get; set; }
    }

    public sealed class ReleaseKeys
    {
        public byte[] Encrypt { get; set; }
        public byte[] Mac { get; set; }
    }

    public static class Vault
    {
        public const int Iterations = 200000;
        private static readonly byte[] Magic = { (byte)'A', (byte)'D', (byte)'X', (byte)'P', 1 };
        private static readonly byte[] VerifyTag = Encoding.ASCII.GetBytes("AutoDXF-v1");
        private static readonly byte[] UnlockEntropy = Encoding.UTF8.GetBytes("AutoDXF-unlock-v1");

        public static string LocalRoot =>
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AutoDXF");

        public static ReleaseKeys Derive(string password, byte[] salt, int iterations)
        {
            byte[] material = Rfc2898DeriveBytes.Pbkdf2(password, salt, iterations, HashAlgorithmName.SHA256, 64);
            return new ReleaseKeys
            {
                Encrypt = Copy(material, 0, 32),
                Mac = Copy(material, 32, 32),
            };
        }

        public static bool PasswordMatches(ReleaseInfo info, string password)
        {
            if (info == null || string.IsNullOrEmpty(password) || string.IsNullOrEmpty(info.Salt) || string.IsNullOrEmpty(info.Verify))
                return false;
            int iterations = info.Iterations > 0 ? info.Iterations : Iterations;
            ReleaseKeys keys = Derive(password, Convert.FromBase64String(info.Salt), iterations);
            byte[] expected = Convert.FromBase64String(info.Verify);
            byte[] actual = Sign(keys.Mac, VerifyTag);
            return FixedEquals(expected, actual);
        }

        public static void Publish(string sourceRoot, string serverDir, string version, string password)
        {
            if (string.IsNullOrWhiteSpace(version) || version.Split('.').Length != 3)
                throw new InvalidOperationException("La versión debe tener la forma 1.0.0.");
            if (string.IsNullOrEmpty(password) || password.Length < 8)
                throw new InvalidOperationException("La contraseña de administrador necesita al menos 8 caracteres.");
            if (!File.Exists(Path.Combine(sourceRoot, "python", "host.py")))
                throw new InvalidOperationException("No está python\\host.py en el origen.");
            if (!File.Exists(Path.Combine(sourceRoot, "ui", "dist", "index.html")))
                throw new InvalidOperationException("Falta ui\\dist. Compila la barra con pnpm build antes de publicar.");
            if (!File.Exists(Path.Combine(sourceRoot, "tools", "InventorGenerativo", "InventorGenerativo.exe")))
                throw new InvalidOperationException("Falta tools\\InventorGenerativo\\InventorGenerativo.exe. Sin ese programa la chapa no funciona en la computadora del cliente.");
            if (!File.Exists(Path.Combine(sourceRoot, "tools", "AWIS", "FaceDrawingVerify.exe")))
                throw new InvalidOperationException("Falta tools\\AWIS\\FaceDrawingVerify.exe. Sin ese programa la pestaña AWIS no corre en la computadora del cliente.");

            serverDir = ResolveServerDir(serverDir);
            byte[] salt = Random(16);
            ReleaseKeys keys = Derive(password, salt, Iterations);
            string packageName = "AutoDXF-" + version + ".adxp";
            string packageDir = Path.Combine(serverDir, "paquetes");
            Directory.CreateDirectory(serverDir);
            Directory.CreateDirectory(packageDir);
            string packagePath = Path.Combine(packageDir, packageName);
            string tempPackage = packagePath + ".tmp";
            File.WriteAllBytes(tempPackage, Seal(Zip(sourceRoot), keys));
            byte[] hash = SHA256.Create().ComputeHash(File.ReadAllBytes(tempPackage));
            if (File.Exists(packagePath)) File.Delete(packagePath);
            File.Move(tempPackage, packagePath);

            var info = new ReleaseInfo
            {
                Version = version,
                File = "paquetes/" + packageName,
                Sha256 = BitConverter.ToString(hash).Replace("-", "").ToLowerInvariant(),
                Iterations = Iterations,
                Salt = Convert.ToBase64String(salt),
                Verify = Convert.ToBase64String(Sign(keys.Mac, VerifyTag)),
                Published = DateTime.Now.ToString("yyyy-MM-dd HH:mm"),
            };
            WriteManifest(Path.Combine(serverDir, "version.json"), info);
        }

        [DllImport("mpr.dll", CharSet = CharSet.Unicode)]
        private static extern int WNetGetConnection(string localName, StringBuilder remoteName, ref int length);

        public static string ResolveServerDir(string serverDir)
        {
            serverDir = (serverDir ?? "").Trim().Trim('"');
            if (string.IsNullOrWhiteSpace(serverDir))
                throw new InvalidOperationException("Falta la carpeta de publicación.");
            serverDir = ToUnc(serverDir);
            if (Directory.Exists(serverDir))
                return serverDir;
            string parent = Path.GetDirectoryName(serverDir);
            string wanted = Path.GetFileName(serverDir);
            if (!string.IsNullOrEmpty(parent) && Directory.Exists(parent) && !string.IsNullOrEmpty(wanted))
            {
                foreach (string dir in Directory.GetDirectories(parent))
                {
                    string name = Path.GetFileName(dir);
                    if (string.Equals(name, wanted, StringComparison.OrdinalIgnoreCase) || Fold(name) == Fold(wanted))
                        return dir;
                }
            }
            try
            {
                Directory.CreateDirectory(serverDir);
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException("No pude usar la carpeta de publicación: " + serverDir + " (" + ex.Message + ")");
            }
            if (Directory.Exists(serverDir))
                return serverDir;
            throw new InvalidOperationException("No encuentro la carpeta de publicación: " + serverDir);
        }

        public static string ToUnc(string path)
        {
            if (string.IsNullOrEmpty(path) || path.StartsWith("\\\\", StringComparison.Ordinal) || path.Length < 2 || path[1] != ':')
                return path;
            var remote = new StringBuilder(512);
            int length = remote.Capacity;
            if (WNetGetConnection(path.Substring(0, 2), remote, ref length) != 0)
                return path;
            string share = remote.ToString();
            if (string.IsNullOrEmpty(share))
                return path;
            string rest = path.Length > 3 ? path.Substring(3) : "";
            return string.IsNullOrEmpty(rest) ? share : share.TrimEnd('\\') + "\\" + rest;
        }

        private static string Fold(string value)
        {
            string form = (value ?? "").Normalize(NormalizationForm.FormD);
            var chars = new StringBuilder();
            foreach (char letter in form)
            {
                if (System.Globalization.CharUnicodeInfo.GetUnicodeCategory(letter) != System.Globalization.UnicodeCategory.NonSpacingMark)
                    chars.Append(char.ToLowerInvariant(letter));
            }
            return chars.ToString();
        }

        public static ReleaseInfo ReadManifest(string path)
        {
            ReleaseInfo info = JsonSerializer.Deserialize<ReleaseInfo>(File.ReadAllText(path), JsonOptions());
            if (info == null || string.IsNullOrWhiteSpace(info.Version))
                throw new InvalidOperationException("version.json no es válido.");
            return info;
        }

        public static string Sync(string serverDir)
        {
            string manifestPath = Path.Combine(serverDir, "version.json");
            if (!File.Exists(manifestPath))
                throw new InvalidOperationException("En el servidor no está version.json. Publica una versión primero.");
            ReleaseInfo remote = ReadManifest(manifestPath);
            string cache = Path.Combine(LocalRoot, "cache");
            Directory.CreateDirectory(cache);
            string localManifest = Path.Combine(cache, "version.json");
            string localPackage = Path.Combine(cache, remote.File.Replace('/', Path.DirectorySeparatorChar));
            bool same = File.Exists(localManifest) && File.Exists(localPackage);
            if (same)
            {
                ReleaseInfo local = ReadManifest(localManifest);
                same = string.Equals(local.Version, remote.Version, StringComparison.Ordinal)
                    && string.Equals(local.Sha256, remote.Sha256, StringComparison.OrdinalIgnoreCase);
            }
            if (!same)
            {
                string remotePackage = Path.Combine(serverDir, remote.File.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(localPackage));
                File.Copy(remotePackage, localPackage, true);
                string actual = BitConverter.ToString(SHA256.Create().ComputeHash(File.ReadAllBytes(localPackage))).Replace("-", "").ToLowerInvariant();
                if (!string.Equals(actual, remote.Sha256, StringComparison.OrdinalIgnoreCase))
                {
                    File.Delete(localPackage);
                    throw new InvalidOperationException("El paquete descargado no coincide con la versión del servidor.");
                }
                File.Copy(manifestPath, localManifest, true);
            }
            return localPackage;
        }

        public static ReleaseKeys UnlockStored(string version)
        {
            string path = UnlockPath(version);
            if (!File.Exists(path)) return null;
            try
            {
                byte[] plain = ProtectedData.Unprotect(File.ReadAllBytes(path), UnlockEntropy, DataProtectionScope.CurrentUser);
                string stored = ReadPrefix(plain, out int offset);
                if (!string.Equals(stored, version, StringComparison.Ordinal) || plain.Length < offset + 64)
                    return null;
                return new ReleaseKeys
                {
                    Encrypt = Copy(plain, offset, 32),
                    Mac = Copy(plain, offset + 32, 32),
                };
            }
            catch (CryptographicException)
            {
                return null;
            }
        }

        public static void StoreUnlock(string version, ReleaseKeys keys)
        {
            byte[] prefix = Encoding.UTF8.GetBytes(version);
            byte[] plain = new byte[4 + prefix.Length + 64];
            plain[0] = (byte)prefix.Length;
            plain[1] = (byte)(prefix.Length >> 8);
            plain[2] = (byte)(prefix.Length >> 16);
            plain[3] = (byte)(prefix.Length >> 24);
            Buffer.BlockCopy(prefix, 0, plain, 4, prefix.Length);
            Buffer.BlockCopy(keys.Encrypt, 0, plain, 4 + prefix.Length, 32);
            Buffer.BlockCopy(keys.Mac, 0, plain, 4 + prefix.Length + 32, 32);
            string path = UnlockPath(version);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllBytes(path, ProtectedData.Protect(plain, UnlockEntropy, DataProtectionScope.CurrentUser));
        }

        public static string Extract(string packagePath, ReleaseInfo info, ReleaseKeys keys)
        {
            return ExtractUnder(packagePath, info, keys, LocalRoot, true);
        }

        private static string ExtractUnder(string packagePath, ReleaseInfo info, ReleaseKeys keys, string root, bool restoreUserData)
        {
            byte[] packed = File.ReadAllBytes(packagePath);
            byte[] zip = Open(packed, keys);
            string runtime = Path.Combine(root, "runtime", info.Version);
            if (Directory.Exists(runtime)) Directory.Delete(runtime, true);
            Directory.CreateDirectory(runtime);
            using (var stream = new MemoryStream(zip))
            using (var archive = new ZipArchive(stream, ZipArchiveMode.Read))
            {
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string name = entry.FullName.Replace('\\', '/');
                    if (name.Length == 0 || name.EndsWith("/", StringComparison.Ordinal)) continue;
                    if (name.StartsWith("/", StringComparison.Ordinal) || name.Contains(".."))
                        throw new InvalidOperationException("El paquete trae una ruta no permitida.");
                    string target = Path.Combine(runtime, name.Replace('/', Path.DirectorySeparatorChar));
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    entry.ExtractToFile(target, true);
                }
            }
            if (restoreUserData) RestoreData(runtime);
            return runtime;
        }

        public static void SaveData(string runtime)
        {
            string datos = Path.Combine(LocalRoot, "datos");
            Directory.CreateDirectory(datos);
            CopyIfExists(Path.Combine(runtime, "config", "sheet-rules.json"), Path.Combine(datos, "sheet-rules.json"));
            CopyIfExists(Path.Combine(runtime, "config", "morfologia.json"), Path.Combine(datos, "morfologia.json"));
            CopyIfExists(Path.Combine(runtime, "config", "autodxf.local.json"), Path.Combine(datos, "autodxf.local.json"));
            CopyIfExists(Path.Combine(runtime, "herinox_sync.local.json"), Path.Combine(datos, "herinox_sync.local.json"));
        }

        public static string SelfTest()
        {
            string root = Path.Combine(Path.GetTempPath(), "autodxf-selftest-" + Guid.NewGuid().ToString("N"));
            string origin = Path.Combine(root, "origen");
            string server = Path.Combine(root, "servidor");
            try
            {
                Directory.CreateDirectory(Path.Combine(origin, "python"));
                Directory.CreateDirectory(Path.Combine(origin, "ui", "dist"));
                File.WriteAllText(Path.Combine(origin, "python", "host.py"), "print('ok')\n");
                File.WriteAllText(Path.Combine(origin, "ui", "dist", "index.html"), "<p>ok</p>");
                Directory.CreateDirectory(Path.Combine(origin, "tools", "InventorGenerativo"));
                File.WriteAllText(Path.Combine(origin, "tools", "InventorGenerativo", "InventorGenerativo.exe"), "ok");
                Directory.CreateDirectory(Path.Combine(origin, "tools", "AWIS"));
                File.WriteAllText(Path.Combine(origin, "tools", "AWIS", "FaceDrawingVerify.exe"), "ok");
                File.WriteAllText(Path.Combine(origin, "AutoDXF 2.0.iLogicVb"), "' regla");
                const string password = "Prueba-AutoDXF-18";
                Publish(origin, server, "1.2.3", password);
                ReleaseInfo info = ReadManifest(Path.Combine(server, "version.json"));
                if (info.Version != "1.2.3") throw new InvalidOperationException("La versión publicada no coincide.");
                if (PasswordMatches(info, "otra-clave")) throw new InvalidOperationException("Aceptó una contraseña incorrecta.");
                if (!PasswordMatches(info, password)) throw new InvalidOperationException("Rechazó la contraseña correcta.");
                ReleaseKeys keys = Derive(password, Convert.FromBase64String(info.Salt), info.Iterations);
                string package = Path.Combine(server, info.File.Replace('/', Path.DirectorySeparatorChar));
                string runtime = ExtractUnder(package, info, keys, Path.Combine(root, "local"), false);
                if (!File.Exists(Path.Combine(runtime, "python", "host.py")))
                    throw new InvalidOperationException("No se abrió el paquete.");
                Directory.Delete(runtime, true);
                return "ok " + info.Sha256.Substring(0, 12);
            }
            finally
            {
                try { if (Directory.Exists(root)) Directory.Delete(root, true); } catch (IOException) { }
            }
        }

        private static void RestoreData(string runtime)
        {
            string datos = Path.Combine(LocalRoot, "datos");
            CopyIfExists(Path.Combine(datos, "sheet-rules.json"), Path.Combine(runtime, "config", "sheet-rules.json"));
            CopyIfExists(Path.Combine(datos, "morfologia.json"), Path.Combine(runtime, "config", "morfologia.json"));
            CopyIfExists(Path.Combine(datos, "autodxf.local.json"), Path.Combine(runtime, "config", "autodxf.local.json"));
            CopyIfExists(Path.Combine(datos, "herinox_sync.local.json"), Path.Combine(runtime, "herinox_sync.local.json"));
        }

        private static byte[] Zip(string sourceRoot)
        {
            var include = new List<string>();
            foreach (string name in new[]
            {
                "AutoDXF 2.0.iLogicVb",
                "SelectorComponentes.iLogicVb",
                "Lista de largos 2.0.iLogicVb",
                "Colorimetria Sub Assembly + Norman.iLogicVb",
                "ColorimetriaInstancia.iLogicVb",
                "config\\sheet-rules.json",
                "config\\acotacion-jpg.json",
                "config\\colorimetria.json",
                "config\\morfologia.json",
                "config\\autodxf.local.json.example",
            })
            {
                string path = Path.Combine(sourceRoot, name);
                if (File.Exists(path)) include.Add(path);
            }
            AddTree(include, Path.Combine(sourceRoot, "python"));
            AddTree(include, Path.Combine(sourceRoot, "ui", "dist"));
            AddTree(include, Path.Combine(sourceRoot, "cotas-por-referencia"));
            AddGenerativo(include, Path.Combine(sourceRoot, "tools", "InventorGenerativo"));
            AddGenerativo(include, Path.Combine(sourceRoot, "tools", "AWIS"));
            using (var memory = new MemoryStream())
            {
                using (var archive = new ZipArchive(memory, ZipArchiveMode.Create, true))
                {
                    foreach (string path in include.Distinct(StringComparer.OrdinalIgnoreCase))
                    {
                        string relative = path.Substring(sourceRoot.Length).TrimStart('\\', '/').Replace('\\', '/');
                        archive.CreateEntryFromFile(path, relative, CompressionLevel.Optimal);
                    }
                }
                return memory.ToArray();
            }
        }

        private static void AddTree(List<string> files, string directory)
        {
            if (!Directory.Exists(directory)) return;
            foreach (string path in Directory.GetFiles(directory, "*", SearchOption.AllDirectories))
            {
                string name = Path.GetFileName(path);
                if (name.EndsWith(".pyc", StringComparison.OrdinalIgnoreCase)) continue;
                if (path.IndexOf("__pycache__", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                if (path.IndexOf("\\salidas\\", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                files.Add(path);
            }
        }

        private static void AddGenerativo(List<string> files, string directory)
        {
            if (!Directory.Exists(directory)) return;
            foreach (string path in Directory.GetFiles(directory))
            {
                string ext = Path.GetExtension(path);
                if (!ext.Equals(".exe", StringComparison.OrdinalIgnoreCase)
                    && !ext.Equals(".dll", StringComparison.OrdinalIgnoreCase)
                    && !ext.Equals(".json", StringComparison.OrdinalIgnoreCase))
                    continue;
                files.Add(path);
            }
        }

        private static byte[] Seal(byte[] plain, ReleaseKeys keys)
        {
            byte[] iv = Random(16);
            byte[] cipher;
            using (var aes = Aes.Create())
            {
                aes.Key = keys.Encrypt;
                aes.IV = iv;
                aes.Mode = CipherMode.CBC;
                aes.Padding = PaddingMode.PKCS7;
                using (var encryptor = aes.CreateEncryptor())
                using (var memory = new MemoryStream())
                {
                    using (var crypto = new CryptoStream(memory, encryptor, CryptoStreamMode.Write))
                        crypto.Write(plain, 0, plain.Length);
                    cipher = memory.ToArray();
                }
            }
            byte[] prefix = Join(Magic, iv, cipher);
            return Join(prefix, Sign(keys.Mac, prefix));
        }

        private static byte[] Open(byte[] packed, ReleaseKeys keys)
        {
            if (packed.Length < Magic.Length + 16 + 32) throw new InvalidOperationException("Paquete incompleto.");
            for (int i = 0; i < Magic.Length; i++)
                if (packed[i] != Magic[i]) throw new InvalidOperationException("El paquete no es de AutoDXF.");
            byte[] mac = Copy(packed, packed.Length - 32, 32);
            byte[] prefix = Copy(packed, 0, packed.Length - 32);
            if (!FixedEquals(mac, Sign(keys.Mac, prefix)))
                throw new InvalidOperationException("El paquete fue alterado o la contraseña no corresponde.");
            byte[] iv = Copy(prefix, Magic.Length, 16);
            byte[] cipher = Copy(prefix, Magic.Length + 16, prefix.Length - Magic.Length - 16);
            using (var aes = Aes.Create())
            {
                aes.Key = keys.Encrypt;
                aes.IV = iv;
                aes.Mode = CipherMode.CBC;
                aes.Padding = PaddingMode.PKCS7;
                using (var decryptor = aes.CreateDecryptor())
                using (var memory = new MemoryStream())
                {
                    using (var crypto = new CryptoStream(memory, decryptor, CryptoStreamMode.Write))
                        crypto.Write(cipher, 0, cipher.Length);
                    return memory.ToArray();
                }
            }
        }

        private static void WriteManifest(string path, ReleaseInfo info)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            string temp = path + ".tmp";
            File.WriteAllText(temp, JsonSerializer.Serialize(info, JsonOptions()));
            if (File.Exists(path)) File.Delete(path);
            File.Move(temp, path);
        }

        private static JsonSerializerOptions JsonOptions()
        {
            return new JsonSerializerOptions { WriteIndented = true };
        }

        private static string UnlockPath(string version)
        {
            foreach (char bad in Path.GetInvalidFileNameChars())
                version = version.Replace(bad, '_');
            return Path.Combine(LocalRoot, "unlock", version + ".bin");
        }

        private static string ReadPrefix(byte[] plain, out int offset)
        {
            if (plain.Length < 4) { offset = 0; return ""; }
            int length = plain[0] | (plain[1] << 8) | (plain[2] << 16) | (plain[3] << 24);
            offset = 4 + length;
            if (length < 0 || offset > plain.Length) return "";
            return Encoding.UTF8.GetString(plain, 4, length);
        }

        private static byte[] Sign(byte[] key, byte[] data)
        {
            using (var hmac = new HMACSHA256(key))
                return hmac.ComputeHash(data);
        }

        private static byte[] Random(int count)
        {
            byte[] data = new byte[count];
            using (var rng = RandomNumberGenerator.Create())
                rng.GetBytes(data);
            return data;
        }

        private static byte[] Copy(byte[] source, int index, int count)
        {
            byte[] data = new byte[count];
            Buffer.BlockCopy(source, index, data, 0, count);
            return data;
        }

        private static byte[] Join(params byte[][] parts)
        {
            int size = 0;
            foreach (byte[] part in parts) size += part.Length;
            byte[] data = new byte[size];
            int index = 0;
            foreach (byte[] part in parts)
            {
                Buffer.BlockCopy(part, 0, data, index, part.Length);
                index += part.Length;
            }
            return data;
        }

        private static bool FixedEquals(byte[] left, byte[] right)
        {
            if (left == null || right == null || left.Length != right.Length) return false;
            int diff = 0;
            for (int i = 0; i < left.Length; i++) diff |= left[i] ^ right[i];
            return diff == 0;
        }

        private static void CopyIfExists(string source, string target)
        {
            if (!File.Exists(source)) return;
            Directory.CreateDirectory(Path.GetDirectoryName(target));
            File.Copy(source, target, true);
        }
    }
}
