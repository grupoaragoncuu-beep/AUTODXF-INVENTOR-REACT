using Inventor;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // Additive producer contract: legacy Faces[] remains the validated exterior flow.
    public class WeldSurfaceVariantBuilder
    {
        private readonly WeldInterfaceBroadPhase broad = new();
        private readonly WeldInterfaceExactDetector exact = new();
        private readonly WeldPhysicalBoundarySelector selector = new();

        public void Build(WeldInterfacePackage package, List<ComponentOccurrence> occurrences,
            Inventor.Application application, HashSet<string> structuralPaths)
        {
            foreach (var parent in package.Faces)
            {
                foreach (var sourceSegment in parent.PhysicalWall.Segments)
                {
                    foreach (string side in new[] { "EXTERIOR", "INTERIOR" })
                    {
                        var view = MakeView(parent, sourceSegment, side);
                        package.SurfaceVariants.Add(view);
                        try
                        {
                            WeldContactPlaneResolver.Resolve(view.Geometry, occurrences, view.Warnings);
                            if (!view.Geometry.ContactPlane.Resolved)
                                throw new InvalidOperationException("Native exterior reference plane unavailable; no surface candidates generated");
                            if (side == "INTERIOR") ResolveInner(view, occurrences, package.Thresholds);
                            view.SurfaceNormal = view.Geometry.ContactPlane.Normal;
                            view.Resolved = true;
                            view.ResolutionStatus = side == "INTERIOR" ? "native_inner_face_resolved" : "native_segment_exterior_resolved";
                            Analyze(view, occurrences, application, structuralPaths, package.Thresholds);
                            if (view.Statistics.ExactAnalysisFailures > 0 || view.Statistics.SectionFailures > 0 || view.Statistics.EdgeSamplingFailures > 0)
                                view.Warnings.Add("Geometry export has native analysis/sampling failures; review surface Statistics and interfaces before selecting welds.");
                        }
                        catch (Exception ex)
                        {
                            view.Resolved = false;
                            view.ResolutionStatus = "unresolved_surface_geometry";
                            view.Geometry.Interfaces.Clear();
                            view.Warnings.Add(ex.GetType().Name + ": " + ex.Message);
                        }
                        if (!view.Resolved || view.Warnings.Count > 0)
                            package.Warnings.Add($"{view.SurfaceId}: {view.ResolutionStatus}; review SurfaceVariants.Warnings.");
                    }
                }
                if (parent.PhysicalWall.Segments.Count == 0)
                    package.Warnings.Add($"{parent.FaceId}: no physical segments available; SurfaceVariants not generated.");
            }
        }

        private WeldSurfaceVariant MakeView(WeldInterfaceFaceRecord parent, WeldPhysicalWallSegment source, string side)
        {
            // Detached geometry objects prevent side scans from modifying exterior data or statistics.
            var wall = JsonSerializer.Deserialize<WeldInterfaceFaceRecord>(JsonSerializer.Serialize(parent))
                ?? throw new InvalidOperationException("Unable to clone canonical face");
            var segment = wall.PhysicalWall.Segments.Single(s => s.SegmentId == source.SegmentId);
            segment.IsAnchorSegment = true;
            wall.Interfaces.Clear();
            wall.SegmentId = segment.SegmentId;
            wall.SurfaceSide = side;
            wall.FaceId = $"{parent.FaceId}_{segment.SegmentId}_{side}";
            wall.PhysicalWall.Segments = new List<WeldPhysicalWallSegment> { segment };
            wall.PhysicalWall.SegmentCount = 1;
            wall.PhysicalWall.Bounds = segment.Bounds;
            wall.PhysicalWall.OuterLoop = segment.OuterLoop;
            wall.PhysicalWall.StructuralSeams.Clear(); // Assembly panel joins do not belong to a separate segment job.
            wall.StructuralSource = new WeldStructuralSource {
                OccurrenceName = segment.OccurrenceName, OccurrencePath = segment.OccurrencePath,
                BodyIndex = segment.SourceBodyIndex, FaceIndex = segment.SourceFaceIndex };
            return new WeldSurfaceVariant {
                SurfaceId = wall.FaceId, ParentFaceId = parent.FaceId, SegmentId = segment.SegmentId,
                SurfaceSide = side, Geometry = wall,
                InteriorViewRule = side == "INTERIOR"
                    ? "U_VIEW=MAX_U-U_CANONICAL; V_VIEW=V_CANONICAL-MIN_V; IN_PLANE_ROTATION_UNRESOLVED"
                    : "U_VIEW=U_CANONICAL-MIN_U; V_VIEW=V_CANONICAL-MIN_V; IN_PLANE_ROTATION_UNRESOLVED" };
        }

        private void ResolveInner(WeldSurfaceVariant view, List<ComponentOccurrence> occurrences, WeldInterfaceThresholds settings)
        {
            var wall = view.Geometry;
            var exterior = wall.ContactPlane;
            var occurrence = occurrences.Single(o => string.Equals(
                WeldInterfaceBroadPhase.BuildOccurrencePath(o), exterior.SourceOccurrencePath, StringComparison.OrdinalIgnoreCase));
            dynamic body = occurrence.SurfaceBodies[exterior.SourceBodyIndex];
            dynamic outsideFace = body.Faces[exterior.SourceFaceIndex];
            double outsideArea = (double)outsideFace.Evaluator.Area * 100.0;
            Box outsideBox = (Box)outsideFace.Evaluator.RangeBox;
            var outerBounds = ProjectBox(outsideBox, wall);
            double bestDepth = double.PositiveInfinity;
            int bestIndex = 0;
            WeldPoint3Mm? bestOrigin = null;
            for (int index = 1; index <= body.Faces.Count; index++)
            {
                if (index == exterior.SourceFaceIndex) continue;
                dynamic face = body.Faces[index];
                object geometry = face.Geometry;
                if (geometry is not Plane plane) continue;
                var n = exterior.Normal;
                double len = Math.Sqrt(plane.Normal.X * plane.Normal.X + plane.Normal.Y * plane.Normal.Y + plane.Normal.Z * plane.Normal.Z);
                if (len < 1e-9) continue;
                double alignment = Math.Abs(plane.Normal.X * n.X + plane.Normal.Y * n.Y + plane.Normal.Z * n.Z) / len;
                if (alignment < Math.Cos(settings.InnerSurfaceParallelToleranceDeg * Math.PI / 180)) continue;
                var point = new WeldPoint3Mm { X = plane.RootPoint.X * 10, Y = plane.RootPoint.Y * 10, Z = plane.RootPoint.Z * 10 };
                double depth = -WeldContactPlaneResolver.Depth(point, wall);
                if (depth <= settings.ContactToleranceMm || depth > settings.InnerSurfaceMaximumThicknessMm) continue;
                double area = (double)face.Evaluator.Area * 100.0;
                if (area < outsideArea * settings.InnerSurfaceMinimumAreaRatio || area > outsideArea / settings.InnerSurfaceMinimumAreaRatio) continue;
                var bounds = ProjectBox((Box)face.Evaluator.RangeBox, wall);
                if (bounds.Zip(outerBounds, (a,b) => Math.Abs(a-b)).Any(d => d > settings.InnerSurfaceFootprintToleranceMm)) continue;
                if (depth < bestDepth) { bestDepth = depth; bestIndex = index; bestOrigin = point; }
            }
            if (bestIndex == 0 || bestOrigin == null)
                throw new InvalidOperationException("No matching native inner planar face found on the same panel body");
            wall.ContactPlane = new WeldContactPlane {
                Resolved = true, ResolutionStatus = "native_physical_inner_wall_plane",
                OriginMm = bestOrigin,
                Normal = new WeldVector3 { X = -exterior.Normal.X, Y = -exterior.Normal.Y, Z = -exterior.Normal.Z },
                TiltFromCanonicalDeg = exterior.TiltFromCanonicalDeg,
                SourceOccurrencePath = exterior.SourceOccurrencePath,
                SourceBodyIndex = exterior.SourceBodyIndex, SourceFaceIndex = bestIndex };
            wall.StructuralSource.FaceIndex = bestIndex;
            view.MeasuredWallThicknessMm = Math.Round(bestDepth, 6);
        }

        private double[] ProjectBox(Box box, WeldInterfaceFaceRecord wall)
        {
            double minU = double.PositiveInfinity, maxU = double.NegativeInfinity;
            double minV = double.PositiveInfinity, maxV = double.NegativeInfinity;
            foreach (double x in new[] {box.MinPoint.X * 10,box.MaxPoint.X * 10})
            foreach (double y in new[] {box.MinPoint.Y * 10,box.MaxPoint.Y * 10})
            foreach (double z in new[] {box.MinPoint.Z * 10,box.MaxPoint.Z * 10})
            {
                double dx = x-wall.OriginMm.X, dy=y-wall.OriginMm.Y, dz=z-wall.OriginMm.Z;
                double u=dx*wall.LocalU.X+dy*wall.LocalU.Y+dz*wall.LocalU.Z;
                double v=dx*wall.LocalV.X+dy*wall.LocalV.Y+dz*wall.LocalV.Z;
                minU=Math.Min(minU,u);maxU=Math.Max(maxU,u);minV=Math.Min(minV,v);maxV=Math.Max(maxV,v);
            }
            return new[] {minU,maxU,minV,maxV};
        }

        private void Analyze(WeldSurfaceVariant view, List<ComponentOccurrence> occurrences,
            Inventor.Application application, HashSet<string> structuralPaths, WeldInterfaceThresholds settings)
        {
            var wall = view.Geometry;
            view.Statistics.FacesProcessed++;
            foreach (var candidate in broad.FindCandidatesForWall(occurrences, wall, structuralPaths, settings, view.Statistics))
            {
                var record = exact.Analyze(application, candidate, wall, settings, view.Statistics);
                if (record == null) continue;
                record.SurfaceId = view.SurfaceId;
                record.SurfaceSide = view.SurfaceSide;
                record.SegmentId = view.SegmentId;
                record.InterfaceId = $"{view.SurfaceId}_IF{wall.Interfaces.Count+1:00000}";
                for (int i=0;i<record.Paths.Count;i++) record.Paths[i].PathId=$"{record.InterfaceId}_P{i+1:000}";
                wall.Interfaces.Add(record);
            }
            selector.Apply(wall,settings,view.Statistics,view.Warnings);
        }
    }
}
