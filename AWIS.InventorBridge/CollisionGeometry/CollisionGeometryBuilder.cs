using Inventor;
using System;
using System.Collections.Generic;
using System.Linq;
using AWIS.InventorBridge.Geometry;
using AWIS.InventorBridge.Models;

namespace AWIS.InventorBridge.CollisionGeometry
{
    /// <summary>
    /// Builds a static collision environment from the active Inventor
    /// assembly. V0.3 preserves the V0.2 adaptive AABB/OBB/cylinder
    /// contract and additionally facets MESH_REQUIRED collision candidates
    /// into a separate runtime payload consumed by CollisionMeshExporter.
    /// Tank boundary source bodies are intentionally not meshed.
    /// </summary>
    public sealed class CollisionGeometryBuilder
    {
        private const double MeshChordToleranceMm = 1.0;

        private int _componentIndex;


        public CollisionGeometryPackage Build(
            AssemblyDocument assemblyDocument,
            TankDetectionResult detection)
        {
            _componentIndex = 0;


            CollisionGeometryPackage package =
                new CollisionGeometryPackage
                {
                    TankName = detection.TankName,
                    DocumentName = assemblyDocument.DisplayName,
                    ExportTime = DateTime.Now
                };


            TankFrameTransform tankFrame =
                BuildTankFrame(
                    detection,
                    package);


            HashSet<string> boundaryOccurrencePaths =
                BuildBoundaryOccurrencePathSet(
                    detection);


            AssemblyComponentDefinition definition =
                assemblyDocument.ComponentDefinition;


            foreach (ComponentOccurrence occurrence
                     in definition.Occurrences)
            {
                ScanOccurrence(
                    occurrence,
                    occurrence.Name,
                    boundaryOccurrencePaths,
                    tankFrame,
                    package);
            }


            return package;
        }


        private void ScanOccurrence(
            ComponentOccurrence occurrence,
            string occurrencePath,
            HashSet<string> boundaryOccurrencePaths,
            TankFrameTransform tankFrame,
            CollisionGeometryPackage package)
        {
            package.Statistics.OccurrencesVisited++;


            if (occurrence.Suppressed)
            {
                package.Statistics.SuppressedOccurrencesSkipped++;
                return;
            }


            if (occurrence.DefinitionDocumentType ==
                DocumentTypeEnum.kPartDocumentObject)
            {
                ExportPartOccurrence(
                    occurrence,
                    occurrencePath,
                    boundaryOccurrencePaths,
                    tankFrame,
                    package);
            }


            foreach (ComponentOccurrence child
                     in occurrence.SubOccurrences)
            {
                string childPath =
                    occurrencePath +
                    "/" +
                    child.Name;


                ScanOccurrence(
                    child,
                    childPath,
                    boundaryOccurrencePaths,
                    tankFrame,
                    package);
            }
        }


        private void ExportPartOccurrence(
            ComponentOccurrence occurrence,
            string occurrencePath,
            HashSet<string> boundaryOccurrencePaths,
            TankFrameTransform tankFrame,
            CollisionGeometryPackage package)
        {
            _componentIndex++;


            bool isBoundarySource =
                boundaryOccurrencePaths.Contains(
                    occurrencePath);


            CollisionComponentRecord component =
                new CollisionComponentRecord
                {
                    ComponentId =
                        $"COMP_{_componentIndex:D6}",

                    OccurrenceName =
                        occurrence.Name,

                    OccurrencePath =
                        occurrencePath,

                    IsTankBoundarySource =
                        isBoundarySource,

                    RoleHint =
                        isBoundarySource
                            ? "TANK_BOUNDARY_SOURCE"
                            : "COLLISION_CANDIDATE"
                };


            int bodyIndex = 0;


            foreach (SurfaceBody body
                     in occurrence.SurfaceBodies)
            {
                bodyIndex++;


                try
                {
                    CollisionBounds3D assemblyBounds =
                        ReadAssemblyRangeBox(
                            body);


                    CollisionOrientedBox3D? assemblyObb =
                        TryReadAssemblyOrientedBox(
                            body);


                    double? volumeMm3 =
                        TryReadVolumeMm3(
                            body);


                    CollisionSurfaceProfile surfaceProfile =
                        ReadSurfaceProfile(
                            body,
                            assemblyObb);


                    CollisionCylinder3D? assemblyCylinder =
                        surfaceProfile.LooksLikeSimpleCylinder
                            ? TryReadAssemblyCylinderEnvelope(
                                body,
                                assemblyObb)
                            : null;


                    CollisionGeometryAssessment assessment =
                        BuildGeometryAssessment(
                            volumeMm3,
                            assemblyObb,
                            surfaceProfile,
                            assemblyCylinder != null);


                    CollisionBodyRecord bodyRecord =
                        new CollisionBodyRecord
                        {
                            BodyIndex =
                                bodyIndex,

                            IsSolid =
                                body.IsSolid,

                            VolumeMm3 =
                                volumeMm3,

                            AssemblyAabbMm =
                                assemblyBounds,

                            AssemblyObbMm =
                                assemblyObb,

                            AssemblyCylinderMm =
                                assemblyCylinder,

                            GeometryAssessment =
                                assessment
                        };


                    if (assemblyObb == null)
                    {
                        bodyRecord.CollisionGeometry =
                            new CollisionGeometryDescriptor
                            {
                                Type = "AABB_BOX",
                                Accuracy = "CONSERVATIVE",
                                Source = "INVENTOR_SURFACE_BODY_PRECISE_RANGE_BOX",
                                BroadPhaseSource = "INVENTOR_SURFACE_BODY_PRECISE_RANGE_BOX",
                                Notes = "Minimum oriented box was unavailable for this body; AWIS must use the precise AABB fallback."
                            };


                        package.Statistics.AabbFallbackBodies++;


                        package.Warnings.Add(
                            $"{occurrencePath} / Body {bodyIndex}: OBB no disponible; se conservó AABB como fallback.");
                    }
                    else if (assemblyCylinder != null)
                    {
                        bodyRecord.CollisionGeometry =
                            new CollisionGeometryDescriptor
                            {
                                Type = "CYLINDER",
                                Accuracy = "CONSERVATIVE_FINITE_CYLINDER_ENVELOPE",
                                Source = "INVENTOR_CYLINDRICAL_FACE_PLUS_OBB_AXIS_EXTENT",
                                BroadPhaseSource = "INVENTOR_SURFACE_BODY_PRECISE_RANGE_BOX",
                                Notes = "Simple cylindrical topology detected. Radius comes from the outer cylindrical face; finite height is conservatively bounded by the body OBB projected onto the cylinder axis."
                            };


                        package.Statistics.CylinderBodies++;
                    }
                    else if (assessment.RecommendedNarrowPhase == "OBB_BOX")
                    {
                        package.Statistics.ObbPreferredBodies++;
                    }
                    else if (assessment.RecommendedNarrowPhase == "MESH_REQUIRED")
                    {
                        package.Statistics.MeshRequiredBodies++;
                    }
                    else
                    {
                        package.Statistics.BodiesWithoutVolumeAssessment++;
                    }


                    if (tankFrame.Resolved)
                    {
                        bodyRecord.TankFrameAabbMm =
                            TransformBoundsToTankFrame(
                                assemblyBounds,
                                tankFrame);


                        if (assemblyObb != null)
                        {
                            bodyRecord.TankFrameObbMm =
                                TransformOrientedBoxToTankFrame(
                                    assemblyObb,
                                    tankFrame);
                        }


                        if (assemblyCylinder != null)
                        {
                            bodyRecord.TankFrameCylinderMm =
                                TransformCylinderToTankFrame(
                                    assemblyCylinder,
                                    tankFrame);
                        }
                    }


                    if (assessment.RecommendedNarrowPhase ==
                        "MESH_REQUIRED")
                    {
                        AttachMeshIfEligible(
                            body,
                            component,
                            bodyRecord,
                            occurrencePath,
                            bodyIndex,
                            isBoundarySource,
                            tankFrame,
                            package);
                    }


                    component.Bodies.Add(
                        bodyRecord);


                    package.Statistics.SurfaceBodiesExported++;
                }
                catch (Exception bodyEx)
                {
                    package.Statistics.BodyFailures++;


                    package.Warnings.Add(
                        $"{occurrencePath} / Body {bodyIndex}: no fue posible exportar la geometría de colisión ({bodyEx.Message}).");
                }
            }


            if (component.Bodies.Count == 0)
            {
                package.Statistics.EmptyPartOccurrencesSkipped++;
                _componentIndex--;
                return;
            }


            component.AssemblyAabbMm =
                UnionBounds(
                    component.Bodies
                    .Select(
                        body =>
                            body.AssemblyAabbMm));


            if (tankFrame.Resolved)
            {
                component.TankFrameAabbMm =
                    UnionBounds(
                        component.Bodies
                        .Where(
                            body =>
                                body.TankFrameAabbMm != null)
                        .Select(
                            body =>
                                body.TankFrameAabbMm!));
            }


            package.Components.Add(
                component);


            package.Statistics.PartOccurrencesExported++;


            if (isBoundarySource)
            {
                package.Statistics.BoundarySourceComponents++;
            }
        }


