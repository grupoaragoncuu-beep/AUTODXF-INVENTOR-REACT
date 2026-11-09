using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using AWIS.InventorBridge.FacePreview;
using AWIS.InventorBridge.Geometry;
using AWIS.InventorBridge.Models;

namespace AWIS.InventorBridge.Services
{
    public sealed class TankFrameDetector
    {
        // ============================================================
        // ORIGINAL B.2 STRUCTURAL DETECTION
        // ============================================================

        private const double ParallelDotThreshold =
            0.9995;


        private const double PerpendicularDotMaximum =
            0.03;


        private const double MinimumStructuralSpanMm =
            100.0;


        private const double BoundaryPlaneToleranceMm =
            3.0;


        private const double BoundaryCoverageMinimum =
            0.50;


        private const double BoundaryCoverageWarning =
            0.65;


        // ============================================================
        // OLD PAIR CONSISTENCY RESCUE
        // ============================================================

        private const double PairPlaneSimilarityMinimum =
            0.80;


        private const double PairCoverageRescueFloor =
            0.45;


        // ============================================================
        // NEW GROSS FOOTPRINT RESCUE
        // ============================================================

        private const double FootprintAreaSimilarityMinimum =
            0.65;


        private const double FootprintWidthSimilarityMinimum =
            0.65;


        private const double FootprintHeightSimilarityMinimum =
            0.65;


        private const double FootprintCombinedSimilarityMinimum =
            0.75;


        private const int MaximumFamiliesForFrameSearch =
            16;


        private const int MaximumFacesPerFamilyForPairSearch =
            30;


        // ============================================================
        // INTERNAL FAMILY
        // ============================================================

        private sealed class OrientationFamily
        {
            public Vector3Data Direction { get; set; } =
                new();


            public List<FaceRecord> Faces { get; set; } =
                new();


            public double MaxAreaMm2 { get; set; }


            public double TotalAreaMm2 { get; set; }
        }


        // ============================================================
        // PUBLIC DETECT
        // ============================================================

