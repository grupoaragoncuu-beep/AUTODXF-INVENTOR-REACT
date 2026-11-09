using Inventor;
using System;
using System.Collections.Generic;
using System.Linq;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // ================================================================
    // V1.1-A / V0.2.1
    // INTERFACE PATH BUILDER
    //
    // Convierte Edge / EdgeLoop en:
    // - XYZ global mm
    // - U/V local de la pared
    //
    // También consolida EDGE_ON_WALL redundantes cuando un
    // COINCIDENT_FACE_LOOP ya representa el mismo perímetro.
    // ================================================================

    public class WeldInterfacePathBuilder
    {
        private const double CmToMm =
            10.0;


        // 0.05 cm = 0.5 mm.
        private const double StrokeToleranceCm =
            0.05;


        public WeldInterfacePath? BuildFromEdge(
            dynamic edge,
            int bodyIndex,
            int edgeIndex,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            string sourceKind)
        {
            WeldEdgeSample sample =
                SampleEdge(
                    edge);


            if (!sample.Success ||
                sample.Points.Count < 2)
            {
                return null;
            }


            bool closed =
                IsClosedEdge(
                    edge,
                    sample.Points,
                    thresholds);


            if (closed)
            {
                ClosePolyline(
                    sample.Points,
                    thresholds
                        .CurveJoinToleranceMm);
            }


            List<WeldPoint2Mm> local =
                ProjectPoints(
                    sample.Points,
                    wall);


            return new WeldInterfacePath
            {
                SourceKind =
                    sourceKind,

                GeometryType =
                    DetermineGeometryType(
                        sample.Points,
                        closed),

                Closed =
                    closed,

                ClippedToWallEnvelope =
                    false,

                LengthMm =
                    Math.Round(
                        PolylineLength(
                            sample.Points),
                        3),

                SourceBodyIndex =
                    bodyIndex,

                SourceEdgeIndex =
                    edgeIndex,

                Model3DPointsMm =
                    Round3D(
                        sample.Points),

                FaceLocalPointsMm =
                    Round2D(
                        local)
            };
        }


        public List<WeldInterfacePath> BuildFromFaceLoops(
            dynamic face,
            int bodyIndex,
            int faceIndex,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            WeldInterfaceStatistics? statistics = null)
        {
            List<(WeldInterfacePath Path, bool? IsOuter)> candidates =
                new List<(WeldInterfacePath Path, bool? IsOuter)>();


            dynamic edgeLoops;


            try
            {
                edgeLoops =
                    face.EdgeLoops;
            }
            catch
            {
                return new List<WeldInterfacePath>();
            }


            int loopIndex =
                0;


            foreach (dynamic edgeLoop
                     in edgeLoops)
            {
                loopIndex++;


                if (statistics != null)
                {
                    statistics
                        .CoincidentFaceLoopsVisited++;
                }


                WeldLoopSample sample =
                    SampleLoop(
                        edgeLoop,
                        thresholds);


                if (!sample.Success ||
                    sample.Points.Count < 3)
                {
                    continue;
                }


                ClosePolyline(
                    sample.Points,
                    thresholds
                        .CurveJoinToleranceMm);


                List<WeldPoint2Mm> local =
                    ProjectPoints(
                        sample.Points,
                        wall);


                bool? isOuter =
                    null;


                try
                {
                    // Autodesk Inventor EdgeLoop.IsOuterEdgeLoop:
                    // true = material-enclosing external loop,
                    // false = void / inner loop.
                    isOuter =
                        (bool)edgeLoop.IsOuterEdgeLoop;
                }
                catch
                {
                    // Fallback below uses projected polygon area.
                }


                WeldInterfacePath path =
                    new WeldInterfacePath
                    {
                        SourceKind =
                            "COINCIDENT_FACE_LOOP",

                        GeometryType =
                            "CLOSED",

                        Closed =
                            true,

                        ClippedToWallEnvelope =
                            false,

                        LengthMm =
                            Math.Round(
                                PolylineLength(
                                    sample.Points),
                                3),

                        SourceBodyIndex =
                            bodyIndex,

                        SourceFaceIndex =
                            faceIndex,

                        SourceLoopIndex =
                            loopIndex,

                        BoundaryRole =
                            isOuter == true
                                ? "OUTER"
                                : isOuter == false
                                    ? "INNER_VOID"
                                    : "UNRESOLVED",

                        BoundarySelectionReason =
                            isOuter.HasValue
                                ? "INVENTOR_EDGE_LOOP_IS_OUTER"
                                : "PENDING_AREA_FALLBACK",

                        BoundaryGroupId =
                            $"BODY_{bodyIndex:000}_FACE_{faceIndex:000}_LOOP_{loopIndex:000}",

                        Model3DPointsMm =
                            Round3D(
                                sample.Points),

                        FaceLocalPointsMm =
                            Round2D(
                                local)
                    };


                candidates.Add(
                    (path, isOuter));
            }


            if (!thresholds.KeepOnlyOuterCoincidentFaceLoops
                ||
                candidates.Count <= 1)
            {
                return candidates
                    .Select(
                        c => c.Path)
                    .ToList();
            }


            List<WeldInterfacePath> explicitOuter =
                candidates
                    .Where(
                        c => c.IsOuter == true)
                    .Select(
                        c => c.Path)
                    .ToList();


            if (explicitOuter.Count > 0)
            {
                int suppressed =
                    candidates.Count
                    -
                    explicitOuter.Count;


                if (statistics != null)
                {
                    statistics
                        .InnerCoincidentFaceLoopsSuppressed
                        +=
                        Math.Max(
                            0,
                            suppressed);
                }


                return explicitOuter;
            }


            // Defensive fallback for old/proxy API contexts where
            // IsOuterEdgeLoop cannot be read. A single planar Face has
            // one material-enclosing external loop and optional hole loops;
            // the external loop has the greatest projected absolute area.
            WeldInterfacePath? fallbackOuter =
                candidates
                    .Select(
                        c => c.Path)
                    .OrderByDescending(
                        path =>
                            Math.Abs(
                                SignedArea2D(
                                    path.FaceLocalPointsMm)))
                    .FirstOrDefault();


            if (fallbackOuter == null)
            {
                return new List<WeldInterfacePath>();
            }


            fallbackOuter.BoundaryRole =
                "OUTER";

            fallbackOuter.BoundarySelectionReason =
                "LARGEST_PROJECTED_LOOP_AREA_FALLBACK";


            if (statistics != null)
            {
                statistics
                    .InnerCoincidentFaceLoopsSuppressed
                    +=
                    Math.Max(
                        0,
                        candidates.Count - 1);
            }


            return new List<WeldInterfacePath>
            {
                fallbackOuter
            };
        }


        public List<WeldPoint3Mm> GetPlaneCrossingPoints(
            List<WeldPoint3Mm> points,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds)
        {
            List<WeldPoint3Mm> result =
                new List<WeldPoint3Mm>();


            if (points.Count < 2)
            {
                return result;
            }


            double tolerance =
                thresholds.ContactToleranceMm;


            for (int i = 0;
                 i < points.Count - 1;
                 i++)
            {
                WeldPoint3Mm a =
                    points[i];

                WeldPoint3Mm b =
                    points[i + 1];


                double da =
                    WallDepth(
                        a,
                        wall);

                double db =
                    WallDepth(
                        b,
                        wall);


                if (Math.Abs(
                        da)
                    <= tolerance)
                {
                    WeldPoint2Mm p2 =
                        ProjectPoint(
                            a,
                            wall);


                    if (PointInsideEnvelope(
                            p2,
                            wall,
                            tolerance))
                    {
                        AddUniquePoint(
                            result,
                            a,
                            thresholds
                                .CurveDedupeToleranceMm);
                    }
                }


                bool crosses =
                    (
                        da <
                            -tolerance
                        &&
                        db >
                            tolerance
                    )
                    ||
                    (
                        da >
                            tolerance
                        &&
                        db <
                            -tolerance
                    );


                if (!crosses)
                {
                    continue;
                }


                double denominator =
                    da - db;


                if (Math.Abs(
                        denominator)
                    < 1e-12)
                {
                    continue;
                }


                double t =
                    da /
                    denominator;


                WeldPoint3Mm intersection =
                    new WeldPoint3Mm
                    {
                        X =
                            a.X
                            +
                            t
                            *
                            (b.X - a.X),

                        Y =
                            a.Y
                            +
                            t
                            *
                            (b.Y - a.Y),

                        Z =
                            a.Z
                            +
                            t
                            *
                            (b.Z - a.Z)
                    };


                WeldPoint2Mm p2Intersection =
                    ProjectPoint(
                        intersection,
                        wall);


                if (PointInsideEnvelope(
                        p2Intersection,
                        wall,
                        tolerance))
                {
                    AddUniquePoint(
                        result,
                        intersection,
                        thresholds
                            .CurveDedupeToleranceMm);
                }
            }


            return result;
        }


        public WeldEdgeSample SampleEdge(
            dynamic edge)
        {
            WeldEdgeSample result =
                new WeldEdgeSample();


            try
            {
                int vertexCount =
                    0;

                int segmentCount =
                    0;

                double[] coordinates =
                    Array.Empty<double>();

                int[] vertexIndices =
                    Array.Empty<int>();


                edge.CalculateStrokes(
                    StrokeToleranceCm,
                    out vertexCount,
                    out segmentCount,
                    out coordinates,
                    out vertexIndices);


                if (coordinates != null &&
                    vertexCount >= 2 &&
                    coordinates.Length >=
                        vertexCount * 3)
                {
                    for (int i = 0;
                         i < vertexCount;
                         i++)
                    {
                        int index =
                            i * 3;


                        result.Points.Add(
                            new WeldPoint3Mm
                            {
                                X =
                                    coordinates[index]
                                    *
                                    CmToMm,

                                Y =
                                    coordinates[index + 1]
                                    *
                                    CmToMm,

                                Z =
                                    coordinates[index + 2]
                                    *
                                    CmToMm
                            });
                    }


                    result.Success =
                        result.Points.Count >= 2;


                    if (result.Success)
                    {
                        return result;
                    }
                }
            }
            catch (Exception ex)
            {
                result.ErrorMessage =
                    "CalculateStrokes: "
                    +
                    ex.GetType().Name
                    +
                    " - "
                    +
                    ex.Message;
            }


            // Fallback para edges simples.
            try
            {
                dynamic? startVertex =
                    edge.StartVertex;

                dynamic? stopVertex =
                    edge.StopVertex;


                if (startVertex != null &&
                    stopVertex != null)
                {
                    dynamic startPoint =
                        startVertex.Point;

                    dynamic stopPoint =
                        stopVertex.Point;


                    if (startPoint != null &&
                        stopPoint != null)
                    {
                        result.Points.Clear();


                        result.Points.Add(
                            new WeldPoint3Mm
                            {
                                X =
                                    ((double)startPoint.X)
                                    *
                                    CmToMm,

                                Y =
                                    ((double)startPoint.Y)
                                    *
                                    CmToMm,

                                Z =
                                    ((double)startPoint.Z)
                                    *
                                    CmToMm
                            });


                        result.Points.Add(
                            new WeldPoint3Mm
                            {
                                X =
                                    ((double)stopPoint.X)
                                    *
                                    CmToMm,

                                Y =
                                    ((double)stopPoint.Y)
                                    *
                                    CmToMm,

                                Z =
                                    ((double)stopPoint.Z)
                                    *
                                    CmToMm
                            });


                        result.Success =
                            Distance3D(
                                result.Points[0],
                                result.Points[1])
                            >
                            1e-6;
                    }
                }
            }
            catch (Exception ex)
            {
                if (string.IsNullOrWhiteSpace(
                        result.ErrorMessage))
                {
                    result.ErrorMessage =
                        "StartStopVertex: "
                        +
                        ex.GetType().Name
                        +
                        " - "
                        +
                        ex.Message;
                }
            }


            return result;
        }


        public List<WeldInterfacePath> DedupePaths(
            IEnumerable<WeldInterfacePath> paths,
            WeldInterfaceThresholds thresholds)
        {
            List<WeldInterfacePath> result =
                new List<WeldInterfacePath>();


            foreach (WeldInterfacePath candidate
                     in paths)
            {
                bool duplicate =
                    false;


                foreach (WeldInterfacePath accepted
                         in result)
                {
                    if (PathsEquivalent(
                            candidate,
                            accepted,
                            thresholds
                                .CurveDedupeToleranceMm))
                    {
                        duplicate =
                            true;

                        break;
                    }
                }


                if (!duplicate)
                {
                    result.Add(
                        candidate);
                }
            }


            return result;
        }


        public List<WeldInterfacePath> ConsolidatePaths(
            IEnumerable<WeldInterfacePath> paths,
            WeldInterfaceThresholds thresholds,
            WeldInterfaceStatistics statistics)
        {
            List<WeldInterfacePath> input =
                paths.ToList();


            statistics
                .PathsBeforeConsolidation
                +=
                input.Count;


            List<WeldInterfacePath> loops =
                input
                    .Where(
                        p =>
                            p.SourceKind ==
                            "COINCIDENT_FACE_LOOP")
                    .ToList();


            if (loops.Count == 0)
            {
                statistics
                    .PathsAfterConsolidation
                    +=
                    input.Count;


                return input;
            }


            List<WeldInterfacePath> result =
                new List<WeldInterfacePath>();


            foreach (WeldInterfacePath path
                     in input)
            {
                if (path.SourceKind !=
                    "EDGE_ON_WALL")
                {
                    result.Add(
                        path);

                    continue;
                }


                bool redundant =
                    loops.Any(
                        loop =>
                            PathLiesOnLoop(
                                path,
                                loop,
                                thresholds
                                    .RedundantEdgeToLoopToleranceMm));


                if (redundant)
                {
                    statistics
                        .RedundantEdgePathsRemoved++;

                    continue;
                }


                result.Add(
                    path);
            }


            statistics
                .PathsAfterConsolidation
                +=
                result.Count;


            return result;
        }


        private WeldLoopSample SampleLoop(
            dynamic edgeLoop,
            WeldInterfaceThresholds thresholds)
        {
            WeldLoopSample result =
                new WeldLoopSample();


            try
            {
                dynamic edgeUses =
                    edgeLoop.EdgeUses;


                foreach (dynamic edgeUse
                         in edgeUses)
                {
                    dynamic edge =
                        edgeUse.Edge;


                    WeldEdgeSample edgeSample =
                        SampleEdge(
                            edge);


                    if (!edgeSample.Success)
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
                        edgeSample
                            .Points
                            .Reverse();
                    }


                    AppendConnected(
                        result.Points,
                        edgeSample.Points,
                        thresholds
                            .CurveJoinToleranceMm);
                }


                RemoveAdjacentDuplicates(
                    result.Points,
                    thresholds
                        .CurveDedupeToleranceMm);


                result.Success =
                    result.Points.Count >= 3;


                return result;
            }
            catch (Exception ex)
            {
                result.ErrorMessage =
                    ex.GetType().Name
                    +
                    ": "
                    +
                    ex.Message;

                return result;
            }
        }


        private bool PathLiesOnLoop(
            WeldInterfacePath edgePath,
            WeldInterfacePath loopPath,
            double tolerance)
        {
            if (edgePath.FaceLocalPointsMm.Count == 0
                ||
                loopPath.FaceLocalPointsMm.Count < 2)
            {
                return false;
            }


            foreach (WeldPoint2Mm point
                     in edgePath.FaceLocalPointsMm)
            {
                if (DistancePointToPolyline2D(
                        point,
                        loopPath.FaceLocalPointsMm)
                    >
                    tolerance)
                {
                    return false;
                }
            }


            return true;
        }


        private double DistancePointToPolyline2D(
            WeldPoint2Mm point,
            List<WeldPoint2Mm> polyline)
        {
            double best =
                double.PositiveInfinity;


            for (int i = 0;
                 i < polyline.Count - 1;
                 i++)
            {
                best =
                    Math.Min(
                        best,
                        DistancePointToSegment2D(
                            point,
                            polyline[i],
                            polyline[i + 1]));
            }


            return best;
        }


        private double DistancePointToSegment2D(
            WeldPoint2Mm p,
            WeldPoint2Mm a,
            WeldPoint2Mm b)
        {
            double vx =
                b.X - a.X;

            double vy =
                b.Y - a.Y;

            double wx =
                p.X - a.X;

            double wy =
                p.Y - a.Y;


            double vv =
                vx * vx
                +
                vy * vy;


            if (vv < 1e-12)
            {
                return Distance2D(
                    p,
                    a);
            }


            double t =
                (
                    wx * vx
                    +
                    wy * vy
                )
                /
                vv;


            t =
                Math.Max(
                    0.0,
                    Math.Min(
                        1.0,
                        t));


            WeldPoint2Mm q =
                new WeldPoint2Mm
                {
                    X =
                        a.X
                        +
                        t * vx,

                    Y =
                        a.Y
                        +
                        t * vy
                };


            return Distance2D(
                p,
                q);
        }


        private void AppendConnected(
            List<WeldPoint3Mm> target,
            List<WeldPoint3Mm> source,
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


            WeldPoint3Mm end =
                target[target.Count - 1];


            double d0 =
                Distance3D(
                    end,
                    source[0]);

            double d1 =
                Distance3D(
                    end,
                    source[source.Count - 1]);


            List<WeldPoint3Mm> ordered =
                source;


            if (d1 < d0)
            {
                ordered =
                    new List<WeldPoint3Mm>(
                        source);

                ordered.Reverse();
            }


            int start =
                Distance3D(
                    end,
                    ordered[0])
                <= tolerance
                    ? 1
                    : 0;


            for (int i = start;
                 i < ordered.Count;
                 i++)
            {
                target.Add(
                    ordered[i]);
            }
        }


        private void RemoveAdjacentDuplicates(
            List<WeldPoint3Mm> points,
            double tolerance)
        {
            for (int i = points.Count - 1;
                 i > 0;
                 i--)
            {
                if (Distance3D(
                        points[i],
                        points[i - 1])
                    <= tolerance)
                {
                    points.RemoveAt(
                        i);
                }
            }
        }


        private void ClosePolyline(
            List<WeldPoint3Mm> points,
            double tolerance)
        {
            if (points.Count < 3)
            {
                return;
            }


            if (Distance3D(
                    points[0],
                    points[points.Count - 1])
                >
                tolerance)
            {
                points.Add(
                    new WeldPoint3Mm
                    {
                        X = points[0].X,
                        Y = points[0].Y,
                        Z = points[0].Z
                    });
            }
        }


        private bool IsClosedEdge(
            dynamic edge,
            List<WeldPoint3Mm> points,
            WeldInterfaceThresholds thresholds)
        {
            if (points.Count >= 3 &&
                Distance3D(
                    points[0],
                    points[points.Count - 1])
                <=
                thresholds
                    .CurveJoinToleranceMm)
            {
                return true;
            }


            try
            {
                dynamic? startVertex =
                    edge.StartVertex;

                dynamic? stopVertex =
                    edge.StopVertex;


                return
                    startVertex == null
                    &&
                    stopVertex == null;
            }
            catch
            {
                return false;
            }
        }


        private string DetermineGeometryType(
            List<WeldPoint3Mm> points,
            bool closed)
        {
            if (closed)
            {
                return "CLOSED";
            }


            if (points.Count <= 2)
            {
                return "LINEAR";
            }


            WeldPoint3Mm a =
                points[0];

            WeldPoint3Mm b =
                points[points.Count - 1];


            double chord =
                Distance3D(
                    a,
                    b);


            if (chord < 1e-9)
            {
                return "CURVED_OR_MULTI_SEGMENT";
            }


            double maxDeviation =
                0.0;


            foreach (WeldPoint3Mm p
                     in points)
            {
                maxDeviation =
                    Math.Max(
                        maxDeviation,
                        PointLineDistance(
                            p,
                            a,
                            b));
            }


            return maxDeviation <= 0.5
                ? "LINEAR"
                : "CURVED_OR_MULTI_SEGMENT";
        }


        private bool PathsEquivalent(
            WeldInterfacePath a,
            WeldInterfacePath b,
            double tolerance)
        {
            if (a.SourceKind != b.SourceKind
                ||
                a.Closed != b.Closed)
            {
                return false;
            }


            if (Math.Abs(
                    a.LengthMm -
                    b.LengthMm)
                >
                Math.Max(
                    tolerance,
                    0.01
                    *
                    Math.Max(
                        a.LengthMm,
                        b.LengthMm)))
            {
                return false;
            }


            WeldBounds2D ab =
                Bounds(
                    a.FaceLocalPointsMm);

            WeldBounds2D bb =
                Bounds(
                    b.FaceLocalPointsMm);


            return
                Math.Abs(
                    ab.MinX - bb.MinX)
                <= tolerance
                &&
                Math.Abs(
                    ab.MaxX - bb.MaxX)
                <= tolerance
                &&
                Math.Abs(
                    ab.MinY - bb.MinY)
                <= tolerance
                &&
                Math.Abs(
                    ab.MaxY - bb.MaxY)
                <= tolerance;
        }


        private List<WeldPoint2Mm> ProjectPoints(
            IEnumerable<WeldPoint3Mm> points,
            WeldInterfaceFaceRecord wall)
        {
            List<WeldPoint2Mm> result =
                new List<WeldPoint2Mm>();


            foreach (WeldPoint3Mm point
                     in points)
            {
                result.Add(
                    ProjectPoint(
                        point,
                        wall));
            }


            return result;
        }


        private WeldPoint2Mm ProjectPoint(
            WeldPoint3Mm point,
            WeldInterfaceFaceRecord wall)
        {
            double dx =
                point.X -
                wall.OriginMm.X;

            double dy =
                point.Y -
                wall.OriginMm.Y;

            double dz =
                point.Z -
                wall.OriginMm.Z;


            return new WeldPoint2Mm
            {
                X =
                    dx * wall.LocalU.X
                    +
                    dy * wall.LocalU.Y
                    +
                    dz * wall.LocalU.Z,

                Y =
                    dx * wall.LocalV.X
                    +
                    dy * wall.LocalV.Y
                    +
                    dz * wall.LocalV.Z
            };
        }


        private double WallDepth(
            WeldPoint3Mm point,
            WeldInterfaceFaceRecord wall)
        {
            return WeldContactPlaneResolver.Depth(point, wall);
        }


        private bool PointInsideEnvelope(
            WeldPoint2Mm point,
            WeldInterfaceFaceRecord wall,
            double margin)
        {
            return WeldInterfaceWallGeometry
                .Contains(
                    point,
                    wall,
                    margin);
        }


        private double PolylineLength(
            List<WeldPoint3Mm> points)
        {
            double total =
                0.0;


            for (int i = 0;
                 i < points.Count - 1;
                 i++)
            {
                total +=
                    Distance3D(
                        points[i],
                        points[i + 1]);
            }


            return total;
        }


        private double PointLineDistance(
            WeldPoint3Mm p,
            WeldPoint3Mm a,
            WeldPoint3Mm b)
        {
            double vx =
                b.X - a.X;

            double vy =
                b.Y - a.Y;

            double vz =
                b.Z - a.Z;

            double wx =
                p.X - a.X;

            double wy =
                p.Y - a.Y;

            double wz =
                p.Z - a.Z;


            double vv =
                vx * vx
                +
                vy * vy
                +
                vz * vz;


            if (vv < 1e-12)
            {
                return Distance3D(
                    p,
                    a);
            }


            double t =
                (
                    wx * vx
                    +
                    wy * vy
                    +
                    wz * vz
                )
                /
                vv;


            WeldPoint3Mm q =
                new WeldPoint3Mm
                {
                    X =
                        a.X
                        +
                        t * vx,

                    Y =
                        a.Y
                        +
                        t * vy,

                    Z =
                        a.Z
                        +
                        t * vz
                };


            return Distance3D(
                p,
                q);
        }


        private void AddUniquePoint(
            List<WeldPoint3Mm> points,
            WeldPoint3Mm candidate,
            double tolerance)
        {
            foreach (WeldPoint3Mm point
                     in points)
            {
                if (Distance3D(
                        point,
                        candidate)
                    <= tolerance)
                {
                    return;
                }
            }


            points.Add(
                candidate);
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


        private double Distance3D(
            WeldPoint3Mm a,
            WeldPoint3Mm b)
        {
            double dx =
                a.X - b.X;

            double dy =
                a.Y - b.Y;

            double dz =
                a.Z - b.Z;


            return Math.Sqrt(
                dx * dx
                +
                dy * dy
                +
                dz * dz);
        }


        private List<WeldPoint3Mm> Round3D(
            IEnumerable<WeldPoint3Mm> points)
        {
            return points
                .Select(
                    p =>
                        new WeldPoint3Mm
                        {
                            X =
                                Math.Round(
                                    p.X,
                                    3),

                            Y =
                                Math.Round(
                                    p.Y,
                                    3),

                            Z =
                                Math.Round(
                                    p.Z,
                                    3)
                        })
                .ToList();
        }


        private List<WeldPoint2Mm> Round2D(
            IEnumerable<WeldPoint2Mm> points)
        {
            return points
                .Select(
                    p =>
                        new WeldPoint2Mm
                        {
                            X =
                                Math.Round(
                                    p.X,
                                    3),

                            Y =
                                Math.Round(
                                    p.Y,
                                    3)
                        })
                .ToList();
        }


        private WeldBounds2D Bounds(
            List<WeldPoint2Mm> points)
        {
            if (points.Count == 0)
            {
                return new WeldBounds2D();
            }


            return new WeldBounds2D
            {
                MinX =
                    points.Min(
                        p => p.X),

                MaxX =
                    points.Max(
                        p => p.X),

                MinY =
                    points.Min(
                        p => p.Y),

                MaxY =
                    points.Max(
                        p => p.Y)
            };
        }
    }


    public class WeldEdgeSample
    {
        public bool Success { get; set; }

        public string ErrorMessage { get; set; } =
            "";

        public List<WeldPoint3Mm> Points { get; set; } =
            new();
    }


    internal class WeldLoopSample
    {
        public bool Success;

        public string ErrorMessage =
            "";

        public List<WeldPoint3Mm> Points =
            new List<WeldPoint3Mm>();
    }


    internal class WeldBounds2D
    {
        public double MinX;

        public double MaxX;

        public double MinY;

        public double MaxY;
    }
}
