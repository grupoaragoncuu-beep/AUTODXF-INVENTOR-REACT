using System;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

namespace AutoDXF.AddIn
{
    internal static class IconPictures
    {
        public static object Small() => FromResource(32);
        public static object Large() => FromResource(128);

        private static object FromResource(int size)
        {
            using (Bitmap source = LoadSource())
            using (var scaled = new Bitmap(source, size, size))
            {
                return PictureHost.Convert(scaled);
            }
        }

        private static Bitmap LoadSource()
        {
            Assembly assembly = typeof(IconPictures).Assembly;
            using (Stream stream = assembly.GetManifestResourceStream("AutoDXF.AddIn.Icons.modulo-ingenieria.jpg"))
            {
                if (stream == null)
                    throw new InvalidOperationException("No está el icono del módulo.");
                return new Bitmap(stream);
            }
        }

        private sealed class PictureHost : AxHost
        {
            private PictureHost() : base("") { }

            public static object Convert(Image image)
            {
                return GetIPictureDispFromPicture(image);
            }
        }
    }
}
