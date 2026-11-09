namespace AWIS.InventorBridge.Models
{
    public sealed class TankBoundaryFace
    {
        // ============================================================
        // DETECTION STATUS
        // ============================================================

        public bool Detected { get; set; }

        public string Status { get; set; } =
            string.Empty;

        public string DetectionReason { get; set; } =
            string.Empty;


        // ============================================================
        // BOUNDARY IDENTITY
        // ============================================================

        public string Side { get; set; } =
            string.Empty;

        public int FaceRecordIndex { get; set; }

        public string OccurrenceName { get; set; } =
            string.Empty;

        public string OccurrencePath { get; set; } =
            string.Empty;

        public int BodyIndex { get; set; }

        public int FaceIndex { get; set; }


        // ============================================================
        // GEOMETRIC EVIDENCE
        // ============================================================

        // Área de la cara representativa elegida.
        public double AreaMm2 { get; set; }

        // Área acumulada de caras estructurales
        // prácticamente coplanares con esta candidata.
        public double PlaneAreaMm2 { get; set; }

        // Área esperada de esta pared según los spans
        // de los otros dos ejes.
        public double ExpectedAreaMm2 { get; set; }

        // PlaneAreaMm2 / ExpectedAreaMm2.
        public double AreaCoverageRatio { get; set; }

        public double ProjectionMm { get; set; }


        public Point3Data PointMm { get; set; } =
            new();

        public Vector3Data Normal { get; set; } =
            new();
    }
}