        private static void AttachMeshIfEligible(
            SurfaceBody body,
            CollisionComponentRecord component,
            CollisionBodyRecord bodyRecord,
            string occurrencePath,
            int bodyIndex,
            bool isBoundarySource,
            TankFrameTransform tankFrame,
            CollisionGeometryPackage package)
        {
            string meshId =
                $"MESH_{component.ComponentId}_BODY_{bodyIndex:D3}";


            if (isBoundarySource)
            {
                bodyRecord.MeshReference =
                    new CollisionMeshReference
                    {
                        MeshId = meshId,
                        Status = "SKIPPED_TANK_BOUNDARY_SOURCE",
                        CoordinateSpace = tankFrame.Resolved
                            ? "TANK_FRAME"
                            : "ASSEMBLY_MODEL_SPACE",
                        Message = "V0.3 intentionally does not facet TANK_BOUNDARY_SOURCE bodies. Conservative AABB/OBB geometry remains available."
                    };


                package.Statistics.MeshSkippedBoundaryBodies++;
                return;
            }


            if (TryBuildCollisionMesh(
                    body,
                    component,
                    bodyIndex,
                    meshId,
                    bodyRecord.AssemblyAabbMm,
                    tankFrame,
                    out CollisionMeshRecord? mesh,
                    out string errorMessage))
            {
                bodyRecord.MeshData =
                    mesh;


                bodyRecord.MeshReference =
                    new CollisionMeshReference
                    {
                        MeshId = mesh!.MeshId,
                        Status = "EXPORTED",
                        CoordinateSpace = mesh.CoordinateSpace,
                        SourceChordToleranceMm = mesh.SourceChordToleranceMm,
                        RequiredCollisionInflationMm = mesh.RequiredCollisionInflationMm,
                        VertexCount = mesh.VertexCount,
                        TriangleCount = mesh.TriangleCount,
                        GenerationMethod = mesh.GenerationMethod,
                        Message = "Mesh payload is stored in the AWIS_COLLISION_MESHES companion. Conservative OBB/AABB remains present in this index as fallback."
                    };


                bodyRecord.CollisionGeometry =
                    new CollisionGeometryDescriptor
                    {
                        Type = "MESH_REFERENCE",
                        Accuracy = "FACETED_CHORD_TOLERANCE_WITH_CONSERVATIVE_OBB_FALLBACK",
                        Source = "INVENTOR_SURFACE_BODY_FACETS",
                        BroadPhaseSource = "INVENTOR_SURFACE_BODY_PRECISE_RANGE_BOX",
                        Notes = "Irregular low-fill collision body. Narrow phase should use MeshReference when available; OBB/AABB remains the conservative fallback."
                    };


                package.Statistics.MeshExportedBodies++;
                package.Statistics.MeshVertexCount +=
                    mesh.VertexCount;
                package.Statistics.MeshTriangleCount +=
                    mesh.TriangleCount;


                if (mesh.GenerationMethod ==
                    "GET_EXISTING_FACETS_FALLBACK")
                {
                    package.Statistics.ExistingFacetFallbackBodies++;
                }


                return;
            }


            bodyRecord.MeshReference =
                new CollisionMeshReference
                {
                    MeshId = meshId,
                    Status = "FAILED",
                    CoordinateSpace = tankFrame.Resolved
                        ? "TANK_FRAME"
                        : "ASSEMBLY_MODEL_SPACE",
                    SourceChordToleranceMm = MeshChordToleranceMm,
                    RequiredCollisionInflationMm = MeshChordToleranceMm,
                    Message = errorMessage
                };


            bodyRecord.CollisionGeometry =
                new CollisionGeometryDescriptor
                {
                    Type = "OBB_BOX_FALLBACK",
                    Accuracy = "CONSERVATIVE_MINIMUM_ORIENTED_BOX",
                    Source = "INVENTOR_SURFACE_BODY_ORIENTED_MINIMUM_RANGE_BOX",
                    BroadPhaseSource = "INVENTOR_SURFACE_BODY_PRECISE_RANGE_BOX",
                    Notes = "MESH_REQUIRED was detected but mesh generation failed. AWIS must use the conservative OBB fallback and must not treat it as exact geometry."
                };


            package.Statistics.MeshFailedBodies++;
            package.Warnings.Add(
                $"{occurrencePath} / Body {bodyIndex}: MESH_REQUIRED pero no fue posible generar la malla ({errorMessage}). Se conservó OBB como fallback.");
        }


