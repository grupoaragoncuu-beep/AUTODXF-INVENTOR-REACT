using Inventor;
using System;
using System.Collections.Generic;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // ================================================================
    // V1.1-A / V0.2.1
    // BROAD PHASE + LEAF OCCURRENCE FILTER
    //
    // Recorre todo el árbol, pero solo entrega piezas hoja con B-Rep.
    // Los subensambles se conservan únicamente como navegación.
    // ================================================================

    public class WeldInterfaceBroadPhase
    {
        private const double CmToMm =
            10.0;


        public List<ComponentOccurrence> GetLeafOccurrences(
            AssemblyDocument assembly,
            WeldInterfaceStatistics statistics)
        {
            List<ComponentOccurrence> result =
                new List<ComponentOccurrence>();


            foreach (ComponentOccurrence occurrence
                     in assembly.ComponentDefinition.Occurrences)
            {
                AddOccurrenceRecursive(
                    occurrence,
                    result,
                    statistics);
            }


            return result;
        }


        public List<WeldBroadPhaseCandidate> FindCandidatesForWall(
            IEnumerable<ComponentOccurrence> occurrences,
            WeldInterfaceFaceRecord wall,
            HashSet<string> structuralOccurrencePaths,
            WeldInterfaceThresholds thresholds,
            WeldInterfaceStatistics statistics)
        {
            List<WeldBroadPhaseCandidate> result =
                new List<WeldBroadPhaseCandidate>();


            foreach (ComponentOccurrence occurrence
                     in occurrences)
            {
                if (IsSuppressed(
                        occurrence))
                {
                    statistics
                        .SuppressedOccurrencesSkipped++;

                    continue;
                }


                string occurrencePath =
                    BuildOccurrencePath(
                        occurrence);


                statistics
                    .OccurrenceWallPairsEvaluated++;


                if (WeldWallBodyScope.IsSameOccurrence(occurrencePath, wall)
                    && !WeldWallBodyScope.HasOtherBodies(occurrencePath,
                        occurrence.SurfaceBodies.Count, wall))
                {
                    statistics
                        .OwnWallPairsSkipped++;

                    continue;
                }


                WeldRangeRelation relation =
                    EvaluateRangeBox(
                        occurrence,
                        wall,
                        thresholds);


                if (!relation.IntersectsBroadPhase)
                {
                    continue;
                }


                result.Add(
                    new WeldBroadPhaseCandidate
                    {
                        Occurrence =
                            occurrence,

                        OccurrenceName =
                            occurrence.Name,

                        OccurrencePath =
                            occurrencePath,

                        IsStructuralBoundaryComponent =
                            structuralOccurrencePaths.Contains(
                                occurrencePath),

                        MinimumAbsoluteDepthMm =
                            relation.MinimumAbsoluteDepthMm,

                        MinimumDepthMm =
                            relation.MinimumDepthMm,

                        MaximumDepthMm =
                            relation.MaximumDepthMm
                    });


                statistics
                    .BroadPhaseCandidates++;
            }


            return result;
        }


        private void AddOccurrenceRecursive(
            ComponentOccurrence occurrence,
            List<ComponentOccurrence> result,
            WeldInterfaceStatistics statistics)
        {
            statistics
                .OccurrencesVisited++;


            int childCount =
                GetSubOccurrenceCount(
                    occurrence);


            if (childCount > 0)
            {
                statistics
                    .ParentOccurrencesSkipped++;


                try
                {
                    foreach (ComponentOccurrence child
                             in occurrence.SubOccurrences)
                    {
                        AddOccurrenceRecursive(
                            child,
                            result,
                            statistics);
                    }
                }
                catch
                {
                    // Si Inventor no permite recorrer un subensamble
                    // puntual, el nodo padre sigue sin convertirse
                    // artificialmente en una pieza física.
                }


                return;
            }


            if (!HasUsableBRep(
                    occurrence))
            {
                statistics
                    .LeafOccurrencesWithoutBRepSkipped++;

                return;
            }


            result.Add(
                occurrence);


            statistics
                .LeafOccurrencesAccepted++;
        }


        private int GetSubOccurrenceCount(
            ComponentOccurrence occurrence)
        {
            try
            {
                return occurrence
                    .SubOccurrences
                    .Count;
            }
            catch
            {
                return 0;
            }
        }


        private bool HasUsableBRep(
            ComponentOccurrence occurrence)
        {
            try
            {
                SurfaceBodies bodies =
                    occurrence.SurfaceBodies;


                return bodies != null
                    &&
                    bodies.Count > 0;
            }
            catch
            {
                return false;
            }
        }


        private WeldRangeRelation EvaluateRangeBox(
            ComponentOccurrence occurrence,
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds)
        {
            try
            {
                Box rangeBox =
                    occurrence.RangeBox;


                List<WeldPoint3Mm> corners =
                    GetBoxCornersMm(
                        rangeBox);


                double minDepth =
                    double.PositiveInfinity;

                double maxDepth =
                    double.NegativeInfinity;

                double minAbsDepth =
                    double.PositiveInfinity;

                double minU =
                    double.PositiveInfinity;

                double maxU =
                    double.NegativeInfinity;

                double minV =
                    double.PositiveInfinity;

                double maxV =
                    double.NegativeInfinity;


                foreach (WeldPoint3Mm corner
                         in corners)
                {
                    double depth =
                        WallDepth(
                            corner,
                            wall);


                    WeldPoint2Mm p2 =
                        ProjectPoint(
                            corner,
                            wall);


                    minDepth =
                        Math.Min(
                            minDepth,
                            depth);

                    maxDepth =
                        Math.Max(
                            maxDepth,
                            depth);

                    minAbsDepth =
                        Math.Min(
                            minAbsDepth,
                            Math.Abs(
                                depth));

                    minU =
                        Math.Min(
                            minU,
                            p2.X);

                    maxU =
                        Math.Max(
                            maxU,
                            p2.X);

                    minV =
                        Math.Min(
                            minV,
                            p2.Y);

                    maxV =
                        Math.Max(
                            maxV,
                            p2.Y);
                }


                double planeBand =
                    thresholds
                        .BroadPhasePlaneBandMm;


                bool planeOverlap =
                    maxDepth >=
                        -planeBand
                    &&
                    minDepth <=
                        planeBand;


                double margin =
                    thresholds
                        .BroadPhaseSurfaceMarginMm;


                WeldWallBounds wallBounds =
                    WeldInterfaceWallGeometry
                        .GetBounds(
                            wall);


                bool envelopeOverlap =
                    maxU >=
                        wallBounds.MinU
                        -
                        margin
                    &&
                    minU <=
                        wallBounds.MaxU
                        +
                        margin
                    &&
                    maxV >=
                        wallBounds.MinV
                        -
                        margin
                    &&
                    minV <=
                        wallBounds.MaxV
                        +
                        margin;


                return new WeldRangeRelation
                {
                    IntersectsBroadPhase =
                        planeOverlap
                        &&
                        envelopeOverlap,

                    MinimumAbsoluteDepthMm =
                        minAbsDepth,

                    MinimumDepthMm =
                        minDepth,

                    MaximumDepthMm =
                        maxDepth
                };
            }
            catch
            {
                // Conservador: si RangeBox falla en una pieza hoja
                // con B-Rep, permitimos que pase al exact detector.
                return new WeldRangeRelation
                {
                    IntersectsBroadPhase =
                        true,

                    MinimumAbsoluteDepthMm =
                        double.PositiveInfinity,

                    MinimumDepthMm =
                        double.NaN,

                    MaximumDepthMm =
                        double.NaN
                };
            }
        }


        public static string BuildOccurrencePath(
            ComponentOccurrence occurrence)
        {
            List<string> names =
                new List<string>();


            ComponentOccurrence? current =
                occurrence;


            while (current != null)
            {
                names.Add(
                    current.Name);


                try
                {
                    current =
                        current.ParentOccurrence;
                }
                catch
                {
                    current =
                        null;
                }
            }


            names.Reverse();


            return string.Join(
                "/",
                names);
        }


        private bool IsSuppressed(
            ComponentOccurrence occurrence)
        {
            try
            {
                return occurrence.Suppressed;
            }
            catch
            {
                return false;
            }
        }


        private List<WeldPoint3Mm> GetBoxCornersMm(
            Box box)
        {
            Point min =
                box.MinPoint;

            Point max =
                box.MaxPoint;


            double minX =
                min.X * CmToMm;

            double minY =
                min.Y * CmToMm;

            double minZ =
                min.Z * CmToMm;

            double maxX =
                max.X * CmToMm;

            double maxY =
                max.Y * CmToMm;

            double maxZ =
                max.Z * CmToMm;


            return new List<WeldPoint3Mm>
            {
                NewPoint(minX, minY, minZ),
                NewPoint(minX, minY, maxZ),
                NewPoint(minX, maxY, minZ),
                NewPoint(minX, maxY, maxZ),
                NewPoint(maxX, minY, minZ),
                NewPoint(maxX, minY, maxZ),
                NewPoint(maxX, maxY, minZ),
                NewPoint(maxX, maxY, maxZ)
            };
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


        private WeldPoint3Mm NewPoint(
            double x,
            double y,
            double z)
        {
            return new WeldPoint3Mm
            {
                X = x,
                Y = y,
                Z = z
            };
        }
    }


    public class WeldBroadPhaseCandidate
    {
        public ComponentOccurrence Occurrence { get; set; } =
            null!;

        public string OccurrenceName { get; set; } =
            "";

        public string OccurrencePath { get; set; } =
            "";

        public bool IsStructuralBoundaryComponent { get; set; }

        public double MinimumAbsoluteDepthMm { get; set; }

        public double MinimumDepthMm { get; set; }

        public double MaximumDepthMm { get; set; }
    }


    internal class WeldRangeRelation
    {
        public bool IntersectsBroadPhase;

        public double MinimumAbsoluteDepthMm;

        public double MinimumDepthMm;

        public double MaximumDepthMm;
    }
}