        public TankDetectionResult Detect(
            GeometryScanResult scan)
        {
            TankDetectionResult result =
                new TankDetectionResult
                {
                    AwisVersion =
                        "Bridge V0.2B.2",

                    TankName =
                        GetTankName(
                            scan),

                    DocumentName =
                        scan.DocumentName,

                    DetectionTime =
                        DateTime.Now,

                    PlanarFacesInput =
                        scan.PlanarFaces.Count,

                    BoundaryCoverageMinimum =
                        BoundaryCoverageMinimum
                };


            if (scan.PlanarFaces.Count == 0)
            {
                result.FrameValid =
                    false;


                result.ModelClosureStatus =
                    "incomplete_or_unresolved";


                result.Warnings.Add(
                    "No se encontraron caras planas.");


                return result;
            }


            // ========================================================
            // DYNAMIC AREA FILTER
            // ========================================================

            double largestArea =
                scan.PlanarFaces
                .Max(
                    face =>
                        face.AreaMm2);


            double candidateAreaThreshold =
                Math.Max(
                    10000.0,
                    largestArea *
                    0.002);


            result.CandidateAreaThresholdMm2 =
                candidateAreaThreshold;


            List<FaceRecord> candidates =
                scan.PlanarFaces
                .Where(
                    face =>
                        face.AreaMm2 >=
                        candidateAreaThreshold)
                .ToList();


            result.CandidateFacesAnalyzed =
                candidates.Count;


            // ========================================================
            // ORIGINAL ORIENTATION FAMILIES
            // ========================================================

            List<OrientationFamily> families =
                BuildOrientationFamilies(
                    candidates);


            result.OrientationFamiliesFound =
                families.Count;


            List<OrientationFamily>? frameFamilies =
                FindBestOrthogonalFrameFamilies(
                    families);


            if (frameFamilies == null ||
                frameFamilies.Count != 3)
            {
                result.FrameValid =
                    false;


                result.ModelClosureStatus =
                    "incomplete_or_unresolved";


                result.Warnings.Add(
                    "No fue posible resolver tres familias estructurales ortogonales.");


                return result;
            }


            // ========================================================
            // ORIGINAL B.2 AXIS CONSTRUCTION
            //
            // Esta parte vuelve a ser la autoridad principal.
            // ========================================================

            List<TankAxisResult> axes =
                frameFamilies
                .Select(
                    family =>
                        BuildAxisResult(
                            family))
                .OrderByDescending(
                    axis =>
                        axis.SpanMm)
                .ToList();


            RenameAxes(
                axes);


            // ========================================================
            // ORIGINAL COVERAGE VALIDATION
            // ========================================================

            ValidateBoundaries(
                axes,
                scan.PlanarFaces);


            // ========================================================
            // PAIR CONSISTENCY RESCUE
            //
            // Solo si una boundary falló.
            // Nunca sobreescribe una pareja que ya pasó normalmente.
            // ========================================================

            foreach (TankAxisResult axis
                     in axes)
            {
                ApplyPairConsistencyRescue(
                    axis);
            }


            // ========================================================
            // NEW:
            // GROSS FOOTPRINT RESCUE
            //
            // Se ejecuta ÚNICAMENTE si todavía queda exactamente
            // una boundary confirmada y una rechazada.
            //
            // No participa en la detección primaria.
            // ========================================================

            foreach (TankAxisResult axis
                     in axes)
            {
                TryGrossFootprintRescue(
                    axis,
                    axes,
                    scan);
            }


            // El rescate puede haber corregido un span.
            axes =
                axes
                .OrderByDescending(
                    axis =>
                        axis.SpanMm)
                .ToList();


            RenameAxes(
                axes);


            // ========================================================
            // FINAL AXIS STATUS
            // ========================================================

            foreach (TankAxisResult axis
                     in axes)
            {
                bool bothDetected =
                    axis.NegativeBoundary.Detected
                    &&
                    axis.PositiveBoundary.Detected;


                axis.SpanConfirmed =
                    bothDetected;


                axis.SpanStatus =
                    bothDetected
                        ? "confirmed"
                        : "unconfirmed_missing_boundary";
            }


            // ========================================================
            // WARNINGS ONLY AFTER ALL RESCUES
            // ========================================================

            AddBoundaryWarnings(
                axes,
                result);


            result.Axes =
                axes;


            // ========================================================
            // COUNTS
            // ========================================================

            result.DetectedBoundaryCount =
                axes.Sum(
                    axis =>
                        (axis.NegativeBoundary.Detected
                            ? 1
                            : 0)
                        +
                        (axis.PositiveBoundary.Detected
                            ? 1
                            : 0));


            result.MissingBoundaryCount =
                6 -
                result.DetectedBoundaryCount;


            result.BoundaryCompleteness =
                Math.Round(
                    result.DetectedBoundaryCount /
                    6.0,
                    4);


            result.ModelClosureStatus =
                result.DetectedBoundaryCount switch
                {
                    6 =>
                        "complete",

                    5 =>
                        "open_one_boundary",

                    4 =>
                        "open_two_boundaries",

                    _ =>
                        "incomplete_or_unresolved"
                };


            // ========================================================
            // FRAME VALID
            // ========================================================

            int completeAxes =
                axes.Count(
                    axis =>
                        axis.NegativeBoundary.Detected
                        &&
                        axis.PositiveBoundary.Detected);


            bool everyAxisHasEvidence =
                axes.All(
                    axis =>
                        axis.NegativeBoundary.Detected
                        ||
                        axis.PositiveBoundary.Detected);


            result.FrameValid =
                axes.Count ==
                3
                &&
                completeAxes >=
                2
                &&
                everyAxisHasEvidence;


            // ========================================================
            // CONFIDENCE
            // ========================================================

            result.Confidence =
                CalculateConfidence(
                    frameFamilies,
                    axes,
                    result);


            if (result.Confidence <
                0.85)
            {
                result.Warnings.Add(
                    $"La confianza global del Tank Frame es relativamente baja ({result.Confidence:P1}).");
            }


            if (!result.FrameValid)
            {
                result.Warnings.Add(
                    "El modelo no contiene evidencia suficiente para confirmar un Tank Frame estructural utilizable.");
            }


            return result;
        }


        // ============================================================
        // ORIENTATION FAMILIES
        // ============================================================

