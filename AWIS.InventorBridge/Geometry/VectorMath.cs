using AWIS.InventorBridge.FacePreview;
using AWIS.InventorBridge.Models;

namespace AWIS.InventorBridge.Geometry
{
    public static class VectorMath
    {
        public static double Magnitude(
            Vector3Data vector)
        {
            return Math.Sqrt(
                (vector.X * vector.X) +
                (vector.Y * vector.Y) +
                (vector.Z * vector.Z));
        }


        public static Vector3Data Normalize(
            Vector3Data vector)
        {
            double magnitude =
                Magnitude(vector);

            if (magnitude < 1e-12)
            {
                throw new InvalidOperationException(
                    "No se puede normalizar un vector de magnitud cero.");
            }

            return new Vector3Data
            {
                X = vector.X / magnitude,
                Y = vector.Y / magnitude,
                Z = vector.Z / magnitude
            };
        }


        public static double Dot(
            Vector3Data a,
            Vector3Data b)
        {
            return
                (a.X * b.X) +
                (a.Y * b.Y) +
                (a.Z * b.Z);
        }


        public static Vector3Data CanonicalizeAxis(
            Vector3Data vector)
        {
            Vector3Data normalized =
                Normalize(vector);

            double absX =
                Math.Abs(normalized.X);

            double absY =
                Math.Abs(normalized.Y);

            double absZ =
                Math.Abs(normalized.Z);

            bool invert;

            if (absX >= absY &&
                absX >= absZ)
            {
                invert =
                    normalized.X < 0.0;
            }
            else if (absY >= absX &&
                     absY >= absZ)
            {
                invert =
                    normalized.Y < 0.0;
            }
            else
            {
                invert =
                    normalized.Z < 0.0;
            }

            if (!invert)
                return normalized;

            return new Vector3Data
            {
                X = -normalized.X,
                Y = -normalized.Y,
                Z = -normalized.Z
            };
        }


        public static double Projection(
            Point3Data point,
            Vector3Data axis)
        {
            return
                (point.X * axis.X) +
                (point.Y * axis.Y) +
                (point.Z * axis.Z);
        }
    }
}