        private static bool TryBuildCollisionMesh(
            SurfaceBody body,
            CollisionComponentRecord component,
            int bodyIndex,
            string meshId,
            CollisionBounds3D expectedAssemblyBounds,
            TankFrameTransform tankFrame,
            out CollisionMeshRecord? mesh,
            out string errorMessage)
        {
            mesh = null;
            errorMessage = string.Empty;


            if (!TryGetFacetData(
                    body,
                    MeshChordToleranceMm,
                    out FacetData? facetData,
                    out string facetError))
            {
                errorMessage =
                    facetError;

                return false;
            }


            if (facetData == null ||
                facetData.VertexCoordinates.Length < 9 ||
                facetData.VertexIndices.Length < 3)
            {
                errorMessage =
                    "Inventor returned empty or incomplete facet arrays.";

                return false;
            }


            int vertexCount =
                Math.Min(
                    facetData.VertexCount,
                    facetData.VertexCoordinates.Length / 3);


            int triangleCount =
                Math.Min(
                    facetData.FacetCount,
                    facetData.VertexIndices.Length / 3);


            if (vertexCount <= 0 ||
                triangleCount <= 0)
            {
                errorMessage =
                    "Inventor returned zero vertices or zero triangle facets.";

                return false;
            }


            List<double> vertices =
                new List<double>(
                    vertexCount * 3);


            double minX = double.PositiveInfinity;
            double minY = double.PositiveInfinity;
            double minZ = double.PositiveInfinity;
            double maxX = double.NegativeInfinity;
            double maxY = double.NegativeInfinity;
            double maxZ = double.NegativeInfinity;

            double assemblyMinX = double.PositiveInfinity;
            double assemblyMinY = double.PositiveInfinity;
            double assemblyMinZ = double.PositiveInfinity;
            double assemblyMaxX = double.NegativeInfinity;
            double assemblyMaxY = double.NegativeInfinity;
            double assemblyMaxZ = double.NegativeInfinity;


            for (int i = 0;
                 i < vertexCount;
                 i++)
            {
                Point3Data assemblyPoint =
                    new Point3Data
                    {
                        X = facetData.VertexCoordinates[(i * 3) + 0] * 10.0,
                        Y = facetData.VertexCoordinates[(i * 3) + 1] * 10.0,
                        Z = facetData.VertexCoordinates[(i * 3) + 2] * 10.0
                    };


                assemblyMinX = Math.Min(assemblyMinX, assemblyPoint.X);
                assemblyMinY = Math.Min(assemblyMinY, assemblyPoint.Y);
                assemblyMinZ = Math.Min(assemblyMinZ, assemblyPoint.Z);
                assemblyMaxX = Math.Max(assemblyMaxX, assemblyPoint.X);
                assemblyMaxY = Math.Max(assemblyMaxY, assemblyPoint.Y);
                assemblyMaxZ = Math.Max(assemblyMaxZ, assemblyPoint.Z);


                Point3Data outputPoint =
                    tankFrame.Resolved
                        ? tankFrame.ToTankFrame(
                            assemblyPoint)
                        : assemblyPoint;


                double x = Math.Round(outputPoint.X, 6);
                double y = Math.Round(outputPoint.Y, 6);
                double z = Math.Round(outputPoint.Z, 6);


                vertices.Add(x);
                vertices.Add(y);
                vertices.Add(z);


                minX = Math.Min(minX, x);
                minY = Math.Min(minY, y);
                minZ = Math.Min(minZ, z);
                maxX = Math.Max(maxX, x);
                maxY = Math.Max(maxY, y);
                maxZ = Math.Max(maxZ, z);
            }


            CollisionBounds3D facetedAssemblyBounds =
                CreateBounds(
                    assemblyMinX,
                    assemblyMinY,
                    assemblyMinZ,
                    assemblyMaxX,
                    assemblyMaxY,
                    assemblyMaxZ);


            double boundsToleranceMm =
                Math.Max(
                    2.0,
                    facetData.SourceChordToleranceMm * 2.0);


            if (!BoundsApproximatelyMatch(
                    facetedAssemblyBounds,
                    expectedAssemblyBounds,
                    boundsToleranceMm))
            {
                errorMessage =
                    "Facet coordinate-space sanity check failed: faceted bounds do not match the body Assembly AABB. Conservative OBB fallback retained.";

                return false;
            }


            List<int> indices =
                new List<int>(
                    triangleCount * 3);


            for (int i = 0;
                 i < triangleCount * 3;
                 i++)
            {
                // Inventor facet arrays are one-based. AWIS mesh companion
                // deliberately stores zero-based indices.
                int index =
                    facetData.VertexIndices[i] - 1;


                if (index < 0 ||
                    index >= vertexCount)
                {
                    errorMessage =
                        $"Facet index {facetData.VertexIndices[i]} is outside the vertex range 1..{vertexCount}.";

                    return false;
                }


                indices.Add(index);
            }


            mesh =
                new CollisionMeshRecord
                {
                    MeshId = meshId,
                    ComponentId = component.ComponentId,
                    OccurrenceName = component.OccurrenceName,
                    OccurrencePath = component.OccurrencePath,
                    BodyIndex = bodyIndex,
                    CoordinateSpace = tankFrame.Resolved
                        ? "TANK_FRAME"
                        : "ASSEMBLY_MODEL_SPACE",
                    GenerationMethod = facetData.GenerationMethod,
                    SourceChordToleranceMm = Math.Round(
                        facetData.SourceChordToleranceMm,
                        6),
                    RequiredCollisionInflationMm = Math.Round(
                        facetData.SourceChordToleranceMm,
                        6),
                    VertexCount = vertexCount,
                    TriangleCount = triangleCount,
                    BoundsMm = CreateBounds(
                        minX,
                        minY,
                        minZ,
                        maxX,
                        maxY,
                        maxZ),
                    VerticesMm = vertices,
                    TriangleVertexIndices = indices
                };


            return true;
        }


