using Inventor;
using System;
using System.Collections.Generic;
using System.Linq;

namespace AWIS.InventorBridge.FacePreview
{
    // ================================================================
    // AWIS FACE PREVIEW COMPANION V0.3
    // PLANAR FACE + EDGE LOOP PROJECTOR
    //
    // Principio:
    // - NO recorrer 17k edges para dibujar todo.
    // - Pre-filtrar occurrences por RangeBox.
    // - Buscar caras planas paralelas/cercanas a cada pared.
    // - Elegir la cara/plano de montaje más cercano.
    // - Exportar Outer + Inner EdgeLoops.
    //
    // No crea PlanarSketch físico; por tanto no ensucia ni modifica IPT.
    // ================================================================

    public class FacePreviewLoopProjector
    {
        private const double CmToMm =
            10.0;


        // Componentes cuya caja queda más lejos que esto
        // del plano no se consideran para esa pared.
        private const double ContactDepthMm =
            75.0;


        // Permitimos una pequeña penetración hacia dentro
        // para capturar pared/placa y geometría de contacto.
        private const double InsideDepthMm =
            25.0;


        // Tolerancia lateral para que un componente cerca del borde
        // no desaparezca del preview.
        private const double EnvelopeMarginMm =
            30.0;


        // La cara candidata debe estar casi paralela a la pared.
        // 0.985 ≈ 10 grados.
        private const double MinimumNormalAlignment =
            0.985;


        // Si varias caras están prácticamente en el mismo plano de
        // montaje, conservamos el cluster cercano.
        private const double FaceDepthClusterToleranceMm =
            2.0;


        // Evita exportar basura microscópica.
        private const double MinimumProjectedExtentMm =
            1.0;

        private const double MinimumProjectedAreaMm2 =
            0.5;


        private readonly FacePreviewLoopSampler
            _loopSampler =
                new FacePreviewLoopSampler();


        public void Project(
            AssemblyDocument assembly,
            FacePreviewPackage package)
        {
            List<ComponentOccurrence> occurrences =
                GetAllOccurrences(
                    assembly);


            foreach (ComponentOccurrence occurrence
                     in occurrences)
            {
                package
                    .Statistics
                    .OccurrencesVisited++;


                if (IsSuppressed(
                        occurrence))
                {
                    package
                        .Statistics
                        .SuppressedOccurrencesSkipped++;

                    continue;
                }


                string occurrencePath =
                    BuildOccurrencePath(
                        occurrence);


                foreach (FacePreviewRecord wall
                         in package.Faces)
                {
                    if (!OccurrenceRangeBoxIntersectsWall(
                            occurrence,
                            wall))
                    {
                        package
                            .Statistics
                            .OccurrencesRejectedByRangeBox++;

                        continue;
                    }


                    ProjectOccurrenceToWall(
                        occurrence,
                        occurrencePath,
                        wall,
                        package);
                }
            }
        }


