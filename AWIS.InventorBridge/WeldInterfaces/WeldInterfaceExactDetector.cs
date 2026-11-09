using Inventor;
using System;
using System.Collections.Generic;
using System.Linq;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // ================================================================
    // V1.1-A / V0.2.1
    // GEOMETRIC INTERFACE DETECTOR
    //
    // Cambios:
    // - B-Rep section real para sólidos que cruzan la pared.
    // - Path consolidation.
    // - Finite wall clipping.
    // - MinimumPlaneDistance = 0 para contacto real.
    // ================================================================

    public class WeldInterfaceExactDetector
    {
        private const double CmToMm =
            10.0;


        private readonly WeldInterfacePathBuilder
            _pathBuilder =
                new WeldInterfacePathBuilder();


        private readonly WeldInterfaceSectionBuilder
            _sectionBuilder =
                new WeldInterfaceSectionBuilder();


        private readonly WeldInterfaceEnvelopeClipper
            _clipper =
                new WeldInterfaceEnvelopeClipper();


        public WeldInterfaceRecord? Analyze(
            Inventor.Application inventorApplication,
            WeldBroadPhaseCandidate candidate,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            WeldInterfaceStatistics statistics)
        {
            statistics
                .ExactChecksPerformed++;


            int innerCoincidentLoopsBefore =
                statistics
                    .InnerCoincidentFaceLoopsSuppressed;

            int nestedSectionWiresBefore =
                statistics
                    .NestedSectionWiresSuppressed;


            int annularSectionWiresBefore =
                statistics
                    .AnnularSectionWiresResolved;


            int annularSectionPathsBefore =
                statistics
                    .AnnularSectionPathsSuppressed;


            WeldInterfaceRecord record =
                new WeldInterfaceRecord
                {
                    FaceId =
                        wall.FaceId,

                    ComponentOccurrenceName =
                        candidate
                            .OccurrenceName,

                    ComponentOccurrencePath =
                        candidate
                            .OccurrencePath,

                    IsStructuralBoundaryComponent =
                        candidate
                            .IsStructuralBoundaryComponent,

                    MinimumPlaneDistanceMm =
                        double.IsInfinity(
                            candidate
                                .MinimumAbsoluteDepthMm)
                            ? 999999.0
                            : candidate
                                .MinimumAbsoluteDepthMm
                };


            List<WeldInterfacePath> rawPaths =
                new List<WeldInterfacePath>();


            bool hasTouchEvidence =
                false;

            bool hasIntersectionEvidence =
                false;

            bool hadExactGeometry =
                false;

            double minimumDistance =
                record
                    .MinimumPlaneDistanceMm;

            double coincidentArea =
                0.0;

            List<WeldPoint3Mm> unresolvedCrossings =
                new List<WeldPoint3Mm>();


            try
            {
                SurfaceBodies bodies =
                    candidate
                        .Occurrence
                        .SurfaceBodies;


                // ----------------------------------------------------
                // A. PLANAR COINCIDENT FACES
                // ----------------------------------------------------

                for (int bodyIndex = 1;
                     bodyIndex <= bodies.Count;
                     bodyIndex++)
                {
                    if (WeldWallBodyScope.IsWallBody(candidate.OccurrencePath, bodyIndex, wall))
                    {
                        statistics.OwnWallBodiesSkippedExact++;
                        continue;
                    }
                    statistics
                        .BodiesVisited++;


                    dynamic body =
                        bodies[bodyIndex];


                    try
                    {
                        dynamic faces =
                            body.Faces;


                        for (int faceIndex = 1;
                             faceIndex <= faces.Count;
                             faceIndex++)
                        {
                            statistics
                                .FacesVisited++;


                            dynamic face =
                                faces[faceIndex];


                            object geometry;


                            try
                            {
                                geometry =
                                    face.Geometry;
                            }
                            catch
                            {
                                continue;
                            }


                            if (geometry
                                is not Inventor.Plane plane)
                            {
                                continue;
                            }


                            hadExactGeometry =
                                true;


                            WeldVector3 faceNormal =
                                new WeldVector3
                                {
                                    X =
                                        plane.Normal.X,

                                    Y =
                                        plane.Normal.Y,

                                    Z =
                                        plane.Normal.Z
                                };


                            double angleDeg =
                                UnsignedAngleDeg(
                                    faceNormal,
                                    WeldContactPlaneResolver.Normal(wall));


                            if (angleDeg >
                                thresholds
                                    .CoplanarAngleToleranceDeg)
                            {
                                continue;
                            }


                            WeldPoint3Mm rootPoint =
                                new WeldPoint3Mm
                                {
                                    X =
                                        plane
                                            .RootPoint
                                            .X
                                        *
                                        CmToMm,

                                    Y =
                                        plane
                                            .RootPoint
                                            .Y
                                        *
                                        CmToMm,

                                    Z =
                                        plane
                                            .RootPoint
                                            .Z
                                        *
                                        CmToMm
                                };


                            double faceDepth =
                                Math.Abs(
                                    WallDepth(
                                        rootPoint,
                                        wall));


                            minimumDistance =
                                Math.Min(
                                    minimumDistance,
                                    faceDepth);


                            if (faceDepth >
                                thresholds
                                    .ContactToleranceMm)
                            {
                                continue;
                            }


                            double areaMm2 =
                                0.0;


                            try
                            {
                                areaMm2 =
                                    ((double)face
                                        .Evaluator
                                        .Area)
                                    *
                                    100.0;
                            }
                            catch
                            {
                                areaMm2 =
                                    0.0;
                            }


                            List<WeldInterfacePath> facePaths =
                                _pathBuilder
                                    .BuildFromFaceLoops(
                                        face,
                                        bodyIndex,
                                        faceIndex,
                                        wall,
                                        thresholds,
                                        statistics);


                            if (facePaths.Count == 0)
                            {
                                continue;
                            }


                            coincidentArea +=
                                Math.Max(
                                    0.0,
                                    areaMm2);


                            rawPaths.AddRange(
                                facePaths);
                        }
                    }
                    catch
                    {
                        // Un body puntual puede no exponer Faces.
                    }


                    // ------------------------------------------------
                    // B. EDGES ON WALL + CROSSING EVIDENCE
                    // ------------------------------------------------

                    try
                    {
                        dynamic edges =
                            body.Edges;


                        for (int edgeIndex = 1;
                             edgeIndex <= edges.Count;
                             edgeIndex++)
                        {
                            statistics
                                .EdgesVisited++;


                            dynamic edge =
                                edges[edgeIndex];


                            WeldEdgeSample sample =
                                _pathBuilder
                                    .SampleEdge(
                                        edge);


                            if (!sample.Success ||
                                sample.Points.Count < 2)
                            {
                                statistics
                                    .EdgeSamplingFailures++;

                                continue;
                            }


                            hadExactGeometry =
                                true;


                            List<double> depths =
                                sample
                                    .Points
                                    .Select(
                                        p =>
                                            WallDepth(
                                                p,
                                                wall))
                                    .ToList();


                            foreach (double depth
                                     in depths)
                            {
                                minimumDistance =
                                    Math.Min(
                                        minimumDistance,
                                        Math.Abs(
                                            depth));
                            }


                            bool allOnPlane =
                                depths.All(
                                    depth =>
                                        Math.Abs(
                                            depth)
                                        <=
                                        thresholds
                                            .ContactToleranceMm);


                            if (allOnPlane)
                            {
                                WeldInterfacePath? edgePath =
                                    _pathBuilder
                                        .BuildFromEdge(
                                            edge,
                                            bodyIndex,
                                            edgeIndex,
                                            wall,
                                            thresholds,
                                            "EDGE_ON_WALL");


                                if (edgePath != null &&
                                    edgePath.LengthMm >
                                    thresholds
                                        .CurveDedupeToleranceMm)
                                {
                                    rawPaths.Add(
                                        edgePath);

                                    hasTouchEvidence =
                                        true;
                                }


                                continue;
                            }


                            List<WeldPoint3Mm> crossings =
                                _pathBuilder
                                    .GetPlaneCrossingPoints(
                                        sample.Points,
                                        wall,
                                        thresholds);


                            if (crossings.Count > 0)
                            {
                                hasIntersectionEvidence =
                                    true;


                                foreach (WeldPoint3Mm point
                                         in crossings)
                                {
                                    AddUniquePoint(
                                        unresolvedCrossings,
                                        point,
                                        thresholds
                                            .CurveDedupeToleranceMm);
                                }
                            }
                        }
                    }
                    catch
                    {
                        // Un body puntual puede no exponer Edges.
                    }
                }


                // ----------------------------------------------------
                // C. EXACT B-REP SECTION
                //
                // Se intenta cuando:
                // - ya vimos un cruce real dentro del envelope, o
                // - el RangeBox de la pieza atraviesa el plano.
                //
                // No se usa como sustituto de COINCIDENT_AREA.
                // ----------------------------------------------------

                bool rangeSpansPlane =
                    RangeBoxSpansWallPlane(
                        candidate,
                        thresholds);


                List<WeldInterfacePath> sectionPaths =
                    new List<WeldInterfacePath>();


                if (coincidentArea <
                    thresholds
                        .MinimumCoincidentAreaMm2
                    &&
                    (
                        hasIntersectionEvidence
                        ||
                        rangeSpansPlane
                    ))
                {
                    sectionPaths =
                        _sectionBuilder
                            .BuildSections(
                                inventorApplication,
                                candidate.Occurrence,
                                wall,
                                thresholds,
                                statistics);


                    rawPaths.AddRange(
                        sectionPaths);
                }


                // ----------------------------------------------------
                // D. DEDUPE + CONSOLIDATION + FINITE ENVELOPE
                // ----------------------------------------------------

                List<WeldInterfacePath> deduped =
                    _pathBuilder
                        .DedupePaths(
                            rawPaths,
                            thresholds);


                List<WeldInterfacePath> consolidated =
                    _pathBuilder
                        .ConsolidatePaths(
                            deduped,
                            thresholds,
                            statistics);


                List<WeldInterfacePath> finalPaths =
                    _clipper
                        .ClipPaths(
                            consolidated,
                            wall,
                            thresholds,
                            statistics,
                            WeldWallBodyScope.IsSameOccurrence(candidate.OccurrencePath, wall)
                                ? Math.Max(thresholds.EnvelopeClipToleranceMm, thresholds.ContactToleranceMm)
                                : (double?)null);

                if (WeldWallBodyScope.IsSameOccurrence(candidate.OccurrencePath, wall))
                {
                    record.Evidence.Add("same_occurrence_other_body_contact_evaluated");
                    record.Evidence.Add("same_occurrence_boundary_uses_contact_tolerance_preserves_model3d");
                    statistics.SameOccurrenceBodyInterfacesEvaluated++;
                }

                finalPaths =
                    _pathBuilder
                        .DedupePaths(
                            finalPaths,
                            thresholds);


                record.Paths =
                    finalPaths;


                bool hasResolvedSection =
                    finalPaths.Any(
                        p =>
                            p.SourceKind ==
                            "BREP_SECTION");


                bool hasResolvedCoincidentLoop =
                    finalPaths.Any(
                        p =>
                            p.SourceKind ==
                            "COINCIDENT_FACE_LOOP");


                bool hasResolvedTouchEdge =
                    finalPaths.Any(
                        p =>
                            p.SourceKind ==
                            "EDGE_ON_WALL");


                bool hadCoplanarPlaneEvidence =
                    coincidentArea >=
                    thresholds
                        .MinimumCoincidentAreaMm2;


                bool coplanarGeometryOutsideFiniteWall =
                    hadCoplanarPlaneEvidence
                    &&
                    !hasResolvedCoincidentLoop;


                bool sectionGeometryOutsideFiniteWall =
                    sectionPaths.Count > 0
                    &&
                    !hasResolvedSection
                    &&
                    !hasIntersectionEvidence;


                bool touchGeometryOutsideFiniteWall =
                    hasTouchEvidence
                    &&
                    !hasResolvedTouchEdge;


                record.CoincidentAreaMetricMm2 =
                    Math.Round(
                        coincidentArea,
                        3);


                record
                    .UnresolvedPlaneCrossingPointCount =
                        unresolvedCrossings.Count;


                // ----------------------------------------------------
                // E. FINAL CONTACT STATE
                // ----------------------------------------------------

                if (coincidentArea >=
                    thresholds
                        .MinimumCoincidentAreaMm2
                    &&
                    hasResolvedCoincidentLoop)
                {
                    record.ContactState =
                        "COINCIDENT_AREA";

                    record.ContactDetected =
                        true;

                    record.ContactGeometryResolved =
                        true;

                    record.ResolutionStatus =
                        "resolved_coincident_face_loops";

                    record.MinimumPlaneDistanceMm =
                        0.0;

                    record.Evidence.Add(
                        "coplanar_component_face_on_wall_plane");
                }
                else if (hasResolvedSection)
                {
                    record.ContactState =
                        "INTERSECTING";

                    record.ContactDetected =
                        true;

                    record.ContactGeometryResolved =
                        true;

                    record.ResolutionStatus =
                        "resolved_brep_section";

                    record.MinimumPlaneDistanceMm =
                        0.0;

                    record.Evidence.Add(
                        "transient_brep_section_on_wall_plane");
                }
                else if (hasIntersectionEvidence)
                {
                    record.ContactState =
                        "INTERSECTING";

                    record.ContactDetected =
                        true;

                    record.ContactGeometryResolved =
                        false;

                    record.ResolutionStatus =
                        "brep_section_unresolved";

                    record.MinimumPlaneDistanceMm =
                        0.0;

                    record.Evidence.Add(
                        "sampled_geometry_crosses_wall_plane");
                }
                else if (hasTouchEvidence
                         &&
                         hasResolvedTouchEdge)
                {
                    record.ContactState =
                        "TOUCHING";

                    record.ContactDetected =
                        true;

                    record.ContactGeometryResolved =
                        true;

                    record.ResolutionStatus =
                        "resolved_edge_on_wall";

                    record.MinimumPlaneDistanceMm =
                        0.0;

                    record.Evidence.Add(
                        "component_edge_on_wall_plane");
                }
                else if (coplanarGeometryOutsideFiniteWall)
                {
                    // Hay coplanaridad con el plano infinito, pero no
                    // existe geometría dentro del rectángulo finito
                    // que representa ESTA pared.
                    record.ContactState =
                        "NO_CONTACT";

                    record.ContactDetected =
                        false;

                    record.ContactGeometryResolved =
                        null;

                    record.ResolutionStatus =
                        "coplanar_geometry_outside_finite_wall_envelope";

                    record.MinimumPlaneDistanceMm =
                        0.0;

                    record.Evidence.Add(
                        "coplanar_plane_evidence_outside_finite_wall");
                }
                else if (sectionGeometryOutsideFiniteWall)
                {
                    record.ContactState =
                        "NO_CONTACT";

                    record.ContactDetected =
                        false;

                    record.ContactGeometryResolved =
                        null;

                    record.ResolutionStatus =
                        "section_geometry_outside_finite_wall_envelope";

                    record.MinimumPlaneDistanceMm =
                        0.0;

                    record.Evidence.Add(
                        "brep_section_outside_finite_wall");
                }
                else if (touchGeometryOutsideFiniteWall)
                {
                    record.ContactState =
                        "NO_CONTACT";

                    record.ContactDetected =
                        false;

                    record.ContactGeometryResolved =
                        null;

                    record.ResolutionStatus =
                        "touch_geometry_outside_finite_wall_envelope";

                    record.MinimumPlaneDistanceMm =
                        0.0;

                    record.Evidence.Add(
                        "edge_on_plane_outside_finite_wall");
                }
                else if (minimumDistance <=
                         thresholds
                             .NearContactToleranceMm)
                {
                    record.ContactState =
                        "NEAR_CONTACT";

                    record.ContactDetected =
                        false;

                    record.ContactGeometryResolved =
                        null;

                    record.ResolutionStatus =
                        "near_contact";

                    record.MinimumPlaneDistanceMm =
                        Math.Round(
                            minimumDistance,
                            3);

                    record.Evidence.Add(
                        "geometry_within_near_contact_tolerance");
                }
                else if (rangeSpansPlane)
                {
                    record.ContactState =
                        "AMBIGUOUS";

                    record.ContactDetected =
                        null;

                    record.ContactGeometryResolved =
                        false;

                    record.ResolutionStatus =
                        sectionPaths.Count == 0
                            ? "range_spans_plane_but_section_not_resolved"
                            : "section_geometry_discarded_by_finite_wall_envelope";

                    record.MinimumPlaneDistanceMm =
                        Math.Round(
                            minimumDistance,
                            3);

                    record.Evidence.Add(
                        "range_box_spans_wall_plane");
                }
                else
                {
                    record.ContactState =
                        "NO_CONTACT";

                    record.ContactDetected =
                        false;

                    record.ContactGeometryResolved =
                        null;

                    record.ResolutionStatus =
                        hadExactGeometry
                            ? "no_contact"
                            : "no_exact_geometry_available";

                    record.MinimumPlaneDistanceMm =
                        Math.Round(
                            minimumDistance,
                            3);
                }


                record.BoundaryFilter.InnerCoincidentFaceLoopsSuppressed =
                    Math.Max(
                        0,
                        statistics.InnerCoincidentFaceLoopsSuppressed
                        -
                        innerCoincidentLoopsBefore);

                record.BoundaryFilter.NestedSectionWiresSuppressed =
                    Math.Max(
                        0,
                        statistics.NestedSectionWiresSuppressed
                        -
                        nestedSectionWiresBefore);

                record.BoundaryFilter.AnnularSectionWiresResolved =
                    Math.Max(
                        0,
                        statistics.AnnularSectionWiresResolved
                        -
                        annularSectionWiresBefore);

                record.BoundaryFilter.AnnularSectionPathsSuppressed =
                    Math.Max(
                        0,
                        statistics.AnnularSectionPathsSuppressed
                        -
                        annularSectionPathsBefore);


                if (record.BoundaryFilter.AnnularSectionWiresResolved > 0)
                {
                    record.Evidence.Add(
                        "annular_brep_section_outer_circumference_reconstructed");
                }


                if (record.BoundaryFilter.Applied)
                {
                    record.Evidence.Add(
                        "physical_outer_boundary_filter_applied");
                }


                UpdateStatistics(
                    record,
                    statistics);


                if (record.ContactState ==
                    "NO_CONTACT")
                {
                    return null;
                }


                statistics
                    .InterfacesExported++;


                statistics
                    .InterfacePathsResolved
                    +=
                    record.Paths.Count;


                return record;
            }
            catch (Exception ex)
            {
                statistics
                    .ExactAnalysisFailures++;


                record.ContactState =
                    "AMBIGUOUS";

                record.ContactDetected =
                    null;

                record.ContactGeometryResolved =
                    false;

                record.ResolutionStatus =
                    "exact_analysis_exception";

                record.Evidence.Add(
                    ex.GetType().Name
                    +
                    ": "
                    +
                    ex.Message);


                record.BoundaryFilter.InnerCoincidentFaceLoopsSuppressed =
                    Math.Max(
                        0,
                        statistics.InnerCoincidentFaceLoopsSuppressed
                        -
                        innerCoincidentLoopsBefore);

                record.BoundaryFilter.NestedSectionWiresSuppressed =
                    Math.Max(
                        0,
                        statistics.NestedSectionWiresSuppressed
                        -
                        nestedSectionWiresBefore);

                record.BoundaryFilter.AnnularSectionWiresResolved =
                    Math.Max(
                        0,
                        statistics.AnnularSectionWiresResolved
                        -
                        annularSectionWiresBefore);

                record.BoundaryFilter.AnnularSectionPathsSuppressed =
                    Math.Max(
                        0,
                        statistics.AnnularSectionPathsSuppressed
                        -
                        annularSectionPathsBefore);


                statistics
                    .Ambiguous++;


                statistics
                    .InterfacesExported++;


                return record;
            }
        }


        private bool RangeBoxSpansWallPlane(
            WeldBroadPhaseCandidate candidate,
            WeldInterfaceThresholds thresholds)
        {
            if (double.IsNaN(
                    candidate.MinimumDepthMm)
                ||
                double.IsNaN(
                    candidate.MaximumDepthMm))
            {
                return false;
            }


            double tolerance =
                thresholds
                    .ContactToleranceMm;


            return
                candidate.MinimumDepthMm <
                    -tolerance
                &&
                candidate.MaximumDepthMm >
                    tolerance;
        }


        private void UpdateStatistics(
            WeldInterfaceRecord record,
            WeldInterfaceStatistics statistics)
        {
            switch (record.ContactState)
            {
                case "NEAR_CONTACT":
                    statistics.NearContact++;
                    break;

                case "TOUCHING":
                    statistics.Touching++;
                    break;

                case "INTERSECTING":
                    statistics.Intersecting++;
                    break;

                case "COINCIDENT_AREA":
                    statistics.CoincidentArea++;
                    break;

                case "AMBIGUOUS":
                    statistics.Ambiguous++;
                    break;

                default:
                    statistics.NoContact++;
                    break;
            }
        }


        private double WallDepth(
            WeldPoint3Mm point,
            WeldInterfaceFaceRecord wall)
        {
            return WeldContactPlaneResolver.Depth(point, wall);
        }


        private double UnsignedAngleDeg(
            WeldVector3 a,
            WeldVector3 b)
        {
            double al =
                Math.Sqrt(
                    a.X * a.X
                    +
                    a.Y * a.Y
                    +
                    a.Z * a.Z);

            double bl =
                Math.Sqrt(
                    b.X * b.X
                    +
                    b.Y * b.Y
                    +
                    b.Z * b.Z);


            if (al < 1e-12 ||
                bl < 1e-12)
            {
                return 180.0;
            }


            double dot =
                (
                    a.X * b.X
                    +
                    a.Y * b.Y
                    +
                    a.Z * b.Z
                )
                /
                (
                    al * bl
                );


            dot =
                Math.Abs(
                    Math.Max(
                        -1.0,
                        Math.Min(
                            1.0,
                            dot)));


            return
                Math.Acos(
                    dot)
                *
                180.0
                /
                Math.PI;
        }


        private void AddUniquePoint(
            List<WeldPoint3Mm> points,
            WeldPoint3Mm candidate,
            double tolerance)
        {
            foreach (WeldPoint3Mm point
                     in points)
            {
                double dx =
                    point.X -
                    candidate.X;

                double dy =
                    point.Y -
                    candidate.Y;

                double dz =
                    point.Z -
                    candidate.Z;


                double distance =
                    Math.Sqrt(
                        dx * dx
                        +
                        dy * dy
                        +
                        dz * dz);


                if (distance <=
                    tolerance)
                {
                    return;
                }
            }


            points.Add(
                candidate);
        }
    }
}
