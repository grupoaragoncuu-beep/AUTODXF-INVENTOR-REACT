using Inventor;
using System;
using System.Collections.Generic;
using System.Linq;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // Geometry-only plane; canonical Origin/UV/OutwardNormal are never changed.
    public static class WeldContactPlaneResolver
    {
        public static void Resolve(WeldInterfaceFaceRecord wall,
            IReadOnlyList<ComponentOccurrence> occurrences, List<string> warnings)
        {
            wall.ContactPlane = new WeldContactPlane {
                OriginMm = wall.OriginMm, Normal = wall.OutwardNormal };
            try
            {
                var segments = wall.PhysicalWall.Segments;
                var anchor = segments.FirstOrDefault(s => s.IsAnchorSegment);
                string path = anchor?.OccurrencePath ?? wall.StructuralSource.OccurrencePath;
                int bodyIndex = anchor?.SourceBodyIndex ?? wall.StructuralSource.BodyIndex;
                int faceIndex = anchor?.SourceFaceIndex ?? wall.StructuralSource.FaceIndex;
                var plane = ReadPlane(occurrences, path, bodyIndex, faceIndex);
                double dot = plane.Normal.X * wall.OutwardNormal.X + plane.Normal.Y * wall.OutwardNormal.Y + plane.Normal.Z * wall.OutwardNormal.Z;
                double magnitude = Math.Sqrt(plane.Normal.X * plane.Normal.X + plane.Normal.Y * plane.Normal.Y + plane.Normal.Z * plane.Normal.Z);
                if (!double.IsFinite(dot) || !double.IsFinite(magnitude) || magnitude < 1e-9) throw new InvalidOperationException("Invalid native normal");
                double cosine = Math.Abs(dot) / magnitude;
                double tilt = Math.Acos(Math.Clamp(cosine, 0, 1)) * 180 / Math.PI;
                if (tilt > 4.0) throw new InvalidOperationException("Native plane differs from canonical face by more than 4 degrees");
                double sign = dot < 0 ? -1 : 1;
                var normal = new WeldVector3 { X = sign * plane.Normal.X / magnitude, Y = sign * plane.Normal.Y / magnitude, Z = sign * plane.Normal.Z / magnitude };
                var origin = new WeldPoint3Mm { X = plane.RootPoint.X * 10, Y = plane.RootPoint.Y * 10, Z = plane.RootPoint.Z * 10 };
                // A single contact plane must be valid for every physical panel.
                foreach (var segment in segments)
                {
                    var other = ReadPlane(occurrences, segment.OccurrencePath, segment.SourceBodyIndex, segment.SourceFaceIndex);
                    double align = Math.Abs(other.Normal.X * normal.X + other.Normal.Y * normal.Y + other.Normal.Z * normal.Z);
                    double depth = (other.RootPoint.X * 10 - origin.X) * normal.X + (other.RootPoint.Y * 10 - origin.Y) * normal.Y + (other.RootPoint.Z * 10 - origin.Z) * normal.Z;
                    if (align < Math.Cos(0.01 * Math.PI / 180) || Math.Abs(depth) > 0.25)
                        throw new InvalidOperationException("Physical panels require separate contact planes");
                }
                wall.ContactPlane = new WeldContactPlane {
                    Resolved = true, ResolutionStatus = "native_physical_wall_plane",
                    OriginMm = origin, Normal = normal, TiltFromCanonicalDeg = tilt,
                    SourceOccurrencePath = path, SourceBodyIndex = bodyIndex, SourceFaceIndex = faceIndex };
            }
            catch (Exception ex)
            {
                wall.ContactPlane.ResolutionStatus = "canonical_fallback_unresolved_native_plane";
                warnings.Add($"{wall.FaceId}: V0.3.5 physical contact plane unresolved; canonical fallback retained. {ex.Message}");
            }
        }

        private static Plane ReadPlane(IReadOnlyList<ComponentOccurrence> occurrences, string path, int bodyIndex, int faceIndex)
        {
            var occurrence = occurrences.FirstOrDefault(o => string.Equals(WeldInterfaceBroadPhase.BuildOccurrencePath(o), path, StringComparison.OrdinalIgnoreCase));
            if (occurrence == null || bodyIndex < 1 || faceIndex < 1) throw new InvalidOperationException("Native wall face reference missing");
            // SurfaceBodies on the occurrence expose assembly-context proxies, matching all path samples.
            dynamic face = occurrence.SurfaceBodies[bodyIndex].Faces[faceIndex];
            object geometry = face.Geometry;
            return geometry as Plane ?? throw new InvalidOperationException("Native wall surface is not planar");
        }

        public static double Depth(WeldPoint3Mm point, WeldInterfaceFaceRecord wall)
        {
            var origin = wall.ContactPlane.Resolved ? wall.ContactPlane.OriginMm : wall.OriginMm;
            var normal = wall.ContactPlane.Resolved ? wall.ContactPlane.Normal : wall.OutwardNormal;
            return (point.X - origin.X) * normal.X + (point.Y - origin.Y) * normal.Y + (point.Z - origin.Z) * normal.Z;
        }

        public static WeldVector3 Normal(WeldInterfaceFaceRecord wall) => wall.ContactPlane.Resolved ? wall.ContactPlane.Normal : wall.OutwardNormal;
        public static WeldPoint3Mm Origin(WeldInterfaceFaceRecord wall) => wall.ContactPlane.Resolved ? wall.ContactPlane.OriginMm : wall.OriginMm;

        public static WeldPoint3Mm LiftUv(WeldPoint2Mm uv, WeldInterfaceFaceRecord wall)
        {
            var point = new WeldPoint3Mm {
                X = wall.OriginMm.X + wall.LocalU.X * uv.X + wall.LocalV.X * uv.Y,
                Y = wall.OriginMm.Y + wall.LocalU.Y * uv.X + wall.LocalV.Y * uv.Y,
                Z = wall.OriginMm.Z + wall.LocalU.Z * uv.X + wall.LocalV.Z * uv.Y };
            var n = Normal(wall); var c = wall.OutwardNormal;
            double denom = n.X * c.X + n.Y * c.Y + n.Z * c.Z;
            if (Math.Abs(denom) < 1e-9) throw new InvalidOperationException("Contact plane cannot be lifted from canonical UV");
            double offset = -Depth(point, wall) / denom;
            return new WeldPoint3Mm { X = Math.Round(point.X + offset * c.X, 3), Y = Math.Round(point.Y + offset * c.Y, 3), Z = Math.Round(point.Z + offset * c.Z, 3) };
        }
    }
}