        private void ProjectOccurrenceToWall(
            ComponentOccurrence occurrence,
            string occurrencePath,
            FacePreviewRecord wall,
            FacePreviewPackage package)
        {
            List<PlanarFaceCandidate> candidates =
                new List<PlanarFaceCandidate>();


            try
            {
                SurfaceBodies bodies =
                    occurrence.SurfaceBodies;


                for (int bodyIndex = 1;
                     bodyIndex <= bodies.Count;
                     bodyIndex++)
                {
                    package
                        .Statistics
                        .BodiesVisited++;


                    dynamic body =
                        bodies[bodyIndex];


                    dynamic faces =
                        body.Faces;


                    for (int faceIndex = 1;
                         faceIndex <= faces.Count;
                         faceIndex++)
                    {
                        package
                            .Statistics
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


                        package
                            .Statistics
                            .PlanarFacesConsidered++;


                        Vector3Mm faceNormal =
                            new Vector3Mm
                            {
                                X =
                                    plane.Normal.X,

                                Y =
                                    plane.Normal.Y,

                                Z =
                                    plane.Normal.Z
                            };


                        Vector3Mm wallNormal =
                            FromDto(
                                wall.OutwardNormal);


                        double alignment =
                            Math.Abs(
                                Dot(
                                    Normalize(
                                        faceNormal),
                                    Normalize(
                                        wallNormal)));


                        if (alignment <
                            MinimumNormalAlignment)
                        {
                            package
                                .Statistics
                                .FacesRejectedByOrientation++;

                            continue;
                        }


                        Point3Mm rootPoint =
                            new Point3Mm
                            {
                                X =
                                    plane.RootPoint.X
                                    * CmToMm,

                                Y =
                                    plane.RootPoint.Y
                                    * CmToMm,

                                Z =
                                    plane.RootPoint.Z
                                    * CmToMm
                            };


                        double depthMm =
                            WallDepth(
                                rootPoint,
                                wall);


                        if (depthMm <
                                -InsideDepthMm
                            ||
                            depthMm >
                                ContactDepthMm)
                        {
                            package
                                .Statistics
                                .FacesRejectedByDepth++;

                            continue;
                        }


                        double areaMm2 =
                            0.0;


                        try
                        {
                            areaMm2 =
                                ((double)face.Evaluator.Area)
                                * 100.0;
                        }
                        catch
                        {
                            areaMm2 =
                                0.0;
                        }


                        candidates.Add(
                            new PlanarFaceCandidate
                            {
                                Face =
                                    face,

                                BodyIndex =
                                    bodyIndex,

                                FaceIndex =
                                    faceIndex,

                                DepthMm =
                                    depthMm,

                                AbsoluteDepthMm =
                                    Math.Abs(
                                        depthMm),

                                AreaMm2 =
                                    areaMm2,

                                Alignment =
                                    alignment
                            });
                    }
                }
            }
            catch
            {
                // Subassembly occurrences y ciertos tipos de occurrence
                // no exponen bodies directamente.
                return;
            }


            if (candidates.Count == 0)
            {
                return;
            }


            double nearestAbsoluteDepth =
                candidates.Min(
                    candidate =>
                        candidate.AbsoluteDepthMm);


            List<PlanarFaceCandidate> selectedFaces =
                candidates
                .Where(
                    candidate =>
                        candidate.AbsoluteDepthMm
                        <=
                        nearestAbsoluteDepth
                        +
                        FaceDepthClusterToleranceMm)
                .OrderByDescending(
                    candidate =>
                        candidate.AreaMm2)
                .ToList();


            foreach (PlanarFaceCandidate candidate
                     in selectedFaces)
            {
                package
                    .Statistics
                    .FacesSelected++;


                ExportFaceLoops(
                    occurrence,
                    occurrencePath,
                    wall,
                    candidate,
                    package);
            }
        }


