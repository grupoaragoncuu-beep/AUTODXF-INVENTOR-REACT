using System;
using System.Collections.Generic;
using AWIS.InventorBridge.Models;

namespace AWIS.InventorBridge.CollisionGeometry
{
    /// <summary>
    /// Heavy companion containing only triangle meshes requested by the
    /// Collision Geometry index. Vertices are a flat XYZ list in millimeters;
    /// triangle indices are flat zero-based triples. Normals are intentionally
    /// omitted because AWIS collision tests only require occupied geometry.
    /// </summary>
    public sealed class CollisionMeshPackage
    {
        public string Schema { get; set; } =
            "AWIS_COLLISION_MESHES";

        public string Version { get; set; } =
            "0.3.0";

        public string TankName { get; set; } =
            string.Empty;

        public string DocumentName { get; set; } =
            string.Empty;

        public DateTime ExportTime { get; set; }

        public string Units { get; set; } =
            "mm";

        public CollisionMeshPolicy Policy { get; set; } =
            new();

        public List<CollisionMeshRecord> Meshes { get; set; } =
            new();

        public CollisionMeshStatistics Statistics { get; set; } =
            new();
    }


    public sealed class CollisionMeshPolicy
    {
        public double RequestedChordToleranceMm { get; set; } =
            1.0;

        public string ExportScope { get; set; } =
            "MESH_REQUIRED_COLLISION_CANDIDATES_ONLY";

        public string VertexEncoding { get; set; } =
            "FLAT_XYZ_MM";

        public string TriangleEncoding { get; set; } =
            "FLAT_ZERO_BASED_VERTEX_INDEX_TRIPLES";

        public string SafetyRule { get; set; } =
            "Before declaring clearance SAFE, subtract at least each mesh SourceChordToleranceMm from geometric mesh clearance, in addition to the configured tool safety margin.";
    }


    public sealed class CollisionMeshReference
    {
        public string MeshId { get; set; } =
            string.Empty;

        public string CompanionSchema { get; set; } =
            "AWIS_COLLISION_MESHES";

        public string CompanionFileName { get; set; } =
            string.Empty;

        public string Status { get; set; } =
            "NOT_REQUESTED";

        public string CoordinateSpace { get; set; } =
            string.Empty;

        public double? SourceChordToleranceMm { get; set; }

        public double? RequiredCollisionInflationMm { get; set; }

        public int VertexCount { get; set; }

        public int TriangleCount { get; set; }

        public string GenerationMethod { get; set; } =
            string.Empty;

        public string Message { get; set; } =
            string.Empty;
    }


    public sealed class CollisionMeshRecord
    {
        public string MeshId { get; set; } =
            string.Empty;

        public string ComponentId { get; set; } =
            string.Empty;

        public string OccurrenceName { get; set; } =
            string.Empty;

        public string OccurrencePath { get; set; } =
            string.Empty;

        public int BodyIndex { get; set; }

        public string CoordinateSpace { get; set; } =
            string.Empty;

        public string GenerationMethod { get; set; } =
            string.Empty;

        public double SourceChordToleranceMm { get; set; }

        public double RequiredCollisionInflationMm { get; set; }

        public int VertexCount { get; set; }

        public int TriangleCount { get; set; }

        public CollisionBounds3D BoundsMm { get; set; } =
            new();

        public List<double> VerticesMm { get; set; } =
            new();

        public List<int> TriangleVertexIndices { get; set; } =
            new();
    }


    public sealed class CollisionMeshStatistics
    {
        public int MeshCount { get; set; }

        public long TotalVertexCount { get; set; }

        public long TotalTriangleCount { get; set; }
    }
}
