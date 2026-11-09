using Inventor;
using AWIS.InventorBridge.Geometry;
using AWIS.InventorBridge.Models;
using AWIS.InventorBridge.FacePreview;

namespace AWIS.InventorBridge.Services
{
    public static class TankDetectionVisualizer
    {
        private const double ParallelDotThreshold =
            0.9995;


        private const double ProjectionToleranceMm =
            3.0;


        // Solo afecta la visualización.
        // Evita colorear microcaras irrelevantes.
        private const double MinimumVisualFaceAreaMm2 =
            1000.0;


        public static List<HighlightSet> HighlightDetectedTank(
            Inventor.Application inventorApplication,
            AssemblyDocument assemblyDocument,
            TankDetectionResult detection,
            GeometryScanResult scan)
        {
            List<HighlightSet> highlightSets =
                new List<HighlightSet>();


            if (detection.Axes.Count != 3)
            {
                return highlightSets;
            }


            byte[][] axisColors =
            {
                new byte[] { 255, 70, 70 },
                new byte[] { 70, 210, 90 },
                new byte[] { 70, 130, 255 }
            };


            for (int axisIndex = 0;
                 axisIndex < detection.Axes.Count;
                 axisIndex++)
            {
                TankAxisResult axis =
                    detection.Axes[axisIndex];


                HighlightSet highlightSet =
                    assemblyDocument
                    .CreateHighlightSet();


                byte[] rgb =
                    axisColors[axisIndex];


                highlightSet.Color =
                    inventorApplication
                    .TransientObjects
                    .CreateColor(
                        rgb[0],
                        rgb[1],
                        rgb[2]);


                int itemsAdded =
                    0;


                itemsAdded +=
                    AddBoundaryPlaneFaces(
                        highlightSet,
                        assemblyDocument,
                        scan,
                        axis.Direction,
                        axis.NegativeBoundary);


                itemsAdded +=
                    AddBoundaryPlaneFaces(
                        highlightSet,
                        assemblyDocument,
                        scan,
                        axis.Direction,
                        axis.PositiveBoundary);


                if (itemsAdded > 0)
                {
                    highlightSets.Add(
                        highlightSet);
                }
                else
                {
                    highlightSet.Delete();
                }
            }


            return highlightSets;
        }


        // ============================================================
        // ADD COMPLETE STRUCTURAL PLANE
        // ============================================================

        private static int AddBoundaryPlaneFaces(
            HighlightSet highlightSet,
            AssemblyDocument assemblyDocument,
            GeometryScanResult scan,
            Vector3Data axisDirection,
            TankBoundaryFace boundary)
        {
            if (!boundary.Detected)
            {
                return 0;
            }


            int added =
                0;


            foreach (FaceRecord face
                     in scan.PlanarFaces)
            {
                if (face.AreaMm2 <
                    MinimumVisualFaceAreaMm2)
                {
                    continue;
                }


                Vector3Data faceAxis =
                    VectorMath.CanonicalizeAxis(
                        face.Normal);


                double parallelDot =
                    Math.Abs(
                        VectorMath.Dot(
                            faceAxis,
                            axisDirection));


                if (parallelDot <
                    ParallelDotThreshold)
                {
                    continue;
                }


                double projection =
                    VectorMath.Projection(
                        face.PointMm,
                        axisDirection);


                if (Math.Abs(
                        projection -
                        boundary.ProjectionMm)
                    >
                    ProjectionToleranceMm)
                {
                    continue;
                }


                object? inventorFace =
                    ResolveFace(
                        assemblyDocument,
                        face);


                if (inventorFace == null)
                {
                    continue;
                }


                highlightSet.AddItem(
                    inventorFace);


                added++;
            }


            return added;
        }


        // ============================================================
        // RESOLVE FACE RECORD BACK TO INVENTOR
        // ============================================================

        private static object? ResolveFace(
            AssemblyDocument assemblyDocument,
            FaceRecord faceRecord)
        {
            foreach (ComponentOccurrence occurrence
                     in assemblyDocument
                     .ComponentDefinition
                     .Occurrences)
            {
                object? result =
                    FindFaceRecursive(
                        occurrence,
                        occurrence.Name,
                        faceRecord);


                if (result != null)
                {
                    return result;
                }
            }


            return null;
        }


        private static object? FindFaceRecursive(
            ComponentOccurrence occurrence,
            string occurrencePath,
            FaceRecord faceRecord)
        {
            if (occurrence.Suppressed)
            {
                return null;
            }


            if (occurrencePath ==
                faceRecord.OccurrencePath)
            {
                if (occurrence.DefinitionDocumentType !=
                    DocumentTypeEnum.kPartDocumentObject)
                {
                    return null;
                }


                if (faceRecord.BodyIndex < 1 ||
                    faceRecord.BodyIndex >
                    occurrence.SurfaceBodies.Count)
                {
                    return null;
                }


                SurfaceBody body =
                    occurrence.SurfaceBodies[
                        faceRecord.BodyIndex];


                if (faceRecord.FaceIndex < 1 ||
                    faceRecord.FaceIndex >
                    body.Faces.Count)
                {
                    return null;
                }


                return body.Faces[
                    faceRecord.FaceIndex];
            }


            foreach (ComponentOccurrence child
                     in occurrence.SubOccurrences)
            {
                string childPath =
                    occurrencePath +
                    "/" +
                    child.Name;


                object? result =
                    FindFaceRecursive(
                        child,
                        childPath,
                        faceRecord);


                if (result != null)
                {
                    return result;
                }
            }


            return null;
        }
    }
}