        private static List<OrientationFamily>
            BuildOrientationFamilies(
                List<FaceRecord> candidateFaces)
        {
            List<OrientationFamily> families =
                new();


            foreach (FaceRecord face
                     in candidateFaces
                     .OrderByDescending(
                         face =>
                             face.AreaMm2))
            {
                Vector3Data direction =
                    VectorMath.CanonicalizeAxis(
                        face.Normal);


                OrientationFamily? family =
                    families
                    .FirstOrDefault(
                        existing =>
                            Math.Abs(
                                VectorMath.Dot(
                                    existing.Direction,
                                    direction))
                            >=
                            ParallelDotThreshold);


                if (family == null)
                {
                    family =
                        new OrientationFamily
                        {
                            Direction =
                                direction
                        };


                    families.Add(
                        family);
                }


                family.Faces.Add(
                    face);


                family.TotalAreaMm2 +=
                    face.AreaMm2;


                family.MaxAreaMm2 =
                    Math.Max(
                        family.MaxAreaMm2,
                        face.AreaMm2);
            }


            return families
                .OrderByDescending(
                    family =>
                        family.MaxAreaMm2)
                .ToList();
        }


        // ============================================================
        // BEST ORTHOGONAL TRIPLE
        // ============================================================

        private static List<OrientationFamily>?
            FindBestOrthogonalFrameFamilies(
                List<OrientationFamily> families)
        {
            List<OrientationFamily> strongest =
                families
                .Take(
                    MaximumFamiliesForFrameSearch)
                .ToList();


            List<OrientationFamily>?
                best =
                    null;


            double bestScore =
                double.NegativeInfinity;


            for (int i = 0;
                 i < strongest.Count - 2;
                 i++)
            {
                for (int j = i + 1;
                     j < strongest.Count - 1;
                     j++)
                {
                    double dotIJ =
                        Math.Abs(
                            VectorMath.Dot(
                                strongest[i].Direction,
                                strongest[j].Direction));


                    if (dotIJ >
                        PerpendicularDotMaximum)
                    {
                        continue;
                    }


                    for (int k = j + 1;
                         k < strongest.Count;
                         k++)
                    {
                        double dotIK =
                            Math.Abs(
                                VectorMath.Dot(
                                    strongest[i].Direction,
                                    strongest[k].Direction));


                        double dotJK =
                            Math.Abs(
                                VectorMath.Dot(
                                    strongest[j].Direction,
                                    strongest[k].Direction));


                        if (dotIK >
                            PerpendicularDotMaximum
                            ||
                            dotJK >
                            PerpendicularDotMaximum)
                        {
                            continue;
                        }


                        double areaScore =
                            strongest[i].MaxAreaMm2
                            +
                            strongest[j].MaxAreaMm2
                            +
                            strongest[k].MaxAreaMm2;


                        double penalty =
                            dotIJ +
                            dotIK +
                            dotJK;


                        double score =
                            areaScore /
                            (1.0 +
                             penalty);


                        if (score >
                            bestScore)
                        {
                            bestScore =
                                score;


                            best =
                                new List<OrientationFamily>
                                {
                                    strongest[i],
                                    strongest[j],
                                    strongest[k]
                                };
                        }
                    }
                }
            }


            return best;
        }


        // ============================================================
        // ORIGINAL B.2 AXIS PAIR
        //
        // min(face area) × separation
        // ============================================================

