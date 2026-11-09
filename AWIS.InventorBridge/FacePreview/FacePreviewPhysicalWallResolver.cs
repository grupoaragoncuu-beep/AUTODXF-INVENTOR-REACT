using System;
using System.Collections.Generic;
using System.Linq;

namespace AWIS.InventorBridge.FacePreview
{
    // ================================================================
    // FACE PREVIEW V0.4.0
    // MULTI-SEGMENT PHYSICAL WALL RESOLVER
    //
    // The official V0 Tank Frame still defines six logical faces.
    // This resolver works one level below that abstraction:
    //   FACE -> 1..N physical plate segments -> structural seams.
    //
    // The exact V0 structural face is always the anchor. Additional
    // segments are admitted only when they are large, nearly coplanar,
    // and geometrically adjacent to the already accepted wall.
    // ================================================================

    internal class FacePreviewPhysicalWallResolver
    {
        private const double BoundsDuplicateToleranceMm =
            1.0;

        private const double NumericalAdjacencyOverlapToleranceMm =
            1.0;


        public void Resolve(
            FacePreviewPackage package)
        {
            foreach (FacePreviewRecord face
                     in package.Faces)
            {
                ResolveFace(
                    package,
                    face);
            }
        }


        private void ResolveFace(
            FacePreviewPackage package,
            FacePreviewRecord face)
        {
            List<PreviewEntity> sameOccurrenceOuter =
                face.Entities
                    .Where(
                        entity =>
                            string.Equals(
                                entity.OccurrencePath,
                                face.DetectionSource.OccurrencePath,
                                StringComparison.OrdinalIgnoreCase)
                            &&
                            string.Equals(
                                entity.LoopType,
                                "OUTER",
                                StringComparison.OrdinalIgnoreCase))
                    .ToList();


            List<PreviewEntity> exactFaceOuter =
                sameOccurrenceOuter
                    .Where(
                        entity =>
                            entity.BodyIndex ==
                                face.DetectionSource.BodyIndex
                            &&
                            entity.SourceFaceIndex ==
                                face.DetectionSource.FaceIndex)
                    .ToList();


            List<PreviewEntity> anchorPool =
                exactFaceOuter.Count > 0
                    ? exactFaceOuter
                    : sameOccurrenceOuter;


            PreviewEntity? anchor =
                anchorPool
                    .Where(
                        entity =>
                            entity.Points != null
                            &&
                            entity.Points.Count >= 4)
                    .OrderByDescending(
                        entity =>
                            Math.Abs(
                                entity.ProjectedAreaMm2))
                    .FirstOrDefault();


            if (anchor == null)
            {
                face.PhysicalWall =
                    BuildCanonicalFallback(
                        face,
                        "fallback_canonical_no_structural_outer_loop");


                package.Warnings.Add(
                    $"{face.FaceId}: PhysicalWall no pudo resolverse desde la cara estructural exacta; se usa CanonicalEnvelope como fallback.");

                return;
            }


            PhysicalWallSegmentationSettings settings =
                package.PhysicalWallSegmentation
                ??
                new PhysicalWallSegmentationSettings();


            SegmentCandidate anchorCandidate =
                BuildCandidate(
                    anchor,
                    true);


            List<SegmentCandidate> candidates =
                BuildPanelCandidatePool(
                    face,
                    anchor,
                    settings);


            // Guarantee the anchor even if a future threshold changes.
            if (!candidates.Any(
                    candidate =>
                        IsSameSource(
                            candidate.Entity,
                            anchor)))
            {
                candidates.Add(
                    anchorCandidate);
            }


            candidates =
                RemoveGeometricDuplicates(
                    candidates,
                    anchor);


            List<SegmentCandidate> accepted =
                GrowConnectedWall(
                    candidates,
                    anchor,
                    settings);


            if (accepted.Count == 0)
            {
                accepted.Add(
                    anchorCandidate);
            }


            accepted =
                accepted
                    .OrderBy(
                        candidate =>
                            candidate.Bounds.MinU)
                    .ThenBy(
                        candidate =>
                            candidate.Bounds.MinV)
                    .ThenBy(
                        candidate =>
                            candidate.Entity.OccurrencePath,
                        StringComparer.OrdinalIgnoreCase)
                    .ToList();


            List<PhysicalWallSegment> segments =
                new List<PhysicalWallSegment>();


            for (int i = 0;
                 i < accepted.Count;
                 i++)
            {
                SegmentCandidate candidate =
                    accepted[i];


                segments.Add(
                    ConvertSegment(
                        face,
                        candidate,
                        i + 1,
                        IsSameSource(
                            candidate.Entity,
                            anchor)));
            }


            List<StructuralSeam> seams =
                BuildStructuralSeams(
                    face,
                    segments,
                    settings);


            PhysicalWallBounds unionBounds =
                BuildUnionBounds(
                    segments);


            face.PhysicalWall =
                new PhysicalWallGeometry
                {
                    Resolved =
                        true,

                    ResolutionStatus =
                        segments.Count > 1
                            ? "resolved_multi_segment_structural_wall"
                            : exactFaceOuter.Count > 0
                                ? "resolved_single_segment_exact_structural_face"
                                : "resolved_single_segment_structural_occurrence_fallback",

                    SourceEntityId =
                        anchor.EntityId,

                    SourceBodyIndex =
                        anchor.BodyIndex,

                    SourceFaceIndex =
                        anchor.SourceFaceIndex,

                    SourceLoopIndex =
                        anchor.SourceLoopIndex,

                    Bounds =
                        unionBounds,

                    OuterLoop =
                        ClonePoints(
                            anchor.Points),

                    SegmentCount =
                        segments.Count,

                    Segments =
                        segments,

                    StructuralSeams =
                        seams
                };
        }


