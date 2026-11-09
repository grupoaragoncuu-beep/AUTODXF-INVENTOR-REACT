using Inventor;
using System.Text.Json;

namespace AWIS.InventorBridge.FacePreview
{
    public class FacePreviewBuilder
    {
        public FacePreviewPackage Build(
            AssemblyDocument assembly,
            string detectionJsonPath)
        {
            string json =
                System.IO.File.ReadAllText(
                    detectionJsonPath);


            using JsonDocument document =
                JsonDocument.Parse(
                    json);


            JsonElement root =
                document.RootElement;


            FacePreviewPackage package =
                new FacePreviewPackage
                {
                    TankName =
                        GetString(
                            root,
                            "TankName"),

                    DocumentName =
                        GetString(
                            root,
                            "DocumentName"),

                    SourceDetectionFile =
                        System.IO.Path.GetFileName(
                            detectionJsonPath)
                };


            // ========================================================
            // 1. CANONICAL TANK FRAME
            //
            // V0 remains the global reference system.
            // Six logical faces are preserved regardless of how many
            // physical plates compose each wall.
            // ========================================================

            FacePreviewFrameBuilder frameBuilder =
                new FacePreviewFrameBuilder();


            frameBuilder.Build(
                root,
                package);


            // ========================================================
            // 2. DISCOVERY PROJECTION PASS
            //
            // Project using the canonical frame. V0.4.0 uses this pass
            // to recover the anchor wall plus any coplanar structural
            // plate segments connected to it by a manufacturing seam.
            // ========================================================

            FacePreviewLoopProjector loopProjector =
                new FacePreviewLoopProjector();


            loopProjector.Project(
                assembly,
                package);


            // ========================================================
            // 3. RESOLVE PHYSICAL WALL SEGMENTS + STRUCTURAL SEAMS
            //
            // The exact V0 face is the anchor. Segmentation grows only
            // through large, coplanar, adjacent panel candidates, so a
            // logical FACE remains one FACE while exposing 1..N plates.
            // ========================================================

            FacePreviewPhysicalWallResolver physicalWallResolver =
                new FacePreviewPhysicalWallResolver();


            physicalWallResolver.Resolve(
                package);


            // ========================================================
            // 4. FINAL PROJECTION PASS
            //
            // Discard discovery entities and project again. The active
            // PhysicalWall.Bounds is now the UNION of all segments.
            // ========================================================

            foreach (FacePreviewRecord face
                     in package.Faces)
            {
                face.Entities.Clear();

                face.Cleaning =
                    new FacePreviewCleaningStatistics();
            }


            package.Statistics =
                new FacePreviewStatistics();


            loopProjector.Project(
                assembly,
                package);


            // ========================================================
            // 5. VISUAL CLEANING
            //
            // Structural segment OUTER loops are hidden from accessory
            // geometry while their INNER loops remain wall openings.
            // ========================================================

            FacePreviewVisualCleaner visualCleaner =
                new FacePreviewVisualCleaner();


            visualCleaner.Clean(
                package);


            package.Statistics.FacesGenerated =
                package.Faces.Count;


            return package;
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
    }
}
