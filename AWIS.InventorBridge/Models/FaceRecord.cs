namespace AWIS.InventorBridge.Models
{
    public sealed class FaceRecord
    {
        public int Index { get; set; }

        public string OccurrenceName { get; set; } =
            string.Empty;

        public string OccurrencePath { get; set; } =
            string.Empty;

        public int BodyIndex { get; set; }

        public int FaceIndex { get; set; }

        public string SurfaceType { get; set; } =
            string.Empty;

        public double AreaMm2 { get; set; }


        public Point3Data PointMm { get; set; } =
            new();


        public Vector3Data Normal { get; set; } =
            new();


        // ============================================================
        // GROSS FOOTPRINT SUPPORT
        //
        // Puntos reales de los bordes de la cara.
        // Más adelante serán proyectados sobre el Tank Frame.
        // ============================================================

        public List<FaceBoundaryPoint> BoundaryPointsMm
        {
            get;
            set;
        } = new();
    }
}