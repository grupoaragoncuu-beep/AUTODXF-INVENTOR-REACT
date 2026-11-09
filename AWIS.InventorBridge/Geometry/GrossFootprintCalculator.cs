using System;
using System.Collections.Generic;
using System.Linq;
using AWIS.InventorBridge.FacePreview;
using AWIS.InventorBridge.Models;

namespace AWIS.InventorBridge.Geometry
{
    public static class GrossFootprintCalculator
    {
        private const double PlaneProjectionToleranceMm =
            3.0;


        private const double ParallelDotThreshold =
            0.9995;


        // ============================================================
        // IMPORTANTE
        //
        // Antes agrupábamos TODAS las caras coplanares del assembly.
        //
        // Eso podía convertir varios accesorios dispersos en un
        // footprint artificial enorme.
        //
        // Ahora el grupo pertenece a:
        //
        //      OCCURRENCE + PLANO FÍSICO
        //
        // De esta manera una pared fragmentada dentro de una misma
        // pieza puede reconstruir su footprint, pero no se mezcla
        // con accesorios independientes.
        // ============================================================

        private sealed class PlaneGroup
        {
            public string OccurrencePath { get; set; } =
                string.Empty;


            public double ReferenceProjectionMm
            {
                get;
                set;
            }


            public List<FaceRecord> Faces
            {
                get;
                set;
            } = new();
        }


        // ============================================================
        // BUILD COMPONENT-PLANE FOOTPRINTS
        // ============================================================

        public static List<PlaneFootprint>
            BuildPlaneFootprints(
                List<FaceRecord> allPlanarFaces,
                Vector3Data normalAxis,
                Vector3Data uAxis,
                Vector3Data vAxis)
        {
            Vector3Data normal =
                VectorMath.CanonicalizeAxis(
                    normalAxis);


            Vector3Data u =
                VectorMath.Normalize(
                    uAxis);


            Vector3Data v =
                VectorMath.Normalize(
                    vAxis);


            // ========================================================
            // 1. FIND PARALLEL FACES
            // ========================================================

            List<FaceRecord> parallelFaces =
                allPlanarFaces
                .Where(
                    face =>
                    {
                        Vector3Data faceNormal =
                            VectorMath.CanonicalizeAxis(
                                face.Normal);


                        double dot =
                            Math.Abs(
                                VectorMath.Dot(
                                    faceNormal,
                                    normal));


                        return dot >=
                               ParallelDotThreshold;
                    })
                .ToList();


            if (parallelFaces.Count == 0)
            {
                return new List<PlaneFootprint>();
            }


            // ========================================================
            // 2. GROUP BY OCCURRENCE + PHYSICAL PLANE
            // ========================================================

            List<PlaneGroup> groups =
                BuildOccurrencePlaneGroups(
                    parallelFaces,
                    normal);


            // ========================================================
            // 3. BUILD FOOTPRINTS
            // ========================================================

            List<PlaneFootprint> footprints =
                new();


            foreach (PlaneGroup group
                     in groups)
            {
                PlaneFootprint? footprint =
                    BuildFootprint(
                        group,
                        normal,
                        u,
                        v);


                if (footprint != null)
                {
                    footprints.Add(
                        footprint);
                }
            }


            return footprints
                .OrderBy(
                    footprint =>
                        footprint.ProjectionMm)
                .ToList();
        }


        // ============================================================
        // GROUP BY OCCURRENCE + PLANE
        // ============================================================

        private static List<PlaneGroup>
            BuildOccurrencePlaneGroups(
                List<FaceRecord> parallelFaces,
                Vector3Data normalAxis)
        {
            List<PlaneGroup> groups =
                new();


            foreach (FaceRecord face
                     in parallelFaces)
            {
                double projection =
                    VectorMath.Projection(
                        face.PointMm,
                        normalAxis);


                // ====================================================
                // CRITICAL CORRECTION
                //
                // El OccurrencePath tiene que coincidir.
                //
                // Dos accesorios diferentes que estén sobre el mismo
                // plano ya NO pueden construir juntos un footprint.
                // ====================================================

                PlaneGroup? matchingGroup =
                    groups
                    .FirstOrDefault(
                        group =>
                            group.OccurrencePath ==
                            face.OccurrencePath
                            &&
                            Math.Abs(
                                group.ReferenceProjectionMm -
                                projection)
                            <=
                            PlaneProjectionToleranceMm);


                if (matchingGroup == null)
                {
                    matchingGroup =
                        new PlaneGroup
                        {
                            OccurrencePath =
                                face.OccurrencePath,

                            ReferenceProjectionMm =
                                projection
                        };


                    groups.Add(
                        matchingGroup);
                }


                matchingGroup.Faces.Add(
                    face);


                matchingGroup.ReferenceProjectionMm =
                    matchingGroup.Faces
                    .Average(
                        groupedFace =>
                            VectorMath.Projection(
                                groupedFace.PointMm,
                                normalAxis));
            }


            return groups;
        }


