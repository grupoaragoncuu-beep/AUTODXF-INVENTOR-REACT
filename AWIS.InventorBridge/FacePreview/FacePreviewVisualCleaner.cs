using System;
using System.Collections.Generic;
using System.Linq;

namespace AWIS.InventorBridge.FacePreview
{
    // ================================================================
    // AWIS FACE PREVIEW COMPANION V0.4.0
    // VISUAL CLEANER
    //
    // INPUT:
    //   FacePreviewPackage ya proyectado por V0.3.
    //
    // OUTPUT:
    //   El mismo package, pero cada Face conserva únicamente
    //   geometría útil para reconocimiento visual.
    //
    // REGLAS:
    // - NO consulta Inventor.
    // - NO modifica Tank Frame.
    // - NO modifica detección V0.
    // - NO decide soldadura.
    // - NO cambia coordenadas.
    // ================================================================

    public class FacePreviewVisualCleaner
    {
        // ------------------------------------------------------------
        // CONFIGURACIÓN INICIAL V0.3.2
        // ------------------------------------------------------------

        // Basura verdaderamente microscópica.
        private const double MinimumDetailSizeMm =
            5.0;


        // Tira estructural periférica:
        // larga, delgada y pegada al borde.
        private const double PeripheralStripMaxThicknessMm =
            80.0;

        private const double PeripheralStripMinAspectRatio =
            8.0;

        private const double PeripheralEdgeDistanceMm =
            40.0;


        // Si menos de este porcentaje del bounding box del loop
        // cae dentro de la pared oficial, se elimina.
        private const double MinimumEnvelopeOverlapRatio =
            0.20;


        // Duplicados geométricos de una misma occurrence.
        private const double DuplicateCenterToleranceMm =
            1.0;

        private const double DuplicateSizeToleranceMm =
            1.0;

        private const double DuplicateAreaToleranceRatio =
            0.02;


        public void Clean(
            FacePreviewPackage package)
        {
            HashSet<string> structuralOccurrences =
                BuildStructuralOccurrenceSet(
                    package);


            foreach (FacePreviewRecord face
                     in package.Faces)
            {
                CleanFace(
                    face,
                    structuralOccurrences);
            }
        }


        // ============================================================
        // STRUCTURAL OCCURRENCES
        //
        // Se obtienen automáticamente de las seis DetectionSource
        // producidas por V0. No existen nombres hardcoded de cliente.
        // ============================================================