        private static bool TryGetFacetData(
            SurfaceBody body,
            double requestedToleranceMm,
            out FacetData? data,
            out string errorMessage)
        {
            data = null;
            errorMessage = string.Empty;


            double toleranceCm =
                requestedToleranceMm / 10.0;


            string calculateError =
                string.Empty;


            if (TryCalculateFacetsTyped(
                    body,
                    toleranceCm,
                    out int calculatedVertexCount,
                    out int calculatedFacetCount,
                    out double[] calculatedVertices,
                    out int[] calculatedIndices,
                    out calculateError) ||
                TryInvokeCalculateFacetsDynamic(
                    body,
                    toleranceCm,
                    out calculatedVertexCount,
                    out calculatedFacetCount,
                    out calculatedVertices,
                    out calculatedIndices,
                    out calculateError))
            {
                data =
                    new FacetData
                    {
                        VertexCount = calculatedVertexCount,
                        FacetCount = calculatedFacetCount,
                        VertexCoordinates = calculatedVertices,
                        VertexIndices = calculatedIndices,
                        SourceChordToleranceMm = requestedToleranceMm,
                        GenerationMethod = "CALCULATE_FACETS"
                    };


                return true;
            }


            if (TryGetExistingFacetFallback(
                    body,
                    out data,
                    out string existingError))
            {
                return true;
            }


            errorMessage =
                $"CalculateFacets failed: {calculateError}; existing-facet fallback failed: {existingError}";


            return false;
        }


        private static bool TryCalculateFacetsTyped(
            SurfaceBody body,
            double toleranceCm,
            out int vertexCount,
            out int facetCount,
            out double[] vertexCoordinates,
            out int[] vertexIndices,
            out string errorMessage)
        {
            vertexCount = 0;
            facetCount = 0;
            vertexCoordinates = Array.Empty<double>();
            vertexIndices = Array.Empty<int>();
            errorMessage = string.Empty;


            try
            {
                double[] normals =
                    Array.Empty<double>();


                body.CalculateFacets(
                    toleranceCm,
                    out vertexCount,
                    out facetCount,
                    out vertexCoordinates,
                    out normals,
                    out vertexIndices);


                if (vertexCount <= 0 ||
                    facetCount <= 0 ||
                    vertexCoordinates.Length < vertexCount * 3 ||
                    vertexIndices.Length < facetCount * 3)
                {
                    errorMessage =
                        "Typed CalculateFacets returned arrays that do not match the reported counts.";

                    return false;
                }


                return true;
            }
            catch (Exception ex)
            {
                errorMessage =
                    ex.Message;

                return false;
            }
        }


        private static bool TryInvokeCalculateFacetsDynamic(
            SurfaceBody body,
            double toleranceCm,
            out int vertexCount,
            out int facetCount,
            out double[] vertexCoordinates,
            out int[] vertexIndices,
            out string errorMessage)
        {
            vertexCount = 0;
            facetCount = 0;
            vertexCoordinates = Array.Empty<double>();
            vertexIndices = Array.Empty<int>();
            errorMessage = string.Empty;


            try
            {
                dynamic dynamicBody =
                    body;


                object vertexCoordinatesRaw =
                    Array.Empty<double>();

                object normalVectorsRaw =
                    Array.Empty<double>();

                object vertexIndicesRaw =
                    Array.Empty<int>();


                dynamicBody.CalculateFacets(
                    toleranceCm,
                    out vertexCount,
                    out facetCount,
                    out vertexCoordinatesRaw,
                    out normalVectorsRaw,
                    out vertexIndicesRaw);


                vertexCoordinates =
                    ConvertToDoubleArray(
                        vertexCoordinatesRaw);


                vertexIndices =
                    ConvertToIntArray(
                        vertexIndicesRaw);


                if (vertexCount <= 0 ||
                    facetCount <= 0 ||
                    vertexCoordinates.Length < vertexCount * 3 ||
                    vertexIndices.Length < facetCount * 3)
                {
                    errorMessage =
                        "Facet arrays were returned but their sizes do not match the reported counts.";

                    return false;
                }


                return true;
            }
            catch (Exception ex)
            {
                errorMessage =
                    ex.Message;

                return false;
            }
        }


        private static bool TryGetExistingFacetFallback(
            SurfaceBody body,
            out FacetData? data,
            out string errorMessage)
        {
            data = null;
            errorMessage = string.Empty;


            try
            {
                dynamic dynamicBody =
                    body;


                int toleranceCount =
                    0;

                object tolerancesRaw =
                    Array.Empty<double>();


                dynamicBody.GetExistingFacetTolerances(
                    out toleranceCount,
                    out tolerancesRaw);


                double[] tolerances =
                    ConvertToDoubleArray(
                        tolerancesRaw);


                if (toleranceCount <= 0 ||
                    tolerances.Length == 0)
                {
                    errorMessage =
                        "Inventor has no existing facet sets for this body.";

                    return false;
                }


                double selectedToleranceCm =
                    tolerances
                    .Where(
                        tolerance =>
                            tolerance > 0.0 &&
                            double.IsFinite(tolerance))
                    .DefaultIfEmpty(0.0)
                    .Min();


                if (selectedToleranceCm <= 0.0)
                {
                    errorMessage =
                        "Existing facet tolerance list did not contain a valid positive value.";

                    return false;
                }


                object vertexCoordinatesRaw =
                    Array.Empty<double>();

                object normalVectorsRaw =
                    Array.Empty<double>();

                object vertexIndicesRaw =
                    Array.Empty<int>();

                int vertexCount =
                    0;

                int facetCount =
                    0;


                dynamicBody.GetExistingFacets(
                    selectedToleranceCm,
                    out vertexCount,
                    out facetCount,
                    out vertexCoordinatesRaw,
                    out normalVectorsRaw,
                    out vertexIndicesRaw);


                double[] vertexCoordinates =
                    ConvertToDoubleArray(
                        vertexCoordinatesRaw);


                int[] vertexIndices =
                    ConvertToIntArray(
                        vertexIndicesRaw);


                if (vertexCount <= 0 ||
                    facetCount <= 0 ||
                    vertexCoordinates.Length < vertexCount * 3 ||
                    vertexIndices.Length < facetCount * 3)
                {
                    errorMessage =
                        "Existing facet arrays were returned but their sizes do not match the reported counts.";

                    return false;
                }


                data =
                    new FacetData
                    {
                        VertexCount = vertexCount,
                        FacetCount = facetCount,
                        VertexCoordinates = vertexCoordinates,
                        VertexIndices = vertexIndices,
                        SourceChordToleranceMm = selectedToleranceCm * 10.0,
                        GenerationMethod = "GET_EXISTING_FACETS_FALLBACK"
                    };


                return true;
            }
            catch (Exception ex)
            {
                errorMessage =
                    ex.Message;

                return false;
            }
        }


