using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;
using AWIS.InventorBridge.Models;

namespace AWIS.InventorBridge.CollisionGeometry
{
    /// <summary>
    /// Companion JSON used by the AWIS Tool Collision Layer.
    ///
    /// V0.3.0 preserves the stable V0.2 adaptive AABB/OBB/cylinder output
    /// and adds a separate mesh companion for irregular low-fill collision
    /// candidates. The main package remains the light spatial index; mesh
    /// vertices/triangles are intentionally excluded from this JSON.
    /// </summary>
    public sealed class CollisionGeometryPackage
    {
        public string Schema { get; set; } =
            "AWIS_COLLISION_GEOMETRY";

        public string Version { get; set; } =
            "0.3.0";

        public string TankName { get; set; } =
            string.Empty;

        public string DocumentName { get; set; } =
            string.Empty;

        public DateTime ExportTime { get; set; }

        public string Units { get; set; } =
            "mm";

        public string Purpose { get; set; } =
            "STATIC_TANK_COLLISION_ENVIRONMENT";

        public string DefaultRepresentation { get; set; } =
            "AABB_BROAD_PHASE_PLUS_ADAPTIVE_NARROW_PHASE";

        public CollisionRepresentationPolicy RepresentationPolicy { get; set; } =
            new();

        public CollisionCoordinateSystem CoordinateSystem { get; set; } =
            new();

        public List<CollisionComponentRecord> Components { get; set; } =
            new();

        public CollisionGeometryStatistics Statistics { get; set; } =
            new();

        public List<string> Warnings { get; set; } =
            new();
    }


    public sealed class CollisionRepresentationPolicy
    {
        public double ObbPreferredMinFillRatio { get; set; } =
            0.80;

        public double VeryTightFillRatio { get; set; } =
            0.95;

        public double ModerateFillRatio { get; set; } =
            0.50;

        public double LooseFillRatio { get; set; } =
            0.25;

        public string SimpleCylinderRule { get; set; } =
            "1-2 cylindrical faces, <=2 planar faces, no other surface types, and two approximately equal OBB dimensions";

        public string MeshRule { get; set; } =
            "If no exact simple cylinder envelope is available and OBB fill ratio is below 0.80, mark MESH_REQUIRED";

        public string SafetyBehavior { get; set; } =
            "V0.3 never discards the conservative OBB/AABB fallback. MESH_REQUIRED collision candidates are exported to the separate AWIS_COLLISION_MESHES companion when faceting succeeds.";

        public double MeshChordToleranceMm { get; set; } =
            1.0;

        public string MeshExportScope { get; set; } =
            "MESH_REQUIRED_COLLISION_CANDIDATES_ONLY";

        public string MeshCompanionSchema { get; set; } =
            "AWIS_COLLISION_MESHES";

        public string MeshSafetyRule { get; set; } =
            "Treat the mesh as a chord-tolerance approximation and inflate collision clearance by at least the mesh SourceChordToleranceMm before declaring SAFE.";
    }


    public sealed class CollisionCoordinateSystem
    {
        public string AssemblySpace { get; set; } =
            "INVENTOR_ASSEMBLY_MODEL_SPACE";

        public string AssemblyUnitsSource { get; set; } =
            "Inventor internal cm converted to mm";

        public CollisionTankFrame TankFrame { get; set; } =
            new();
    }


    public sealed class CollisionTankFrame
    {
        public bool Resolved { get; set; }

        public string Status { get; set; } =
            "UNRESOLVED";

        public string CoordinateConvention { get; set; } =
            "X=AXIS_1, Y=AXIS_2, Z=AXIS_3; origin at the three NEGATIVE Tank Frame planes";

        public Point3Data OriginAssemblyMm { get; set; } =
            new();

        public List<CollisionFrameAxis> Axes { get; set; } =
            new();
    }


    public sealed class CollisionFrameAxis
    {
        public string AxisName { get; set; } =
            string.Empty;

        public Vector3Data DirectionAssembly { get; set; } =
            new();

        public double NegativePlaneProjectionMm { get; set; }

        public double PositivePlaneProjectionMm { get; set; }

        public bool NegativeBoundaryDetected { get; set; }

        public bool PositiveBoundaryDetected { get; set; }

        public double SpanMm { get; set; }

        public bool SpanConfirmed { get; set; }
    }


    public sealed class CollisionComponentRecord
    {
        public string ComponentId { get; set; } =
            string.Empty;

        public string OccurrenceName { get; set; } =
            string.Empty;

        public string OccurrencePath { get; set; } =
            string.Empty;

        public string RoleHint { get; set; } =
            "COLLISION_CANDIDATE";

        public bool IsTankBoundarySource { get; set; }

        public CollisionBounds3D AssemblyAabbMm { get; set; } =
            new();

        public CollisionBounds3D? TankFrameAabbMm { get; set; }