        private HashSet<string> BuildStructuralOccurrenceSet(
            FacePreviewPackage package)
        {
            HashSet<string> result =
                new HashSet<string>(
                    StringComparer.OrdinalIgnoreCase);


            foreach (FacePreviewRecord face
                     in package.Faces)
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


        // ============================================================
        // FACE CLEANING
        // ============================================================

        private void CleanFace(
            FacePreviewRecord face,
            HashSet<string> structuralOccurrences)
        {
            List<PreviewEntity> rawEntities =
                face.Entities.ToList();


            FacePreviewCleaningStatistics stats =
                new FacePreviewCleaningStatistics
                {
                    RawEntityCount =
                        rawEntities.Count
                };


            // --------------------------------------------------------
            // PASO 1:
            // Detectar grupos periféricos completos.
            //
            // Si el OUTER LOOP de una occurrence/source-face es una
            // tira periférica, también eliminamos sus INNER LOOPS.
            // Esto evita dejar flotando una fila de barrenos después
            // de quitar el soporte que los contiene.
            // --------------------------------------------------------

            HashSet<EntityGroupKey> peripheralGroups =
                FindPeripheralGroups(
                    face,
                    rawEntities);


            List<PreviewEntity> candidates =
                new List<PreviewEntity>();


            foreach (PreviewEntity entity
                     in rawEntities)
            {
                CleaningDecision decision =
                    ClassifyEntity(
                        face,
                        entity,
                        structuralOccurrences,
                        peripheralGroups);


                switch (decision)
                {
                    case CleaningDecision.KeepWallOpening:
                        entity.VisualRole =
                            "WALL_OPENING";

                        candidates.Add(
                            entity);
                        break;


                    case CleaningDecision.KeepAccessory:
                        entity.VisualRole =
                            "ACCESSORY";

                        candidates.Add(
                            entity);
                        break;


                    case CleaningDecision.RejectOwnWallOuter:
                        stats.RejectedOwnWallOuter++;
                        break;


                    case CleaningDecision.RejectAdjacentWall:
                        stats.RejectedAdjacentWall++;
                        break;


                    case CleaningDecision.RejectPeripheralSupport:
                        stats.RejectedPeripheralSupport++;
                        break;


                    case CleaningDecision.RejectOutsideEnvelope:
                        stats.RejectedOutsideEnvelope++;
                        break;


                    case CleaningDecision.RejectSmallNoise:
                        stats.RejectedSmall++;
                        break;
                }
            }


            // --------------------------------------------------------
            // PASO 2:
            // Remover duplicados después del filtrado principal.
            // --------------------------------------------------------

            candidates =
                RemoveDuplicates(
                    candidates,
                    stats);


            face.Entities =
                candidates;


            stats.DisplayEntityCount =
                candidates.Count;


            face.Cleaning =
                stats;
        }


        // ============================================================
        // ENTITY CLASSIFICATION
        // ============================================================

        private CleaningDecision ClassifyEntity(
            FacePreviewRecord face,
            PreviewEntity entity,
            HashSet<string> structuralOccurrences,
            HashSet<EntityGroupKey> peripheralGroups)
        {
            // --------------------------------------------------------
            // 1. Geometría de la propia pared.
            //
            // Outer loop:
            // ya está representado por face.Envelope.
            //
            // Inner loop:
            // conservar como opening real.
            // --------------------------------------------------------

            if (IsOwnWall(
                    face,
                    entity))
            {
                if (string.Equals(
                        entity.LoopType,
                        "INNER",
                        StringComparison.OrdinalIgnoreCase))
                {
                    // V0.3.2:
                    // Un opening de la propia pared solo se conserva
                    // si realmente intersecta el Envelope oficial.
                    //
                    // Esto elimina barrenados/perforaciones que
                    // pertenecen a pestañas o extensiones de la placa
                    // pero quedan completamente fuera de la vista
                    // canónica de la pared.
                    double wallOpeningOverlapRatio =
                        CalculateEnvelopeOverlapRatio(
                            face,
                            entity);


                    if (wallOpeningOverlapRatio <
                        MinimumEnvelopeOverlapRatio)
                    {
                        return
                            CleaningDecision
                                .RejectOutsideEnvelope;
                    }


                    return
                        CleaningDecision
                            .KeepWallOpening;
                }


                return
                    CleaningDecision
                        .RejectOwnWallOuter;
            }


            // --------------------------------------------------------
            // 2. Otra de las seis paredes principales.
            // --------------------------------------------------------

            if (structuralOccurrences.Contains(
                    entity.OccurrencePath))
            {
                return
                    CleaningDecision
                        .RejectAdjacentWall;
            }


            // --------------------------------------------------------
            // 3. Grupo identificado como soporte/tira periférica.
            // --------------------------------------------------------

            EntityGroupKey groupKey =
                BuildGroupKey(
                    entity);


            if (peripheralGroups.Contains(
                    groupKey))
            {
                return
                    CleaningDecision
                        .RejectPeripheralSupport;
            }


            // --------------------------------------------------------
            // 4. Entidad mayormente fuera de la pared oficial.
            // --------------------------------------------------------

            double overlapRatio =
                CalculateEnvelopeOverlapRatio(
                    face,
                    entity);


            if (overlapRatio <
                MinimumEnvelopeOverlapRatio)
            {
                return
                    CleaningDecision
                        .RejectOutsideEnvelope;
            }


            // --------------------------------------------------------
            // 5. Ruido microscópico.
            //
            // Importante:
            // los openings de la propia pared ya fueron resueltos
            // arriba y por eso no pueden desaparecer aquí.
            // --------------------------------------------------------

            if (IsSmallNoise(
                    entity))
            {
                return
                    CleaningDecision
                        .RejectSmallNoise;
            }


            // --------------------------------------------------------
            // Lo restante se conserva como geometría visual.
            // Aún NO significa "weldable".
            // --------------------------------------------------------

            return
                CleaningDecision
                    .KeepAccessory;
        }


        private bool IsOwnWall(
            FacePreviewRecord face,
            PreviewEntity entity)
        {
            // Legacy behavior for the V0 anchor occurrence.
            if (string.Equals(
                    face
                        .DetectionSource
                        .OccurrencePath,
                    entity.OccurrencePath,
                    StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }


            // V0.4.0: a logical FACE may contain additional physical
            // plate segments. Match the exact planar source face so
            // its OUTER loop is structural and its INNER loops remain
            // visible as real wall openings.
            if (face.PhysicalWall?.Segments == null)
            {
                return false;
            }


            return face.PhysicalWall.Segments.Any(
                segment =>
                    string.Equals(
                        segment.OccurrencePath,
                        entity.OccurrencePath,
                        StringComparison.OrdinalIgnoreCase)
                    &&
                    segment.SourceBodyIndex ==
                        entity.BodyIndex
                    &&
                    segment.SourceFaceIndex ==
                        entity.SourceFaceIndex);
        }


        // ============================================================
        // PERIPHERAL SUPPORT GROUPS
        // ============================================================

        private HashSet<EntityGroupKey> FindPeripheralGroups(
            FacePreviewRecord face,
            List<PreviewEntity> entities)
        {
            HashSet<EntityGroupKey> result =
                new HashSet<EntityGroupKey>();


            foreach (PreviewEntity entity
                     in entities)
            {
                if (!string.Equals(
                        entity.LoopType,
                        "OUTER",
                        StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }


                if (IsPeripheralSupport(
                        face,
                        entity))
                {
                    result.Add(
                        BuildGroupKey(
                            entity));
                }
            }


            return result;
        }


        private bool IsPeripheralSupport(
            FacePreviewRecord face,
            PreviewEntity entity)
        {
            double width =
                Math.Abs(
                    entity.ProjectedWidthMm);

            double height =
                Math.Abs(
                    entity.ProjectedHeightMm);


            double longSide =
                Math.Max(
                    width,
                    height);

            double shortSide =
                Math.Min(
                    width,
                    height);


            if (shortSide <=
                1e-9)
            {
                return true;
            }


            double aspectRatio =
                longSide /
                shortSide;


            if (shortSide >
                    PeripheralStripMaxThicknessMm
                ||
                aspectRatio <
                    PeripheralStripMinAspectRatio)
            {
                return false;
            }


            return IsNearEnvelopeEdge(
                face,
                entity);
        }


        private bool IsNearEnvelopeEdge(
            FacePreviewRecord face,
            PreviewEntity entity)
        {
            EntityBounds bounds =
                GetBounds(
                    entity);


            EntityBounds wallBounds =
                GetWallBounds(
                    face);


            double leftDistance =
                Math.Abs(
                    bounds.MinX -
                    wallBounds.MinX);


            double rightDistance =
                Math.Abs(
                    wallBounds.MaxX -
                    bounds.MaxX);


            double bottomDistance =
                Math.Abs(
                    bounds.MinY -
                    wallBounds.MinY);


            double topDistance =
                Math.Abs(
                    wallBounds.MaxY -
                    bounds.MaxY);


            double nearest =
                Math.Min(
                    Math.Min(
                        leftDistance,
                        rightDistance),
                    Math.Min(
                        bottomDistance,
                        topDistance));


            return nearest <=
                PeripheralEdgeDistanceMm;
        }


        // ============================================================
        // ENVELOPE OVERLAP
        //
        // V0.3.2 usa bounding-box overlap deliberadamente.
        // Para visualización no necesitamos clipping poligonal exacto.
        // ============================================================

        private double CalculateEnvelopeOverlapRatio(
            FacePreviewRecord face,
            PreviewEntity entity)
        {
            EntityBounds bounds =
                GetBounds(
                    entity);


            double width =
                Math.Max(
                    0.0,
                    bounds.MaxX -
                    bounds.MinX);


            double height =
                Math.Max(
                    0.0,
                    bounds.MaxY -
                    bounds.MinY);


            double entityBoxArea =
                width *
                height;


            if (entityBoxArea <=
                1e-9)
            {
                return 0.0;
            }


            EntityBounds wallBounds =
                GetWallBounds(
                    face);


            double intersectionMinX =
                Math.Max(
                    wallBounds.MinX,
                    bounds.MinX);


            double intersectionMaxX =
                Math.Min(
                    wallBounds.MaxX,
                    bounds.MaxX);


            double intersectionMinY =
                Math.Max(
                    wallBounds.MinY,
                    bounds.MinY);


            double intersectionMaxY =
                Math.Min(
                    wallBounds.MaxY,
                    bounds.MaxY);


            double intersectionWidth =
                Math.Max(
                    0.0,
                    intersectionMaxX -
                    intersectionMinX);


            double intersectionHeight =
                Math.Max(
                    0.0,
                    intersectionMaxY -
                    intersectionMinY);


            double intersectionArea =
                intersectionWidth *
                intersectionHeight;


            return intersectionArea /
                entityBoxArea;
        }


        // ============================================================
        // SMALL NOISE
        // ============================================================

        private bool IsSmallNoise(
            PreviewEntity entity)
        {
            return
                Math.Abs(
                    entity.ProjectedWidthMm)
                <
                MinimumDetailSizeMm
                &&
                Math.Abs(
                    entity.ProjectedHeightMm)
                <
                MinimumDetailSizeMm;
        }


        // ============================================================
        // DUPLICATE REMOVAL
        // ============================================================

        private List<PreviewEntity> RemoveDuplicates(
            List<PreviewEntity> input,
            FacePreviewCleaningStatistics stats)
        {
            List<PreviewEntity> result =
                new List<PreviewEntity>();


            foreach (PreviewEntity candidate
                     in input)
            {
                bool duplicate =
                    false;


                foreach (PreviewEntity accepted
                         in result)
                {
                    if (AreDuplicates(
                            accepted,
                            candidate))
                    {
                        duplicate =
                            true;

                        break;
                    }
                }


                if (duplicate)
                {
                    stats.RejectedDuplicate++;

                    continue;
                }


                result.Add(
                    candidate);
            }


            return result;
        }


        private bool AreDuplicates(
            PreviewEntity a,
            PreviewEntity b)
        {
            // Para evitar borrar dos componentes diferentes que
            // casualmente tengan forma y posición similares.
            if (!string.Equals(
                    a.OccurrencePath,
                    b.OccurrencePath,
                    StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }


            if (!string.Equals(
                    a.LoopType,
                    b.LoopType,
                    StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }


            EntityBounds aBounds =
                GetBounds(
                    a);

            EntityBounds bBounds =
                GetBounds(
                    b);


            double aCenterX =
                (aBounds.MinX +
                 aBounds.MaxX)
                /
                2.0;

            double aCenterY =
                (aBounds.MinY +
                 aBounds.MaxY)
                /
                2.0;


            double bCenterX =
                (bBounds.MinX +
                 bBounds.MaxX)
                /
                2.0;

            double bCenterY =
                (bBounds.MinY +
                 bBounds.MaxY)
                /
                2.0;


            if (Math.Abs(
                    aCenterX -
                    bCenterX)
                >
                DuplicateCenterToleranceMm)
            {
                return false;
            }


            if (Math.Abs(
                    aCenterY -
                    bCenterY)
                >
                DuplicateCenterToleranceMm)
            {
                return false;
            }


            if (Math.Abs(
                    a.ProjectedWidthMm -
                    b.ProjectedWidthMm)
                >
                DuplicateSizeToleranceMm)
            {
                return false;
            }


            if (Math.Abs(
                    a.ProjectedHeightMm -
                    b.ProjectedHeightMm)
                >
                DuplicateSizeToleranceMm)
            {
                return false;
            }


            double referenceArea =
                Math.Max(
                    Math.Abs(
                        a.ProjectedAreaMm2),
                    Math.Abs(
                        b.ProjectedAreaMm2));


            if (referenceArea <=
                1e-9)
            {
                return true;
            }


            double areaDifferenceRatio =
                Math.Abs(
                    a.ProjectedAreaMm2 -
                    b.ProjectedAreaMm2)
                /
                referenceArea;


            return areaDifferenceRatio <=
                DuplicateAreaToleranceRatio;
        }


        // ============================================================
        // GEOMETRY HELPERS
        // ============================================================

        private EntityBounds GetWallBounds(
            FacePreviewRecord face)
        {
            if (face.PhysicalWall != null
                &&
                face.PhysicalWall.Resolved
                &&
                face.PhysicalWall.Bounds != null
                &&
                face.PhysicalWall.Bounds.MaxU >
                    face.PhysicalWall.Bounds.MinU
                &&
                face.PhysicalWall.Bounds.MaxV >
                    face.PhysicalWall.Bounds.MinV)
            {
                return new EntityBounds
                {
                    MinX =
                        face.PhysicalWall.Bounds.MinU,

                    MaxX =
                        face.PhysicalWall.Bounds.MaxU,

                    MinY =
                        face.PhysicalWall.Bounds.MinV,

                    MaxY =
                        face.PhysicalWall.Bounds.MaxV
                };
            }


            return new EntityBounds
            {
                MinX = 0.0,
                MaxX = face.WidthMm,
                MinY = 0.0,
                MaxY = face.HeightMm
            };
        }


        private EntityBounds GetBounds(
            PreviewEntity entity)
        {
            if (entity.Points == null ||
                entity.Points.Count == 0)
            {
                return new EntityBounds();
            }


            return new EntityBounds
            {
                MinX =
                    entity.Points.Min(
                        point =>
                            point.X),

                MaxX =
                    entity.Points.Max(
                        point =>
                            point.X),

                MinY =
                    entity.Points.Min(
                        point =>
                            point.Y),

                MaxY =
                    entity.Points.Max(
                        point =>
                            point.Y)
            };
        }


        private EntityGroupKey BuildGroupKey(
            PreviewEntity entity)
        {
            return new EntityGroupKey(
                entity.OccurrencePath,
                entity.BodyIndex,
                entity.SourceFaceIndex);
        }


        // ============================================================
        // INTERNAL TYPES
        // ============================================================

        private enum CleaningDecision
        {
            KeepWallOpening,
            KeepAccessory,

            RejectOwnWallOuter,
            RejectAdjacentWall,
            RejectPeripheralSupport,
            RejectOutsideEnvelope,
            RejectSmallNoise
        }


        private class EntityBounds
        {
            public double MinX;

            public double MaxX;

            public double MinY;

            public double MaxY;
        }


        private readonly struct EntityGroupKey :
            IEquatable<EntityGroupKey>
        {
            private readonly string
                _occurrencePath;

            private readonly int
                _bodyIndex;

            private readonly int
                _sourceFaceIndex;


            public EntityGroupKey(
                string occurrencePath,
                int bodyIndex,
                int sourceFaceIndex)
            {
                _occurrencePath =
                    occurrencePath ?? "";

                _bodyIndex =
                    bodyIndex;

                _sourceFaceIndex =
                    sourceFaceIndex;
            }


            public bool Equals(
                EntityGroupKey other)
            {
                return
                    string.Equals(
                        _occurrencePath,
                        other._occurrencePath,
                        StringComparison.OrdinalIgnoreCase)
                    &&
                    _bodyIndex ==
                        other._bodyIndex
                    &&
                    _sourceFaceIndex ==
                        other._sourceFaceIndex;
            }


            public override bool Equals(
                object? obj)
            {
                return
                    obj
                    is EntityGroupKey other
                    &&
                    Equals(
                        other);
            }


            public override int GetHashCode()
            {
                return HashCode.Combine(
                    StringComparer
                        .OrdinalIgnoreCase
                        .GetHashCode(
                            _occurrencePath),
                    _bodyIndex,
                    _sourceFaceIndex);
            }
        }
    }
}