        private static bool BoundsApproximatelyMatch(
            CollisionBounds3D a,
            CollisionBounds3D b,
            double toleranceMm)
        {
            return
                Math.Abs(a.Min.X - b.Min.X) <= toleranceMm &&
                Math.Abs(a.Min.Y - b.Min.Y) <= toleranceMm &&
                Math.Abs(a.Min.Z - b.Min.Z) <= toleranceMm &&
                Math.Abs(a.Max.X - b.Max.X) <= toleranceMm &&
                Math.Abs(a.Max.Y - b.Max.Y) <= toleranceMm &&
                Math.Abs(a.Max.Z - b.Max.Z) <= toleranceMm;
        }


        private static double[] ConvertToDoubleArray(
            object value)
        {
            if (value is double[] doubles)
            {
                return doubles;
            }


            if (value is Array array)
            {
                double[] result =
                    new double[array.Length];


                for (int i = 0;
                     i < array.Length;
                     i++)
                {
                    result[i] =
                        Convert.ToDouble(
                            array.GetValue(i));
                }


                return result;
            }


            return Array.Empty<double>();
        }


        private static int[] ConvertToIntArray(
            object value)
        {
            if (value is int[] integers)
            {
                return integers;
            }


            if (value is Array array)
            {
                int[] result =
                    new int[array.Length];


                for (int i = 0;
                     i < array.Length;
                     i++)
                {
                    result[i] =
                        Convert.ToInt32(
                            array.GetValue(i));
                }


                return result;
            }


            return Array.Empty<int>();
        }


        private sealed class FacetData
        {
            public int VertexCount { get; set; }

            public int FacetCount { get; set; }

            public double[] VertexCoordinates { get; set; } =
                Array.Empty<double>();

            public int[] VertexIndices { get; set; } =
                Array.Empty<int>();

            public double SourceChordToleranceMm { get; set; }

            public string GenerationMethod { get; set; } =
                string.Empty;
        }


        private static CollisionBounds3D ReadAssemblyRangeBox(
            SurfaceBody body)
        {
            // occurrence.SurfaceBodies provides proxy geometry in the
            // assembly coordinate system, matching the stable scanner.
            Inventor.Box rangeBox =
                body.PreciseRangeBox;


            Point3Data min =
                new Point3Data
                {
                    X = rangeBox.MinPoint.X * 10.0,
                    Y = rangeBox.MinPoint.Y * 10.0,
                    Z = rangeBox.MinPoint.Z * 10.0
                };


            Point3Data max =
                new Point3Data
                {
                    X = rangeBox.MaxPoint.X * 10.0,
                    Y = rangeBox.MaxPoint.Y * 10.0,
                    Z = rangeBox.MaxPoint.Z * 10.0
                };


            return CreateBounds(
                min.X,
                min.Y,
                min.Z,
                max.X,
                max.Y,
                max.Z);
        }


        private static CollisionOrientedBox3D? TryReadAssemblyOrientedBox(
            SurfaceBody body)
        {
            try
            {
                OrientedBox box =
                    body.OrientedMinimumRangeBox;


            Inventor.Point corner =
                box.CornerPoint;

            Inventor.Vector edgeOne =
                box.DirectionOne;

            Inventor.Vector edgeTwo =
                box.DirectionTwo;

            Inventor.Vector edgeThree =
                box.DirectionThree;


                return new CollisionOrientedBox3D
                {
                    Corner =
                        new Point3Data
                        {
                            X = Math.Round(corner.X * 10.0, 6),
                            Y = Math.Round(corner.Y * 10.0, 6),
                            Z = Math.Round(corner.Z * 10.0, 6)
                        },

                    EdgeOne =
                        ToVectorMm(edgeOne),

                    EdgeTwo =
                        ToVectorMm(edgeTwo),

                    EdgeThree =
                        ToVectorMm(edgeThree),

                    EdgeLengthsMm =
                        new Point3Data
                        {
                            X = Math.Round(edgeOne.Length * 10.0, 6),
                            Y = Math.Round(edgeTwo.Length * 10.0, 6),
                            Z = Math.Round(edgeThree.Length * 10.0, 6)
                        }
                };
            }
            catch
            {
                return null;
            }
        }


        private static double? TryReadVolumeMm3(
            SurfaceBody body)
        {
            try
            {
                if (!body.IsSolid)
                {
                    return null;
                }


                // Inventor database length unit is cm, therefore Volume
                // is cm^3. 1 cm^3 = 1000 mm^3.
                // SurfaceBody.Volume is an indexed COM property and
                // requires PrecisionPercent. Autodesk documents 0.01 as
                // a request for approximately 1% relative accuracy.
                return Math.Round(
                    body.Volume[0.01] * 1000.0,
                    6);
            }
            catch
            {
                return null;
            }
        }


        private static CollisionSurfaceProfile ReadSurfaceProfile(
            SurfaceBody body,
            CollisionOrientedBox3D? assemblyObb)
        {
            CollisionSurfaceProfile profile =
                new CollisionSurfaceProfile();


            foreach (Face face
                     in body.Faces)
            {
                profile.TotalFaceCount++;


                if (face.SurfaceType ==
                    SurfaceTypeEnum.kPlaneSurface)
                {
                    profile.PlanarFaceCount++;
                    continue;
                }


                if (face.SurfaceType ==
                    SurfaceTypeEnum.kCylinderSurface)
                {
                    profile.CylindricalFaceCount++;
                    continue;
                }


                profile.OtherFaceCount++;
            }


            profile.HasCylindricalFaces =
                profile.CylindricalFaceCount > 0;


            bool simpleTopology =
                profile.CylindricalFaceCount >= 1 &&
                profile.CylindricalFaceCount <= 2 &&
                profile.PlanarFaceCount <= 2 &&
                profile.OtherFaceCount == 0;


            profile.LooksLikeSimpleCylinder =
                simpleTopology &&
                HasApproximatelyEqualObbPair(
                    assemblyObb);


            return profile;
        }