        private static TankAxisResult BuildAxisResult(
            OrientationFamily family)
        {
            List<FaceRecord> strongestFaces =
                family.Faces
                .OrderByDescending(
                    face =>
                        face.AreaMm2)
                .Take(
                    MaximumFacesPerFamilyForPairSearch)
                .ToList();


            FaceRecord? bestA =
                null;


            FaceRecord? bestB =
                null;


            double bestScore =
                double.NegativeInfinity;


            for (int i = 0;
                 i < strongestFaces.Count - 1;
                 i++)
            {
                for (int j = i + 1;
                     j < strongestFaces.Count;
                     j++)
                {
                    FaceRecord faceA =
                        strongestFaces[i];


                    FaceRecord faceB =
                        strongestFaces[j];


                    double projectionA =
                        VectorMath.Projection(
                            faceA.PointMm,
                            family.Direction);


                    double projectionB =
                        VectorMath.Projection(
                            faceB.PointMm,
                            family.Direction);


                    double separation =
                        Math.Abs(
                            projectionB -
                            projectionA);


                    if (separation <
                        MinimumStructuralSpanMm)
                    {
                        continue;
                    }


                    double score =
                        Math.Min(
                            faceA.AreaMm2,
                            faceB.AreaMm2)
                        *
                        separation;


                    if (score >
                        bestScore)
                    {
                        bestScore =
                            score;


                        bestA =
                            faceA;


                        bestB =
                            faceB;
                    }
                }
            }


            if (bestA == null ||
                bestB == null)
            {
                FaceRecord anchor =
                    strongestFaces
                    .First();


                return new TankAxisResult
                {
                    Direction =
                        family.Direction,


                    SpanMm =
                        0.0,


                    SpanConfirmed =
                        false,


                    SpanStatus =
                        "unconfirmed_missing_boundary",


                    NegativeBoundary =
                        CreateBoundaryFromFace(
                            anchor,
                            family.Direction,
                            "NEGATIVE"),


                    PositiveBoundary =
                        CreateMissingBoundary(
                            "POSITIVE")
                };
            }


            double projectionBestA =
                VectorMath.Projection(
                    bestA.PointMm,
                    family.Direction);


            double projectionBestB =
                VectorMath.Projection(
                    bestB.PointMm,
                    family.Direction);


            FaceRecord negativeFace;
            FaceRecord positiveFace;


            if (projectionBestA <=
                projectionBestB)
            {
                negativeFace =
                    bestA;

                positiveFace =
                    bestB;
            }
            else
            {
                negativeFace =
                    bestB;

                positiveFace =
                    bestA;
            }


            double negativeProjection =
                VectorMath.Projection(
                    negativeFace.PointMm,
                    family.Direction);


            double positiveProjection =
                VectorMath.Projection(
                    positiveFace.PointMm,
                    family.Direction);


            return new TankAxisResult
            {
                Direction =
                    family.Direction,


                SpanMm =
                    Math.Abs(
                        positiveProjection -
                        negativeProjection),


                SpanConfirmed =
                    false,


                SpanStatus =
                    "pending_validation",


                NegativeBoundary =
                    CreateBoundaryFromFace(
                        negativeFace,
                        family.Direction,
                        "NEGATIVE"),


                PositiveBoundary =
                    CreateBoundaryFromFace(
                        positiveFace,
                        family.Direction,
                        "POSITIVE")
            };
        }


        // ============================================================
        // CREATE BOUNDARY FROM FACE
        // ============================================================

        private static TankBoundaryFace
            CreateBoundaryFromFace(
                FaceRecord face,
                Vector3Data axisDirection,
                string side)
        {
            return new TankBoundaryFace
            {
                Detected =
                    false,


                Status =
                    "pending_validation",


                DetectionReason =
                    "Structural boundary pending validation.",


                Side =
                    side,


                FaceRecordIndex =
                    face.Index,


                OccurrenceName =
                    face.OccurrenceName,


                OccurrencePath =
                    face.OccurrencePath,


                BodyIndex =
                    face.BodyIndex,


                FaceIndex =
                    face.FaceIndex,


                AreaMm2 =
                    face.AreaMm2,


                ProjectionMm =
                    VectorMath.Projection(
                        face.PointMm,
                        axisDirection),


                PointMm =
                    new Point3Data
                    {
                        X =
                            face.PointMm.X,

                        Y =
                            face.PointMm.Y,

                        Z =
                            face.PointMm.Z
                    },


                Normal =
                    new Vector3Data
                    {
                        X =
                            face.Normal.X,

                        Y =
                            face.Normal.Y,

                        Z =
                            face.Normal.Z
                    }
            };
        }


        private static TankBoundaryFace
            CreateMissingBoundary(
                string side)
        {
            return new TankBoundaryFace
            {
                Detected =
                    false,

                Status =
                    "missing_or_unconfirmed",

                DetectionReason =
                    "No structural boundary candidate was confirmed.",

                Side =
                    side
            };
        }


        // ============================================================
        // ORIGINAL B.2 COVERAGE VALIDATION
        // ============================================================

