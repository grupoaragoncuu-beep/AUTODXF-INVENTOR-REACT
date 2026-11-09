using Inventor;
using System;
using System.Collections.Generic;
using System.Linq;
using AWIS.InventorBridge.Models;

namespace AWIS.InventorBridge.Services
{
    public sealed class InventorGeometryScanner
    {
        private readonly Inventor.Application
            _inventorApplication;


        private readonly GeometryScanResult
            _result =
                new GeometryScanResult();


        private int
            _faceRecordIndex =
                0;


        // ============================================================
        // CONSTRUCTOR
        // ============================================================

        public InventorGeometryScanner(
            Inventor.Application inventorApplication)
        {
            _inventorApplication =
                inventorApplication;
        }


        // ============================================================
        // SCAN ACTIVE ASSEMBLY
        // ============================================================

        public GeometryScanResult ScanActiveAssembly()
        {
            if (_inventorApplication.ActiveDocument == null)
            {
                throw new InvalidOperationException(
                    "No hay ningún documento abierto en Inventor.");
            }


            if (_inventorApplication.ActiveDocument
                is not AssemblyDocument assemblyDocument)
            {
                throw new InvalidOperationException(
                    "El documento activo no es un ensamblaje.");
            }


            _result.DocumentName =
                assemblyDocument.DisplayName;


            _result.DocumentFullPath =
                assemblyDocument.FullFileName
                ??
                string.Empty;


            _result.ScanTime =
                DateTime.Now;


            AssemblyComponentDefinition
                componentDefinition =
                    assemblyDocument
                    .ComponentDefinition;


            foreach (ComponentOccurrence occurrence
                     in componentDefinition.Occurrences)
            {
                ScanOccurrence(
                    occurrence,
                    occurrence.Name);
            }


            _result.PlanarFacesFound =
                _result.PlanarFaces.Count;


            return _result;
        }


        // ============================================================
        // RECURSIVE OCCURRENCE SCAN
        // ============================================================

        private void ScanOccurrence(
            ComponentOccurrence occurrence,
            string occurrencePath)
        {
            if (occurrence.Suppressed)
            {
                return;
            }


            _result.OccurrencesScanned++;


            // ========================================================
            // PART OCCURRENCE
            // ========================================================

            if (occurrence.DefinitionDocumentType ==
                DocumentTypeEnum.kPartDocumentObject)
            {
                ScanPartOccurrence(
                    occurrence,
                    occurrencePath);
            }


            // ========================================================
            // SUBASSEMBLIES / CHILD OCCURRENCES
            // ========================================================

            foreach (ComponentOccurrence child
                     in occurrence.SubOccurrences)
            {
                string childPath =
                    occurrencePath +
                    "/" +
                    child.Name;


                ScanOccurrence(
                    child,
                    childPath);
            }
        }


        // ============================================================
        // SCAN PART GEOMETRY
        // ============================================================