        private static CollisionGeometryAssessment BuildGeometryAssessment(
            double? volumeMm3,
            CollisionOrientedBox3D? assemblyObb,
            CollisionSurfaceProfile surfaceProfile,
            bool finiteCylinderAvailable)
        {
            CollisionGeometryAssessment result =
                new CollisionGeometryAssessment
                {
                    SurfaceProfile =
                        surfaceProfile
                };


            if (assemblyObb == null)
            {
                result.RecommendedNarrowPhase =
                    "AABB_FALLBACK";

                result.RecommendationReason =
                    "OBB unavailable; use precise AABB conservatively.";

                return result;
            }


            double obbVolume =
                assemblyObb.EdgeLengthsMm.X *
                assemblyObb.EdgeLengthsMm.Y *
                assemblyObb.EdgeLengthsMm.Z;


            if (obbVolume > 0.0)
            {
                result.ObbVolumeMm3 =
                    Math.Round(
                        obbVolume,
                        6);
            }


            if (volumeMm3.HasValue &&
                obbVolume > 0.0)
            {
                double rawFill =
                    volumeMm3.Value /
                    obbVolume;


                double fill =
                    Math.Max(
                        0.0,
                        Math.Min(
                            1.0,
                            rawFill));


                result.FillRatio =
                    Math.Round(
                        fill,
                        6);


                result.FillRatioClass =
                    ClassifyFillRatio(
                        fill);
            }


            if (finiteCylinderAvailable)
            {
                result.RecommendedNarrowPhase =
                    "CYLINDER";

                result.RecommendationReason =
                    "Simple cylindrical topology detected and a finite conservative cylinder envelope was resolved.";

                return result;
            }


            if (!result.FillRatio.HasValue)
            {
                result.RecommendedNarrowPhase =
                    "OBB_BOX";

                result.RecommendationReason =
                    "Volume unavailable; preserve conservative OBB until a richer representation is available.";

                return result;
            }


            if (result.FillRatio.Value >= 0.80)
            {
                result.RecommendedNarrowPhase =
                    "OBB_BOX";

                result.RecommendationReason =
                    "OBB fill ratio is at least 0.80, so the oriented box is considered sufficiently tight for V0.2 narrow phase.";
            }
            else
            {
                result.RecommendedNarrowPhase =
                    "MESH_REQUIRED";

                result.RecommendationReason =
                    "OBB fill ratio is below 0.80 and the body is not a resolved simple cylinder; exact/mesh geometry is recommended to reduce false-positive collisions.";
            }


            return result;
        }


        private static string ClassifyFillRatio(
            double fillRatio)
        {
            if (fillRatio >= 0.95)
            {
                return "VERY_TIGHT";
            }


            if (fillRatio >= 0.80)
            {
                return "TIGHT";
            }


            if (fillRatio >= 0.50)
            {
                return "MODERATE";
            }


            if (fillRatio >= 0.25)
            {
                return "LOOSE";
            }


            return "VERY_LOOSE";
        }


        private static bool HasApproximatelyEqualObbPair(
            CollisionOrientedBox3D? assemblyObb)
        {
            if (assemblyObb == null)
            {
                return false;
            }


            double[] lengths =
            {
                assemblyObb.EdgeLengthsMm.X,
                assemblyObb.EdgeLengthsMm.Y,
                assemblyObb.EdgeLengthsMm.Z
            };


            for (int i = 0; i < lengths.Length; i++)
            {
                for (int j = i + 1; j < lengths.Length; j++)
                {
                    double max =
                        Math.Max(
                            Math.Abs(lengths[i]),
                            Math.Abs(lengths[j]));


                    if (max <= 1e-9)
                    {
                        continue;
                    }


                    double relativeDifference =
                        Math.Abs(lengths[i] - lengths[j]) /
                        max;


                    if (relativeDifference <= 0.05)
                    {
                        return true;
                    }
                }
            }


            return false;
        }


        private static CollisionCylinder3D? TryReadAssemblyCylinderEnvelope(
            SurfaceBody body,
            CollisionOrientedBox3D? assemblyObb)
        {
            if (assemblyObb == null)
            {
                return null;
            }


            try
            {
                Inventor.Cylinder? outerCylinder =
                    null;


                foreach (Face face
                         in body.Faces)
                {
                    if (face.SurfaceType !=
                        SurfaceTypeEnum.kCylinderSurface)
                    {
                        continue;
                    }


                    if (face.Geometry
                        is not Inventor.Cylinder cylinder)
                    {
                        continue;
                    }


                    if (outerCylinder == null ||
                        cylinder.Radius > outerCylinder.Radius)
                    {
                        outerCylinder =
                            cylinder;
                    }
                }


                if (outerCylinder == null)
                {
                    return null;
                }


                Point3Data basePoint =
                    new Point3Data
                    {
                        X = outerCylinder.BasePoint.X * 10.0,
                        Y = outerCylinder.BasePoint.Y * 10.0,
                        Z = outerCylinder.BasePoint.Z * 10.0
                    };


                Vector3Data axis =
                    VectorMath.Normalize(
                        new Vector3Data
                        {
                            X = outerCylinder.AxisVector.X,
                            Y = outerCylinder.AxisVector.Y,
                            Z = outerCylinder.AxisVector.Z
                        });


                List<Point3Data> corners =
                    GetOrientedBoxCorners(
                        assemblyObb);


                double minT =
                    double.PositiveInfinity;

                double maxT =
                    double.NegativeInfinity;


                foreach (Point3Data corner
                         in corners)
                {
                    Vector3Data delta =
                        new Vector3Data
                        {
                            X = corner.X - basePoint.X,
                            Y = corner.Y - basePoint.Y,
                            Z = corner.Z - basePoint.Z
                        };


                    double t =
                        VectorMath.Dot(
                            delta,
                            axis);


                    minT =
                        Math.Min(
                            minT,
                            t);

                    maxT =
                        Math.Max(
                            maxT,
                            t);
                }


                if (!double.IsFinite(minT) ||
                    !double.IsFinite(maxT) ||
                    maxT <= minT)
                {
                    return null;
                }


                Point3Data start =
                    AddScaled(
                        basePoint,
                        axis,
                        minT);


                Point3Data end =
                    AddScaled(
                        basePoint,
                        axis,
                        maxT);


                return new CollisionCylinder3D
                {
                    StartCenter =
                        RoundPoint(
                            start),

                    EndCenter =
                        RoundPoint(
                            end),

                    AxisDirection =
                        RoundVector(
                            axis),

                    RadiusMm =
                        Math.Round(
                            outerCylinder.Radius * 10.0,
                            6),

                    HeightMm =
                        Math.Round(
                            maxT - minT,
                            6),

                    IsConservativeEnvelope =
                        true
                };
            }
            catch
            {
                return null;
            }
        }


        private static List<Point3Data> GetOrientedBoxCorners(
            CollisionOrientedBox3D box)
        {
            List<Point3Data> result =
                new List<Point3Data>();


            for (int a = 0; a <= 1; a++)
            {
                for (int b = 0; b <= 1; b++)
                {
                    for (int c = 0; c <= 1; c++)
                    {
                        result.Add(
                            new Point3Data
                            {
                                X = box.Corner.X +
                                    (a * box.EdgeOne.X) +
                                    (b * box.EdgeTwo.X) +
                                    (c * box.EdgeThree.X),

                                Y = box.Corner.Y +
                                    (a * box.EdgeOne.Y) +
                                    (b * box.EdgeTwo.Y) +
                                    (c * box.EdgeThree.Y),

                                Z = box.Corner.Z +
                                    (a * box.EdgeOne.Z) +
                                    (b * box.EdgeTwo.Z) +
                                    (c * box.EdgeThree.Z)
                            });
                    }
                }
            }


            return result;
        }


