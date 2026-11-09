using System;
using System.Collections.Generic;

namespace AWIS.InventorBridge.WeldInterfaces
{
    // Body identity is occurrence path + 1-based index, not occurrence alone.
    internal static class WeldWallBodyScope
    {
        internal static bool IsSameOccurrence(string path, WeldInterfaceFaceRecord wall)
        {
            return !string.IsNullOrWhiteSpace(path) && string.Equals(path,
                wall.StructuralSource.OccurrencePath, StringComparison.OrdinalIgnoreCase);
        }

        internal static HashSet<int> WallBodies(string path, WeldInterfaceFaceRecord wall)
        {
            var result = new HashSet<int>();
            if (IsSameOccurrence(path, wall) && wall.StructuralSource.BodyIndex > 0)
                result.Add(wall.StructuralSource.BodyIndex);
            if (wall.PhysicalWall?.Segments != null)
                foreach (var segment in wall.PhysicalWall.Segments)
                    if (segment.SourceBodyIndex > 0 && string.Equals(path, segment.OccurrencePath,
                        StringComparison.OrdinalIgnoreCase)) result.Add(segment.SourceBodyIndex);
            return result;
        }

        internal static bool HasOtherBodies(string path, int count, WeldInterfaceFaceRecord wall)
        {
            var wallBodies = WallBodies(path, wall);
            // Without a resolved body identity, preserve the legacy exclusion.
            if (wallBodies.Count == 0) return false;
            for (int i = 1; i <= count; i++) if (!wallBodies.Contains(i)) return true;
            return false;
        }

        internal static bool IsWallBody(string path, int index, WeldInterfaceFaceRecord wall)
        {
            return WallBodies(path, wall).Contains(index);
        }
    }
}