        private List<SegmentCandidate> BuildPanelCandidatePool(
            FacePreviewRecord face,
            PreviewEntity anchor,
            PhysicalWallSegmentationSettings settings)
        {
            double canonicalArea =
                Math.Max(
                    1.0,
                    Math.Abs(
                        face.WidthMm *
                        face.HeightMm));


            List<SegmentCandidate> result =
                new List<SegmentCandidate>();


            foreach (PreviewEntity entity
                     in face.Entities)
            {
                if (!string.Equals(
                        entity.LoopType,
                        "OUTER",
                        StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }


                if (entity.Points == null
                    ||
                    entity.Points.Count < 4)
                {
                    continue;
                }


                bool isAnchor =
                    IsSameSource(
                        entity,
                        anchor);


                if (!isAnchor)
                {
                    if (Math.Abs(
                            entity.SourceFaceDepthMm -
                            anchor.SourceFaceDepthMm)
                        >
                        settings.CoplanarDepthToleranceMm)
                    {
                        continue;
                    }


                    if (entity.NormalAlignment <
                        settings.MinimumSegmentNormalAlignment)
                    {
                        continue;
                    }


                    double areaRatio =
                        Math.Abs(
                            entity.ProjectedAreaMm2)
                        /
                        canonicalArea;


                    if (areaRatio <
                        settings.MinimumSegmentAreaRatioToCanonicalWall)
                    {
                        continue;
                    }
                }


                SegmentCandidate candidate =
                    BuildCandidate(
                        entity,
                        isAnchor);


                if (!isAnchor
                    &&
                    CalculateCanonicalOverlapRatio(
                        face,
                        candidate.Bounds)
                    <
                    0.50)
                {
                    continue;
                }


                result.Add(
                    candidate);
            }


            return result;
        }


        private List<SegmentCandidate> RemoveGeometricDuplicates(
            List<SegmentCandidate> candidates,
            PreviewEntity anchor)
        {
            List<SegmentCandidate> ordered =
                candidates
                    .OrderByDescending(
                        candidate =>
                            IsSameSource(
                                candidate.Entity,
                                anchor))
                    .ThenByDescending(
                        candidate =>
                            Math.Abs(
                                candidate.Entity.ProjectedAreaMm2))
                    .ToList();


            List<SegmentCandidate> result =
                new List<SegmentCandidate>();


            foreach (SegmentCandidate candidate
                     in ordered)
            {
                bool duplicate =
                    result.Any(
                        existing =>
                            BoundsAlmostEqual(
                                existing.Bounds,
                                candidate.Bounds));


                if (!duplicate)
                {
                    result.Add(
                        candidate);
                }
            }


            return result;
        }


        private List<SegmentCandidate> GrowConnectedWall(
            List<SegmentCandidate> candidates,
            PreviewEntity anchor,
            PhysicalWallSegmentationSettings settings)
        {
            SegmentCandidate? anchorCandidate =
                candidates.FirstOrDefault(
                    candidate =>
                        IsSameSource(
                            candidate.Entity,
                            anchor));


            if (anchorCandidate == null)
            {
                return new List<SegmentCandidate>();
            }


            List<SegmentCandidate> accepted =
                new List<SegmentCandidate>
                {
                    anchorCandidate
                };


            HashSet<SegmentCandidate> pending =
                candidates
                    .Where(
                        candidate =>
                            !ReferenceEquals(
                                candidate,
                                anchorCandidate))
                    .ToHashSet();


            bool changed =
                true;


            while (changed)
            {
                changed =
                    false;


                foreach (SegmentCandidate candidate
                         in pending.ToList())
                {
                    bool connected =
                        accepted.Any(
                            existing =>
                                TryDescribeAdjacency(
                                    existing.Bounds,
                                    candidate.Bounds,
                                    settings,
                                    out _));


                    if (!connected)
                    {
                        continue;
                    }


                    accepted.Add(
                        candidate);

                    pending.Remove(
                        candidate);

                    changed =
                        true;
                }
            }


            return accepted;
        }


        private List<StructuralSeam> BuildStructuralSeams(
            FacePreviewRecord face,
            List<PhysicalWallSegment> segments,
            PhysicalWallSegmentationSettings settings)
        {
            List<StructuralSeam> result =
                new List<StructuralSeam>();


            for (int i = 0;
                 i < segments.Count;
                 i++)
            {
                for (int j = i + 1;
                     j < segments.Count;
                     j++)
                {
                    if (!TryDescribeAdjacency(
                            segments[i].Bounds,
                            segments[j].Bounds,
                            settings,
                            out AdjacencyDescription adjacency))
                    {
                        continue;
                    }


                    StructuralSeam seam =
                        new StructuralSeam
                        {
                            SeamId =
                                $"{face.FaceId}_SEAM_{result.Count + 1:000}",

                            SegmentAId =
                                segments[i].SegmentId,

                            SegmentBId =
                                segments[j].SegmentId,

                            SeparationAxis =
                                adjacency.SeparationAxis,

                            GapMm =
                                Math.Round(
                                    adjacency.GapMm,
                                    3),

                            SharedSpanStartMm =
                                Math.Round(
                                    adjacency.SharedSpanStartMm,
                                    3),

                            SharedSpanEndMm =
                                Math.Round(
                                    adjacency.SharedSpanEndMm,
                                    3),

                            LengthMm =
                                Math.Round(
                                    adjacency.SharedSpanEndMm -
                                    adjacency.SharedSpanStartMm,
                                    3)
                        };


                    if (string.Equals(
                            adjacency.SeparationAxis,
                            "U_GAP",
                            StringComparison.OrdinalIgnoreCase))
                    {
                        seam.FaceLocalCenterline.Add(
                            new Point2Dto
                            {
                                X =
                                    Math.Round(
                                        adjacency.CenterCoordinateMm,
                                        3),
                                Y =
                                    Math.Round(
                                        adjacency.SharedSpanStartMm,
                                        3)
                            });

                        seam.FaceLocalCenterline.Add(
                            new Point2Dto
                            {
                                X =
                                    Math.Round(
                                        adjacency.CenterCoordinateMm,
                                        3),
                                Y =
                                    Math.Round(
                                        adjacency.SharedSpanEndMm,
                                        3)
                            });
                    }
                    else
                    {
                        seam.FaceLocalCenterline.Add(
                            new Point2Dto
                            {
                                X =
                                    Math.Round(
                                        adjacency.SharedSpanStartMm,
                                        3),
                                Y =
                                    Math.Round(
                                        adjacency.CenterCoordinateMm,
                                        3)
                            });

                        seam.FaceLocalCenterline.Add(
                            new Point2Dto
                            {
                                X =
                                    Math.Round(
                                        adjacency.SharedSpanEndMm,
                                        3),
                                Y =
                                    Math.Round(
                                        adjacency.CenterCoordinateMm,
                                        3)
                            });
                    }


                    result.Add(
                        seam);
                }
            }


            return result;
        }


        private bool TryDescribeAdjacency(
            PhysicalWallBounds a,
            PhysicalWallBounds b,
            PhysicalWallSegmentationSettings settings,
            out AdjacencyDescription adjacency)
        {
            adjacency =
                new AdjacencyDescription();


            List<AdjacencyDescription> options =
                new List<AdjacencyDescription>();


            // --------------------------------------------------------
            // Panels separated along U, sharing V span.
            // --------------------------------------------------------

            double uGap =
                AxisGap(
                    a.MinU,
                    a.MaxU,
                    b.MinU,
                    b.MaxU);


            double sharedVStart =
                Math.Max(
                    a.MinV,
                    b.MinV);

            double sharedVEnd =
                Math.Min(
                    a.MaxV,
                    b.MaxV);

            double sharedV =
                Math.Max(
                    0.0,
                    sharedVEnd -
                    sharedVStart);

            double minVSpan =
                Math.Max(
                    1e-9,
                    Math.Min(
                        a.MaxV - a.MinV,
                        b.MaxV - b.MinV));

            double sharedVRatio =
                sharedV /
                minVSpan;


            if (uGap >= 0.0
                &&
                uGap <=
                    settings.MaximumStructuralSeamGapMm
                &&
                sharedVRatio >=
                    settings.MinimumSharedSpanRatio)
            {
                double centerU =
                    SeparationCenter(
                        a.MinU,
                        a.MaxU,
                        b.MinU,
                        b.MaxU);


                options.Add(
                    new AdjacencyDescription
                    {
                        SeparationAxis =
                            "U_GAP",
                        GapMm =
                            uGap,
                        SharedSpanStartMm =
                            sharedVStart,
                        SharedSpanEndMm =
                            sharedVEnd,
                        SharedSpanRatio =
                            sharedVRatio,
                        CenterCoordinateMm =
                            centerU
                    });
            }


            // --------------------------------------------------------
            // Panels separated along V, sharing U span.
            // --------------------------------------------------------

            double vGap =
                AxisGap(
                    a.MinV,
                    a.MaxV,
                    b.MinV,
                    b.MaxV);


            double sharedUStart =
                Math.Max(
                    a.MinU,
                    b.MinU);

            double sharedUEnd =
                Math.Min(
                    a.MaxU,
                    b.MaxU);

            double sharedU =
                Math.Max(
                    0.0,
                    sharedUEnd -
                    sharedUStart);

            double minUSpan =
                Math.Max(
                    1e-9,
                    Math.Min(
                        a.MaxU - a.MinU,
                        b.MaxU - b.MinU));

            double sharedURatio =
                sharedU /
                minUSpan;


            if (vGap >= 0.0
                &&
                vGap <=
                    settings.MaximumStructuralSeamGapMm
                &&
                sharedURatio >=
                    settings.MinimumSharedSpanRatio)
            {
                double centerV =
                    SeparationCenter(
                        a.MinV,
                        a.MaxV,
                        b.MinV,
                        b.MaxV);


                options.Add(
                    new AdjacencyDescription
                    {
                        SeparationAxis =
                            "V_GAP",
                        GapMm =
                            vGap,
                        SharedSpanStartMm =
                            sharedUStart,
                        SharedSpanEndMm =
                            sharedUEnd,
                        SharedSpanRatio =
                            sharedURatio,
                        CenterCoordinateMm =
                            centerV
                    });
            }


            if (options.Count == 0)
            {
                return false;
            }


            adjacency =
                options
                    .OrderByDescending(
                        option =>
                            option.SharedSpanRatio)
                    .ThenBy(
                        option =>
                            option.GapMm)
                    .First();


            return true;
        }


        private double AxisGap(
            double aMin,
            double aMax,
            double bMin,
            double bMax)
        {
            if (bMin >= aMax)
            {
                return bMin -
                    aMax;
            }


            if (aMin >= bMax)
            {
                return aMin -
                    bMax;
            }


            double overlap =
                Math.Min(
                    aMax,
                    bMax)
                -
                Math.Max(
                    aMin,
                    bMin);


            return overlap <=
                NumericalAdjacencyOverlapToleranceMm
                    ? 0.0
                    : -1.0;
        }


        private double SeparationCenter(
            double aMin,
            double aMax,
            double bMin,
            double bMax)
        {
            if (bMin >= aMax)
            {
                return (aMax + bMin) /
                    2.0;
            }


            if (aMin >= bMax)
            {
                return (bMax + aMin) /
                    2.0;
            }


            return (
                Math.Max(
                    aMin,
                    bMin)
                +
                Math.Min(
                    aMax,
                    bMax)) /
                2.0;
        }


        private PhysicalWallSegment ConvertSegment(
            FacePreviewRecord face,
            SegmentCandidate candidate,
            int index,
            bool isAnchor)
        {
            PreviewEntity entity =
                candidate.Entity;


            return new PhysicalWallSegment
            {
                SegmentId =
                    $"{face.FaceId}_SEG_{index:000}",

                IsAnchorSegment =
                    isAnchor,

                SourceEntityId =
                    entity.EntityId,

                OccurrenceName =
                    entity.OccurrenceName,

                OccurrencePath =
                    entity.OccurrencePath,

                SourceBodyIndex =
                    entity.BodyIndex,

                SourceFaceIndex =
                    entity.SourceFaceIndex,

                SourceLoopIndex =
                    entity.SourceLoopIndex,

                SourceFaceDepthMm =
                    entity.SourceFaceDepthMm,

                NormalAlignment =
                    entity.NormalAlignment,

                ProjectedAreaMm2 =
                    entity.ProjectedAreaMm2,

                Bounds =
                    CloneBounds(
                        candidate.Bounds),

                OuterLoop =
                    ClonePoints(
                        entity.Points)
            };
        }


        private SegmentCandidate BuildCandidate(
            PreviewEntity entity,
            bool isAnchor)
        {
            double minU =
                entity.Points.Min(
                    point => point.X);

            double maxU =
                entity.Points.Max(
                    point => point.X);

            double minV =
                entity.Points.Min(
                    point => point.Y);

            double maxV =
                entity.Points.Max(
                    point => point.Y);


            return new SegmentCandidate
            {
                Entity =
                    entity,

                IsAnchor =
                    isAnchor,

                Bounds =
                    new PhysicalWallBounds
                    {
                        MinU =
                            minU,
                        MaxU =
                            maxU,
                        MinV =
                            minV,
                        MaxV =
                            maxV,
                        WidthMm =
                            maxU - minU,
                        HeightMm =
                            maxV - minV
                    }
            };
        }


        private PhysicalWallBounds BuildUnionBounds(
            List<PhysicalWallSegment> segments)
        {
            double minU =
                segments.Min(
                    segment => segment.Bounds.MinU);

            double maxU =
                segments.Max(
                    segment => segment.Bounds.MaxU);

            double minV =
                segments.Min(
                    segment => segment.Bounds.MinV);

            double maxV =
                segments.Max(
                    segment => segment.Bounds.MaxV);


            return new PhysicalWallBounds
            {
                MinU =
                    Math.Round(
                        minU,
                        3),
                MaxU =
                    Math.Round(
                        maxU,
                        3),
                MinV =
                    Math.Round(
                        minV,
                        3),
                MaxV =
                    Math.Round(
                        maxV,
                        3),
                WidthMm =
                    Math.Round(
                        maxU - minU,
                        3),
                HeightMm =
                    Math.Round(
                        maxV - minV,
                        3)
            };
        }


        private double CalculateCanonicalOverlapRatio(
            FacePreviewRecord face,
            PhysicalWallBounds bounds)
        {
            double width =
                Math.Max(
                    0.0,
                    bounds.MaxU -
                    bounds.MinU);

            double height =
                Math.Max(
                    0.0,
                    bounds.MaxV -
                    bounds.MinV);

            double area =
                width *
                height;


            if (area <= 1e-9)
            {
                return 0.0;
            }


            double overlapMinU =
                Math.Max(
                    0.0,
                    bounds.MinU);

            double overlapMaxU =
                Math.Min(
                    face.WidthMm,
                    bounds.MaxU);

            double overlapMinV =
                Math.Max(
                    0.0,
                    bounds.MinV);

            double overlapMaxV =
                Math.Min(
                    face.HeightMm,
                    bounds.MaxV);


            double overlapArea =
                Math.Max(
                    0.0,
                    overlapMaxU -
                    overlapMinU)
                *
                Math.Max(
                    0.0,
                    overlapMaxV -
                    overlapMinV);


            return overlapArea /
                area;
        }


        private bool BoundsAlmostEqual(
            PhysicalWallBounds a,
            PhysicalWallBounds b)
        {
            return
                Math.Abs(a.MinU - b.MinU) <=
                    BoundsDuplicateToleranceMm
                &&
                Math.Abs(a.MaxU - b.MaxU) <=
                    BoundsDuplicateToleranceMm
                &&
                Math.Abs(a.MinV - b.MinV) <=
                    BoundsDuplicateToleranceMm
                &&
                Math.Abs(a.MaxV - b.MaxV) <=
                    BoundsDuplicateToleranceMm;
        }


        private bool IsSameSource(
            PreviewEntity a,
            PreviewEntity b)
        {
            return string.Equals(
                    a.OccurrencePath,
                    b.OccurrencePath,
                    StringComparison.OrdinalIgnoreCase)
                &&
                a.BodyIndex ==
                    b.BodyIndex
                &&
                a.SourceFaceIndex ==
                    b.SourceFaceIndex
                &&
                a.SourceLoopIndex ==
                    b.SourceLoopIndex;
        }


        private PhysicalWallBounds CloneBounds(
            PhysicalWallBounds source)
        {
            return new PhysicalWallBounds
            {
                MinU =
                    Math.Round(
                        source.MinU,
                        3),
                MaxU =
                    Math.Round(
                        source.MaxU,
                        3),
                MinV =
                    Math.Round(
                        source.MinV,
                        3),
                MaxV =
                    Math.Round(
                        source.MaxV,
                        3),
                WidthMm =
                    Math.Round(
                        source.MaxU - source.MinU,
                        3),
                HeightMm =
                    Math.Round(
                        source.MaxV - source.MinV,
                        3)
            };
        }


        private List<Point2Dto> ClonePoints(
            List<Point2Dto> source)
        {
            return source
                .Select(
                    point =>
                        new Point2Dto
                        {
                            X = point.X,
                            Y = point.Y
                        })
                .ToList();
        }


        private PhysicalWallGeometry BuildCanonicalFallback(
            FacePreviewRecord face,
            string status)
        {
            List<Point2Dto> outer =
                face.Envelope != null
                &&
                face.Envelope.Count >= 4
                    ? ClonePoints(
                        face.Envelope)
                    : new List<Point2Dto>
                        {
                            new Point2Dto { X = 0.0, Y = 0.0 },
                            new Point2Dto { X = face.WidthMm, Y = 0.0 },
                            new Point2Dto { X = face.WidthMm, Y = face.HeightMm },
                            new Point2Dto { X = 0.0, Y = face.HeightMm },
                            new Point2Dto { X = 0.0, Y = 0.0 }
                        };


            return new PhysicalWallGeometry
            {
                Resolved =
                    false,

                ResolutionStatus =
                    status,

                Bounds =
                    new PhysicalWallBounds
                    {
                        MinU = 0.0,
                        MaxU = face.WidthMm,
                        MinV = 0.0,
                        MaxV = face.HeightMm,
                        WidthMm = face.WidthMm,
                        HeightMm = face.HeightMm
                    },

                OuterLoop =
                    outer,

                SegmentCount =
                    0
            };
        }


        private sealed class SegmentCandidate
        {
            public PreviewEntity Entity { get; set; } =
                new PreviewEntity();

            public bool IsAnchor { get; set; }

            public PhysicalWallBounds Bounds { get; set; } =
                new PhysicalWallBounds();
        }


        private sealed class AdjacencyDescription
        {
            public string SeparationAxis { get; set; } =
                "";

            public double GapMm { get; set; }

            public double SharedSpanStartMm { get; set; }

            public double SharedSpanEndMm { get; set; }

            public double SharedSpanRatio { get; set; }

            public double CenterCoordinateMm { get; set; }
        }
    }
}
