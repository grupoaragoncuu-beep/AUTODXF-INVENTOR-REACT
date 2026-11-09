using Inventor;
using System;
using System.Collections.Generic;
using System.Linq;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // ================================================================
    // V1.1-A / V0.2.1
    // EXACT B-REP SECTION BUILDER
    //
    // IMPORTANTE:
    // No se intenta operar directamente sobre SurfaceBodyProxy.
    //
    // Patrón:
    // native definition body
    //      ↓
    // TransientBRep.Copy()
    //      ↓
    // TransientBRep.Transform(occurrence.Transformation)
    //      ↓
    // CreateIntersectionWithPlane()
    //
    // El clipping al envelope finito se ejecuta DESPUÉS.
    // ================================================================

    public class WeldInterfaceSectionBuilder
    {
        private const double MmToCm =
            0.1;


        private const int MaxFailureSamples =
            12;


        private readonly WeldInterfacePathBuilder
            _pathBuilder =
                new WeldInterfacePathBuilder();


        public List<WeldInterfacePath> BuildSections(
            Inventor.Application inventorApplication,
            ComponentOccurrence occurrence,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            WeldInterfaceStatistics statistics)
        {
            List<WeldInterfacePath> result =
                new List<WeldInterfacePath>();


            Plane wallPlane =
                CreateWallPlane(
                    inventorApplication,
                    wall);


            TransientBRep transientBRep =
                inventorApplication
                    .TransientBRep;


            ComponentDefinition definition =
                occurrence.Definition;


            SurfaceBodies nativeBodies =
                definition.SurfaceBodies;


            Matrix occurrenceTransform =
                occurrence
                    .Transformation
                    .Copy();


            for (int bodyIndex = 1;
                 bodyIndex <= nativeBodies.Count;
                 bodyIndex++)
            {
                if (WeldWallBodyScope.IsWallBody(
                    WeldInterfaceBroadPhase.BuildOccurrencePath(occurrence), bodyIndex, wall))
                {
                    statistics.OwnWallBodiesSkippedSection++;
                    continue;
                }
                statistics
                    .SectionAttempts++;


                SurfaceBody transientBody;


                try
                {
                    SurfaceBody nativeBody =
                        nativeBodies[bodyIndex];


                    transientBody =
                        transientBRep.Copy(
                            nativeBody);


                    // Coloca el body transitorio en el mismo contexto
                    // espacial de assembly que usa el wall frame.
                    transientBRep.Transform(
                        transientBody,
                        occurrenceTransform);
                }
                catch (Exception copyEx)
                {
                    statistics
                        .SectionFailures++;

                    statistics
                        .SectionCopyTransformFailures++;


                    AddFailureSample(
                        statistics,
                        occurrence,
                        bodyIndex,
                        "COPY_TRANSFORM",
                        copyEx);


                    continue;
                }


                try
                {
                    SurfaceBody wireBody =
                        transientBRep
                            .CreateIntersectionWithPlane(
                                transientBody,
                                wallPlane);


                    int edgeCount =
                        wireBody.Edges.Count;


                    if (edgeCount <= 0)
                    {
                        // Operación válida pero sin curva.
                        continue;
                    }


                    int pathsBefore =
                        result.Count;


                    List<WeldInterfacePath> sectionBodyPaths =
                        BuildSectionBodyPaths(
                            wireBody,
                            bodyIndex,
                            wall,
                            thresholds,
                            statistics);


                    result.AddRange(
                        sectionBodyPaths);


                    if (result.Count >
                        pathsBefore)
                    {
                        statistics
                            .SectionSuccesses++;
                    }
                }
                catch (Exception intersectionEx)
                {
                    statistics
                        .SectionFailures++;

                    statistics
                        .SectionIntersectionFailures++;


                    AddFailureSample(
                        statistics,
                        occurrence,
                        bodyIndex,
                        "INTERSECTION",
                        intersectionEx);
                }
            }


            result =
                _pathBuilder
                    .DedupePaths(
                        result,
                        thresholds);


            statistics
                .SectionPathsGenerated
                +=
                result.Count;


            return result;
        }


        private List<WeldInterfacePath> BuildSectionBodyPaths(
            SurfaceBody wireBody,
            int bodyIndex,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            WeldInterfaceStatistics statistics)
        {
            try
            {
                dynamic wires =
                    wireBody.Wires;


                if (wires != null
                    &&
                    wires.Count > 0)
                {
                    List<SectionWireCandidate> candidates =
                        new List<SectionWireCandidate>();


                    int syntheticEdgeIndex =
                        0;


                    for (int wireIndex = 1;
                         wireIndex <= wires.Count;
                         wireIndex++)
                    {
                        statistics
                            .SectionWiresVisited++;


                        dynamic wire =
                            wires[wireIndex];


                        SectionWireCandidate candidate =
                            BuildWireCandidate(
                                wire,
                                wireIndex,
                                bodyIndex,
                                wall,
                                thresholds,
                                ref syntheticEdgeIndex);


                        if (candidate.Paths.Count > 0)
                        {
                            candidates.Add(
                                candidate);
                        }
                    }


                    if (candidates.Count > 0)
                    {
                        ClassifyNestedWires(
                            candidates,
                            thresholds,
                            statistics);


                        ResolveAnnularSectionWires(
                            candidates,
                            wall,
                            thresholds,
                            statistics);


                        return candidates
                            .Where(
                                c =>
                                    !c.Suppress)
                            .SelectMany(
                                c => c.Paths)
                            .ToList();
                    }
                }
            }
            catch
            {
                // Some transient B-Rep contexts can expose Edges but no Wires.
                // Fall through to the legacy edge iteration.
            }


            return BuildSectionEdgesFallback(
                wireBody,
                bodyIndex,
                wall,
                thresholds);
        }


        private SectionWireCandidate BuildWireCandidate(
            dynamic wire,
            int wireIndex,
            int bodyIndex,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            ref int syntheticEdgeIndex)
        {
            SectionWireCandidate candidate =
                new SectionWireCandidate
                {
                    WireIndex =
                        wireIndex
                };


            dynamic edgeUses =
                wire.EdgeUses;


            foreach (dynamic edgeUse
                     in edgeUses)
            {
                syntheticEdgeIndex++;


                dynamic edge =
                    edgeUse.Edge;


                WeldInterfacePath? path =
                    _pathBuilder
                        .BuildFromEdge(
                            edge,
                            bodyIndex,
                            syntheticEdgeIndex,
                            wall,
                            thresholds,
                            "BREP_SECTION");


                if (path == null
                    ||
                    path.LengthMm <=
                        thresholds
                            .CurveDedupeToleranceMm)
                {
                    continue;
                }


                bool opposed =
                    false;


                try
                {
                    opposed =
                        (bool)edgeUse.IsOpposedToEdge;
                }
                catch
                {
                    opposed =
                        false;
                }


                if (opposed)
                {
                    path.Model3DPointsMm.Reverse();
                    path.FaceLocalPointsMm.Reverse();
                }


                path.BoundaryGroupId =
                    $"BODY_{bodyIndex:000}_SECTION_WIRE_{wireIndex:000}";


                candidate.Paths.Add(
                    path);


                AppendConnected2D(
                    candidate.Contour,
                    path.FaceLocalPointsMm,
                    thresholds
                        .CurveJoinToleranceMm);
            }


            candidate.Closed =
                candidate.Contour.Count >= 3
                &&
                Distance2D(
                    candidate.Contour[0],
                    candidate.Contour[
                        candidate.Contour.Count - 1])
                <=
                thresholds
                    .CurveJoinToleranceMm;


            if (candidate.Closed)
            {
                candidate.AreaAbsMm2 =
                    Math.Abs(
                        SignedArea2D(
                            candidate.Contour));
            }


            return candidate;
        }


        private void ClassifyNestedWires(
            List<SectionWireCandidate> candidates,
            WeldInterfaceThresholds thresholds,
            WeldInterfaceStatistics statistics)
        {
            foreach (SectionWireCandidate candidate
                     in candidates)
            {
                if (!candidate.Closed
                    ||
                    candidate.Contour.Count < 3)
                {
                    foreach (WeldInterfacePath path
                             in candidate.Paths)
                    {
                        path.BoundaryRole =
                            "OPEN_SECTION";

                        path.BoundarySelectionReason =
                            "BREP_SECTION_OPEN_WIRE";
                    }


                    continue;
                }


                int depth =
                    0;


                WeldPoint2Mm probe =
                    candidate.Contour[0];


                foreach (SectionWireCandidate other
                         in candidates)
                {
                    if (ReferenceEquals(
                            candidate,
                            other)
                        ||
                        !other.Closed
                        ||
                        other.Contour.Count < 3
                        ||
                        other.AreaAbsMm2 <=
                            candidate.AreaAbsMm2
                            +
                            thresholds
                                .CurveDedupeToleranceMm
                            *
                            thresholds
                                .CurveDedupeToleranceMm)
                    {
                        continue;
                    }


                    if (PointInPolygon(
                            probe,
                            other.Contour))
                    {
                        depth++;
                    }
                }


                candidate.NestingDepth =
                    depth;


                bool innerVoid =
                    thresholds
                        .SuppressNestedSectionWires
                    &&
                    depth % 2 == 1;


                candidate.Suppress =
                    innerVoid;


                foreach (WeldInterfacePath path
                         in candidate.Paths)
                {
                    path.BoundaryRole =
                        innerVoid
                            ? "INNER_VOID"
                            : "OUTER";

                    path.BoundarySelectionReason =
                        innerVoid
                            ? "NESTED_BREP_SECTION_WIRE_SUPPRESSED"
                            : depth == 0
                                ? "BREP_SECTION_OUTER_WIRE"
                                : "BREP_SECTION_MATERIAL_ISLAND";
                }


                if (innerVoid)
                {
                    statistics
                        .NestedSectionWiresSuppressed++;
                }
            }
        }


        // ============================================================
        // V0.3.4 ANNULAR SECTION OUTER CIRCUMFERENCE
        //
        // Some OTC circular penetrations are returned by transient B-Rep as
        // one closed wire composed of:
        //   curved near-360 edge + short radial connector +
        //   curved near-360 edge + short radial connector.
        //
        // Both curved edges are real B-Rep boundaries, but only the external
        // circumference is the weld candidate on the selected wall. Exporting
        // all four paths makes AWIS see two partial circular candidates.
        //
        // This resolver is conservative: it only transforms a closed wire
        // with exactly two circular near-360 curves and two short connectors,
        // validates concentricity and radial thickness, then reconstructs one
        // exact 360-degree OUTER path.
        // ============================================================
        private void ResolveAnnularSectionWires(
            List<SectionWireCandidate> candidates,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            WeldInterfaceStatistics statistics)
        {
            if (!thresholds.ResolveAnnularSectionOuterWeldEdge)
            {
                return;
            }


            foreach (SectionWireCandidate candidate
                     in candidates)
            {
                if (candidate.Suppress
                    ||
                    !candidate.Closed
                    ||
                    candidate.Paths.Count != 4)
                {
                    continue;
                }


                List<WeldInterfacePath> curved =
                    candidate.Paths
                        .Where(
                            p =>
                                string.Equals(
                                    p.GeometryType,
                                    "CURVED_OR_MULTI_SEGMENT",
                                    StringComparison.OrdinalIgnoreCase)
                                &&
                                p.FaceLocalPointsMm.Count >= 12)
                        .ToList();


                List<WeldInterfacePath> connectors =
                    candidate.Paths
                        .Where(
                            p =>
                                string.Equals(
                                    p.GeometryType,
                                    "LINEAR",
                                    StringComparison.OrdinalIgnoreCase)
                                &&
                                p.FaceLocalPointsMm.Count >= 2)
                        .ToList();


                if (curved.Count != 2
                    ||
                    connectors.Count != 2)
                {
                    continue;
                }


                if (connectors.Any(
                        p =>
                            p.LengthMm <=
                                thresholds.CurveDedupeToleranceMm
                            ||
                            p.LengthMm >
                                thresholds.AnnularSectionMaximumThicknessMm))
                {
                    continue;
                }


                if (!TryFitCircle(
                        curved[0].FaceLocalPointsMm,
                        out CircleFit first)
                    ||
                    !TryFitCircle(
                        curved[1].FaceLocalPointsMm,
                        out CircleFit second))
                {
                    continue;
                }


                if (first.MaxRadialErrorMm >
                        thresholds.AnnularSectionCircularityToleranceMm
                    ||
                    second.MaxRadialErrorMm >
                        thresholds.AnnularSectionCircularityToleranceMm)
                {
                    continue;
                }


                double centerGap =
                    Distance2D(
                        new WeldPoint2Mm
                        {
                            X = first.CenterX,
                            Y = first.CenterY
                        },
                        new WeldPoint2Mm
                        {
                            X = second.CenterX,
                            Y = second.CenterY
                        });


                if (centerGap >
                    thresholds.AnnularSectionCenterToleranceMm)
                {
                    continue;
                }


                double coverageFirstDeg =
                    ArcCoverageDeg(
                        curved[0].LengthMm,
                        first.RadiusMm);

                double coverageSecondDeg =
                    ArcCoverageDeg(
                        curved[1].LengthMm,
                        second.RadiusMm);


                if (coverageFirstDeg <
                        thresholds.AnnularSectionMinimumCoverageDeg
                    ||
                    coverageSecondDeg <
                        thresholds.AnnularSectionMinimumCoverageDeg)
                {
                    continue;
                }


                double thickness =
                    Math.Abs(
                        first.RadiusMm
                        -
                        second.RadiusMm);


                if (thickness <=
                        thresholds.CurveDedupeToleranceMm
                    ||
                    thickness >
                        thresholds.AnnularSectionMaximumThicknessMm)
                {
                    continue;
                }


                // The two short connectors should represent the same radial
                // thickness. Allow a small numeric margin because the B-Rep
                // section is sampled/rounded before it reaches this contract.
                double connectorTolerance =
                    Math.Max(
                        1.0,
                        0.10 * thickness);


                if (connectors.Any(
                        p =>
                            Math.Abs(
                                p.LengthMm
                                -
                                thickness)
                            >
                            connectorTolerance))
                {
                    continue;
                }


                bool firstIsOuter =
                    first.RadiusMm >
                    second.RadiusMm;


                WeldInterfacePath outerSource =
                    firstIsOuter
                        ? curved[0]
                        : curved[1];

                CircleFit outerFit =
                    firstIsOuter
                        ? first
                        : second;


                int originalPathCount =
                    candidate.Paths.Count;

                double originalWireLength =
                    candidate.Paths.Sum(
                        p => p.LengthMm);


                WeldInterfacePath reconstructed =
                    ReconstructFullCircle(
                        outerSource,
                        outerFit,
                        wall,
                        thresholds,
                        originalWireLength);


                candidate.Paths.Clear();
                candidate.Paths.Add(
                    reconstructed);


                statistics.AnnularSectionWiresResolved++;
                statistics.AnnularSectionPathsSuppressed +=
                    Math.Max(
                        0,
                        originalPathCount - 1);
            }
        }


        private WeldInterfacePath ReconstructFullCircle(
            WeldInterfacePath source,
            CircleFit fit,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            double originalWireLength)
        {
            int segmentCount =
                Math.Max(
                    48,
                    (int)Math.Ceiling(
                        2.0
                        *
                        Math.PI
                        *
                        fit.RadiusMm
                        /
                        Math.Max(
                            5.0,
                            thresholds.AnnularSectionTargetSampleStepMm)));


            segmentCount =
                Math.Min(
                    360,
                    segmentCount);


            double startAngle =
                Math.Atan2(
                    source.FaceLocalPointsMm[0].Y
                    -
                    fit.CenterY,
                    source.FaceLocalPointsMm[0].X
                    -
                    fit.CenterX);


            double direction =
                DetermineAngularDirection(
                    source.FaceLocalPointsMm,
                    fit);


            List<WeldPoint2Mm> local =
                new List<WeldPoint2Mm>();

            List<WeldPoint3Mm> model =
                new List<WeldPoint3Mm>();


            for (int i = 0;
                 i <= segmentCount;
                 i++)
            {
                double angle =
                    startAngle
                    +
                    direction
                    *
                    2.0
                    *
                    Math.PI
                    *
                    i
                    /
                    segmentCount;


                double u =
                    fit.CenterX
                    +
                    fit.RadiusMm
                    *
                    Math.Cos(
                        angle);

                double v =
                    fit.CenterY
                    +
                    fit.RadiusMm
                    *
                    Math.Sin(
                        angle);


                WeldPoint2Mm localPoint =
                    new WeldPoint2Mm
                    {
                        X = Math.Round(u, 3),
                        Y = Math.Round(v, 3)
                    };


                local.Add(
                    localPoint);


                model.Add(
                    LocalToModel(
                        localPoint,
                        wall));
            }


            string memberGroupId =
                string.IsNullOrWhiteSpace(
                    source.BoundaryGroupId)
                    ?
                        $"BODY_{source.SourceBodyIndex:000}_ANNULAR_SECTION"
                    :
                        source.BoundaryGroupId
                        +
                        "_ANNULAR";


            return new WeldInterfacePath
            {
                SourceKind =
                    "BREP_SECTION",

                GeometryType =
                    "CLOSED",

                Closed =
                    true,

                ClippedToWallEnvelope =
                    source.ClippedToWallEnvelope,

                LengthMm =
                    Math.Round(
                        2.0
                        *
                        Math.PI
                        *
                        fit.RadiusMm,
                        3),

                SourceBodyIndex =
                    source.SourceBodyIndex,

                SourceFaceIndex =
                    source.SourceFaceIndex,

                SourceLoopIndex =
                    source.SourceLoopIndex,

                SourceEdgeIndex =
                    source.SourceEdgeIndex,

                BoundaryRole =
                    "OUTER",

                BoundarySelectionReason =
                    "ANNULAR_BREP_SECTION_OUTER_CIRCUMFERENCE_RECONSTRUCTED",

                BoundaryGroupId =
                    source.BoundaryGroupId,

                PhysicalMemberType =
                    "ANNULAR_SECTION",

                PhysicalMemberGroupId =
                    memberGroupId,

                PhysicalSideRole =
                    "OUTER_CIRCUMFERENCE",

                PhysicalBoundaryRole =
                    "OUTER_WELD_EDGE",

                OriginalClosedLoopLengthMm =
                    Math.Round(
                        originalWireLength,
                        3),

                Model3DPointsMm =
                    model,

                FaceLocalPointsMm =
                    local
            };
        }


        private WeldPoint3Mm LocalToModel(
            WeldPoint2Mm local,
            WeldInterfaceFaceRecord wall)
        {
            return WeldContactPlaneResolver.LiftUv(local, wall);
        }


        private double DetermineAngularDirection(
            IReadOnlyList<WeldPoint2Mm> points,
            CircleFit fit)
        {
            for (int i = 1;
                 i < points.Count;
                 i++)
            {
                double a0 =
                    Math.Atan2(
                        points[i - 1].Y
                        -
                        fit.CenterY,
                        points[i - 1].X
                        -
                        fit.CenterX);

                double a1 =
                    Math.Atan2(
                        points[i].Y
                        -
                        fit.CenterY,
                        points[i].X
                        -
                        fit.CenterX);


                double delta =
                    NormalizeSignedAngle(
                        a1 - a0);


                if (Math.Abs(delta) > 1e-6)
                {
                    return delta >= 0.0
                        ? 1.0
                        : -1.0;
                }
            }


            return 1.0;
        }


        private double NormalizeSignedAngle(
            double angle)
        {
            while (angle > Math.PI)
            {
                angle -=
                    2.0 * Math.PI;
            }


            while (angle < -Math.PI)
            {
                angle +=
                    2.0 * Math.PI;
            }


            return angle;
        }


        private double ArcCoverageDeg(
            double lengthMm,
            double radiusMm)
        {
            if (radiusMm <= 1e-9)
            {
                return 0.0;
            }


            return Math.Min(
                360.0,
                lengthMm
                /
                radiusMm
                *
                180.0
                /
                Math.PI);
        }


        private bool TryFitCircle(
            IReadOnlyList<WeldPoint2Mm> points,
            out CircleFit fit)
        {
            fit =
                new CircleFit();


            if (points.Count < 6)
            {
                return false;
            }


            WeldPoint2Mm p1 =
                points[0];

            WeldPoint2Mm p2 =
                points[points.Count / 3];

            WeldPoint2Mm p3 =
                points[(2 * points.Count) / 3];


            double d =
                2.0
                *
                (
                    p1.X * (p2.Y - p3.Y)
                    +
                    p2.X * (p3.Y - p1.Y)
                    +
                    p3.X * (p1.Y - p2.Y)
                );


            if (Math.Abs(d) < 1e-9)
            {
                return false;
            }


            double p1Sq =
                p1.X * p1.X
                +
                p1.Y * p1.Y;

            double p2Sq =
                p2.X * p2.X
                +
                p2.Y * p2.Y;

            double p3Sq =
                p3.X * p3.X
                +
                p3.Y * p3.Y;


            double centerX =
                (
                    p1Sq * (p2.Y - p3.Y)
                    +
                    p2Sq * (p3.Y - p1.Y)
                    +
                    p3Sq * (p1.Y - p2.Y)
                )
                /
                d;

            double centerY =
                (
                    p1Sq * (p3.X - p2.X)
                    +
                    p2Sq * (p1.X - p3.X)
                    +
                    p3Sq * (p2.X - p1.X)
                )
                /
                d;


            List<double> radii =
                points
                    .Select(
                        p =>
                            Math.Sqrt(
                                (p.X - centerX)
                                *
                                (p.X - centerX)
                                +
                                (p.Y - centerY)
                                *
                                (p.Y - centerY)))
                    .ToList();


            double radius =
                radii.Average();


            if (radius <= 1e-6)
            {
                return false;
            }


            double maxError =
                radii.Max(
                    r =>
                        Math.Abs(
                            r - radius));


            fit =
                new CircleFit
                {
                    CenterX = centerX,
                    CenterY = centerY,
                    RadiusMm = radius,
                    MaxRadialErrorMm = maxError
                };


            return true;
        }


        private sealed class CircleFit
        {
            public double CenterX { get; set; }

            public double CenterY { get; set; }

            public double RadiusMm { get; set; }

            public double MaxRadialErrorMm { get; set; }
        }


        private List<WeldInterfacePath> BuildSectionEdgesFallback(
            SurfaceBody wireBody,
            int bodyIndex,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds)
        {
            List<WeldInterfacePath> result =
                new List<WeldInterfacePath>();


            int edgeCount =
                wireBody.Edges.Count;


            for (int edgeIndex = 1;
                 edgeIndex <= edgeCount;
                 edgeIndex++)
            {
                dynamic edge =
                    wireBody
                        .Edges[edgeIndex];


                WeldInterfacePath? path =
                    _pathBuilder
                        .BuildFromEdge(
                            edge,
                            bodyIndex,
                            edgeIndex,
                            wall,
                            thresholds,
                            "BREP_SECTION");


                if (path == null
                    ||
                    path.LengthMm <=
                        thresholds
                            .CurveDedupeToleranceMm)
                {
                    continue;
                }


                path.BoundaryRole =
                    "UNRESOLVED";

                path.BoundarySelectionReason =
                    "BREP_SECTION_EDGE_FALLBACK_NO_WIRE_TOPOLOGY";


                result.Add(
                    path);
            }


            return result;
        }


        private void AppendConnected2D(
            List<WeldPoint2Mm> target,
            List<WeldPoint2Mm> source,
            double tolerance)
        {
            if (source.Count == 0)
            {
                return;
            }


            if (target.Count == 0)
            {
                target.AddRange(
                    source);

                return;
            }


            int start =
                Distance2D(
                    target[target.Count - 1],
                    source[0])
                <= tolerance
                    ? 1
                    : 0;


            for (int i = start;
                 i < source.Count;
                 i++)
            {
                target.Add(
                    source[i]);
            }
        }


        private double SignedArea2D(
            IReadOnlyList<WeldPoint2Mm> points)
        {
            if (points.Count < 3)
            {
                return 0.0;
            }


            double area2 =
                0.0;


            for (int i = 0;
                 i < points.Count;
                 i++)
            {
                WeldPoint2Mm a =
                    points[i];

                WeldPoint2Mm b =
                    points[
                        (i + 1)
                        %
                        points.Count];


                area2 +=
                    a.X * b.Y
                    -
                    b.X * a.Y;
            }


            return
                0.5 * area2;
        }


        private bool PointInPolygon(
            WeldPoint2Mm point,
            IReadOnlyList<WeldPoint2Mm> polygon)
        {
            bool inside =
                false;


            int j =
                polygon.Count - 1;


            for (int i = 0;
                 i < polygon.Count;
                 i++)
            {
                WeldPoint2Mm pi =
                    polygon[i];

                WeldPoint2Mm pj =
                    polygon[j];


                bool crosses =
                    (
                        pi.Y > point.Y
                    )
                    !=
                    (
                        pj.Y > point.Y
                    )
                    &&
                    point.X
                    <
                    (
                        pj.X - pi.X
                    )
                    *
                    (
                        point.Y - pi.Y
                    )
                    /
                    (
                        pj.Y - pi.Y
                        +
                        1e-12
                    )
                    +
                    pi.X;


                if (crosses)
                {
                    inside =
                        !inside;
                }


                j =
                    i;
            }


            return inside;
        }


        private double Distance2D(
            WeldPoint2Mm a,
            WeldPoint2Mm b)
        {
            double dx =
                a.X - b.X;

            double dy =
                a.Y - b.Y;


            return Math.Sqrt(
                dx * dx
                +
                dy * dy);
        }


        private sealed class SectionWireCandidate
        {
            public int WireIndex { get; set; }

            public List<WeldInterfacePath> Paths { get; } =
                new List<WeldInterfacePath>();

            public List<WeldPoint2Mm> Contour { get; } =
                new List<WeldPoint2Mm>();

            public bool Closed { get; set; }

            public double AreaAbsMm2 { get; set; }

            public int NestingDepth { get; set; }

            public bool Suppress { get; set; }
        }


        private Plane CreateWallPlane(Inventor.Application inventorApplication, WeldInterfaceFaceRecord wall)
        {
            var geometry = inventorApplication.TransientGeometry;
            var point = WeldContactPlaneResolver.Origin(wall);
            var direction = WeldContactPlaneResolver.Normal(wall);
            return geometry.CreatePlane(
                geometry.CreatePoint(point.X * MmToCm, point.Y * MmToCm, point.Z * MmToCm),
                geometry.CreateVector(direction.X, direction.Y, direction.Z));
        }


        private void AddFailureSample(
            WeldInterfaceStatistics statistics,
            ComponentOccurrence occurrence,
            int bodyIndex,
            string stage,
            Exception exception)
        {
            if (statistics
                .SectionFailureSamples
                .Count >=
                MaxFailureSamples)
            {
                return;
            }


            string path =
                WeldInterfaceBroadPhase
                    .BuildOccurrencePath(
                        occurrence);


            statistics
                .SectionFailureSamples
                .Add(
                    $"{stage} | {path} | Body {bodyIndex} | " +
                    $"{exception.GetType().Name}: {exception.Message}");
        }
    }
}
