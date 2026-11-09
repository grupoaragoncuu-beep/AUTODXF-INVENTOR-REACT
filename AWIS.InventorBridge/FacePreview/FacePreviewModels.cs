using System.Collections.Generic;

namespace AWIS.InventorBridge.FacePreview
{
    public class FacePreviewPackage
    {
        public string Schema { get; set; } =
            "AWIS_FACE_PREVIEWS";

        public string Version { get; set; } =
            "0.4.0";

        public string TankName { get; set; } =
            "";

        public string DocumentName { get; set; } =
            "";

        public string Units { get; set; } =
            "mm";

        public string SourceDetectionFile { get; set; } =
            "";

        public string ProjectionMethod { get; set; } =
            "PLANAR_FACE_EDGE_LOOPS";

        public string VisualCleaningMethod { get; set; } =
            "DETERMINISTIC_VISUAL_FILTERS";

        public string PhysicalWallMethod { get; set; } =
            "MULTI_SEGMENT_STRUCTURAL_WALL_IN_CANONICAL_FACE_UV";

        public PhysicalWallSegmentationSettings PhysicalWallSegmentation { get; set; } =
            new();

        public List<FacePreviewRecord> Faces { get; set; } =
            new();

        public FacePreviewStatistics Statistics { get; set; } =
            new();

        public List<string> Warnings { get; set; } =
            new();
    }


    public class FacePreviewRecord
    {
        public string FaceId { get; set; } =
            "";

        public string AxisName { get; set; } =
            "";

        public string Side { get; set; } =
            "";

        public double PlaneProjectionMm { get; set; }

        public string HorizontalAxisName { get; set; } =
            "";

        public int HorizontalAxisSign { get; set; } =
            1;

        public string VerticalAxisName { get; set; } =
            "";

        public int VerticalAxisSign { get; set; } =
            1;

        public Vector3Dto OriginMm { get; set; } =
            new();

        public Vector3Dto OutwardNormal { get; set; } =
            new();

        public Vector3Dto LocalU { get; set; } =
            new();

        public Vector3Dto LocalV { get; set; } =
            new();

        public double WidthMm { get; set; }

        public double HeightMm { get; set; }

        // Canonical Tank Frame envelope.
        // It remains 0..WidthMm / 0..HeightMm for V0 compatibility.
        public List<Point2Dto> Envelope { get; set; } =
            new();

        // V0.3.3:
        // Actual structural wall geometry in the SAME canonical UV system.
        // This is independent from the Tank Frame envelope.
        public PhysicalWallGeometry PhysicalWall { get; set; } =
            new();

        public BoundaryDetectionSource DetectionSource { get; set; } =
            new();

        public List<PreviewEntity> Entities { get; set; } =
            new();

        public FacePreviewCleaningStatistics Cleaning { get; set; } =
            new();
    }


    public class PhysicalWallGeometry
    {
        public bool Resolved { get; set; }

        public string ResolutionStatus { get; set; } =
            "unresolved";

        // Legacy anchor fields retained for backward compatibility.
        // They point to the V0 structural face used to seed segmentation.
        public string SourceEntityId { get; set; } =
            "";

        public int SourceBodyIndex { get; set; }

        public int SourceFaceIndex { get; set; }

        public int SourceLoopIndex { get; set; }

        // Union of all resolved structural segments.
        public PhysicalWallBounds Bounds { get; set; } =
            new();

        // Legacy outer loop: anchor segment loop.
        public List<Point2Dto> OuterLoop { get; set; } =
            new();

        public int SegmentCount { get; set; }

        public List<PhysicalWallSegment> Segments { get; set; } =
            new();

        public List<StructuralSeam> StructuralSeams { get; set; } =
            new();
    }


    public class PhysicalWallSegmentationSettings
    {
        // A second panel must be close to the same mounting plane.
        public double CoplanarDepthToleranceMm { get; set; } =
            2.0;

        // Deliberately wider than WeldInterfaces.NearContactToleranceMm.
        // This is a manufacturing-joint search, not a global contact rule.
        public double MaximumStructuralSeamGapMm { get; set; } =
            25.0;

        // Adjacent panels must share most of their confronting span.
        public double MinimumSharedSpanRatio { get; set; } =
            0.70;

        // Reject small accessories before adjacency growth.
        public double MinimumSegmentAreaRatioToCanonicalWall { get; set; } =
            0.12;

        public double MinimumSegmentNormalAlignment { get; set; } =
            0.995;

        public string Strategy { get; set; } =
            "ANCHOR_CONNECTED_COPLANAR_PANEL_SEGMENTS";
    }


    public class PhysicalWallSegment
    {
        public string SegmentId { get; set; } =
            "";

        public bool IsAnchorSegment { get; set; }

