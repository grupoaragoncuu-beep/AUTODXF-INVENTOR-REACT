namespace AWIS.InventorBridge.Models
{
    public sealed class TankAxisResult
    {
        public string AxisName { get; set; } =
            string.Empty;

        public Vector3Data Direction { get; set; } =
            new();


        // Cuando falta un límite, este valor se conserva
        // como separación geométrica provisional para
        // auditoría, pero SpanConfirmed será false.
        public double SpanMm { get; set; }

        public bool SpanConfirmed { get; set; }

        public string SpanStatus { get; set; } =
            string.Empty;


        public TankBoundaryFace NegativeBoundary
        {
            get;
            set;
        } = new();


        public TankBoundaryFace PositiveBoundary
        {
            get;
            set;
        } = new();
    }
}