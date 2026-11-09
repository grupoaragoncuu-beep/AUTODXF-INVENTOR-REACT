using System;
using System.Collections.Generic;
using System.Linq;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // ================================================================
    // V0.3.3
    // PHYSICAL WELD BOUNDARY SELECTOR
    //
    // OTC brace case:
    // - Four narrow coplanar strips form one rectangular frame.
    // - Every strip arrives as a CLOSED coincident face loop.
    // - A closed strip contains two long edges, but only the edge on the
    //   external perimeter of the frame is a physical weld candidate.
    //
    // This pass is intentionally conservative. It only transforms groups
    // that resolve unambiguously as exactly 2 horizontal + 2 vertical
    // narrow strips under the same parent occurrence path.
    // ================================================================

    public class WeldPhysicalBoundarySelector
    {
        public int Apply(
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds,
            WeldInterfaceStatistics statistics,
            List<string> warnings)
        {
            if (!thresholds.ResolveBraceFrameOuterWeldEdges)
            {
                return 0;
            }


            List<StripCandidate> candidates =
                CollectCandidates(
                    wall,
                    thresholds);


            int groupsResolved =
                0;


            foreach (IGrouping<string, StripCandidate> parentGroup
                     in candidates
                         .Where(
                             c =>
                                 !string.IsNullOrWhiteSpace(
                                     c.ParentOccurrencePath))
                         .GroupBy(
                             c => c.ParentOccurrencePath,
                             StringComparer.OrdinalIgnoreCase))
            {
                List<StripCandidate> group =
                    parentGroup
                        .ToList();


                // Conservative V0.3.3 contract:
                // do not guess inside complex parent assemblies.
                if (group.Count != 4)
                {
                    continue;
                }


                List<StripCandidate> horizontal =
                    group
                        .Where(
                            c => c.Orientation == "H")
                        .OrderBy(
                            c => c.CenterY)
                        .ToList();


                List<StripCandidate> vertical =
                    group
                        .Where(
                            c => c.Orientation == "V")
                        .OrderBy(
                            c => c.CenterX)
                        .ToList();


                if (horizontal.Count != 2
                    ||
                    vertical.Count != 2)
                {
                    continue;
                }


                if (!FormsClosedFrame(
                        horizontal,
                        vertical,
                        thresholds))
                {
                    continue;
                }


                double frameMinX =
                    group.Min(
                        c => c.MinX);

                double frameMaxX =
                    group.Max(
                        c => c.MaxX);

                double frameMinY =
                    group.Min(
                        c => c.MinY);

                double frameMaxY =
                    group.Max(
                        c => c.MaxY);


                double frameCenterX =
                    (frameMinX + frameMaxX)
                    /
                    2.0;

                double frameCenterY =
                    (frameMinY + frameMaxY)
                    /
                    2.0;


                string groupId =
                    BuildGroupId(
                        wall.FaceId,
                        parentGroup.Key);


                int converted =
                    0;


                foreach (StripCandidate strip
                         in group)
                {
                    string side =
                        DetermineSide(
                            strip,
                            frameCenterX,
                            frameCenterY);


                    if (string.IsNullOrWhiteSpace(
                            side))
                    {
                        continue;
                    }


                    ConvertToPhysicalOuterEdge(
                        strip,
                        side,
                        groupId,
                        wall);


                    strip.Record
                        .BoundaryFilter
                        .BraceFrameClosedLoopsConverted++;


                    if (!strip.Record
                            .BoundaryFilter
                            .BraceFrameGroupIds
                            .Contains(
                                groupId,
                                StringComparer.OrdinalIgnoreCase))
                    {
                        strip.Record
                            .BoundaryFilter
                            .BraceFrameGroupIds
                            .Add(
                                groupId);
                    }


                    if (!strip.Record
                            .Evidence
                            .Contains(
                                "brace_frame_outer_weld_edge_selected",
                                StringComparer.OrdinalIgnoreCase))
                    {
                        strip.Record
                            .Evidence
                            .Add(
                                "brace_frame_outer_weld_edge_selected");
                    }


                    converted++;
                }


                if (converted == 4)
                {
                    groupsResolved++;

                    statistics
                        .BraceFrameGroupsResolved++;

                    statistics
                        .BraceFrameClosedLoopsConverted
                        +=
                        converted;
                }
            }


            if (groupsResolved > 0)
            {
                warnings.Add(
                    $"{wall.FaceId}: V0.3.3 resolved {groupsResolved} brace-frame group(s); each narrow coincident strip now exports one external physical weld edge instead of both long edges of its closed loop.");
            }


            return groupsResolved;
        }


        private List<StripCandidate> CollectCandidates(
            WeldInterfaceFaceRecord wall,
            WeldInterfaceThresholds thresholds)
        {
            List<StripCandidate> result =
                new List<StripCandidate>();


            foreach (WeldInterfaceRecord record
                     in wall.Interfaces)
            {
                string parent =
                    ParentOccurrencePath(
                        record.ComponentOccurrencePath);


                foreach (WeldInterfacePath path
                         in record.Paths)
                {
                    if (!string.Equals(
                            path.SourceKind,
                            "COINCIDENT_FACE_LOOP",
                            StringComparison.OrdinalIgnoreCase)
                        ||
                        !path.Closed
                        ||
                        !string.Equals(
                            path.GeometryType,
                            "CLOSED",
                            StringComparison.OrdinalIgnoreCase)
                        ||
                        !string.Equals(
                            path.BoundaryRole,
                            "OUTER",
                            StringComparison.OrdinalIgnoreCase)
                        ||
                        path.FaceLocalPointsMm.Count < 4)
                    {
                        continue;
                    }


                    double minX =
                        path.FaceLocalPointsMm.Min(
                            p => p.X);

                    double maxX =
                        path.FaceLocalPointsMm.Max(
                            p => p.X);

                    double minY =
                        path.FaceLocalPointsMm.Min(
                            p => p.Y);

                    double maxY =
                        path.FaceLocalPointsMm.Max(
                            p => p.Y);


                    double width =
                        maxX - minX;

                    double height =
                        maxY - minY;

                    double minor =
                        Math.Min(
                            width,
                            height);

                    double major =
                        Math.Max(
                            width,
                            height);


                    if (minor <=
                        thresholds.CurveDedupeToleranceMm)
                    {
                        continue;
                    }


                    if (minor >
                        thresholds.BraceFrameMaximumStripWidthMm)
                    {
                        continue;
                    }


                    if (major / minor <
                        thresholds.BraceFrameMinimumAspectRatio)
                    {
                        continue;
                    }


                    result.Add(
                        new StripCandidate
                        {
                            Record = record,
                            Path = path,
                            ParentOccurrencePath = parent,
                            MinX = minX,
                            MaxX = maxX,
                            MinY = minY,
                            MaxY = maxY,
                            Width = width,
                            Height = height,
                            Orientation =
                                width >= height
                                    ? "H"
                                    : "V"
                        });
                }
            }


            return result;
        }


        private bool FormsClosedFrame(
            IReadOnlyList<StripCandidate> horizontal,
            IReadOnlyList<StripCandidate> vertical,
            WeldInterfaceThresholds thresholds)
        {
            StripCandidate top =
                horizontal[0];

            StripCandidate bottom =
                horizontal[1];

            StripCandidate left =
                vertical[0];

            StripCandidate right =
                vertical[1];


            if (top.CenterY >= bottom.CenterY
                ||
                left.CenterX >= right.CenterX)
            {
                return false;
            }


            double largestStripWidth =
                Math.Max(
                    Math.Max(
                        top.MinorWidth,
                        bottom.MinorWidth),
                    Math.Max(
                        left.MinorWidth,
                        right.MinorWidth));


            double tolerance =
                largestStripWidth / 2.0
                +
                thresholds.BraceFrameClosureToleranceMm;


            bool horizontalSpansVerticals =
                ContainsWithTolerance(
                    top.MinX,
                    top.MaxX,
                    left.CenterX,
                    tolerance)
                &&
                ContainsWithTolerance(
                    top.MinX,
                    top.MaxX,
                    right.CenterX,
                    tolerance)
                &&
                ContainsWithTolerance(
                    bottom.MinX,
                    bottom.MaxX,
                    left.CenterX,
                    tolerance)
                &&
                ContainsWithTolerance(
                    bottom.MinX,
                    bottom.MaxX,
                    right.CenterX,
                    tolerance);


            bool verticalSpansHorizontals =
                ContainsWithTolerance(
                    left.MinY,
                    left.MaxY,
                    top.CenterY,
                    tolerance)
                &&
                ContainsWithTolerance(
                    left.MinY,
                    left.MaxY,
                    bottom.CenterY,
                    tolerance)
                &&
                ContainsWithTolerance(
                    right.MinY,
                    right.MaxY,
                    top.CenterY,
                    tolerance)
                &&
                ContainsWithTolerance(
                    right.MinY,
                    right.MaxY,
                    bottom.CenterY,
                    tolerance);


            return
                horizontalSpansVerticals
                &&
                verticalSpansHorizontals;
        }


        private bool ContainsWithTolerance(
            double min,
            double max,
            double value,
            double tolerance)
        {
            return
                value >= min - tolerance
                &&
                value <= max + tolerance;
        }


        private string DetermineSide(
            StripCandidate strip,
            double frameCenterX,
            double frameCenterY)
        {
            if (strip.Orientation == "V")
            {
                return
                    strip.CenterX < frameCenterX
                        ? "LEFT"
                        : "RIGHT";
            }


            if (strip.Orientation == "H")
            {
                return
                    strip.CenterY < frameCenterY
                        ? "TOP"
                        : "BOTTOM";
            }


            return "";
        }


        private void ConvertToPhysicalOuterEdge(
            StripCandidate strip,
            string side,
            string groupId,
            WeldInterfaceFaceRecord wall)
        {
            WeldPoint2Mm p0;
            WeldPoint2Mm p1;


            switch (side)
            {
                case "LEFT":
                    p0 = Point2(
                        strip.MinX,
                        strip.MinY);

                    p1 = Point2(
                        strip.MinX,
                        strip.MaxY);
                    break;

                case "RIGHT":
                    p0 = Point2(
                        strip.MaxX,
                        strip.MinY);

                    p1 = Point2(
                        strip.MaxX,
                        strip.MaxY);
                    break;

                case "TOP":
                    p0 = Point2(
                        strip.MinX,
                        strip.MinY);

                    p1 = Point2(
                        strip.MaxX,
                        strip.MinY);
                    break;

                case "BOTTOM":
                    p0 = Point2(
                        strip.MinX,
                        strip.MaxY);

                    p1 = Point2(
                        strip.MaxX,
                        strip.MaxY);
                    break;

                default:
                    return;
            }


            strip.Path.OriginalClosedLoopLengthMm ??=
                strip.Path.LengthMm;

            strip.Path.FaceLocalPointsMm =
                new List<WeldPoint2Mm>
                {
                    p0,
                    p1
                };

            strip.Path.Model3DPointsMm =
                new List<WeldPoint3Mm>
                {
                    ToModelPoint(
                        p0,
                        wall),
                    ToModelPoint(
                        p1,
                        wall)
                };

            strip.Path.LengthMm =
                Math.Round(
                    side == "LEFT"
                    ||
                    side == "RIGHT"
                        ? strip.Height
                        : strip.Width,
                    3);

            strip.Path.Closed =
                false;

            strip.Path.GeometryType =
                "LINEAR";

            strip.Path.BoundaryRole =
                "OUTER";

            strip.Path.BoundarySelectionReason =
                "BRACE_FRAME_OUTER_PERIMETER_EDGE";

            strip.Path.PhysicalMemberType =
                "BRACE_FRAME";

            strip.Path.PhysicalMemberGroupId =
                groupId;

            strip.Path.PhysicalSideRole =
                side;

            strip.Path.PhysicalBoundaryRole =
                "OUTER_WELD_EDGE";
        }


        private WeldPoint2Mm Point2(
            double x,
            double y)
        {
            return new WeldPoint2Mm
            {
                X = Math.Round(x, 3),
                Y = Math.Round(y, 3)
            };
        }


        private WeldPoint3Mm ToModelPoint(
            WeldPoint2Mm point,
            WeldInterfaceFaceRecord wall)
        {
            return new WeldPoint3Mm
            {
                X = Math.Round(
                    wall.OriginMm.X
                    +
                    wall.LocalU.X * point.X
                    +
                    wall.LocalV.X * point.Y,
                    3),

                Y = Math.Round(
                    wall.OriginMm.Y
                    +
                    wall.LocalU.Y * point.X
                    +
                    wall.LocalV.Y * point.Y,
                    3),

                Z = Math.Round(
                    wall.OriginMm.Z
                    +
                    wall.LocalU.Z * point.X
                    +
                    wall.LocalV.Z * point.Y,
                    3)
            };
        }


        private string ParentOccurrencePath(
            string occurrencePath)
        {
            if (string.IsNullOrWhiteSpace(
                    occurrencePath))
            {
                return "";
            }


            int separator =
                occurrencePath
                    .LastIndexOf('/');


            if (separator <= 0)
            {
                return "";
            }


            return occurrencePath
                .Substring(
                    0,
                    separator);
        }


        private string BuildGroupId(
            string faceId,
            string parentOccurrencePath)
        {
            return
                $"{faceId}::BRACE_FRAME::{parentOccurrencePath}";
        }


        private sealed class StripCandidate
        {
            public WeldInterfaceRecord Record { get; set; } =
                null!;

            public WeldInterfacePath Path { get; set; } =
                null!;

            public string ParentOccurrencePath { get; set; } =
                "";

            public string Orientation { get; set; } =
                "";

            public double MinX { get; set; }

            public double MaxX { get; set; }

            public double MinY { get; set; }

            public double MaxY { get; set; }

            public double Width { get; set; }

            public double Height { get; set; }

            public double CenterX =>
                (MinX + MaxX) / 2.0;

            public double CenterY =>
                (MinY + MaxY) / 2.0;

            public double MinorWidth =>
                Math.Min(
                    Width,
                    Height);
        }
    }
}
