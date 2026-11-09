namespace AWIS.InventorBridge.Models
{
    public sealed class TankDetectionResult
    {
        public string AwisVersion { get; set; } =
            "Bridge V0.2B.2";


        // Nombre explícito del tanque.
        // Se deriva del documento activo sin extensión.
        public string TankName { get; set; } =
            string.Empty;


        public string DocumentName { get; set; } =
            string.Empty;

        public DateTime DetectionTime { get; set; }


        public int PlanarFacesInput { get; set; }

        public int CandidateFacesAnalyzed { get; set; }

        public int OrientationFamiliesFound { get; set; }


        public double CandidateAreaThresholdMm2
        {
            get;
            set;
        }


        // Cobertura mínima necesaria para aceptar
        // una superficie como límite estructural.
        public double BoundaryCoverageMinimum
        {
            get;
            set;
        }


        // El frame puede ser válido aunque el modelo
        // esté abierto y falte una tapa.
        public bool FrameValid { get; set; }

        public double Confidence { get; set; }


        // ============================================================
        // MODEL COMPLETENESS
        // ============================================================

        public int DetectedBoundaryCount { get; set; }

        public int MissingBoundaryCount { get; set; }

        public double BoundaryCompleteness { get; set; }

        public string ModelClosureStatus { get; set; } =
            string.Empty;


        public List<TankAxisResult> Axes
        {
            get;
            set;
        } = new();


        public List<string> Warnings
        {
            get;
            set;
        } = new();
    }
}