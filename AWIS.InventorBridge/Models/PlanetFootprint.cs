namespace AWIS.InventorBridge.Models
{
    public sealed class PlaneFootprint
    {
        // ============================================================
        // PLANE IDENTITY
        // ============================================================

        // Posición del plano medida sobre su eje normal.
        public double ProjectionMm { get; set; }


        // Dirección normal canónica de esta familia.
        public Vector3Data NormalAxis { get; set; } =
            new();


        // Los otros dos ejes del Tank Frame.
        // Sobre ellos medimos Width y Height.
        public Vector3Data UAxis { get; set; } =
            new();

        public Vector3Data VAxis { get; set; } =
            new();


        // ============================================================
        // MATERIAL / GEOMETRY
        // ============================================================

        // Área real de acero presente en ese plano.
        //
        // Una ventana grande puede reducir mucho este valor.
        public double NetAreaMm2 { get; set; }


        // Límites exteriores proyectados sobre U.
        public double MinU { get; set; }

        public double MaxU { get; set; }


        // Límites exteriores proyectados sobre V.
        public double MinV { get; set; }

        public double MaxV { get; set; }


        // Extensión estructural exterior.
        public double WidthMm { get; set; }

        public double HeightMm { get; set; }


        // Width × Height.
        //
        // Este valor NO disminuye por ventanas internas.
        public double GrossAreaMm2 { get; set; }


        // NetArea / GrossArea.
        //
        // Sirve posteriormente para reconocer cuánto
        // material existe dentro del footprint.
        public double NetMaterialRatio { get; set; }


        // ============================================================
        // MEMBERS
        // ============================================================

        // Todas las caras coplanares utilizadas para construir
        // este plano estructural.
        public List<int> FaceRecordIndices { get; set; } =
            new();


        public int FaceCount =>
            FaceRecordIndices.Count;


        // Cara más grande del grupo.
        // La conservamos para auditoría y para localizar
        // nuevamente la geometría en Inventor.
        public int RepresentativeFaceRecordIndex
        {
            get;
            set;
        }


        public string RepresentativeOccurrenceName
        {
            get;
            set;
        } = string.Empty;


        public string RepresentativeOccurrencePath
        {
            get;
            set;
        } = string.Empty;


        public int RepresentativeBodyIndex
        {
            get;
            set;
        }


        public int RepresentativeFaceIndex
        {
            get;
            set;
        }
    }
}