        private void ExportFaceLoops(
            ComponentOccurrence occurrence,
            string occurrencePath,
            FacePreviewRecord wall,
            PlanarFaceCandidate candidate,
            FacePreviewPackage package)
        {
            dynamic edgeLoops;


            try
            {
                edgeLoops =
                    candidate.Face.EdgeLoops;
            }
            catch
            {
                return;
            }


            int loopIndex =
                0;


            foreach (dynamic edgeLoop
                     in edgeLoops)
            {
                loopIndex++;


                package
                    .Statistics
                    .LoopsVisited++;


                LoopSampleResult sample =
                    _loopSampler.SampleLoop(
                        edgeLoop);


                if (!sample.Success)
                {
                    package
                        .Statistics
                        .LoopSamplingFailures++;

                    continue;
                }


                List<Point2Dto> projected =
                    ProjectLoop(
                        sample.PointsMm,
                        wall);


                if (projected.Count < 4)
                {
                    package
                        .Statistics
                        .DegenerateLoopsRejected++;

                    continue;
                }


                LoopMetrics metrics =
                    CalculateMetrics(
                        projected);


                if (metrics.WidthMm <
                        MinimumProjectedExtentMm
                    &&
                    metrics.HeightMm <
                        MinimumProjectedExtentMm)
                {
                    package
                        .Statistics
                        .DegenerateLoopsRejected++;

                    continue;
                }


                if (metrics.AreaMm2 <
                    MinimumProjectedAreaMm2)
                {
                    package
                        .Statistics
                        .DegenerateLoopsRejected++;

                    continue;
                }


                if (!LoopIntersectsEnvelope(
                        metrics,
                        wall))
                {
                    package
                        .Statistics
                        .LoopsRejectedByEnvelope++;

                    continue;
                }


                string loopType =
                    sample.IsOuter
                        ? "OUTER"
                        : "INNER";


                wall.Entities.Add(
                    new PreviewEntity
                    {
                        EntityId =
                            $"{wall.FaceId}_L{wall.Entities.Count + 1:000000}",

                        Role =
                            sample.IsOuter
                                ? "PROJECTED_OUTER_LOOP"
                                : "PROJECTED_INNER_LOOP",

                        LoopType =
                            loopType,

                        OccurrenceName =
                            occurrence.Name,

                        OccurrencePath =
                            occurrencePath,

                        BodyIndex =
                            candidate.BodyIndex,

                        SourceFaceIndex =
                            candidate.FaceIndex,

                        SourceLoopIndex =
                            loopIndex,

                        SourceFaceDepthMm =
                            Math.Round(
                                candidate.DepthMm,
                                3),

                        SourceFaceAreaMm2 =
                            Math.Round(
                                candidate.AreaMm2,
                                3),

                        NormalAlignment =
                            Math.Round(
                                candidate.Alignment,
                                6),

                        ProjectedWidthMm =
                            Math.Round(
                                metrics.WidthMm,
                                3),

                        ProjectedHeightMm =
                            Math.Round(
                                metrics.HeightMm,
                                3),

                        ProjectedAreaMm2 =
                            Math.Round(
                                metrics.AreaMm2,
                                3),

                        Points =
                            projected
                    });


                package
                    .Statistics
                    .LoopsExported++;
            }
        }


        // ============================================================
        // RANGE BOX PREFILTER
        // ============================================================

        private bool OccurrenceRangeBoxIntersectsWall(
            ComponentOccurrence occurrence,
            FacePreviewRecord wall)
        {
            try
            {
                Box rangeBox =
                    occurrence.RangeBox;


                List<Point3Mm> corners =
                    GetBoxCornersMm(
                        rangeBox);


                if (corners.Count == 0)
                {
                    return false;
                }


                double minDepth =
                    double.PositiveInfinity;

                double maxDepth =
                    double.NegativeInfinity;

                double minX =
                    double.PositiveInfinity;

                double maxX =
                    double.NegativeInfinity;

                double minY =
                    double.PositiveInfinity;

                double maxY =
                    double.NegativeInfinity;


                foreach (Point3Mm corner
                         in corners)
                {
                    double depth =
                        WallDepth(
                            corner,
                            wall);


                    Point2Dto p2 =
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

                    minX =
                        Math.Min(
                            minX,
                            p2.X);

                    maxX =
                        Math.Max(
                            maxX,
                            p2.X);

                    minY =
                        Math.Min(
                            minY,
                            p2.Y);

                    maxY =
                        Math.Max(
                            maxY,
                            p2.Y);
                }


                bool depthOverlap =
                    maxDepth >=
                        -InsideDepthMm
                    &&
                    minDepth <=
                        ContactDepthMm;


                if (!depthOverlap)
                {
                    return false;
                }


                EnvelopeBounds wallBounds =
                    GetActiveEnvelopeBounds(
                        wall);


                bool envelopeOverlap =
                    maxX >=
                        wallBounds.MinU
                        -
                        EnvelopeMarginMm
                    &&
                    minX <=
                        wallBounds.MaxU
                        +
                        EnvelopeMarginMm
                    &&
                    maxY >=
                        wallBounds.MinV
                        -
                        EnvelopeMarginMm
                    &&
                    minY <=
                        wallBounds.MaxV
                        +
                        EnvelopeMarginMm;


                return envelopeOverlap;
            }
            catch
            {
                // Si RangeBox no está disponible, preferimos continuar
                // al filtro exacto de faces en lugar de perder geometría.
                return true;
            }
        }