        private static CollisionCylinder3D TransformCylinderToTankFrame(
            CollisionCylinder3D assemblyCylinder,
            TankFrameTransform tankFrame)
        {
            Vector3Data axis =
                tankFrame.VectorToTankFrame(
                    assemblyCylinder.AxisDirection);


            axis =
                VectorMath.Normalize(
                    axis);


            return new CollisionCylinder3D
            {
                StartCenter =
                    RoundPoint(
                        tankFrame.ToTankFrame(
                            assemblyCylinder.StartCenter)),

                EndCenter =
                    RoundPoint(
                        tankFrame.ToTankFrame(
                            assemblyCylinder.EndCenter)),

                AxisDirection =
                    RoundVector(
                        axis),

                RadiusMm =
                    assemblyCylinder.RadiusMm,

                HeightMm =
                    assemblyCylinder.HeightMm,

                IsConservativeEnvelope =
                    assemblyCylinder.IsConservativeEnvelope
            };
        }


        private static Point3Data AddScaled(
            Point3Data point,
            Vector3Data direction,
            double scalar)
        {
            return new Point3Data
            {
                X = point.X + (direction.X * scalar),
                Y = point.Y + (direction.Y * scalar),
                Z = point.Z + (direction.Z * scalar)
            };
        }


        private static Point3Data RoundPoint(
            Point3Data point)
        {
            return new Point3Data
            {
                X = Math.Round(point.X, 6),
                Y = Math.Round(point.Y, 6),
                Z = Math.Round(point.Z, 6)
            };
        }


        private static Vector3Data RoundVector(
            Vector3Data vector)
        {
            return new Vector3Data
            {
                X = Math.Round(vector.X, 9),
                Y = Math.Round(vector.Y, 9),
                Z = Math.Round(vector.Z, 9)
            };
        }


        private static CollisionOrientedBox3D TransformOrientedBoxToTankFrame(
            CollisionOrientedBox3D assemblyObb,
            TankFrameTransform tankFrame)
        {
            Vector3Data edgeOne =
                tankFrame.VectorToTankFrame(
                    assemblyObb.EdgeOne);

            Vector3Data edgeTwo =
                tankFrame.VectorToTankFrame(
                    assemblyObb.EdgeTwo);

            Vector3Data edgeThree =
                tankFrame.VectorToTankFrame(
                    assemblyObb.EdgeThree);


            return new CollisionOrientedBox3D
            {
                Corner =
                    tankFrame.ToTankFrame(
                        assemblyObb.Corner),

                EdgeOne =
                    edgeOne,

                EdgeTwo =
                    edgeTwo,

                EdgeThree =
                    edgeThree,

                EdgeLengthsMm =
                    new Point3Data
                    {
                        X = Math.Round(VectorMath.Magnitude(edgeOne), 6),
                        Y = Math.Round(VectorMath.Magnitude(edgeTwo), 6),
                        Z = Math.Round(VectorMath.Magnitude(edgeThree), 6)
                    }
            };
        }


        private static Vector3Data ToVectorMm(
            Inventor.Vector vector)
        {
            return new Vector3Data
            {
                X = Math.Round(vector.X * 10.0, 6),
                Y = Math.Round(vector.Y * 10.0, 6),
                Z = Math.Round(vector.Z * 10.0, 6)
            };
        }


        private static CollisionBounds3D TransformBoundsToTankFrame(
            CollisionBounds3D assemblyBounds,
            TankFrameTransform tankFrame)
        {
            List<Point3Data> corners =
                GetBoundsCorners(
                    assemblyBounds);


            List<Point3Data> transformed =
                corners
                .Select(
                    point =>
                        tankFrame.ToTankFrame(
                            point))
                .ToList();


            return CreateBounds(
                transformed.Min(point => point.X),
                transformed.Min(point => point.Y),
                transformed.Min(point => point.Z),
                transformed.Max(point => point.X),
                transformed.Max(point => point.Y),
                transformed.Max(point => point.Z));
        }


        private static List<Point3Data> GetBoundsCorners(
            CollisionBounds3D bounds)
        {
            return new List<Point3Data>
            {
                new() { X = bounds.Min.X, Y = bounds.Min.Y, Z = bounds.Min.Z },
                new() { X = bounds.Max.X, Y = bounds.Min.Y, Z = bounds.Min.Z },
                new() { X = bounds.Min.X, Y = bounds.Max.Y, Z = bounds.Min.Z },
                new() { X = bounds.Max.X, Y = bounds.Max.Y, Z = bounds.Min.Z },
                new() { X = bounds.Min.X, Y = bounds.Min.Y, Z = bounds.Max.Z },
                new() { X = bounds.Max.X, Y = bounds.Min.Y, Z = bounds.Max.Z },
                new() { X = bounds.Min.X, Y = bounds.Max.Y, Z = bounds.Max.Z },
                new() { X = bounds.Max.X, Y = bounds.Max.Y, Z = bounds.Max.Z }
            };
        }


        private static CollisionBounds3D UnionBounds(
            IEnumerable<CollisionBounds3D> bounds)
        {
            List<CollisionBounds3D> list =
                bounds.ToList();


            if (list.Count == 0)
            {
                return new CollisionBounds3D();
            }


            return CreateBounds(
                list.Min(item => item.Min.X),
                list.Min(item => item.Min.Y),
                list.Min(item => item.Min.Z),
                list.Max(item => item.Max.X),
                list.Max(item => item.Max.Y),
                list.Max(item => item.Max.Z));
        }


        private static CollisionBounds3D CreateBounds(
            double minX,
            double minY,
            double minZ,
            double maxX,
            double maxY,
            double maxZ)
        {
            return new CollisionBounds3D
            {
                Min =
                    new Point3Data
                    {
                        X = Math.Round(minX, 6),
                        Y = Math.Round(minY, 6),
                        Z = Math.Round(minZ, 6)
                    },

                Max =
                    new Point3Data
                    {
                        X = Math.Round(maxX, 6),
                        Y = Math.Round(maxY, 6),
                        Z = Math.Round(maxZ, 6)
                    },

                Center =
                    new Point3Data
                    {
                        X = Math.Round((minX + maxX) / 2.0, 6),
                        Y = Math.Round((minY + maxY) / 2.0, 6),
                        Z = Math.Round((minZ + maxZ) / 2.0, 6)
                    },

                Size =
                    new Point3Data
                    {
                        X = Math.Round(maxX - minX, 6),
                        Y = Math.Round(maxY - minY, 6),
                        Z = Math.Round(maxZ - minZ, 6)
                    }
            };
        }