        public List<CollisionBodyRecord> Bodies { get; set; } =
            new();
    }


    public sealed class CollisionBodyRecord
    {
        public int BodyIndex { get; set; }

        public CollisionGeometryDescriptor CollisionGeometry { get; set; } =
            new();

        public CollisionGeometryAssessment GeometryAssessment { get; set; } =
            new();

        public bool IsSolid { get; set; }

        public double? VolumeMm3 { get; set; }

        public CollisionBounds3D AssemblyAabbMm { get; set; } =
            new();

        public CollisionBounds3D? TankFrameAabbMm { get; set; }

        public CollisionOrientedBox3D? AssemblyObbMm { get; set; }

        public CollisionOrientedBox3D? TankFrameObbMm { get; set; }

        public CollisionCylinder3D? AssemblyCylinderMm { get; set; }

        public CollisionCylinder3D? TankFrameCylinderMm { get; set; }

        public CollisionMeshReference? MeshReference { get; set; }

        // Runtime-only payload used by CollisionMeshExporter. Keeping this
        // out of the main JSON prevents the spatial index from becoming huge.
        [JsonIgnore]
        public CollisionMeshRecord? MeshData { get; set; }
    }


    public sealed class CollisionGeometryDescriptor
    {
        public string Type { get; set; } =
            "OBB_BOX";

        public string Accuracy { get; set; } =
            "CONSERVATIVE_MINIMUM_ORIENTED_BOX";

        public string Source { get; set; } =
            "INVENTOR_SURFACE_BODY_ORIENTED_MINIMUM_RANGE_BOX";

        public string BroadPhaseSource { get; set; } =
            "INVENTOR_SURFACE_BODY_PRECISE_RANGE_BOX";

        public string Notes { get; set; } =
            "V0.3 preserves AABB broad phase and conservative OBB fallback. Irregular low-fill collision candidates can reference a separate faceted mesh companion.";
    }


    public sealed class CollisionGeometryAssessment
    {
        public double? ObbVolumeMm3 { get; set; }

        public double? FillRatio { get; set; }

        public string FillRatioClass { get; set; } =
            "UNAVAILABLE";

        public string RecommendedNarrowPhase { get; set; } =
            "UNASSESSED";

        public string RecommendationReason { get; set; } =
            string.Empty;

        public CollisionSurfaceProfile SurfaceProfile { get; set; } =
            new();
    }


    public sealed class CollisionSurfaceProfile
    {
        public int TotalFaceCount { get; set; }

        public int PlanarFaceCount { get; set; }

        public int CylindricalFaceCount { get; set; }

        public int OtherFaceCount { get; set; }

        public bool HasCylindricalFaces { get; set; }

        public bool LooksLikeSimpleCylinder { get; set; }
    }


    public sealed class CollisionCylinder3D
    {
        public Point3Data StartCenter { get; set; } =
            new();

        public Point3Data EndCenter { get; set; } =
            new();

        public Vector3Data AxisDirection { get; set; } =
            new();

        public double RadiusMm { get; set; }

        public double HeightMm { get; set; }

        public bool IsConservativeEnvelope { get; set; } =
            true;
    }


    public sealed class CollisionOrientedBox3D
    {
        public Point3Data Corner { get; set; } =
            new();

        // Each edge vector includes both direction and length.
        public Vector3Data EdgeOne { get; set; } =
            new();

        public Vector3Data EdgeTwo { get; set; } =
            new();

        public Vector3Data EdgeThree { get; set; } =
            new();

        public Point3Data EdgeLengthsMm { get; set; } =
            new();
    }


    public sealed class CollisionBounds3D
    {
        public Point3Data Min { get; set; } =
            new();

        public Point3Data Max { get; set; } =
            new();

        public Point3Data Center { get; set; } =
            new();

        public Point3Data Size { get; set; } =
            new();
    }


    public sealed class CollisionGeometryStatistics
    {
        public int OccurrencesVisited { get; set; }

        public int PartOccurrencesExported { get; set; }

        public int SurfaceBodiesExported { get; set; }

        public int EmptyPartOccurrencesSkipped { get; set; }

        public int SuppressedOccurrencesSkipped { get; set; }

        public int BodyFailures { get; set; }

        public int BoundarySourceComponents { get; set; }

        public int ObbPreferredBodies { get; set; }

        public int CylinderBodies { get; set; }

        public int MeshRequiredBodies { get; set; }

        public int AabbFallbackBodies { get; set; }

        public int BodiesWithoutVolumeAssessment { get; set; }

        public int MeshExportedBodies { get; set; }

        public int MeshFailedBodies { get; set; }

        public int MeshSkippedBoundaryBodies { get; set; }

        public int ExistingFacetFallbackBodies { get; set; }

        public long MeshVertexCount { get; set; }

        public long MeshTriangleCount { get; set; }
    }
}
