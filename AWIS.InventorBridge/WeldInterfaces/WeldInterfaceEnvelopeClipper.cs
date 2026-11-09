using System;
using System.Collections.Generic;
using System.Linq;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // ================================================================
    // V1.1-A / V0.2.2
    // PHYSICAL WALL BOUNDS CLIPPER
    //
    // V0.2.2 recorta contra PhysicalWall.Bounds:
    // U = MinU..MaxU
    // V = MinV..MaxV
    //
    // If PhysicalWall is unresolved, it falls back to the legacy
    // canonical 0..WidthMm / 0..HeightMm envelope.
    //
    // NO hace clamp de puntos.
    // Interpola simultáneamente UV y XYZ con el mismo parámetro t.
    // ================================================================

    public class WeldInterfaceEnvelopeClipper
    {
        public List<WeldInterfacePath> ClipPaths(
            IEnumerable<WeldInterfacePath> paths,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            WeldInterfaceStatistics statistics,
            double? boundaryToleranceMm = null)
        {
            List<WeldInterfacePath> result =
                new List<WeldInterfacePath>();


            foreach (WeldInterfacePath path
                     in paths)
            {
                List<WeldInterfacePath> clipped =
                    ClipPath(
                        path,
                        wall,
                        thresholds,
                        boundaryToleranceMm);


                if (clipped.Count == 0)
                {
                    statistics
                        .PathsDiscardedOutsideEnvelope++;

                    continue;
                }


                bool changed =
                    clipped.Count != 1
                    ||
                    clipped[0]
                        .ClippedToWallEnvelope;


                if (changed)
                {
                    statistics
                        .SourcePathsClipped++;


                    statistics
                        .ClippedFragmentsGenerated
                        +=
                        clipped.Count;
                }


                result.AddRange(
                    clipped);
            }


            return result;
        }


        public List<WeldInterfacePath> ClipPath(
            WeldInterfacePath path,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            double? boundaryToleranceMm = null)
        {
            if (path.Model3DPointsMm.Count < 2
                ||
                path.FaceLocalPointsMm.Count < 2
                ||
                path.Model3DPointsMm.Count
                    !=
                    path.FaceLocalPointsMm.Count)
            {
                return new List<WeldInterfacePath>();
            }


            double tolerance = boundaryToleranceMm ?? thresholds.EnvelopeClipToleranceMm;


            bool allInside =
                path.FaceLocalPointsMm.All(
                    p =>
                        IsInside(
                            p,
                            wall,
                            tolerance));


            if (allInside)
            {
                WeldInterfacePath copy =
                    ClonePath(
                        path);


                copy.ClippedToWallEnvelope =
                    false;


                return new List<WeldInterfacePath>
                {
                    copy
                };
            }


            List<WeldPathFragment> fragments =
                new List<WeldPathFragment>();


            WeldPathFragment? current =
                null;


            for (int i = 0;
                 i < path.FaceLocalPointsMm.Count - 1;
                 i++)
            {
                WeldPoint2Mm uvA =
                    path.FaceLocalPointsMm[i];

                WeldPoint2Mm uvB =
                    path.FaceLocalPointsMm[i + 1];

                WeldPoint3Mm xyzA =
                    path.Model3DPointsMm[i];

                WeldPoint3Mm xyzB =
                    path.Model3DPointsMm[i + 1];


                if (!ClipSegment(
                        uvA,
                        uvB,
                        wall,
                        tolerance,
                        out double t0,
                        out double t1))
                {
                    current =
                        null;

                    continue;
                }


                WeldPoint2Mm cUvA =
                    Interpolate2D(
                        uvA,
                        uvB,
                        t0);

                WeldPoint2Mm cUvB =
                    Interpolate2D(
                        uvA,
                        uvB,
                        t1);

                WeldPoint3Mm cXyzA =
                    Interpolate3D(
                        xyzA,
                        xyzB,
                        t0);

                WeldPoint3Mm cXyzB =
                    Interpolate3D(
                        xyzA,
                        xyzB,
                        t1);


                if (Distance2D(
                        cUvA,
                        cUvB)
                    <= tolerance)
                {
                    continue;
                }


                if (current == null
                    ||
                    current
                        .LocalPoints
                        .Count == 0
                    ||
                    Distance2D(
                        current
                            .LocalPoints[
                                current.LocalPoints.Count - 1],
                        cUvA)
                        >
                        Math.Max(
                            thresholds.CurveJoinToleranceMm,
                            tolerance))
                {
                    current =
                        new WeldPathFragment();


                    fragments.Add(
                        current);


                    current.LocalPoints.Add(
                        cUvA);

                    current.ModelPoints.Add(
                        cXyzA);
                }
                else
                {
                    ReplaceLastIfNearlyEqual(
                        current,
                        cUvA,
                        cXyzA,
                        thresholds
                            .CurveJoinToleranceMm);
                }


                current.LocalPoints.Add(
                    cUvB);

                current.ModelPoints.Add(
                    cXyzB);
            }


            List<WeldInterfacePath> result =
                new List<WeldInterfacePath>();


            foreach (WeldPathFragment fragment
                     in fragments)
            {
                RemoveAdjacentDuplicates(
                    fragment,
                    thresholds
                        .CurveDedupeToleranceMm);


                if (fragment.LocalPoints.Count < 2)
                {
                    continue;
                }


                WeldInterfacePath clippedPath =
                    CloneMetadataOnly(
                        path);


                clippedPath.ClippedToWallEnvelope =
                    true;

                clippedPath.Closed =
                    false;

                clippedPath.Model3DPointsMm =
                    Round3D(
                        fragment.ModelPoints);

                clippedPath.FaceLocalPointsMm =
                    Round2D(
                        fragment.LocalPoints);

                clippedPath.LengthMm =
                    Math.Round(
                        PolylineLength(
                            fragment.ModelPoints),
                        3);

                clippedPath.GeometryType =
                    DetermineGeometryType(
                        fragment.ModelPoints,
                        false);


                if (clippedPath.LengthMm >
                    thresholds
                        .CurveDedupeToleranceMm)
                {
                    result.Add(
                        clippedPath);
                }
            }


            return result;
        }


        private bool ClipSegment(
            WeldPoint2Mm a,
            WeldPoint2Mm b,
            WeldInterfaceFaceRecord wall,
            double tolerance,
            out double t0,
            out double t1)
        {
            t0 =
                0.0;

            t1 =
                1.0;


            WeldWallBounds wallBounds =
                WeldInterfaceWallGeometry
                    .GetBounds(
                        wall);


            double minX =
                wallBounds.MinU
                -
                tolerance;

            double maxX =
                wallBounds.MaxU
                +
                tolerance;

            double minY =
                wallBounds.MinV
                -
                tolerance;

            double maxY =
                wallBounds.MaxV
                +
                tolerance;


            double dx =
                b.X - a.X;

            double dy =
                b.Y - a.Y;


            if (!ClipTest(
                    -dx,
                    a.X - minX,
                    ref t0,
                    ref t1))
            {
                return false;
            }


            if (!ClipTest(
                    dx,
                    maxX - a.X,
                    ref t0,
                    ref t1))
            {
                return false;
            }


            if (!ClipTest(
                    -dy,
                    a.Y - minY,
                    ref t0,
                    ref t1))
            {
                return false;
            }


            if (!ClipTest(
                    dy,
                    maxY - a.Y,
                    ref t0,
                    ref t1))
            {
                return false;
            }


            return t1 >= t0;
        }


        private bool ClipTest(
            double p,
            double q,
            ref double t0,
            ref double t1)
        {
            const double epsilon =
                1e-12;


            if (Math.Abs(
                    p)
                < epsilon)
            {
                return q >= 0.0;
            }


            double r =
                q / p;


            if (p < 0.0)
            {
                if (r > t1)
                {
                    return false;
                }


                if (r > t0)
                {
                    t0 =
                        r;
                }
            }
            else
            {
                if (r < t0)
                {
                    return false;
                }


                if (r < t1)
                {
                    t1 =
                        r;
                }
            }


            return true;
        }


        private bool IsInside(
            WeldPoint2Mm point,
            WeldInterfaceFaceRecord wall,
            double tolerance)
        {
            return WeldInterfaceWallGeometry
                .Contains(
                    point,
                    wall,
                    tolerance);
        }


        private WeldInterfacePath ClonePath(
            WeldInterfacePath source)
        {
            WeldInterfacePath clone =
                CloneMetadataOnly(
                    source);


            clone.Model3DPointsMm =
                source
                    .Model3DPointsMm
                    .Select(
                        p =>
                            new WeldPoint3Mm
                            {
                                X = p.X,
                                Y = p.Y,
                                Z = p.Z
                            })
                    .ToList();


            clone.FaceLocalPointsMm =
                source
                    .FaceLocalPointsMm
                    .Select(
                        p =>
                            new WeldPoint2Mm
                            {
                                X = p.X,
                                Y = p.Y
                            })
                    .ToList();


            return clone;
        }


        private WeldInterfacePath CloneMetadataOnly(
            WeldInterfacePath source)
        {
            return new WeldInterfacePath
            {
                PathId =
                    source.PathId,

                SourceKind =
                    source.SourceKind,

                GeometryType =
                    source.GeometryType,

                Closed =
                    source.Closed,

                ClippedToWallEnvelope =
                    source.ClippedToWallEnvelope,

                LengthMm =
                    source.LengthMm,

                SourceBodyIndex =
                    source.SourceBodyIndex,

                SourceFaceIndex =
                    source.SourceFaceIndex,

                SourceLoopIndex =
                    source.SourceLoopIndex,

                SourceEdgeIndex =
                    source.SourceEdgeIndex,

                BoundaryRole =
                    source.BoundaryRole,

                BoundarySelectionReason =
                    source.BoundarySelectionReason,

                BoundaryGroupId =
                    source.BoundaryGroupId,

                PhysicalMemberType =
                    source.PhysicalMemberType,

                PhysicalMemberGroupId =
                    source.PhysicalMemberGroupId,

                PhysicalSideRole =
                    source.PhysicalSideRole,

                PhysicalBoundaryRole =
                    source.PhysicalBoundaryRole,

                OriginalClosedLoopLengthMm =
                    source.OriginalClosedLoopLengthMm
            };
        }


        private void ReplaceLastIfNearlyEqual(
            WeldPathFragment fragment,
            WeldPoint2Mm uv,
            WeldPoint3Mm xyz,
            double tolerance)
        {
            int lastIndex =
                fragment.LocalPoints.Count - 1;


            if (lastIndex < 0)
            {
                return;
            }


            if (Distance2D(
                    fragment.LocalPoints[lastIndex],
                    uv)
                <= tolerance)
            {
                fragment.LocalPoints[lastIndex] =
                    uv;

                fragment.ModelPoints[lastIndex] =
                    xyz;
            }
        }


        private void RemoveAdjacentDuplicates(
            WeldPathFragment fragment,
            double tolerance)
        {
            for (int i =
                     fragment.LocalPoints.Count - 1;
                 i > 0;
                 i--)
            {
                if (Distance2D(
                        fragment.LocalPoints[i],
                        fragment.LocalPoints[i - 1])
                    <= tolerance)
                {
                    fragment
                        .LocalPoints
                        .RemoveAt(
                            i);

                    fragment
                        .ModelPoints
                        .RemoveAt(
                            i);
                }
            }
        }


        private WeldPoint2Mm Interpolate2D(
            WeldPoint2Mm a,
            WeldPoint2Mm b,
            double t)
        {
            return new WeldPoint2Mm
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
                    (b.Y - a.Y)
            };
        }


        private WeldPoint3Mm Interpolate3D(
            WeldPoint3Mm a,
            WeldPoint3Mm b,
            double t)
        {
            return new WeldPoint3Mm
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
                    X = a.X + t * vx,
                    Y = a.Y + t * vy,
                    Z = a.Z + t * vz
                };


            return Distance3D(
                p,
                q);
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
    }


    internal class WeldPathFragment
    {
        public List<WeldPoint3Mm> ModelPoints { get; } =
            new();

        public List<WeldPoint2Mm> LocalPoints { get; } =
            new();
    }
}
