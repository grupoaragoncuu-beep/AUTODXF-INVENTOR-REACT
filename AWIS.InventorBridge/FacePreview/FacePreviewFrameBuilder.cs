using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace AWIS.InventorBridge.FacePreview
{
    public class FacePreviewFrameBuilder
    {
        public void Build(
            JsonElement detectionRoot,
            FacePreviewPackage package)
        {
            if (!detectionRoot.TryGetProperty(
                    "Axes",
                    out JsonElement axesElement))
            {
                package.Warnings.Add(
                    "Face Preview V0.2: el JSON de V0 no contiene Axes.");

                return;
            }


            if (axesElement.ValueKind !=
                JsonValueKind.Array)
            {
                package.Warnings.Add(
                    "Face Preview V0.2: Axes no es un arreglo válido.");

                return;
            }


            List<AxisFrameData> axes =
                ReadAxes(
                    axesElement,
                    package);


            if (axes.Count < 3)
            {
                package.Warnings.Add(
                    $"Face Preview V0.2: se esperaban 3 ejes principales y se obtuvieron {axes.Count}.");

                return;
            }


            // La detección estable V0 trabaja con tres ejes.
            // Si en el futuro aparecen más, V0.2 del companion
            // utiliza únicamente los tres primeros del Tank Frame.
            axes =
                axes.Take(3).ToList();


            for (int normalAxisIndex = 0;
                 normalAxisIndex < axes.Count;
                 normalAxisIndex++)
            {
                AxisFrameData normalAxis =
                    axes[normalAxisIndex];


                if (normalAxis.Negative.Detected)
                {
                    BuildFace(
                        package,
                        axes,
                        normalAxisIndex,
                        normalAxis.Negative,
                        "NEGATIVE");
                }


                if (normalAxis.Positive.Detected)
                {
                    BuildFace(
                        package,
                        axes,
                        normalAxisIndex,
                        normalAxis.Positive,
                        "POSITIVE");
                }
            }
        }


        private void BuildFace(
            FacePreviewPackage package,
            List<AxisFrameData> axes,
            int normalAxisIndex,
            BoundaryFrameData boundary,
            string side)
        {
            AxisFrameData normalAxis =
                axes[normalAxisIndex];


            Vector3 normal =
                Normalize(
                    normalAxis.Direction);


            if (side == "NEGATIVE")
            {
                normal =
                    Scale(
                        normal,
                        -1.0);
            }


            // Selección determinista de eje horizontal.
            //
            // AXIS_1 normal -> AXIS_2 horizontal
            // AXIS_2 normal -> AXIS_1 horizontal
            // AXIS_3 normal -> AXIS_2 horizontal
            //
            // Con el GIGA esto produce:
            // normal AXIS_1 -> 1672 x 902
            // normal AXIS_2 -> 1890 x 902
            // normal AXIS_3 -> 1672 x 1890 o equivalente,
            // dependiendo del sistema local exterior.
            int horizontalAxisIndex =
                normalAxisIndex switch
                {
                    0 => 1,
                    1 => 0,
                    _ => 1
                };


            AxisFrameData horizontalAxis =
                axes[horizontalAxisIndex];


            Vector3 localU =
                Normalize(
                    RemoveNormalComponent(
                        horizontalAxis.Direction,
                        normal));


            if (Length(localU) < 0.5)
            {
                package.Warnings.Add(
                    $"{normalAxis.AxisName}_{side}: no fue posible construir LocalU.");

                return;
            }


            // U x V = outward normal.
            // De esta forma la vista queda orientada desde el
            // exterior del tanque.
            Vector3 localV =
                Normalize(
                    Cross(
                        normal,
                        localU));


            int verticalAxisIndex =
                FindClosestTransverseAxis(
                    axes,
                    normalAxisIndex,
                    horizontalAxisIndex,
                    localV);


            if (verticalAxisIndex < 0)
            {
                package.Warnings.Add(
                    $"{normalAxis.AxisName}_{side}: no fue posible identificar el eje vertical.");

                return;
            }


            AxisFrameData verticalAxis =
                axes[verticalAxisIndex];


            int horizontalSign =
                Dot(
                    localU,
                    Normalize(
                        horizontalAxis.Direction))
                >= 0.0
                    ? 1
                    : -1;


            int verticalSign =
                Dot(
                    localV,
                    Normalize(
                        verticalAxis.Direction))
                >= 0.0
                    ? 1
                    : -1;


            double horizontalOriginProjection =
                horizontalSign > 0
                    ? horizontalAxis.MinProjectionMm
                    : horizontalAxis.MaxProjectionMm;


            double verticalOriginProjection =
                verticalSign > 0
                    ? verticalAxis.MinProjectionMm
                    : verticalAxis.MaxProjectionMm;


            // La esquina (0,0) se reconstruye como la intersección
            // matemática de los tres planos del Tank Frame.
            //
            // Los ejes V0 son ortogonales por construcción del frame.
            Vector3 origin =
                Add(
                    Add(
                        Scale(
                            Normalize(
                                normalAxis.Direction),
                            boundary.ProjectionMm),

                        Scale(
                            Normalize(
                                horizontalAxis.Direction),
                            horizontalOriginProjection)),

                    Scale(
                        Normalize(
                            verticalAxis.Direction),
                        verticalOriginProjection));


            double widthMm =
                horizontalAxis.SpanMm;


            double heightMm =
                verticalAxis.SpanMm;


            FacePreviewRecord face =
                new FacePreviewRecord
                {
                    FaceId =
                        $"{normalAxis.AxisName}_{side}",

                    AxisName =
                        normalAxis.AxisName,

                    Side =
                        side,

                    PlaneProjectionMm =
                        boundary.ProjectionMm,

                    HorizontalAxisName =
                        horizontalAxis.AxisName,

                    HorizontalAxisSign =
                        horizontalSign,

                    VerticalAxisName =
                        verticalAxis.AxisName,

                    VerticalAxisSign =
                        verticalSign,

                    OriginMm =
                        ToDto(
                            origin),

                    OutwardNormal =
                        ToDto(
                            normal),

                    LocalU =
                        ToDto(
                            localU),

                    LocalV =
                        ToDto(
                            localV),

                    WidthMm =
                        Math.Round(
                            widthMm,
                            3),

                    HeightMm =
                        Math.Round(
                            heightMm,
                            3),

                    DetectionSource =
                        new BoundaryDetectionSource
                        {
                            FaceRecordIndex =
                                boundary.FaceRecordIndex,

                            OccurrenceName =
                                boundary.OccurrenceName,

                            OccurrencePath =
                                boundary.OccurrencePath,

                            BodyIndex =
                                boundary.BodyIndex,

                            FaceIndex =
                                boundary.FaceIndex,

                            AreaMm2 =
                                boundary.AreaMm2,

                            AreaCoverageRatio =
                                boundary.AreaCoverageRatio,

                            DetectionReason =
                                boundary.DetectionReason
                        }
                };


            face.Envelope.Add(
                new Point2Dto
                {
                    X = 0.0,
                    Y = 0.0
                });

            face.Envelope.Add(
                new Point2Dto
                {
                    X = face.WidthMm,
                    Y = 0.0
                });

            face.Envelope.Add(
                new Point2Dto
                {
                    X = face.WidthMm,
                    Y = face.HeightMm
                });

            face.Envelope.Add(
                new Point2Dto
                {
                    X = 0.0,
                    Y = face.HeightMm
                });

            face.Envelope.Add(
                new Point2Dto
                {
                    X = 0.0,
                    Y = 0.0
                });


            package.Faces.Add(
                face);
        }


        private List<AxisFrameData> ReadAxes(
            JsonElement axesElement,
            FacePreviewPackage package)
        {
            List<AxisFrameData> result =
                new List<AxisFrameData>();


            foreach (JsonElement axisElement
                     in axesElement.EnumerateArray())
            {
                try
                {
                    AxisFrameData axis =
                        new AxisFrameData
                        {
                            AxisName =
                                GetString(
                                    axisElement,
                                    "AxisName"),

                            Direction =
                                ReadVector(
                                    axisElement.GetProperty(
                                        "Direction")),

                            SpanMm =
                                GetDouble(
                                    axisElement,
                                    "SpanMm")
                        };


                    if (axisElement.TryGetProperty(
                            "NegativeBoundary",
                            out JsonElement negative))
                    {
                        axis.Negative =
                            ReadBoundary(
                                negative);
                    }


                    if (axisElement.TryGetProperty(
                            "PositiveBoundary",
                            out JsonElement positive))
                    {
                        axis.Positive =
                            ReadBoundary(
                                positive);
                    }


                    // Preferimos las proyecciones reales de V0.
                    // Si faltara una boundary, usamos la disponible
                    // junto con SpanMm para completar el rango solo
                    // a nivel matemático. No inventamos una Face.
                    if (axis.Negative.Detected &&
                        axis.Positive.Detected)
                    {
                        axis.MinProjectionMm =
                            Math.Min(
                                axis.Negative.ProjectionMm,
                                axis.Positive.ProjectionMm);

                        axis.MaxProjectionMm =
                            Math.Max(
                                axis.Negative.ProjectionMm,
                                axis.Positive.ProjectionMm);
                    }
                    else if (axis.Negative.Detected)
                    {
                        axis.MinProjectionMm =
                            axis.Negative.ProjectionMm;

                        axis.MaxProjectionMm =
                            axis.MinProjectionMm +
                            axis.SpanMm;
                    }
                    else if (axis.Positive.Detected)
                    {
                        axis.MaxProjectionMm =
                            axis.Positive.ProjectionMm;

                        axis.MinProjectionMm =
                            axis.MaxProjectionMm -
                            axis.SpanMm;
                    }
                    else
                    {
                        package.Warnings.Add(
                            $"{axis.AxisName}: no tiene boundaries detectadas.");

                        continue;
                    }


                    result.Add(
                        axis);
                }
                catch (Exception ex)
                {
                    package.Warnings.Add(
                        $"Face Preview V0.2: no fue posible leer un eje: {ex.Message}");
                }
            }


            return result;
        }


        private BoundaryFrameData ReadBoundary(
            JsonElement element)
        {
            BoundaryFrameData boundary =
                new BoundaryFrameData();


            boundary.Detected =
                GetBool(
                    element,
                    "Detected");


            if (!boundary.Detected)
            {
                return boundary;
            }


            boundary.ProjectionMm =
                GetDouble(
                    element,
                    "ProjectionMm");


            boundary.FaceRecordIndex =
                GetInt(
                    element,
                    "FaceRecordIndex");


            boundary.OccurrenceName =
                GetString(
                    element,
                    "OccurrenceName");


            boundary.OccurrencePath =
                GetString(
                    element,
                    "OccurrencePath");


            boundary.BodyIndex =
                GetInt(
                    element,
                    "BodyIndex");


            boundary.FaceIndex =
                GetInt(
                    element,
                    "FaceIndex");


            boundary.AreaMm2 =
                GetDouble(
                    element,
                    "AreaMm2");


            boundary.AreaCoverageRatio =
                GetDouble(
                    element,
                    "AreaCoverageRatio");


            boundary.DetectionReason =
                GetString(
                    element,
                    "DetectionReason");


            return boundary;
        }


        private int FindClosestTransverseAxis(
            List<AxisFrameData> axes,
            int normalAxisIndex,
            int horizontalAxisIndex,
            Vector3 target)
        {
            int bestIndex =
                -1;

            double bestScore =
                -1.0;


            for (int i = 0;
                 i < axes.Count;
                 i++)
            {
                if (i == normalAxisIndex ||
                    i == horizontalAxisIndex)
                {
                    continue;
                }


                double score =
                    Math.Abs(
                        Dot(
                            Normalize(
                                axes[i].Direction),
                            target));


                if (score > bestScore)
                {
                    bestScore =
                        score;

                    bestIndex =
                        i;
                }
            }


            return bestIndex;
        }


        private static Vector3 ReadVector(
            JsonElement element)
        {
            return new Vector3
            {
                X =
                    GetDouble(
                        element,
                        "X"),

                Y =
                    GetDouble(
                        element,
                        "Y"),

                Z =
                    GetDouble(
                        element,
                        "Z")
            };
        }


        private static string GetString(
            JsonElement element,
            string propertyName)
        {
            if (!element.TryGetProperty(
                    propertyName,
                    out JsonElement property))
            {
                return "";
            }


            return property.ValueKind ==
                   JsonValueKind.String
                ? property.GetString() ?? ""
                : property.ToString();
        }


        private static double GetDouble(
            JsonElement element,
            string propertyName)
        {
            if (!element.TryGetProperty(
                    propertyName,
                    out JsonElement property))
            {
                return 0.0;
            }


            if (property.ValueKind ==
                    JsonValueKind.Number &&
                property.TryGetDouble(
                    out double value))
            {
                return value;
            }


            return 0.0;
        }


        private static int GetInt(
            JsonElement element,
            string propertyName)
        {
            if (!element.TryGetProperty(
                    propertyName,
                    out JsonElement property))
            {
                return 0;
            }


            if (property.ValueKind ==
                    JsonValueKind.Number &&
                property.TryGetInt32(
                    out int value))
            {
                return value;
            }


            return 0;
        }


        private static bool GetBool(
            JsonElement element,
            string propertyName)
        {
            if (!element.TryGetProperty(
                    propertyName,
                    out JsonElement property))
            {
                return false;
            }


            return property.ValueKind ==
                   JsonValueKind.True;
        }


        private static Vector3Dto ToDto(
            Vector3 vector)
        {
            return new Vector3Dto
            {
                X =
                    Math.Round(
                        vector.X,
                        9),

                Y =
                    Math.Round(
                        vector.Y,
                        9),

                Z =
                    Math.Round(
                        vector.Z,
                        9)
            };
        }


        private static Vector3 Add(
            Vector3 a,
            Vector3 b)
        {
            return new Vector3
            {
                X = a.X + b.X,
                Y = a.Y + b.Y,
                Z = a.Z + b.Z
            };
        }


        private static Vector3 Subtract(
            Vector3 a,
            Vector3 b)
        {
            return new Vector3
            {
                X = a.X - b.X,
                Y = a.Y - b.Y,
                Z = a.Z - b.Z
            };
        }


        private static Vector3 Scale(
            Vector3 vector,
            double scalar)
        {
            return new Vector3
            {
                X = vector.X * scalar,
                Y = vector.Y * scalar,
                Z = vector.Z * scalar
            };
        }


        private static double Dot(
            Vector3 a,
            Vector3 b)
        {
            return
                a.X * b.X +
                a.Y * b.Y +
                a.Z * b.Z;
        }


        private static Vector3 Cross(
            Vector3 a,
            Vector3 b)
        {
            return new Vector3
            {
                X =
                    a.Y * b.Z -
                    a.Z * b.Y,

                Y =
                    a.Z * b.X -
                    a.X * b.Z,

                Z =
                    a.X * b.Y -
                    a.Y * b.X
            };
        }


        private static double Length(
            Vector3 vector)
        {
            return Math.Sqrt(
                Dot(
                    vector,
                    vector));
        }


        private static Vector3 Normalize(
            Vector3 vector)
        {
            double length =
                Length(
                    vector);


            if (length < 1e-12)
            {
                return vector;
            }


            return Scale(
                vector,
                1.0 / length);
        }


        private static Vector3 RemoveNormalComponent(
            Vector3 vector,
            Vector3 normal)
        {
            return Subtract(
                vector,
                Scale(
                    normal,
                    Dot(
                        vector,
                        normal)));
        }


        private class AxisFrameData
        {
            public string AxisName =
                "";

            public Vector3 Direction =
                new Vector3();

            public double SpanMm;

            public double MinProjectionMm;

            public double MaxProjectionMm;

            public BoundaryFrameData Negative =
                new BoundaryFrameData();

            public BoundaryFrameData Positive =
                new BoundaryFrameData();
        }


        private class BoundaryFrameData
        {
            public bool Detected;

            public double ProjectionMm;

            public int FaceRecordIndex;

            public string OccurrenceName =
                "";

            public string OccurrencePath =
                "";

            public int BodyIndex;

            public int FaceIndex;

            public double AreaMm2;

            public double AreaCoverageRatio;

            public string DetectionReason =
                "";
        }


        private class Vector3
        {
            public double X;

            public double Y;

            public double Z;
        }
    }
}
