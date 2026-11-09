using System.Collections.Generic;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // ================================================================
    // AWIS V1.1-A
    // INVENTOR WELD INTERFACE COMPANION V0.3.4
    //
    // Contrato geométrico.
    // NO representa todavía soldaduras confirmadas.
    // ================================================================

    public class WeldInterfacePackage
    {
        public string Schema { get; set; } =
            "AWIS_WELD_INTERFACES";

        public string Version { get; set; } =
            "0.3.8";

        public string AwisStage { get; set; } =
            "V1.1";

        public string GeneratorVersion { get; set; } =
            "Inventor Weld Interface Companion V0.3.8-MULTIBODY_CONTACT";

        public string TankName { get; set; } =
            "";

        public string DocumentName { get; set; } =
            "";

        public string Units { get; set; } =
            "mm";

        public WeldInterfaceSourceInfo Sources { get; set; } =
            new();

        public WeldInterfaceThresholds Thresholds { get; set; } =
            new();

        public List<WeldInterfaceFaceRecord> Faces { get; set; } =
            new();

        public List<WeldSurfaceVariant> SurfaceVariants { get; set; } = new();

        public WeldInterfaceStatistics Statistics { get; set; } =
            new();

        public List<string> Warnings { get; set; } =
            new();
    }


    public class WeldInterfaceSourceInfo
    {
        public string TankDetectionFile { get; set; } =
            "";

        public string TankDetectionSha256 { get; set; } =
            "";

        public string FacePreviewFile { get; set; } =
            "";

        public string FacePreviewSha256 { get; set; } =
            "";

        public string FacePreviewSchema { get; set; } =
            "";

        public string FacePreviewVersion { get; set; } =
            "";
    }


    public class WeldInterfaceThresholds
    {
        public bool ExportSegmentSurfaceVariants { get; set; } = true;
        public double InnerSurfaceParallelToleranceDeg { get; set; } = 0.01;
        public double InnerSurfaceMinimumAreaRatio { get; set; } = 0.75;
        public double InnerSurfaceFootprintToleranceMm { get; set; } = 0.5;
        public double InnerSurfaceMaximumThicknessMm { get; set; } = 100.0;

        public double ContactToleranceMm { get; set; } =
            0.25;

        public double NearContactToleranceMm { get; set; } =
            1.0;

        public double CoplanarAngleToleranceDeg { get; set; } =
            4.0;

        public double BroadPhasePlaneBandMm { get; set; } =
            40.0;

        public double BroadPhaseSurfaceMarginMm { get; set; } =
            75.0;

        public double CurveJoinToleranceMm { get; set; } =
            0.25;

        public double CurveDedupeToleranceMm { get; set; } =
            0.10;

        public double MinimumCoincidentAreaMm2 { get; set; } =
            1.0;

        // Tolerancia exclusivamente para consolidar segmentos que
        // repiten un COINCIDENT_FACE_LOOP ya resuelto.
        public double RedundantEdgeToLoopToleranceMm { get; set; } =
            0.50;

        // El envelope útil sigue siendo exactamente 0..Width,
        // 0..Height. Esta tolerancia evita microfragmentos numéricos
        // durante el clipping.
        public double EnvelopeClipToleranceMm { get; set; } =
            0.01;

        // V0.3.2:
        // Para una cara coplanar con agujeros/perfiles huecos, únicamente
        // el loop exterior representa el perímetro físicamente soldable.
        // Los loops interiores son cavidades y no deben convertirse en
        // un segundo candidato por cada lado.
        public bool KeepOnlyOuterCoincidentFaceLoops { get; set; } =
            true;

        // Para secciones B-Rep, elimina wires cerrados que estén contenidos
        // dentro de otro wire cerrado del mismo body (por ejemplo el
        // contorno interior de un brace/tubo rectangular hueco).
        public bool SuppressNestedSectionWires { get; set; } =
            true;

        // V0.3.3:
        // Algunos braces OTC llegan como cuatro tiras coplanares angostas
        // (dos verticales + dos horizontales). Cada tira contiene dos
        // bordes largos, pero físicamente solo el perímetro exterior del
        // frame debe convertirse en candidato de soldadura.
        public bool ResolveBraceFrameOuterWeldEdges { get; set; } =
            true;

        // Una tira candidata a brace debe ser claramente alargada.
        public double BraceFrameMinimumAspectRatio { get; set; } =
            4.0;

        // Ancho máximo de la cara coplanar angosta usada como tira de brace.
        // Es intencionalmente configurable y solo se usa junto con la
        // validación completa 2H + 2V del frame.
        public double BraceFrameMaximumStripWidthMm { get; set; } =
            75.0;

        // Holgura geométrica adicional al validar que las cuatro tiras
        // realmente cierren un frame común.
        public double BraceFrameClosureToleranceMm { get; set; } =
            2.0;

        // V0.3.4:
        // Algunas penetraciones circulares OTC llegan de Inventor como un
        // wire anular: arco casi 360 externo + conector corto + arco casi
        // 360 interno + conector corto. Solo la circunferencia exterior
        // representa el cordón físico en la cara seleccionada.
        public bool ResolveAnnularSectionOuterWeldEdge { get; set; } =
            true;

        // Espesor radial máximo admisible para reconocer el patrón anular.
        // La regla también exige dos curvas concéntricas y dos conectores.
        public double AnnularSectionMaximumThicknessMm { get; set; } =
            75.0;

        // Error radial máximo permitido al ajustar cada curva a un círculo.
        public double AnnularSectionCircularityToleranceMm { get; set; } =
            0.75;

        // Diferencia máxima entre los centros ajustados de ambas curvas.
        public double AnnularSectionCenterToleranceMm { get; set; } =
            1.0;

        // Cobertura angular mínima de cada curva para considerarla una
        // circunferencia casi completa y poder reconstruir 360 grados.
        public double AnnularSectionMinimumCoverageDeg { get; set; } =
            300.0;

        // Paso objetivo para reconstruir la circunferencia completa.
        public double AnnularSectionTargetSampleStepMm { get; set; } =
            25.0;
    }


    public class WeldSurfaceVariant
    {
        public string SurfaceId { get; set; } = "";
        public string ParentFaceId { get; set; } = "";
        public string SegmentId { get; set; } = "";
        public string SurfaceSide { get; set; } = "";
        public string ResolutionStatus { get; set; } = "unresolved";
        public bool Resolved { get; set; }
        public bool ReadyForProgramming { get; set; } = false;
        public string CoordinateContract { get; set; } = "CANONICAL_FACE_UV_WITH_REAL_MODEL3D";
        public string PresentationRequirement { get; set; } = "SELECTED_SURFACE_FACING_UP_SEPARATE_SEGMENT";
        public string InteriorViewRule { get; set; } = "U_VIEW=MAX_U-U_CANONICAL; V_VIEW=V_CANONICAL-MIN_V; IN_PLANE_ROTATION_UNRESOLVED";
        public double? MeasuredWallThicknessMm { get; set; }
        public WeldVector3 SurfaceNormal { get; set; } = new();
        public WeldInterfaceFaceRecord Geometry { get; set; } = new();
        public WeldInterfaceStatistics Statistics { get; set; } = new();
        public List<string> Warnings { get; set; } = new();
    }

    public class WeldInterfaceFaceRecord
    {
        public string FaceId { get; set; } =
            "";

        public string SurfaceSide { get; set; } = "EXTERIOR";
        public string SegmentId { get; set; } = "";

        public string AxisName { get; set; } =
            "";

        public string Side { get; set; } =
            "";

        public double WidthMm { get; set; }

        public double HeightMm { get; set; }

        // V0.2.2:
        // Real structural wall extent projected in canonical Face-Local UV.
        // WidthMm / HeightMm above remain the canonical Tank Frame dimensions.
        public WeldPhysicalWallGeometry PhysicalWall { get; set; } =
            new();

        public WeldPoint3Mm OriginMm { get; set; } =
            new();

        public WeldVector3 OutwardNormal { get; set; } =
            new();

        public WeldVector3 LocalU { get; set; } =
            new();

        public WeldVector3 LocalV { get; set; } =
            new();

        public WeldContactPlane ContactPlane { get; set; } = new();

        public WeldStructuralSource StructuralSource { get; set; } =
            new();

        public List<WeldInterfaceRecord> Interfaces { get; set; } =
            new();
    }


    public class WeldContactPlane
    {
        public bool Resolved { get; set; }
        public string ResolutionStatus { get; set; } = "canonical_fallback";
        public WeldPoint3Mm OriginMm { get; set; } = new();
        public WeldVector3 Normal { get; set; } = new();
        public double TiltFromCanonicalDeg { get; set; }
        public string SourceOccurrencePath { get; set; } = "";
        public int SourceBodyIndex { get; set; }
        public int SourceFaceIndex { get; set; }
    }

    public class WeldPhysicalWallGeometry
    {
        public bool Resolved { get; set; }

        public string ResolutionStatus { get; set; } =
            "unresolved";

        public WeldPhysicalWallBounds Bounds { get; set; } =
            new();

        // Legacy anchor loop retained for compatibility.
        public List<WeldPoint2Mm> OuterLoop { get; set; } =
            new();

        public int SegmentCount { get; set; }

        public List<WeldPhysicalWallSegment> Segments { get; set; } =
            new();

        // Manufacturing seams detected geometrically by Face Preview.
        // They are candidates only; weld type remains UNCONFIRMED.
        public List<WeldStructuralSeam> StructuralSeams { get; set; } =
            new();
    }


    public class WeldPhysicalWallSegment
    {
        public string SegmentId { get; set; } =
            "";

        public bool IsAnchorSegment { get; set; }

        public string OccurrenceName { get; set; } =
            "";

        public string OccurrencePath { get; set; } =
            "";

        public int SourceBodyIndex { get; set; }

        public int SourceFaceIndex { get; set; }

        public int SourceLoopIndex { get; set; }

        public double SourceFaceDepthMm { get; set; }

        public double ProjectedAreaMm2 { get; set; }

        public WeldPhysicalWallBounds Bounds { get; set; } =
            new();

        public List<WeldPoint2Mm> OuterLoop { get; set; } =
            new();
    }


    public class WeldStructuralSeam
    {
        public string SeamId { get; set; } =
            "";

        public string SegmentAId { get; set; } =
            "";

        public string SegmentBId { get; set; } =
            "";

        public string SeparationAxis { get; set; } =
            "";

        public double GapMm { get; set; }

        public double LengthMm { get; set; }

        public string Classification { get; set; } =
            "PANEL_TO_PANEL_SEAM";

        public string WeldClassification { get; set; } =
            "UNCONFIRMED";

        public string DetectionStatus { get; set; } =
            "GEOMETRY_DETECTED";

        public List<WeldPoint2Mm> FaceLocalCenterline { get; set; } =
            new();
    }


    public class WeldPhysicalWallBounds
    {
        public double MinU { get; set; }

        public double MaxU { get; set; }

        public double MinV { get; set; }

        public double MaxV { get; set; }

        public double WidthMm { get; set; }

        public double HeightMm { get; set; }
    }


    public readonly struct WeldWallBounds
    {
        public WeldWallBounds(
            double minU,
            double maxU,
            double minV,
            double maxV)
        {
            MinU = minU;
            MaxU = maxU;
            MinV = minV;
            MaxV = maxV;
        }

        public double MinU { get; }

        public double MaxU { get; }

        public double MinV { get; }

        public double MaxV { get; }
    }


    public static class WeldInterfaceWallGeometry
    {
        public static WeldWallBounds GetBounds(
            WeldInterfaceFaceRecord wall)
        {
            if (wall.PhysicalWall != null
                &&
                wall.PhysicalWall.Resolved
                &&
                wall.PhysicalWall.Bounds != null
                &&
                wall.PhysicalWall.Bounds.MaxU >
                    wall.PhysicalWall.Bounds.MinU
                &&
                wall.PhysicalWall.Bounds.MaxV >
                    wall.PhysicalWall.Bounds.MinV)
            {
                return new WeldWallBounds(
                    wall.PhysicalWall.Bounds.MinU,
                    wall.PhysicalWall.Bounds.MaxU,
                    wall.PhysicalWall.Bounds.MinV,
                    wall.PhysicalWall.Bounds.MaxV);
            }


            return new WeldWallBounds(
                0.0,
                wall.WidthMm,
                0.0,
                wall.HeightMm);
        }


        public static bool Contains(
            WeldPoint2Mm point,
            WeldInterfaceFaceRecord wall,
            double margin)
        {
            WeldWallBounds bounds =
                GetBounds(
                    wall);


            return
                point.X >=
                    bounds.MinU - margin
                &&
                point.X <=
                    bounds.MaxU + margin
                &&
                point.Y >=
                    bounds.MinV - margin
                &&
                point.Y <=
                    bounds.MaxV + margin;
        }
    }


    public class WeldStructuralSource
    {
        public string OccurrenceName { get; set; } =
            "";

        public string OccurrencePath { get; set; } =
            "";

        public int BodyIndex { get; set; }

        public int FaceIndex { get; set; }

        public int FaceRecordIndex { get; set; }
    }


    public class WeldInterfaceRecord
    {
        public string SurfaceId { get; set; } = "";
        public string SurfaceSide { get; set; } = "EXTERIOR";
        public string SegmentId { get; set; } = "";
        public string InterfaceId { get; set; } =
            "";

        // V0.3.1: identifies whether this record came from the
        // regular component-interface detector or from a structural
        // seam already resolved by Face Preview.
        public string CandidateKind { get; set; } =
            "COMPONENT_INTERFACE";

        public string FaceId { get; set; } =
            "";

        public string StructuralSeamId { get; set; } =
            "";

        public string SegmentAId { get; set; } =
            "";

        public string SegmentBId { get; set; } =
            "";

        public string Classification { get; set; } =
            "";

        public string WeldClassification { get; set; } =
            "UNCONFIRMED";

        public string DetectionStatus { get; set; } =
            "";

        public double? GapMm { get; set; }

        public string ComponentOccurrenceName { get; set; } =
            "";

        public string ComponentOccurrencePath { get; set; } =
            "";

        public bool IsStructuralBoundaryComponent { get; set; }

        public string ContactState { get; set; } =
            "NO_CONTACT";

        public bool? ContactDetected { get; set; }

        public bool? ContactGeometryResolved { get; set; }

        public string ResolutionStatus { get; set; } =
            "";

        public double MinimumPlaneDistanceMm { get; set; }

        public double CoincidentAreaMetricMm2 { get; set; }

        public int UnresolvedPlaneCrossingPointCount { get; set; }

        public List<string> Evidence { get; set; } =
            new();

        public WeldBoundaryFilterAudit BoundaryFilter { get; set; } =
            new();

        public List<WeldInterfacePath> Paths { get; set; } =
            new();
    }


    public class WeldBoundaryFilterAudit
    {
        public string CoincidentFaceLoopPolicy { get; set; } =
            "OUTER_BOUNDARY_ONLY";

        public string SectionWirePolicy { get; set; } =
            "SUPPRESS_NESTED_VOID_WIRES";

        public string BraceFramePolicy { get; set; } =
            "OUTER_PERIMETER_EDGE_ONLY";

        public string AnnularSectionPolicy { get; set; } =
            "RECONSTRUCT_OUTER_CIRCUMFERENCE_ONLY";

        public int InnerCoincidentFaceLoopsSuppressed { get; set; }

        public int NestedSectionWiresSuppressed { get; set; }

        // V0.3.3: cantidad de loops coplanares cerrados que fueron
        // convertidos en un solo borde físico de soldadura porque
        // pertenecían a un brace rectangular validado.
        public int BraceFrameClosedLoopsConverted { get; set; }

        public List<string> BraceFrameGroupIds { get; set; } =
            new();

        // V0.3.4: wires anulares B-Rep reducidos a una sola
        // circunferencia exterior cerrada.
        public int AnnularSectionWiresResolved { get; set; }

        public int AnnularSectionPathsSuppressed { get; set; }

        public bool Applied =>
            InnerCoincidentFaceLoopsSuppressed > 0
            ||
            NestedSectionWiresSuppressed > 0
            ||
            BraceFrameClosedLoopsConverted > 0
            ||
            AnnularSectionWiresResolved > 0;
    }


    public class WeldInterfacePath
    {
        public string PathId { get; set; } =
            "";

        public string SourceKind { get; set; } =
            "";

        public string GeometryType { get; set; } =
            "";

        public bool Closed { get; set; }

        public bool ClippedToWallEnvelope { get; set; }

        public double LengthMm { get; set; }

        public int SourceBodyIndex { get; set; }

        public int SourceFaceIndex { get; set; }

        public int SourceLoopIndex { get; set; }

        public int SourceEdgeIndex { get; set; }

        // V0.3.2 audit metadata. "OUTER" is an exposed/material-enclosing
        // boundary; "INNER_VOID" is intentionally suppressed before export.
        public string BoundaryRole { get; set; } =
            "UNSPECIFIED";

        public string BoundarySelectionReason { get; set; } =
            "";

        // Groups edges that belong to the same physical closed contour.
        // Useful downstream for brace/paired-member recognition without
        // pairing unrelated nearby lines.
        public string BoundaryGroupId { get; set; } =
            "";

        // V0.3.3 physical side metadata. These fields are informative for
        // AWIS grouping; they do not force a paired member downstream.
        public string PhysicalMemberType { get; set; } =
            "";

        public string PhysicalMemberGroupId { get; set; } =
            "";

        public string PhysicalSideRole { get; set; } =
            "";

        public string PhysicalBoundaryRole { get; set; } =
            "";

        public double? OriginalClosedLoopLengthMm { get; set; }

        public List<WeldPoint3Mm> Model3DPointsMm { get; set; } =
            new();

        public List<WeldPoint2Mm> FaceLocalPointsMm { get; set; } =
            new();
    }


    public class WeldPoint2Mm
    {
        public double X { get; set; }

        public double Y { get; set; }
    }


    public class WeldPoint3Mm
    {
        public double X { get; set; }

        public double Y { get; set; }

        public double Z { get; set; }
    }


    public class WeldVector3
    {
        public double X { get; set; }

        public double Y { get; set; }

        public double Z { get; set; }
    }


    public class WeldInterfaceStatistics
    {
        public int FacesProcessed { get; set; }

        // Todos los nodos del árbol recorridos.
        public int OccurrencesVisited { get; set; }

        // Nodos de subensamble que solo sirven para llegar a hojas.
        public int ParentOccurrencesSkipped { get; set; }

        // Hojas físicas con B-Rep aceptadas para análisis.
        public int LeafOccurrencesAccepted { get; set; }

        public int LeafOccurrencesWithoutBRepSkipped { get; set; }

        public int SuppressedOccurrencesSkipped { get; set; }

        public int OccurrenceWallPairsEvaluated { get; set; }

        public int OwnWallPairsSkipped { get; set; }
        public int OwnWallBodiesSkippedExact { get; set; }
        public int OwnWallBodiesSkippedSection { get; set; }
        public int SameOccurrenceBodyInterfacesEvaluated { get; set; }

        public int BroadPhaseCandidates { get; set; }

        public int ExactChecksPerformed { get; set; }

        public int BodiesVisited { get; set; }

        public int FacesVisited { get; set; }

        public int EdgesVisited { get; set; }

        public int EdgeSamplingFailures { get; set; }

        // B-Rep exact section.
        public int SectionAttempts { get; set; }

        public int SectionSuccesses { get; set; }

        public int SectionFailures { get; set; }

        public int SectionCopyTransformFailures { get; set; }

        public int SectionIntersectionFailures { get; set; }

        public int SectionPathsGenerated { get; set; }

        // Solo muestras de diagnóstico; se limita su cantidad
        // para no inflar el JSON.
        public List<string> SectionFailureSamples { get; set; } =
            new();

        // Limpieza/consolidación.
        public int PathsBeforeConsolidation { get; set; }

        public int PathsAfterConsolidation { get; set; }

        public int RedundantEdgePathsRemoved { get; set; }

        // V0.3.2 physical-boundary filtering.
        public int CoincidentFaceLoopsVisited { get; set; }

        public int InnerCoincidentFaceLoopsSuppressed { get; set; }

        public int SectionWiresVisited { get; set; }

        public int NestedSectionWiresSuppressed { get; set; }

        // V0.3.3 brace-frame physical edge selection.
        public int BraceFrameGroupsResolved { get; set; }

        public int BraceFrameClosedLoopsConverted { get; set; }

        // V0.3.4 annular B-Rep section reconstruction.
        public int AnnularSectionWiresResolved { get; set; }

        public int AnnularSectionPathsSuppressed { get; set; }

        // Envelope finito de la pared.
        // Cantidad de paths fuente que requirieron clipping.
        public int SourcePathsClipped { get; set; }

        // Fragmentos finales producidos por esos paths fuente.
        // Puede ser mayor que SourcePathsClipped.
        public int ClippedFragmentsGenerated { get; set; }

        public int PathsDiscardedOutsideEnvelope { get; set; }

        public int NoContact { get; set; }

        public int NearContact { get; set; }

        public int Touching { get; set; }

        public int Intersecting { get; set; }

        public int CoincidentArea { get; set; }

        public int Ambiguous { get; set; }

        public int InterfacesExported { get; set; }

        public int StructuralWallSegmentsImported { get; set; }

        public int StructuralSeamsImported { get; set; }

        // Structural seams promoted into Faces[].Interfaces[] as
        // first-class weld candidates.
        public int StructuralSeamCandidatesExported { get; set; }

        public int InterfacePathsResolved { get; set; }

        public int ExactAnalysisFailures { get; set; }
    }
}