        private static HashSet<string> BuildBoundaryOccurrencePathSet(
            TankDetectionResult detection)
        {
            HashSet<string> result =
                new HashSet<string>(
                    StringComparer.OrdinalIgnoreCase);


            foreach (TankAxisResult axis
                     in detection.Axes)
            {
                AddBoundaryPath(
                    axis.NegativeBoundary,
                    result);


                AddBoundaryPath(
                    axis.PositiveBoundary,
                    result);
            }


            return result;
        }


        private static void AddBoundaryPath(
            TankBoundaryFace boundary,
            HashSet<string> paths)
        {
            if (!boundary.Detected ||
                string.IsNullOrWhiteSpace(
                    boundary.OccurrencePath))
            {
                return;
            }


            paths.Add(
                boundary.OccurrencePath);
        }


        private static TankFrameTransform BuildTankFrame(
            TankDetectionResult detection,
            CollisionGeometryPackage package)
        {
            TankFrameTransform transform =
                new TankFrameTransform();


            List<TankAxisResult> axes =
                detection.Axes
                .Take(3)
                .ToList();


            foreach (TankAxisResult axis
                     in axes)
            {
                package.CoordinateSystem.TankFrame.Axes.Add(
                    new CollisionFrameAxis
                    {
                        AxisName = axis.AxisName,
                        DirectionAssembly = CopyVector(axis.Direction),
                        NegativePlaneProjectionMm = axis.NegativeBoundary.ProjectionMm,
                        PositivePlaneProjectionMm = axis.PositiveBoundary.ProjectionMm,
                        NegativeBoundaryDetected = axis.NegativeBoundary.Detected,
                        PositiveBoundaryDetected = axis.PositiveBoundary.Detected,
                        SpanMm = axis.SpanMm,
                        SpanConfirmed = axis.SpanConfirmed
                    });
            }


            if (axes.Count != 3)
            {
                package.CoordinateSystem.TankFrame.Status =
                    "UNRESOLVED_AXIS_COUNT";

                package.Warnings.Add(
                    $"Collision Geometry: se requieren 3 ejes para resolver Tank Frame y se encontraron {axes.Count}. Se exportará únicamente AssemblySpace.");

                return transform;
            }


            bool allNegativeBoundariesDetected =
                axes.All(
                    axis =>
                        axis.NegativeBoundary.Detected);


            if (!allNegativeBoundariesDetected)
            {
                package.CoordinateSystem.TankFrame.Status =
                    "UNRESOLVED_MISSING_NEGATIVE_BOUNDARY";

                package.Warnings.Add(
                    "Collision Geometry: falta al menos un límite NEGATIVE del Tank Frame. Se exportará AssemblySpace, pero TankFrameAabbMm quedará sin resolver.");

                return transform;
            }


            try
            {
                transform.Axis1 =
                    VectorMath.Normalize(
                        axes[0].Direction);

                transform.Axis2 =
                    VectorMath.Normalize(
                        axes[1].Direction);

                transform.Axis3 =
                    VectorMath.Normalize(
                        axes[2].Direction);


                transform.Projection1 =
                    axes[0].NegativeBoundary.ProjectionMm;

                transform.Projection2 =
                    axes[1].NegativeBoundary.ProjectionMm;

                transform.Projection3 =
                    axes[2].NegativeBoundary.ProjectionMm;


                transform.Origin =
                    Add(
                        Add(
                            Scale(
                                transform.Axis1,
                                transform.Projection1),

                            Scale(
                                transform.Axis2,
                                transform.Projection2)),

                        Scale(
                            transform.Axis3,
                            transform.Projection3));


                transform.Resolved =
                    true;


                package.CoordinateSystem.TankFrame.Resolved =
                    true;

                package.CoordinateSystem.TankFrame.Status =
                    "RESOLVED_FROM_NEGATIVE_BOUNDARY_PLANES";

                package.CoordinateSystem.TankFrame.OriginAssemblyMm =
                    CopyPoint(
                        transform.Origin);
            }
            catch (Exception frameEx)
            {
                transform =
                    new TankFrameTransform();

                package.CoordinateSystem.TankFrame.Status =
                    "UNRESOLVED_INVALID_AXES";

                package.Warnings.Add(
                    $"Collision Geometry: no fue posible construir Tank Frame ({frameEx.Message}). Se exportará únicamente AssemblySpace.");
            }


            return transform;
        }


        private static Vector3Data Scale(
            Vector3Data vector,
            double scalar)
        {
            return new Vector3Data
            {
                X = vector.X * scalar,
                Y = vector.Y * scalar,
                Z = vector.Z * scalar
            };
        }


        private static Point3Data Add(
            Vector3Data a,
            Vector3Data b)
        {
            return new Point3Data
            {
                X = a.X + b.X,
                Y = a.Y + b.Y,
                Z = a.Z + b.Z
            };
        }


        private static Point3Data Add(
            Point3Data point,
            Vector3Data vector)
        {
            return new Point3Data
            {
                X = point.X + vector.X,
                Y = point.Y + vector.Y,
                Z = point.Z + vector.Z
            };
        }


        private static Vector3Data CopyVector(
            Vector3Data vector)
        {
            return new Vector3Data
            {
                X = vector.X,
                Y = vector.Y,
                Z = vector.Z
            };
        }


        private static Point3Data CopyPoint(
            Point3Data point)
        {
            return new Point3Data
            {
                X = point.X,
                Y = point.Y,
                Z = point.Z
            };
        }


        private sealed class TankFrameTransform
        {
            public bool Resolved { get; set; }

            public Vector3Data Axis1 { get; set; } =
                new();

            public Vector3Data Axis2 { get; set; } =
                new();

            public Vector3Data Axis3 { get; set; } =
                new();

            public double Projection1 { get; set; }

            public double Projection2 { get; set; }

            public double Projection3 { get; set; }

            public Point3Data Origin { get; set; } =
                new();


            public Point3Data ToTankFrame(
                Point3Data point)
            {
                return new Point3Data
                {
                    X =
                        VectorMath.Projection(
                            point,
                            Axis1)
                        -
                        Projection1,

                    Y =
                        VectorMath.Projection(
                            point,
                            Axis2)
                        -
                        Projection2,

                    Z =
                        VectorMath.Projection(
                            point,
                            Axis3)
                        -
                        Projection3
                };
            }


            public Vector3Data VectorToTankFrame(
                Vector3Data vector)
            {
                return new Vector3Data
                {
                    X = Math.Round(VectorMath.Dot(vector, Axis1), 6),
                    Y = Math.Round(VectorMath.Dot(vector, Axis2), 6),
                    Z = Math.Round(VectorMath.Dot(vector, Axis3), 6)
                };
            }
        }
    }
}