        private static void ValidateBoundaries(
            List<TankAxisResult> axes,
            List<FaceRecord> allPlanarFaces)
        {
            if (axes.Count != 3)
            {
                return;
            }


            for (int axisIndex = 0;
                 axisIndex < axes.Count;
                 axisIndex++)
            {
                TankAxisResult axis =
                    axes[axisIndex];


                List<int> otherIndices =
                    Enumerable
                    .Range(
                        0,
                        axes.Count)
                    .Where(
                        index =>
                            index !=
                            axisIndex)
                    .ToList();


                double expectedArea =
                    axes[otherIndices[0]].SpanMm
                    *
                    axes[otherIndices[1]].SpanMm;


                axis.NegativeBoundary.PlaneAreaMm2 =
                    CalculateFullPlaneAreaMm2(
                        allPlanarFaces,
                        axis.Direction,
                        axis.NegativeBoundary.ProjectionMm);


                axis.PositiveBoundary.PlaneAreaMm2 =
                    CalculateFullPlaneAreaMm2(
                        allPlanarFaces,
                        axis.Direction,
                        axis.PositiveBoundary.ProjectionMm);


                ValidateBoundaryInitial(
                    axis.NegativeBoundary,
                    expectedArea);


                ValidateBoundaryInitial(
                    axis.PositiveBoundary,
                    expectedArea);
            }
        }


        // ============================================================
        // FULL PLANE AREA
        // ============================================================

        private static double CalculateFullPlaneAreaMm2(
            List<FaceRecord> allPlanarFaces,
            Vector3Data axisDirection,
            double targetProjection)
        {
            double total =
                0.0;


            foreach (FaceRecord face
                     in allPlanarFaces)
            {
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
                        targetProjection)
                    >
                    BoundaryPlaneToleranceMm)
                {
                    continue;
                }


                total +=
                    face.AreaMm2;
            }