        public string SourceEntityId { get; set; } =
            "";

        public string OccurrenceName { get; set; } =
            "";

        public string OccurrencePath { get; set; } =
            "";

        public int SourceBodyIndex { get; set; }

        public int SourceFaceIndex { get; set; }

        public int SourceLoopIndex { get; set; }

        public double SourceFaceDepthMm { get; set; }

        public double NormalAlignment { get; set; }

        public double ProjectedAreaMm2 { get; set; }

        public PhysicalWallBounds Bounds { get; set; } =
            new();

        public List<Point2Dto> OuterLoop { get; set; } =
            new();
    }


    public class StructuralSeam
    {
        public string SeamId { get; set; } =
            "";

        public string SegmentAId { get; set; } =
            "";

        public string SegmentBId { get; set; } =
            "";

        // U_GAP => panels are separated along U and share V span.
        // V_GAP => panels are separated along V and share U span.
        public string SeparationAxis { get; set; } =
            "";

        public double GapMm { get; set; }

        public double SharedSpanStartMm { get; set; }

        public double SharedSpanEndMm { get; set; }

        public double LengthMm { get; set; }

        public string Classification { get; set; } =
            "PANEL_TO_PANEL_SEAM";

        public string WeldClassification { get; set; } =
            "UNCONFIRMED";

        public string DetectionStatus { get; set; } =
            "GEOMETRY_DETECTED";

        // Two points representing the centerline of the physical gap
        // in canonical Face-Local UV coordinates.
        public List<Point2Dto> FaceLocalCenterline { get; set; } =
            new();
    }


    public class PhysicalWallBounds
    {
        public double MinU { get; set; }

        public double MaxU { get; set; }

        public double MinV { get; set; }

        public double MaxV { get; set; }

        public double WidthMm { get; set; }

        public double HeightMm { get; set; }
    }


    public class BoundaryDetectionSource
    {
        public int FaceRecordIndex { get; set; }

        public string OccurrenceName { get; set; } =
            "";

        public string OccurrencePath { get; set; } =
            "";

        public int BodyIndex { get; set; }

        public int FaceIndex { get; set; }

        public double AreaMm2 { get; set; }

        public double AreaCoverageRatio { get; set; }

        public string DetectionReason { get; set; } =
            "";
    }


    public class PreviewEntity
    {
        public string EntityId { get; set; } =
            "";

        public string Role { get; set; } =
            "";

        public string LoopType { get; set; } =
            "";

        // V0.3.1:
        // WALL_OPENING / ACCESSORY.
        // No representa todavía una clasificación de soldadura.
        public string VisualRole { get; set; } =
            "";

        public string OccurrenceName { get; set; } =
            "";

        public string OccurrencePath { get; set; } =
            "";

        public int BodyIndex { get; set; }

        public int SourceFaceIndex { get; set; }

        public int SourceLoopIndex { get; set; }

        public double SourceFaceDepthMm { get; set; }

        public double SourceFaceAreaMm2 { get; set; }

        public double NormalAlignment { get; set; }

        public double ProjectedWidthMm { get; set; }

        public double ProjectedHeightMm { get; set; }

        public double ProjectedAreaMm2 { get; set; }

        public List<Point2Dto> Points { get; set; } =
            new();
    }


    public class Point2Dto
    {
        public double X { get; set; }

        public double Y { get; set; }
    }


    public class Vector3Dto
    {
        public double X { get; set; }

        public double Y { get; set; }

        public double Z { get; set; }
    }


    public class FacePreviewStatistics
    {
        public int FacesGenerated { get; set; }

        public int OccurrencesVisited { get; set; }

        public int SuppressedOccurrencesSkipped { get; set; }

        public int OccurrencesRejectedByRangeBox { get; set; }

        public int BodiesVisited { get; set; }

        public int FacesVisited { get; set; }

        public int PlanarFacesConsidered { get; set; }

        public int FacesRejectedByOrientation { get; set; }

        public int FacesRejectedByDepth { get; set; }

        public int FacesSelected { get; set; }

        public int LoopsVisited { get; set; }

        public int LoopsExported { get; set; }

        public int LoopSamplingFailures { get; set; }

        public int DegenerateLoopsRejected { get; set; }

        public int LoopsRejectedByEnvelope { get; set; }
    }


    public class FacePreviewCleaningStatistics
    {
        public int RawEntityCount { get; set; }

        public int DisplayEntityCount { get; set; }

        public int RejectedOwnWallOuter { get; set; }

        public int RejectedAdjacentWall { get; set; }

        public int RejectedPeripheralSupport { get; set; }

        public int RejectedOutsideEnvelope { get; set; }

        public int RejectedSmall { get; set; }

        public int RejectedDuplicate { get; set; }
    }
}