        // ============================================================
        // BUILD ONE OCCURRENCE-PLANE FOOTPRINT
        // ============================================================

        private static PlaneFootprint?
            BuildFootprint(
                PlaneGroup group,
                Vector3Data normalAxis,
                Vector3Data uAxis,
                Vector3Data vAxis)
        {
            if (group.Faces.Count == 0)
            {
                return null;
            }


            List<double> uValues =
                new();


            List<double> vValues =
                new();


            foreach (FaceRecord face
                     in group.Faces)
            {
                foreach (FaceBoundaryPoint point
                         in face.BoundaryPointsMm)
                {
                    uValues.Add(
                        ProjectBoundaryPoint(
                            point,
                            uAxis));


                    vValues.Add(
                        ProjectBoundaryPoint(
                            point,
                            vAxis));
                }
            }


            // ========================================================
            // FALLBACK
            // ========================================================

            if (uValues.Count == 0 ||
                vValues.Count == 0)
            {
                foreach (FaceRecord face
                         in group.Faces)
                {
                    uValues.Add(
                        VectorMath.Projection(
                            face.PointMm,
                            uAxis));


                    vValues.Add(
                        VectorMath.Projection(
                            face.PointMm,
                            vAxis));
                }
            }


            if (uValues.Count == 0 ||
                vValues.Count == 0)
            {
                return null;
            }


            double minU =
                uValues.Min();


            double maxU =
                uValues.Max();


            double minV =
                vValues.Min();


            double maxV =
                vValues.Max();


            double width =
                Math.Abs(
                    maxU -
                    minU);


            double height =
                Math.Abs(
                    maxV -
                    minV);


            double grossArea =
                width *
                height;


            double netArea =
                group.Faces
                .Sum(
                    face =>
                        face.AreaMm2);


            double netMaterialRatio =
                grossArea <=
                0.0
                    ? 0.0
                    : netArea /
                      grossArea;


            FaceRecord representativeFace =
                group.Faces
                .OrderByDescending(
                    face =>
                        face.AreaMm2)
                .First();


            return new PlaneFootprint
            {
                ProjectionMm =
                    group.ReferenceProjectionMm,


                NormalAxis =
                    normalAxis,


                UAxis =
                    uAxis,


                VAxis =
                    vAxis,


                NetAreaMm2 =
                    netArea,


                MinU =
                    minU,


                MaxU =
                    maxU,


                MinV =
                    minV,


                MaxV =
                    maxV,


                WidthMm =
                    width,


                HeightMm =
                    height,


                GrossAreaMm2 =
                    grossArea,


                NetMaterialRatio =
                    netMaterialRatio,


                FaceRecordIndices =
                    group.Faces
                    .Select(
                        face =>
                            face.Index)
                    .Distinct()
                    .ToList(),


                RepresentativeFaceRecordIndex =
                    representativeFace.Index,


                RepresentativeOccurrenceName =
                    representativeFace.OccurrenceName,


                RepresentativeOccurrencePath =
                    representativeFace.OccurrencePath,


                RepresentativeBodyIndex =
                    representativeFace.BodyIndex,


                RepresentativeFaceIndex =
                    representativeFace.FaceIndex
            };
        }


        // ============================================================
        // PROJECT BOUNDARY POINT
        // ============================================================

        private static double ProjectBoundaryPoint(
            FaceBoundaryPoint point,
            Vector3Data axis)
        {
            return
                (point.X * axis.X)
                +
                (point.Y * axis.Y)
                +
                (point.Z * axis.Z);
        }
    }
}