            return total;
        }


        // ============================================================
        // INITIAL COVERAGE VALIDATION
        // ============================================================

        private static void ValidateBoundaryInitial(
            TankBoundaryFace boundary,
            double expectedAreaMm2)
        {
            boundary.ExpectedAreaMm2 =
                expectedAreaMm2;


            double coverage =
                expectedAreaMm2 <=
                0.0
                    ? 0.0
                    : boundary.PlaneAreaMm2 /
                      expectedAreaMm2;


            boundary.AreaCoverageRatio =
                Math.Round(
                    coverage,
                    6);


            if (coverage >=
                BoundaryCoverageMinimum)
            {
                boundary.Detected =
                    true;


                boundary.Status =
                    coverage <
                    BoundaryCoverageWarning
                        ? "detected_low_coverage"
                        : "detected";


                boundary.DetectionReason =
                    coverage <
                    BoundaryCoverageWarning
                        ?
                        $"Structural plane coverage {coverage:P1} is above the minimum, but remains relatively low."
                        :
                        $"Structural plane coverage {coverage:P1} confirms this candidate as a principal tank boundary.";


                return;
            }


            boundary.Detected =
                false;


            boundary.Status =
                "missing_or_unconfirmed";


            boundary.DetectionReason =
                $"Candidate initially rejected because structural plane coverage {coverage:P1} is below the required {BoundaryCoverageMinimum:P0}.";
        }


        // ============================================================
        // PAIR CONSISTENCY RESCUE
        // ============================================================

        private static void ApplyPairConsistencyRescue(
            TankAxisResult axis)
        {
            TankBoundaryFace negative =
                axis.NegativeBoundary;


            TankBoundaryFace positive =
                axis.PositiveBoundary;


            // ========================================================
            // IMPORTANT CORRECTION:
            //
            // Si ambas ya pasaron normalmente, NO tocar su status.
            // ========================================================

            if (negative.Detected &&
                positive.Detected)
            {
                return;
            }


            // Este rescate requiere exactamente una boundary dudosa.
            if (negative.Detected ==
                positive.Detected)
            {
                return;
            }


            double largerArea =
                Math.Max(
                    negative.PlaneAreaMm2,
                    positive.PlaneAreaMm2);


            if (largerArea <=
                0.0)
            {
                return;
            }


            double planeSimilarity =
                Math.Min(
                    negative.PlaneAreaMm2,
                    positive.PlaneAreaMm2)
                /
                largerArea;


            double lowerCoverage =
                Math.Min(
                    negative.AreaCoverageRatio,
                    positive.AreaCoverageRatio);


            if (planeSimilarity <
                PairPlaneSimilarityMinimum
                ||
                lowerCoverage <
                PairCoverageRescueFloor)
            {
                return;
            }


            negative.Detected =
                true;


            positive.Detected =
                true;


            negative.Status =
                "detected_pair_consistency";


            positive.Status =
                "detected_pair_consistency";


            negative.DetectionReason =
                $"Boundary confirmed by opposite-wall consistency. Plane similarity: {planeSimilarity:P1}.";


            positive.DetectionReason =
                $"Boundary confirmed by opposite-wall consistency. Plane similarity: {planeSimilarity:P1}.";
        }


        // ============================================================
        // GROSS FOOTPRINT RESCUE
        // ============================================================

        private static void TryGrossFootprintRescue(
            TankAxisResult axis,
            List<TankAxisResult> allAxes,
            GeometryScanResult scan)
        {
            bool negativeDetected =
                axis.NegativeBoundary.Detected;


            bool positiveDetected =
                axis.PositiveBoundary.Detected;


            // Exactly one boundary must be valid.
            if (negativeDetected ==
                positiveDetected)
            {
                return;
            }


            TankBoundaryFace anchorBoundary =
                negativeDetected
                    ? axis.NegativeBoundary
                    : axis.PositiveBoundary;


            bool missingPositive =
                negativeDetected;


            List<TankAxisResult> otherAxes =
                allAxes
                .Where(
                    other =>
                        !ReferenceEquals(
                            other,
                            axis))
                .ToList();


            if (otherAxes.Count !=
                2)
            {
                return;
            }


            List<PlaneFootprint> footprints =
                GrossFootprintCalculator
                .BuildPlaneFootprints(
                    scan.PlanarFaces,
                    axis.Direction,
                    otherAxes[0].Direction,
                    otherAxes[1].Direction);


            if (footprints.Count ==
                0)
            {
                return;
            }


            // ========================================================
            // FIND FOOTPRINT OF ALREADY CONFIRMED WALL
            // ========================================================

            PlaneFootprint? anchorFootprint =
                footprints
                .Where(
                    footprint =>
                        footprint
                        .RepresentativeOccurrencePath
                        ==
                        anchorBoundary
                        .OccurrencePath)
                .OrderBy(
                    footprint =>
                        Math.Abs(
                            footprint.ProjectionMm -
                            anchorBoundary.ProjectionMm))
                .FirstOrDefault();


            if (anchorFootprint ==
                null)
            {
                return;
            }


            // Require that we actually resolved roughly the same plane.
            if (Math.Abs(
                    anchorFootprint.ProjectionMm -
                    anchorBoundary.ProjectionMm)
                >
                20.0)
            {
                return;
            }


            // ========================================================
            // POSSIBLE OPPOSITE WALLS
            // ========================================================

            List<PlaneFootprint> eligible =
                footprints
                .Where(
                    footprint =>
                    {
                        double delta =
                            footprint.ProjectionMm -
                            anchorFootprint.ProjectionMm;


                        if (missingPositive)
                        {
                            return delta >=
                                   MinimumStructuralSpanMm;
                        }


                        return delta <=
                               -MinimumStructuralSpanMm;
                    })
                .ToList();


            if (eligible.Count ==
                0)
            {
                return;
            }


            double maximumSeparation =
                eligible
                .Max(
                    footprint =>
                        Math.Abs(
                            footprint.ProjectionMm -
                            anchorFootprint.ProjectionMm));


            PlaneFootprint? best =
                null;


            double bestScore =
                double.NegativeInfinity;


            double bestAreaSimilarity =
                0.0;


            double bestWidthSimilarity =
                0.0;


            double bestHeightSimilarity =
                0.0;


            double bestCombinedSimilarity =
                0.0;


            foreach (PlaneFootprint candidate
                     in eligible)
            {
                double areaSimilarity =
                    RatioSimilarity(
                        anchorFootprint.GrossAreaMm2,
                        candidate.GrossAreaMm2);


                double widthSimilarity =
                    RatioSimilarity(
                        anchorFootprint.WidthMm,
                        candidate.WidthMm);


                double heightSimilarity =
                    RatioSimilarity(
                        anchorFootprint.HeightMm,
                        candidate.HeightMm);


                double combinedSimilarity =
                    (areaSimilarity *
                     0.50)
                    +
                    (widthSimilarity *
                     0.25)
                    +
                    (heightSimilarity *
                     0.25);


                // First gate: must really look like the same wall.
                if (areaSimilarity <
                    FootprintAreaSimilarityMinimum
                    ||
                    widthSimilarity <
                    FootprintWidthSimilarityMinimum
                    ||
                    heightSimilarity <
                    FootprintHeightSimilarityMinimum
                    ||
                    combinedSimilarity <
                    FootprintCombinedSimilarityMinimum)
                {
                    continue;
                }


                double separation =
                    Math.Abs(
                        candidate.ProjectionMm -
                        anchorFootprint.ProjectionMm);


                double separationScore =
                    maximumSeparation <=
                    0.0
                        ? 0.0
                        : separation /
                          maximumSeparation;


                // Geometry has authority.
                // Separation is only a tie breaker.
                double score =
                    (combinedSimilarity *
                     0.90)
                    +
                    (separationScore *
                     0.10);


                if (score >
                    bestScore)
                {
                    bestScore =
                        score;


                    best =
                        candidate;


                    bestAreaSimilarity =
                        areaSimilarity;


                    bestWidthSimilarity =
                        widthSimilarity;


                    bestHeightSimilarity =
                        heightSimilarity;


                    bestCombinedSimilarity =
                        combinedSimilarity;
                }
            }


            if (best ==
                null)
            {
                return;
            }


            // ========================================================
            // REPLACE ONLY THE REJECTED CANDIDATE
            // ========================================================

            string missingSide =
                missingPositive
                    ? "POSITIVE"
                    : "NEGATIVE";


            TankBoundaryFace rescuedBoundary =
                CreateBoundaryFromFootprint(
                    best,
                    scan,
                    missingSide);


            rescuedBoundary.Detected =
                true;


            rescuedBoundary.Status =
                "detected_footprint_rescue";


            rescuedBoundary.DetectionReason =
                $"Boundary recovered using component gross footprint. " +
                $"Area similarity: {bestAreaSimilarity:P1}; " +
                $"width similarity: {bestWidthSimilarity:P1}; " +
                $"height similarity: {bestHeightSimilarity:P1}; " +
                $"combined: {bestCombinedSimilarity:P1}.";


            if (missingPositive)
            {
                axis.PositiveBoundary =
                    rescuedBoundary;
            }
            else
            {
                axis.NegativeBoundary =
                    rescuedBoundary;
            }


            axis.SpanMm =
                Math.Abs(
                    axis.PositiveBoundary.ProjectionMm -
                    axis.NegativeBoundary.ProjectionMm);
        }


        // ============================================================
        // CREATE RESCUED BOUNDARY
        // ============================================================

        private static TankBoundaryFace
            CreateBoundaryFromFootprint(
                PlaneFootprint footprint,
                GeometryScanResult scan,
                string side)
        {
            FaceRecord? representative =
                scan.PlanarFaces
                .FirstOrDefault(
                    face =>
                        face.Index ==
                        footprint
                        .RepresentativeFaceRecordIndex);


            if (representative ==
                null)
            {
                return CreateMissingBoundary(
                    side);
            }


            return new TankBoundaryFace
            {
                Side =
                    side,


                FaceRecordIndex =
                    representative.Index,


                OccurrenceName =
                    representative.OccurrenceName,


                OccurrencePath =
                    representative.OccurrencePath,


                BodyIndex =
                    representative.BodyIndex,


                FaceIndex =
                    representative.FaceIndex,


                AreaMm2 =
                    representative.AreaMm2,


                // Diagnostic:
                // material actually present on component plane.
                PlaneAreaMm2 =
                    footprint.NetAreaMm2,


                // Diagnostic:
                // exterior envelope of component wall.
                ExpectedAreaMm2 =
                    footprint.GrossAreaMm2,


                AreaCoverageRatio =
                    footprint.GrossAreaMm2 <=
                    0.0
                        ? 0.0
                        : Math.Round(
                            footprint.NetAreaMm2 /
                            footprint.GrossAreaMm2,
                            6),


                ProjectionMm =
                    footprint.ProjectionMm,


                PointMm =
                    new Point3Data
                    {
                        X =
                            representative.PointMm.X,

                        Y =
                            representative.PointMm.Y,

                        Z =
                            representative.PointMm.Z
                    },


                Normal =
                    new Vector3Data
                    {
                        X =
                            representative.Normal.X,

                        Y =
                            representative.Normal.Y,

                        Z =
                            representative.Normal.Z
                    }
            };
        }


        // ============================================================
        // WARNINGS
        // ============================================================

        private static void AddBoundaryWarnings(
            List<TankAxisResult> axes,
            TankDetectionResult result)
        {
            foreach (TankAxisResult axis
                     in axes)
            {
                AddSingleBoundaryWarning(
                    axis,
                    axis.NegativeBoundary,
                    result);


                AddSingleBoundaryWarning(
                    axis,
                    axis.PositiveBoundary,
                    result);
            }
        }


        private static void AddSingleBoundaryWarning(
            TankAxisResult axis,
            TankBoundaryFace boundary,
            TankDetectionResult result)
        {
            if (!boundary.Detected)
            {
                result.Warnings.Add(
                    $"{axis.AxisName} {boundary.Side}: " +
                    $"superficie estructural no confirmada. " +
                    $"Candidata '{boundary.OccurrenceName}'.");


                return;
            }


            if (boundary.Status ==
                "detected_low_coverage")
            {
                result.Warnings.Add(
                    $"{axis.AxisName} {boundary.Side}: " +
                    $"límite aceptado con cobertura baja " +
                    $"({boundary.AreaCoverageRatio:P1}).");
            }
        }


        // ============================================================
        // RATIO SIMILARITY
        // ============================================================

        private static double RatioSimilarity(
            double a,
            double b)
        {
            double larger =
                Math.Max(
                    Math.Abs(a),
                    Math.Abs(b));


            if (larger <=
                0.0)
            {
                return 0.0;
            }


            return
                Math.Clamp(
                    Math.Min(
                        Math.Abs(a),
                        Math.Abs(b))
                    /
                    larger,
                    0.0,
                    1.0);
        }


        // ============================================================
        // AXIS NAMES
        // ============================================================

        private static void RenameAxes(
            List<TankAxisResult> axes)
        {
            for (int i = 0;
                 i < axes.Count;
                 i++)
            {
                axes[i].AxisName =
                    $"AXIS_{i + 1}";
            }
        }


        // ============================================================
        // CONFIDENCE
        // ============================================================

        private static double CalculateConfidence(
            List<OrientationFamily> families,
            List<TankAxisResult> axes,
            TankDetectionResult result)
        {
            if (families.Count <
                3)
            {
                return 0.0;
            }


            double dot01 =
                Math.Abs(
                    VectorMath.Dot(
                        families[0].Direction,
                        families[1].Direction));


            double dot02 =
                Math.Abs(
                    VectorMath.Dot(
                        families[0].Direction,
                        families[2].Direction));


            double dot12 =
                Math.Abs(
                    VectorMath.Dot(
                        families[1].Direction,
                        families[2].Direction));


            double orthogonality =
                1.0 -
                Math.Clamp(
                    (dot01 +
                     dot02 +
                     dot12) /
                    3.0,
                    0.0,
                    1.0);


            List<double> detectedCoverage =
                axes
                .SelectMany(
                    axis =>
                        new[]
                        {
                            axis.NegativeBoundary,
                            axis.PositiveBoundary
                        })
                .Where(
                    boundary =>
                        boundary.Detected)
                .Select(
                    boundary =>
                        Math.Clamp(
                            boundary.AreaCoverageRatio,
                            0.0,
                            1.0))
                .ToList();


            double coverageQuality =
                detectedCoverage.Count >
                0
                    ? detectedCoverage.Average()
                    : 0.0;


            double completeness =
                result.DetectedBoundaryCount /
                6.0;


            double confidence =
                (orthogonality *
                 0.60)
                +
                (coverageQuality *
                 0.30)
                +
                (completeness *
                 0.10);


            return Math.Round(
                Math.Clamp(
                    confidence,
                    0.0,
                    1.0),
                4);
        }


        // ============================================================
        // TANK NAME
        // ============================================================

        private static string GetTankName(
            GeometryScanResult scan)
        {
            if (!string.IsNullOrWhiteSpace(
                    scan.DocumentName))
            {
                string tankName =
                    Path.GetFileNameWithoutExtension(
                        scan.DocumentName);


                if (!string.IsNullOrWhiteSpace(
                        tankName))
                {
                    return tankName;
                }
            }


            if (!string.IsNullOrWhiteSpace(
                    scan.DocumentFullPath))
            {
                string tankName =
                    Path.GetFileNameWithoutExtension(
                        scan.DocumentFullPath);


                if (!string.IsNullOrWhiteSpace(
                        tankName))
                {
                    return tankName;
                }
            }


            return "UNKNOWN_TANK";
        }
    }
}