        private List<Point3Mm> GetBoxCornersMm(
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


            return new List<Point3Mm>
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


        // ============================================================
        // CANONICAL 3D -> 2D PROJECTION
        // ============================================================

        private List<Point2Dto> ProjectLoop(
            List<Point3Mm> points,
            FacePreviewRecord wall)
        {
            List<Point2Dto> output =
                new List<Point2Dto>();


            foreach (Point3Mm point
                     in points)
            {
                output.Add(
                    ProjectPoint(
                        point,
                        wall));
            }


            RemoveAdjacentDuplicates(
                output);


            if (output.Count >= 3)
            {
                CloseLoop(
                    output);
            }


            return output;
        }


        private Point2Dto ProjectPoint(
            Point3Mm point,
            FacePreviewRecord wall)
        {
            Vector3Mm origin =
                FromDto(
                    wall.OriginMm);

            Vector3Mm localU =
                FromDto(
                    wall.LocalU);

            Vector3Mm localV =
                FromDto(
                    wall.LocalV);


            Vector3Mm delta =
                new Vector3Mm
                {
                    X =
                        point.X - origin.X,

                    Y =
                        point.Y - origin.Y,

                    Z =
                        point.Z - origin.Z
                };


            return new Point2Dto
            {
                X =
                    Math.Round(
                        Dot(
                            delta,
                            localU),
                        3),

                Y =
                    Math.Round(
                        Dot(
                            delta,
                            localV),
                        3)
            };
        }


        private double WallDepth(
            Point3Mm point,
            FacePreviewRecord wall)
        {
            Vector3Mm origin =
                FromDto(
                    wall.OriginMm);

            Vector3Mm normal =
                FromDto(
                    wall.OutwardNormal);


            Vector3Mm delta =
                new Vector3Mm
                {
                    X =
                        point.X - origin.X,

                    Y =
                        point.Y - origin.Y,

                    Z =
                        point.Z - origin.Z
                };


            return Dot(
                delta,
                normal);
        }


        // ============================================================
        // LOOP METRICS / FILTERS
        // ============================================================

        private LoopMetrics CalculateMetrics(
            List<Point2Dto> points)
        {
            double minX =
                points.Min(
                    p => p.X);

            double maxX =
                points.Max(
                    p => p.X);

            double minY =
                points.Min(
                    p => p.Y);

            double maxY =
                points.Max(
                    p => p.Y);


            double signedAreaTwice =
                0.0;


            for (int i = 0;
                 i < points.Count - 1;
                 i++)
            {
                signedAreaTwice +=
                    points[i].X
                    *
                    points[i + 1].Y
                    -
                    points[i + 1].X
                    *
                    points[i].Y;
            }


            return new LoopMetrics
            {
                MinX =
                    minX,

                MaxX =
                    maxX,

                MinY =
                    minY,

                MaxY =
                    maxY,

                WidthMm =
                    maxX - minX,

                HeightMm =
                    maxY - minY,

                AreaMm2 =
                    Math.Abs(
                        signedAreaTwice)
                    /
                    2.0
            };
        }


        private bool LoopIntersectsEnvelope(
            LoopMetrics metrics,
            FacePreviewRecord wall)
        {
            EnvelopeBounds wallBounds =
                GetActiveEnvelopeBounds(
                    wall);


            return
                metrics.MaxX >=
                    wallBounds.MinU
                    -
                    EnvelopeMarginMm
                &&
                metrics.MinX <=
                    wallBounds.MaxU
                    +
                    EnvelopeMarginMm
                &&
                metrics.MaxY >=
                    wallBounds.MinV
                    -
                    EnvelopeMarginMm
                &&
                metrics.MinY <=
                    wallBounds.MaxV
                    +
                    EnvelopeMarginMm;
        }



        private EnvelopeBounds GetActiveEnvelopeBounds(
            FacePreviewRecord wall)
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
                return new EnvelopeBounds
                {
                    MinU =
                        wall.PhysicalWall.Bounds.MinU,

                    MaxU =
                        wall.PhysicalWall.Bounds.MaxU,

                    MinV =
                        wall.PhysicalWall.Bounds.MinV,

                    MaxV =
                        wall.PhysicalWall.Bounds.MaxV
                };
            }


