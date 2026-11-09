namespace AWIS.InventorBridge.Models
{
    public sealed class GeometryScanResult
    {
        public string AwisVersion { get; set; } = "Bridge V0.2A";

        public string SourceApplication { get; set; } =
            "Autodesk Inventor";

        public string DocumentName { get; set; } = string.Empty;

        public string DocumentFullPath { get; set; } = string.Empty;

        public DateTime ScanTime { get; set; }

        public int OccurrencesScanned { get; set; }

        public int TotalFacesScanned { get; set; }

        public int PlanarFacesFound { get; set; }

        public List<FaceRecord> PlanarFaces { get; set; } = new();
    }
}