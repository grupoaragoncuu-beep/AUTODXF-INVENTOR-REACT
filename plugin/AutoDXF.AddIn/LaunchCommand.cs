using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using AutoDXF.Core;

namespace AutoDXF.AddIn
{
    internal static class LaunchCommand
    {
        public static string Run()
        {
            string server = ServerPath();
            if (string.IsNullOrWhiteSpace(server))
                throw new InvalidOperationException("Falta la ruta del servidor. Escríbela en servidor.txt, junto al complemento.");
            if (!Directory.Exists(server))
                throw new InvalidOperationException("No se encuentra la carpeta del servidor: " + server);

            if (AlreadyRunning())
                return "AutoDXF ya está abierto.";

            ReleaseInfo info = Vault.ReadManifest(Path.Combine(server, "version.json"));
            string package = Vault.Sync(server);
            ReleaseKeys keys = Vault.UnlockStored(info.Version);
            if (keys == null)
            {
                keys = AskKeys(info);
                if (keys == null) return "AutoDXF cancelado.";
                Vault.StoreUnlock(info.Version, keys);
            }

            string runtime = Vault.Extract(package, info, keys);
            string log = Path.Combine(Vault.LocalRoot, "ultimo-arranque.log");
            Process process = StartHost(runtime, log);
            process.EnableRaisingEvents = true;
            process.Exited += (_, __) => Finish(runtime, process, log);
            WritePid(process.Id);
            return "AutoDXF " + info.Version;
        }

        private static ReleaseKeys AskKeys(ReleaseInfo info)
        {
            for (int attempt = 0; attempt < 3; attempt++)
            {
                string password = PasswordDialog.Ask(info.Version);
                if (password == null) return null;
                try
                {
                    if (!Vault.PasswordMatches(info, password))
                    {
                        MessageBox.Show("Contraseña incorrecta.", "Módulo Ingenieria", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                        continue;
                    }
                    return Vault.Derive(password, Convert.FromBase64String(info.Salt), info.Iterations > 0 ? info.Iterations : Vault.Iterations);
                }
                finally
                {
                    password = null;
                }
            }
            return null;
        }

        private static Process StartHost(string runtime, string log)
        {
            string script = Path.Combine(runtime, "python", "launch_plugin.py");
            if (!File.Exists(script))
                throw new InvalidOperationException("Esta versión no trae el arranque de AutoDXF.");
            string python = FindPython();
            var start = new ProcessStartInfo
            {
                FileName = python,
                Arguments = "-3 \"" + script + "\"",
                WorkingDirectory = runtime,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            start.Environment["PYTHONIOENCODING"] = "utf-8";
            start.Environment["PYTHONUTF8"] = "1";
            File.WriteAllText(log, "");
            Process process = Process.Start(start);
            if (process == null)
                throw new InvalidOperationException("No pude arrancar Python.");
            process.OutputDataReceived += (_, e) => Append(log, e.Data);
            process.ErrorDataReceived += (_, e) => Append(log, e.Data);
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            return process;
        }

        private static void Finish(string runtime, Process process, string log)
        {
            try
            {
                Vault.SaveData(runtime);
                try { process.WaitForExit(2000); } catch (Exception) { }
                if (process.ExitCode != 0)
                    MessageBox.Show(Tail(log), "Módulo Ingenieria no pudo abrir", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
            catch (Exception)
            {
            }
            finally
            {
                try { if (Directory.Exists(runtime)) Directory.Delete(runtime, true); } catch (Exception) { }
                try { File.Delete(PidPath()); } catch (Exception) { }
            }
        }

        private static string ServerPath()
        {
            string beside = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "servidor.txt");
            if (!File.Exists(beside))
                beside = Path.Combine(Path.GetDirectoryName(typeof(LaunchCommand).Assembly.Location), "servidor.txt");
            if (!File.Exists(beside)) return "";
            foreach (string raw in File.ReadAllLines(beside))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal)) continue;
                return line;
            }
            return "";
        }

        private static string FindPython()
        {
            string py = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Launcher", "py.exe");
            if (File.Exists(py)) return py;
            return "py";
        }

        private static bool AlreadyRunning()
        {
            string path = PidPath();
            if (!File.Exists(path)) return false;
            if (!int.TryParse(File.ReadAllText(path).Trim(), out int pid)) return false;
            try
            {
                Process process = Process.GetProcessById(pid);
                return !process.HasExited;
            }
            catch (Exception)
            {
                return false;
            }
        }

        private static void WritePid(int pid)
        {
            Directory.CreateDirectory(Vault.LocalRoot);
            File.WriteAllText(PidPath(), pid.ToString());
        }

        private static string PidPath() => Path.Combine(Vault.LocalRoot, "sesion.pid");

        private static void Append(string log, string line)
        {
            if (string.IsNullOrEmpty(line)) return;
            try { File.AppendAllText(log, line + Environment.NewLine); } catch (Exception) { }
        }

        private static string Tail(string log)
        {
            if (!File.Exists(log)) return "Revisa que Python esté instalado en esta laptop.";
            string text = File.ReadAllText(log).Trim();
            if (text.Length > 500) text = text.Substring(text.Length - 500);
            return text.Length == 0 ? "Revisa que Python esté instalado en esta laptop." : text;
        }
    }

    internal static class PasswordDialog
    {
        public static string Ask(string version)
        {
            using (var form = new Form())
            {
                form.Text = "Módulo Ingenieria";
                form.FormBorderStyle = FormBorderStyle.FixedDialog;
                form.StartPosition = FormStartPosition.CenterScreen;
                form.MaximizeBox = false;
                form.MinimizeBox = false;
                form.TopMost = true;
                form.ClientSize = new System.Drawing.Size(440, 168);
                var label = new Label
                {
                    AutoSize = false,
                    Bounds = new System.Drawing.Rectangle(16, 12, 408, 52),
                    Text = "Versión " + version + ". Contraseña de administrador. Solo se pide la primera vez de esta versión en esta laptop. No queda guardada.",
                };
                var box = new TextBox
                {
                    Bounds = new System.Drawing.Rectangle(16, 72, 408, 24),
                    UseSystemPasswordChar = true,
                };
                var ok = new Button
                {
                    Text = "Continuar",
                    DialogResult = DialogResult.OK,
                    Bounds = new System.Drawing.Rectangle(236, 116, 88, 28),
                };
                var cancel = new Button
                {
                    Text = "Cancelar",
                    DialogResult = DialogResult.Cancel,
                    Bounds = new System.Drawing.Rectangle(332, 116, 92, 28),
                };
                form.Controls.Add(label);
                form.Controls.Add(box);
                form.Controls.Add(ok);
                form.Controls.Add(cancel);
                form.AcceptButton = ok;
                form.CancelButton = cancel;
                form.Shown += (_, __) => box.Focus();
                return form.ShowDialog() == DialogResult.OK ? box.Text : null;
            }
        }
    }
}