            return new EnvelopeBounds
            {
                MinU = 0.0,
                MaxU = wall.WidthMm,
                MinV = 0.0,
                MaxV = wall.HeightMm
            };
        }


        private void RemoveAdjacentDuplicates(
            List<Point2Dto> points)
        {
            const double toleranceMm =
                0.02;


            for (int i = points.Count - 1;
                 i > 0;
                 i--)
            {
                if (Distance2D(
                        points[i],
                        points[i - 1])
                    <=
                    toleranceMm)
                {
                    points.RemoveAt(
                        i);
                }
            }
        }


        private void CloseLoop(
            List<Point2Dto> points)
        {
            const double toleranceMm =
                0.05;


            if (Distance2D(
                    points[0],
                    points[points.Count - 1])
                >
                toleranceMm)
            {
                points.Add(
                    new Point2Dto
                    {
                        X =
                            points[0].X,

                        Y =
                            points[0].Y
                    });
            }
        }


        // ============================================================
        // OCCURRENCE TRAVERSAL
        // ============================================================

        private List<ComponentOccurrence> GetAllOccurrences(
            AssemblyDocument assembly)
        {
            List<ComponentOccurrence> result =
                new List<ComponentOccurrence>();


            foreach (ComponentOccurrence occurrence
                     in assembly
                     .ComponentDefinition
                     .Occurrences)
            {
                AddOccurrenceRecursive(
                    occurrence,
                    result);
            }


            return result;
        }


        private void AddOccurrenceRecursive(
            ComponentOccurrence occurrence,
            List<ComponentOccurrence> result)
        {
            result.Add(
                occurrence);


            try
            {
                foreach (ComponentOccurrence child
                         in occurrence.SubOccurrences)
                {
                    AddOccurrenceRecursive(
                        child,
                        result);
                }
            }
            catch
            {
                // Part occurrence sin hijos.
            }
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


        private string BuildOccurrencePath(
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


        // ============================================================
        // HELPERS
        // ============================================================

        private static Point3Mm NewPoint(
            double x,
            double y,
            double z)
        {
            return new Point3Mm
            {
                X = x,
                Y = y,
                Z = z
            };
        }


        private static Vector3Mm FromDto(
            Vector3Dto dto)
        {
            return new Vector3Mm
            {
                X = dto.X,
                Y = dto.Y,
                Z = dto.Z
            };
        }


        private static double Dot(
            Vector3Mm a,
            Vector3Mm b)
        {
            return
                a.X * b.X
                +
                a.Y * b.Y
                +
                a.Z * b.Z;
        }


        private static double Length(
            Vector3Mm vector)
        {
            return Math.Sqrt(
                Dot(
                    vector,
                    vector));
        }


        private static Vector3Mm Normalize(
            Vector3Mm vector)
        {
            double length =
                Length(
                    vector);


            if (length < 1e-12)
            {
                return vector;
            }


            return new Vector3Mm
            {
                X =
                    vector.X / length,

                Y =
                    vector.Y / length,

                Z =
                    vector.Z / length
            };
        }


        private static double Distance2D(
            Point2Dto a,
            Point2Dto b)
        {
            double dx =
                a.X - b.X;

            double dy =
                a.Y - b.Y;


            return Math.Sqrt(
                dx * dx +
                dy * dy);
        }


        private class EnvelopeBounds
        {
            public double MinU;

            public double MaxU;

            public double MinV;

            public double MaxV;
        }


        private class PlanarFaceCandidate
        {
            public dynamic Face =
                null!;

            public int BodyIndex;

            public int FaceIndex;

            public double DepthMm;

            public double AbsoluteDepthMm;

            public double AreaMm2;

            public double Alignment;
        }


        private class Vector3Mm
        {
            public double X;

            public double Y;

            public double Z;
        }


        private class LoopMetrics
        {
            public double MinX;

            public double MaxX;

            public double MinY;

            public double MaxY;

            public double WidthMm;

            public double HeightMm;

            public double AreaMm2;
        }
    }
}
