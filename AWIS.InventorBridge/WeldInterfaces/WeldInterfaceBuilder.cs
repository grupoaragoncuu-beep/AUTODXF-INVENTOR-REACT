using Inventor;
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using AWIS.InventorBridge.FacePreview;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // ================================================================
    // V1.1-A / V0.3.4
    // PACKAGE BUILDER
    //
    // Consume:
    //   - AssemblyDocument ya abierto en Inventor
    //   - AWIS_TANK_DETECTION
    //   - AWIS_FACE_PREVIEWS V0.4.0
    //
    // NO vuelve a detectar el tanque.
    // NO modifica Face Preview.
    // ================================================================

    public class WeldInterfaceBuilder
    {
        private readonly WeldInterfaceBroadPhase
            _broadPhase =
                new WeldInterfaceBroadPhase();


        private readonly WeldInterfaceExactDetector
            _exactDetector =
                new WeldInterfaceExactDetector();


        private readonly WeldPhysicalBoundarySelector
            _physicalBoundarySelector =
                new WeldPhysicalBoundarySelector();


        public WeldInterfacePackage Build(
            AssemblyDocument assembly,
            string tankDetectionPath,
            string facePreviewPath)
        {
            FacePreviewPackage preview =
                ReadPreview(
                    facePreviewPath);


            WeldInterfacePackage package =
                new WeldInterfacePackage
                {
                    TankName =
                        preview.TankName,

                    DocumentName =
                        preview.DocumentName,

                    Sources =
                        new WeldInterfaceSourceInfo
                        {
                            TankDetectionFile =
                                System.IO.Path.GetFileName(
                                    tankDetectionPath),

                            TankDetectionSha256 =
                                ComputeSha256(
                                    tankDetectionPath),

                            FacePreviewFile =
                                System.IO.Path.GetFileName(
                                    facePreviewPath),

                            FacePreviewSha256 =
                                ComputeSha256(
                                    facePreviewPath),

                            FacePreviewSchema =
                                preview.Schema,

                            FacePreviewVersion =
                                preview.Version
                        }
                };


            if (string.IsNullOrWhiteSpace(
                    package.TankName)
                ||
                string.IsNullOrWhiteSpace(
                    package.DocumentName))
            {
                FillIdentityFromDetection(
                    tankDetectionPath,
                    package);
            }


            HashSet<string> structuralPaths =
                BuildStructuralOccurrenceSet(
                    preview);


            foreach (FacePreviewRecord sourceFace
                     in preview.Faces)
            {
                WeldInterfaceFaceRecord wall =
                    ConvertFace(
                        sourceFace);


                package.Faces.Add(
                    wall);


                package.Statistics.StructuralWallSegmentsImported +=
                    wall.PhysicalWall.Segments.Count;

                package.Statistics.StructuralSeamsImported +=
                    wall.PhysicalWall.StructuralSeams.Count;


                if (!wall.PhysicalWall.Resolved)
                {
                    package.Warnings.Add(
                        $"{wall.FaceId}: Weld Interfaces V0.3.4 usa CanonicalEnvelope como fallback porque PhysicalWall no fue resuelto.");
                }
            }


            List<ComponentOccurrence> occurrences =
                _broadPhase
                    .GetLeafOccurrences(
                        assembly,
                        package.Statistics);


            Inventor.Application inventorApplication =
                (Inventor.Application)
                assembly
                    .ComponentDefinition
                    .Application;


            foreach (WeldInterfaceFaceRecord wall
                     in package.Faces)
            {
                WeldContactPlaneResolver.Resolve(wall, occurrences, package.Warnings);

                package
                    .Statistics
                    .FacesProcessed++;


                List<WeldBroadPhaseCandidate> candidates =
                    _broadPhase
                        .FindCandidatesForWall(
                            occurrences,
                            wall,
                            structuralPaths,
                            package.Thresholds,
                            package.Statistics);


                foreach (WeldBroadPhaseCandidate candidate
                         in candidates)
                {
                    WeldInterfaceRecord? interfaceRecord =
                        _exactDetector
                            .Analyze(
                                inventorApplication,
                                candidate,
                                wall,
                                package.Thresholds,
                                package.Statistics);


                    if (interfaceRecord == null)
                    {
                        continue;
                    }


                    interfaceRecord.SurfaceId = wall.FaceId;
                    interfaceRecord.SurfaceSide = "EXTERIOR";
                    interfaceRecord.InterfaceId =
                        $"{wall.FaceId}_IF{wall.Interfaces.Count + 1:00000}";


                    for (int pathIndex = 0;
                         pathIndex <
                         interfaceRecord.Paths.Count;
                         pathIndex++)
                    {
                        interfaceRecord
                            .Paths[pathIndex]
                            .PathId =
                                $"{interfaceRecord.InterfaceId}_P{pathIndex + 1:000}";
                    }


                    wall.Interfaces.Add(
                        interfaceRecord);
                }


                // V0.3.4:
                // Preserve V0.3.3 brace/frame physical weld-edge cleanup only after all
                // component interfaces on this wall are available. The rule
                // is group-aware (same parent occurrence) and never invents
                // a paired member: it only converts validated narrow CLOSED
                // strips into one external physical weld edge per side.
                _physicalBoundarySelector
                    .Apply(
                        wall,
                        package.Thresholds,
                        package.Statistics,
                        package.Warnings);


                // Face Preview already resolved manufacturing seams between
                // coplanar physical wall segments. Promote those seams into
                // the standard Interfaces[] contract AFTER regular interfaces
                // so existing IF numbering remains stable.
                AppendStructuralSeamCandidates(
                    wall,
                    package.Statistics,
                    package.Warnings);
            }


            if (package.Thresholds.ExportSegmentSurfaceVariants)
            {
                new WeldSurfaceVariantBuilder().Build(package, occurrences, inventorApplication, structuralPaths);
            }

            if (package
                .Statistics
                .ExactAnalysisFailures > 0)
            {
                package.Warnings.Add(
                    "One or more exact interface checks raised an exception. Review AMBIGUOUS interfaces and Statistics.ExactAnalysisFailures.");
            }


            if (package
                .Statistics
                .EdgeSamplingFailures > 0)
            {
                package.Warnings.Add(
                    "Some Inventor edges could not be sampled. Resolved interfaces remain usable, but missing paths may appear as AMBIGUOUS.");
            }


            if (package
                .Statistics
                .SectionFailures > 0)
            {
                package.Warnings.Add(
                    "One or more B-Rep plane section attempts failed. Review Statistics.SectionFailures and unresolved INTERSECTING/AMBIGUOUS records.");
            }


            if (package.Statistics.InnerCoincidentFaceLoopsSuppressed > 0
                ||
                package.Statistics.NestedSectionWiresSuppressed > 0)
            {
                package.Warnings.Add(
                    "V0.3.4 physical-boundary filter removed internal/void contours before weld-candidate export. Review BoundaryFilter and BoundaryRole metadata when validating hollow members.");
            }


            if (package.Statistics.BraceFrameGroupsResolved > 0)
            {
                package.Warnings.Add(
                    $"V0.3.4 brace-frame selector resolved {package.Statistics.BraceFrameGroupsResolved} frame group(s) and converted {package.Statistics.BraceFrameClosedLoopsConverted} narrow closed loops into one external weld edge per physical side. Paired-member grouping remains a downstream decision.");
            }


            if (package.Statistics.AnnularSectionWiresResolved > 0)
            {
                package.Warnings.Add(
                    $"V0.3.5 annular-section selector resolved {package.Statistics.AnnularSectionWiresResolved} B-Rep annular wire(s) and suppressed {package.Statistics.AnnularSectionPathsSuppressed} inner/connector section path(s); each resolved wire now exports one reconstructed 360-degree outer circumference.");
            }


            return package;
        }


        private FacePreviewPackage ReadPreview(
            string facePreviewPath)
        {
            string json =
                System.IO.File.ReadAllText(
                    facePreviewPath);


            FacePreviewPackage? package =
                JsonSerializer
                    .Deserialize<FacePreviewPackage>(
                        json);


            if (package == null)
            {
                throw new InvalidOperationException(
                    "AWIS_FACE_PREVIEWS could not be deserialized.");
            }


            if (!string.Equals(
                    package.Schema,
                    "AWIS_FACE_PREVIEWS",
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(
                    "The supplied preview JSON is not AWIS_FACE_PREVIEWS.");
            }


            if (package.Faces.Count == 0)
            {
                throw new InvalidOperationException(
                    "AWIS_FACE_PREVIEWS contains no structural faces.");
            }


            return package;
        }


        private HashSet<string> BuildStructuralOccurrenceSet(
            FacePreviewPackage preview)
        {
            HashSet<string> result =
                new HashSet<string>(
                    StringComparer.OrdinalIgnoreCase);


            foreach (FacePreviewRecord face
                     in preview.Faces)
            {
                string path =
                    face
                        .DetectionSource
                        .OccurrencePath;


                if (!string.IsNullOrWhiteSpace(
                        path))
                {
                    result.Add(
                        path);
                }


                if (face.PhysicalWall?.Segments == null)
                {
                    continue;
                }


                foreach (PhysicalWallSegment segment
                         in face.PhysicalWall.Segments)
                {
                    if (!string.IsNullOrWhiteSpace(
                            segment.OccurrencePath))
                    {
                        result.Add(
                            segment.OccurrencePath);
                    }
                }
            }


            return result;
        }


        private WeldPhysicalWallGeometry ConvertPhysicalWall(
            FacePreviewRecord face)
        {
            PhysicalWallGeometry source =
                face.PhysicalWall
                ??
                new PhysicalWallGeometry();


            WeldPhysicalWallGeometry result =
                new WeldPhysicalWallGeometry
                {
                    Resolved =
                        source.Resolved,

                    ResolutionStatus =
                        source.ResolutionStatus ?? ""
                };


            if (source.Bounds != null)
            {
                result.Bounds =
                    new WeldPhysicalWallBounds
                    {
                        MinU = source.Bounds.MinU,
                        MaxU = source.Bounds.MaxU,
                        MinV = source.Bounds.MinV,
                        MaxV = source.Bounds.MaxV,
                        WidthMm = source.Bounds.WidthMm,
                        HeightMm = source.Bounds.HeightMm
                    };
            }


            if (source.OuterLoop != null)
            {
                foreach (Point2Dto point
                         in source.OuterLoop)
                {
                    result.OuterLoop.Add(
                        new WeldPoint2Mm
                        {
                            X = point.X,
                            Y = point.Y
                        });
                }
            }


            result.SegmentCount =
                source.Segments?.Count
                ??
                source.SegmentCount;


            if (source.Segments != null)
            {
                foreach (PhysicalWallSegment segment
                         in source.Segments)
                {
                    WeldPhysicalWallSegment target =
                        new WeldPhysicalWallSegment
                        {
                            SegmentId = segment.SegmentId,
                            IsAnchorSegment = segment.IsAnchorSegment,
                            OccurrenceName = segment.OccurrenceName,
                            OccurrencePath = segment.OccurrencePath,
                            SourceBodyIndex = segment.SourceBodyIndex,
                            SourceFaceIndex = segment.SourceFaceIndex,
                            SourceLoopIndex = segment.SourceLoopIndex,
                            SourceFaceDepthMm = segment.SourceFaceDepthMm,
                            ProjectedAreaMm2 = segment.ProjectedAreaMm2,
                            Bounds = new WeldPhysicalWallBounds
                            {
                                MinU = segment.Bounds.MinU,
                                MaxU = segment.Bounds.MaxU,
                                MinV = segment.Bounds.MinV,
                                MaxV = segment.Bounds.MaxV,
                                WidthMm = segment.Bounds.WidthMm,
                                HeightMm = segment.Bounds.HeightMm
                            }
                        };


                    if (segment.OuterLoop != null)
                    {
                        foreach (Point2Dto point
                                 in segment.OuterLoop)
                        {
                            target.OuterLoop.Add(
                                new WeldPoint2Mm
                                {
                                    X = point.X,
                                    Y = point.Y
                                });
                        }
                    }


                    result.Segments.Add(
                        target);
                }
            }


            if (source.StructuralSeams != null)
            {
                foreach (StructuralSeam seam
                         in source.StructuralSeams)
                {
                    WeldStructuralSeam target =
                        new WeldStructuralSeam
                        {
                            SeamId = seam.SeamId,
                            SegmentAId = seam.SegmentAId,
                            SegmentBId = seam.SegmentBId,
                            SeparationAxis = seam.SeparationAxis,
                            GapMm = seam.GapMm,
                            LengthMm = seam.LengthMm,
                            Classification = seam.Classification,
                            WeldClassification = seam.WeldClassification,
                            DetectionStatus = seam.DetectionStatus
                        };


                    if (seam.FaceLocalCenterline != null)
                    {
                        foreach (Point2Dto point
                                 in seam.FaceLocalCenterline)
                        {
                            target.FaceLocalCenterline.Add(
                                new WeldPoint2Mm
                                {
                                    X = point.X,
                                    Y = point.Y
                                });
                        }
                    }


                    result.StructuralSeams.Add(
                        target);
                }
            }


            return result;
        }


        private WeldInterfaceFaceRecord ConvertFace(
            FacePreviewRecord face)
        {
            return new WeldInterfaceFaceRecord
            {
                FaceId =
                    face.FaceId,

                AxisName =
                    face.AxisName,

                Side =
                    face.Side,

                WidthMm =
                    face.WidthMm,

                HeightMm =
                    face.HeightMm,

                PhysicalWall =
                    ConvertPhysicalWall(
                        face),

                OriginMm =
                    new WeldPoint3Mm
                    {
                        X =
                            face.OriginMm.X,

                        Y =
                            face.OriginMm.Y,

                        Z =
                            face.OriginMm.Z
                    },

                OutwardNormal =
                    new WeldVector3
                    {
                        X =
                            face.OutwardNormal.X,

                        Y =
                            face.OutwardNormal.Y,

                        Z =
                            face.OutwardNormal.Z
                    },

                LocalU =
                    new WeldVector3
                    {
                        X =
                            face.LocalU.X,

                        Y =
                            face.LocalU.Y,

                        Z =
                            face.LocalU.Z
                    },

                LocalV =
                    new WeldVector3
                    {
                        X =
                            face.LocalV.X,

                        Y =
                            face.LocalV.Y,

                        Z =
                            face.LocalV.Z
                    },

                StructuralSource =
                    new WeldStructuralSource
                    {
                        OccurrenceName =
                            face
                                .DetectionSource
                                .OccurrenceName,

                        OccurrencePath =
                            face
                                .DetectionSource
                                .OccurrencePath,

                        BodyIndex =
                            face
                                .DetectionSource
                                .BodyIndex,

                        FaceIndex =
                            face
                                .DetectionSource
                                .FaceIndex,

                        FaceRecordIndex =
                            face
                                .DetectionSource
                                .FaceRecordIndex
                    }
            };
        }


        private static void AppendStructuralSeamCandidates(
            WeldInterfaceFaceRecord wall,
            WeldInterfaceStatistics statistics,
            List<string> warnings)
        {
            if (wall.PhysicalWall == null
                ||
                wall.PhysicalWall.StructuralSeams == null
                ||
                wall.PhysicalWall.StructuralSeams.Count == 0)
            {
                return;
            }


            foreach (WeldStructuralSeam seam
                     in wall.PhysicalWall.StructuralSeams)
            {
                if (!string.Equals(
                        seam.DetectionStatus,
                        "GEOMETRY_DETECTED",
                        StringComparison.OrdinalIgnoreCase)
                    ||
                    seam.FaceLocalCenterline == null
                    ||
                    seam.FaceLocalCenterline.Count < 2
                    ||
                    seam.LengthMm <= 0.0)
                {
                    warnings.Add(
                        $"{wall.FaceId}: structural seam '{seam.SeamId}' was not promoted to Interfaces[] because its geometry is incomplete.");

                    continue;
                }


                WeldInterfaceRecord interfaceRecord =
                    new WeldInterfaceRecord
                    {
                        InterfaceId =
                            $"{wall.FaceId}_IF{wall.Interfaces.Count + 1:00000}",

                        CandidateKind =
                            "STRUCTURAL_SEAM",

                        FaceId =
                            wall.FaceId,

                        StructuralSeamId =
                            seam.SeamId,

                        SegmentAId =
                            seam.SegmentAId,

                        SegmentBId =
                            seam.SegmentBId,

                        Classification =
                            seam.Classification,

                        WeldClassification =
                            seam.WeldClassification,

                        DetectionStatus =
                            seam.DetectionStatus,

                        GapMm =
                            seam.GapMm,

                        // Synthetic source identity: this candidate is not an
                        // accessory occurrence. The explicit CandidateKind and
                        // StructuralSeamId are the authoritative identity.
                        ComponentOccurrenceName =
                            seam.SeamId,

                        ComponentOccurrencePath =
                            $"STRUCTURAL_SEAM/{wall.FaceId}/{seam.SeamId}",

                        IsStructuralBoundaryComponent =
                            false,

                        ContactState =
                            "STRUCTURAL_SEAM",

                        ContactDetected =
                            true,

                        ContactGeometryResolved =
                            true,

                        ResolutionStatus =
                            "resolved_structural_seam_from_face_preview",

                        MinimumPlaneDistanceMm =
                            0.0,

                        CoincidentAreaMetricMm2 =
                            0.0,

                        UnresolvedPlaneCrossingPointCount =
                            0
                    };


                interfaceRecord.Evidence.Add(
                    "face_preview_structural_seam");

                interfaceRecord.Evidence.Add(
                    "panel_to_panel_centerline_resolved");


                WeldInterfacePath path =
                    new WeldInterfacePath
                    {
                        PathId =
                            $"{interfaceRecord.InterfaceId}_P001",

                        SourceKind =
                            "STRUCTURAL_SEAM_CENTERLINE",

                        GeometryType =
                            "LINEAR",

                        Closed =
                            false,

                        ClippedToWallEnvelope =
                            false,

                        LengthMm =
                            seam.LengthMm
                    };


                foreach (WeldPoint2Mm point
                         in seam.FaceLocalCenterline)
                {
                    path.FaceLocalPointsMm.Add(
                        new WeldPoint2Mm
                        {
                            X = point.X,
                            Y = point.Y
                        });


                    path.Model3DPointsMm.Add(
                        FaceLocalToModel(
                            wall,
                            point));
                }


                interfaceRecord.Paths.Add(
                    path);

                wall.Interfaces.Add(
                    interfaceRecord);

                statistics.StructuralSeamCandidatesExported++;
                statistics.InterfacesExported++;
                statistics.InterfacePathsResolved++;
            }
        }


        private static WeldPoint3Mm FaceLocalToModel(
            WeldInterfaceFaceRecord wall,
            WeldPoint2Mm point)
        {
            return new WeldPoint3Mm
            {
                X =
                    wall.OriginMm.X
                    +
                    wall.LocalU.X * point.X
                    +
                    wall.LocalV.X * point.Y,

                Y =
                    wall.OriginMm.Y
                    +
                    wall.LocalU.Y * point.X
                    +
                    wall.LocalV.Y * point.Y,

                Z =
                    wall.OriginMm.Z
                    +
                    wall.LocalU.Z * point.X
                    +
                    wall.LocalV.Z * point.Y
            };
        }


        private void FillIdentityFromDetection(
            string tankDetectionPath,
            WeldInterfacePackage package)
        {
            try
            {
                using JsonDocument document =
                    JsonDocument.Parse(
                        System.IO.File.ReadAllText(
                            tankDetectionPath));


                JsonElement root =
                    document.RootElement;


                if (string.IsNullOrWhiteSpace(
                        package.TankName)
                    &&
                    root.TryGetProperty(
                        "TankName",
                        out JsonElement tankName))
                {
                    package.TankName =
                        tankName.GetString()
                        ??
                        "";
                }


                if (string.IsNullOrWhiteSpace(
                        package.DocumentName)
                    &&
                    root.TryGetProperty(
                        "DocumentName",
                        out JsonElement documentName))
                {
                    package.DocumentName =
                        documentName.GetString()
                        ??
                        "";
                }
            }
            catch
            {
                // Identity is useful but not allowed to invalidate
                // a valid preview package.
            }
        }


        public static string ComputeSha256(
            string filePath)
        {
            using SHA256 sha =
                SHA256.Create();


            using System.IO.FileStream stream =
                System.IO.File.OpenRead(
                    filePath);


            byte[] hash =
                sha.ComputeHash(
                    stream);


            return Convert.ToHexString(
                    hash)
                .ToLowerInvariant();
        }
    }
}
