using Inventor;
using System;
using System.Collections.Generic;

namespace AWIS.InventorBridge.FacePreview
{
    // ================================================================
    // AWIS FACE PREVIEW COMPANION V0.3
    // LOOP SAMPLER
    //
    // Convierte un EdgeLoop/EdgeLoopProxy en una polyline 3D ordenada.
    // Usa EdgeUse para respetar la orientación topológica del loop.
    // ================================================================

    internal class FacePreviewLoopSampler
    {
        private const double CmToMm =
            10.0;


        // 0.05 cm = 0.5 mm.
        private const double StrokeToleranceCm =
            0.05;


        private const double JoinToleranceMm =
            0.05;


        public LoopSampleResult SampleLoop(
            dynamic edgeLoop)
        {
            LoopSampleResult result =
                new LoopSampleResult();


            try
            {
                result.IsOuter =
                    (bool)edgeLoop.IsOuterEdgeLoop;


                dynamic edgeUses =
                    edgeLoop.EdgeUses;


                foreach (dynamic edgeUse
                         in edgeUses)
                {
                    dynamic edge =
                        edgeUse.Edge;


                    EdgeSampleResult edgeSample =
                        SampleEdge(
                            edge);


                    if (!edgeSample.Success ||
                        edgeSample.PointsMm.Count < 2)
                    {
                        result.EdgeSamplingFailures++;

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
                            .PointsMm
                            .Reverse();
                    }


                    AppendConnected(
                        result.PointsMm,
                        edgeSample.PointsMm);
                }


                RemoveAdjacentDuplicates(
                    result.PointsMm);


                if (result.PointsMm.Count >= 3)
                {
                    CloseLoop(
                        result.PointsMm);


                    result.Success =
                        result.PointsMm.Count >= 4;
                }


                return result;
            }
            catch (Exception ex)
            {
                result.ErrorMessage =
                    $"{ex.GetType().Name}: {ex.Message}";

                return result;
            }
        }


        private EdgeSampleResult SampleEdge(
            dynamic edge)
        {
            EdgeSampleResult result =
                new EdgeSampleResult();


            // --------------------------------------------------------
            // Primary:
            // Edge / EdgeProxy CalculateStrokes.
            //
            // Esta llamada ya quedó validada en Companion V0.2.1.
            // --------------------------------------------------------

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
                        int coordinateIndex =
                            i * 3;


                        result.PointsMm.Add(
                            new Point3Mm
                            {
                                X =
                                    coordinates[coordinateIndex]
                                    * CmToMm,

                                Y =
                                    coordinates[coordinateIndex + 1]
                                    * CmToMm,

                                Z =
                                    coordinates[coordinateIndex + 2]
                                    * CmToMm
                            });
                    }


                    result.Success =
                        result.PointsMm.Count >= 2;


                    if (result.Success)
                    {
                        return result;
                    }
                }
            }
            catch (Exception ex)
            {
                result.ErrorMessage =
                    $"CalculateStrokes: {ex.GetType().Name} - {ex.Message}";
            }


            // --------------------------------------------------------
            // Fallback:
            // StartVertex / StopVertex para una edge abierta sencilla.
            // --------------------------------------------------------

            try
            {
                dynamic startVertex =
                    edge.StartVertex;

                dynamic stopVertex =
                    edge.StopVertex;


                if (startVertex != null &&
                    stopVertex != null)
                {
                    dynamic startPoint =
                        startVertex.Point;

                    dynamic stopPoint =
                        stopVertex.Point;


                    result.PointsMm.Clear();


                    result.PointsMm.Add(
                        new Point3Mm
                        {
                            X =
                                ((double)startPoint.X)
                                * CmToMm,

                            Y =
                                ((double)startPoint.Y)
                                * CmToMm,

                            Z =
                                ((double)startPoint.Z)
                                * CmToMm
                        });


                    result.PointsMm.Add(
                        new Point3Mm
                        {
                            X =
                                ((double)stopPoint.X)
                                * CmToMm,

                            Y =
                                ((double)stopPoint.Y)
                                * CmToMm,

                            Z =
                                ((double)stopPoint.Z)
                                * CmToMm
                        });


                    result.Success =
                        Distance(
                            result.PointsMm[0],
                            result.PointsMm[1])
                        >
                        JoinToleranceMm;
                }
            }
            catch (Exception ex)
            {
                if (string.IsNullOrWhiteSpace(
                        result.ErrorMessage))
                {
                    result.ErrorMessage =
                        $"StartStopVertex: {ex.GetType().Name} - {ex.Message}";
                }
            }


            return result;
        }


        private void AppendConnected(
            List<Point3Mm> target,
            List<Point3Mm> source)
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


            Point3Mm targetEnd =
                target[target.Count - 1];


            double distanceToSourceStart =
                Distance(
                    targetEnd,
                    source[0]);


            double distanceToSourceEnd =
                Distance(
                    targetEnd,
                    source[source.Count - 1]);


            if (distanceToSourceEnd <
                distanceToSourceStart)
            {
                source =
                    new List<Point3Mm>(
                        source);

                source.Reverse();
            }


            int startIndex =
                Distance(
                    targetEnd,
                    source[0])
                <=
                JoinToleranceMm
                    ? 1
                    : 0;


            for (int i = startIndex;
                 i < source.Count;
                 i++)
            {
                target.Add(
                    source[i]);
            }
        }


        private void RemoveAdjacentDuplicates(
            List<Point3Mm> points)
        {
            if (points.Count < 2)
            {
                return;
            }


            for (int i = points.Count - 1;
                 i > 0;
                 i--)
            {
                if (Distance(
                        points[i],
                        points[i - 1])
                    <=
                    JoinToleranceMm)
                {
                    points.RemoveAt(
                        i);
                }
            }
        }


        private void CloseLoop(
            List<Point3Mm> points)
        {
            if (points.Count < 3)
            {
                return;
            }


            if (Distance(
                    points[0],
                    points[points.Count - 1])
                >
                JoinToleranceMm)
            {
                points.Add(
                    new Point3Mm
                    {
                        X = points[0].X,
                        Y = points[0].Y,
                        Z = points[0].Z
                    });
            }
        }


        private static double Distance(
            Point3Mm a,
            Point3Mm b)
        {
            double dx =
                a.X - b.X;

            double dy =
                a.Y - b.Y;

            double dz =
                a.Z - b.Z;


            return Math.Sqrt(
                dx * dx +
                dy * dy +
                dz * dz);
        }
    }


    internal class EdgeSampleResult
    {
        public bool Success;

        public string ErrorMessage =
            "";

        public List<Point3Mm> PointsMm =
            new List<Point3Mm>();
    }



    internal class LoopSampleResult
    {
        public bool Success;

        public bool IsOuter;

        public int EdgeSamplingFailures;

        public string ErrorMessage =
            "";

        public List<Point3Mm> PointsMm =
            new List<Point3Mm>();
    }


    internal class Point3Mm
    {
        public double X;

        public double Y;

        public double Z;
    }
}
