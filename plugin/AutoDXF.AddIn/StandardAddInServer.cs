using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Inventor;

namespace AutoDXF.AddIn
{
    [ComVisible(true)]
    [Guid(StandardAddInServer.AddInGuid)]
    [ProgId("AutoDXF.StandardAddInServer")]
    public class StandardAddInServer : ApplicationAddInServer
    {
        public const string AddInGuid = "7C3E9A14-2B68-4F0D-9A51-6E8D4C1B70A2";
        private const string AddInClientId = "{" + AddInGuid + "}";

        private Inventor.Application _app;
        private ButtonDefinition _button;

        public void Activate(ApplicationAddInSite addInSiteObject, bool firstTime)
        {
            _app = addInSiteObject.Application;
            try
            {
                try
                {
                    _button = _app.CommandManager.ControlDefinitions.AddButtonDefinition(
                        "Módulo Ingenieria",
                        "ModuloIngenieria.Launch",
                        CommandTypesEnum.kNonShapeEditCmdType,
                        AddInClientId,
                        "Abre el Módulo Ingenieria y descarga la versión publicada en el servidor, si hay una nueva.",
                        "Módulo Ingenieria",
                        IconPictures.Small(),
                        IconPictures.Large(),
                        ButtonDisplayEnum.kAlwaysDisplayText);
                }
                catch
                {
                    _button = (ButtonDefinition)_app.CommandManager.ControlDefinitions["ModuloIngenieria.Launch"];
                }
                _button.OnExecute += OnExecute;
                foreach (string ribbonName in new[] { "Assembly", "Part", "Drawing", "ZeroDoc" })
                    AddTab(ribbonName);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "Módulo Ingenieria", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        public void Deactivate()
        {
            if (_button != null)
            {
                _button.OnExecute -= OnExecute;
                Marshal.ReleaseComObject(_button);
                _button = null;
            }
            if (_app != null)
            {
                Marshal.ReleaseComObject(_app);
                _app = null;
            }
            GC.Collect();
            GC.WaitForPendingFinalizers();
        }

        public void ExecuteCommand(int commandID)
        {
        }

        public object Automation => null;

        private void AddTab(string ribbonName)
        {
            Ribbon ribbon;
            try { ribbon = _app.UserInterfaceManager.Ribbons[ribbonName]; }
            catch { return; }
            RibbonTab tab = null;
            foreach (RibbonTab existing in ribbon.RibbonTabs)
            {
                if (existing.InternalName == "ModuloIngenieria.Tab") tab = existing;
            }
            if (tab == null)
                tab = ribbon.RibbonTabs.Add("Módulo Ingenieria", "ModuloIngenieria.Tab", AddInClientId);
            RibbonPanel panel = null;
            foreach (RibbonPanel existing in tab.RibbonPanels)
            {
                if (existing.InternalName == "ModuloIngenieria.Panel") panel = existing;
            }
            if (panel == null)
                panel = tab.RibbonPanels.Add("Módulo Ingenieria", "ModuloIngenieria.Panel", AddInClientId, "", false);
            panel.CommandControls.AddButton(_button, true);
        }

        private void OnExecute(NameValueMap context)
        {
            try
            {
                string message = LaunchCommand.Run();
                if (!string.IsNullOrWhiteSpace(message) && _app != null)
                    _app.StatusBarText = message;
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "Módulo Ingenieria", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }
    }
}