        private void ScanPartOccurrence(
            ComponentOccurrence occurrence,
            string occurrencePath)
        {
            int bodyIndex =
                0;


            foreach (SurfaceBody body
                     in occurrence.SurfaceBodies)
            {
                bodyIndex++;


                int faceIndex =
                    0;


                foreach (Face face
                         in body.Faces)
                {
                    faceIndex++;


                    _result.TotalFacesScanned++;


                    // =================================================
                    // SOLO SUPERFICIES PLANAS
                    // =================================================

                    if (face.SurfaceType !=
                        SurfaceTypeEnum.kPlaneSurface)
                    {
                        continue;
                    }


                    if (face.Geometry
                        is not Inventor.Plane plane)
                    {
                        continue;
                    }


                    // =================================================
                    // AREA
                    //
                    // Inventor:
                    // cm²
                    //
                    // AWIS:
                    // mm²
                    // =================================================

                    double areaCm2 =
                        face.Evaluator.Area;


                    double areaMm2 =
                        areaCm2 *
                        100.0;


                    // =================================================
                    // REPRESENTATIVE POINT
                    //
                    // Inventor:
                    // cm
                    //
                    // AWIS:
                    // mm
                    // =================================================

                    Inventor.Point point =
                        face.PointOnFace;


                    // =================================================
                    // NORMAL
                    // =================================================

                    UnitVector normal =
                        plane.Normal;


                    // =================================================
                    // NEW V0.2B.2 SUPPORT
                    //
                    // Extraemos los puntos reales de los bordes
                    // de la cara para poder calcular posteriormente
                    // su Gross Structural Footprint.
                    //
                    // Esto nos permitirá identificar una pared
                    // completa aunque tenga ventanas grandes.
                    // =================================================

                    List<FaceBoundaryPoint>
                        boundaryPoints =
                            ExtractBoundaryPoints(
                                face);


                    // =================================================
                    // CREATE RECORD
                    // =================================================

                    _faceRecordIndex++;


                    FaceRecord record =
                        new FaceRecord
                        {
                            Index =
                                _faceRecordIndex,


                            OccurrenceName =
                                occurrence.Name,


                            OccurrencePath =
                                occurrencePath,


                            BodyIndex =
                                bodyIndex,


                            FaceIndex =
                                faceIndex,


                            SurfaceType =
                                "plane",


                            AreaMm2 =
                                areaMm2,


                            PointMm =
                                new Point3Data
                                {
                                    X =
                                        point.X *
                                        10.0,

                                    Y =
                                        point.Y *
                                        10.0,

                                    Z =
                                        point.Z *
                                        10.0
                                },


                            Normal =
                                new Vector3Data
                                {
                                    X =
                                        normal.X,

                                    Y =
                                        normal.Y,

                                    Z =
                                        normal.Z
                                },


                            BoundaryPointsMm =
                                boundaryPoints
                        };


                    _result.PlanarFaces.Add(
                        record);
                }
            }
        }


        // ============================================================
        // EXTRACT FACE BOUNDARY POINTS
        //
        // Obtiene StartVertex y StopVertex de todos los edges
        // pertenecientes a la cara.
        //
        // Los puntos quedan guardados en coordenadas del assembly,
        // porque las Face que estamos recorriendo provienen de
        // occurrence.SurfaceBodies.
        // ============================================================

        private static List<FaceBoundaryPoint>
            ExtractBoundaryPoints(
                Face face)
        {
            List<FaceBoundaryPoint> points =
                new List<FaceBoundaryPoint>();


            // Tolerancia para evitar guardar el mismo vértice
            // varias veces cuando pertenece a varios edges.
            const double duplicateToleranceMm =
                0.001;


            foreach (Edge edge
                     in face.Edges)
            {
                AddVertexPoint(
                    edge.StartVertex,
                    points,
                    duplicateToleranceMm);


                AddVertexPoint(
                    edge.StopVertex,
                    points,
                    duplicateToleranceMm);
            }


            return points;
        }


        // ============================================================
        // ADD UNIQUE VERTEX
        // ============================================================

        private static void AddVertexPoint(
            Vertex? vertex,
            List<FaceBoundaryPoint> points,
            double duplicateToleranceMm)
        {
            if (vertex == null)
            {
                return;
            }


            Inventor.Point point =
                vertex.Point;


            // Inventor trabaja internamente en cm.
            // Convertimos a mm.
            double xMm =
                point.X *
                10.0;


            double yMm =
                point.Y *
                10.0;


            double zMm =
                point.Z *
                10.0;


            // ========================================================
            // DUPLICATE CHECK
            // ========================================================

            bool alreadyExists =
                points.Any(
                    existing =>
                        Math.Abs(
                            existing.X -
                            xMm)
                        <=
                        duplicateToleranceMm
                        &&
                        Math.Abs(
                            existing.Y -
                            yMm)
                        <=
                        duplicateToleranceMm
                        &&
                        Math.Abs(
                            existing.Z -
                            zMm)
                        <=
                        duplicateToleranceMm);


            if (alreadyExists)
            {
                return;
            }


            points.Add(
                new FaceBoundaryPoint
                {
                    X =
                        xMm,

                    Y =
                        yMm,

                    Z =
                        zMm
                });
        }
    }
}