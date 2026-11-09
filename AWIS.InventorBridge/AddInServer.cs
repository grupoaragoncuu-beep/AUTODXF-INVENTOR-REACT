using Inventor;
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using AWIS.InventorBridge.Services;
using AWIS.InventorBridge.FacePreview;
using AWIS.InventorBridge.WeldInterfaces;
using AWIS.InventorBridge.CollisionGeometry;


namespace AWIS.InventorBridge
{
    [Guid("653272b1-7ff2-4700-8e4b-7e6cc8e1e5fa")]
    [ComVisible(true)]
    public class AddInServer : ApplicationAddInServer
    {
        private Inventor.Application?
            _inventorApplication;


        private ButtonDefinition?
            _selectFaceButton;


        private ButtonDefinition?
            _scanGeometryButton;


        private ButtonDefinition?
            _detectTankButton;


        // Mantiene vivos los HighlightSet mientras
        // queremos que Inventor conserve la visualización.
        private readonly List<HighlightSet>
            _tankDetectionHighlightSets =
                new List<HighlightSet>();


        // ============================================================
        // ACTIVATE
        // ============================================================

        public void Activate(
            ApplicationAddInSite addInSiteObject,
            bool firstTime)
        {
            _inventorApplication =
                addInSiteObject.Application;


            CreateSelectFaceButton();

            CreateScanGeometryButton();

            CreateDetectTankButton();


            _inventorApplication.StatusBarText =
                "AWIS FACE SEGMENTATION 0.4.0 | " +
                System.Reflection.Assembly
                    .GetExecutingAssembly()
                    .Location;
        }


        // ============================================================
        // SELECT WORKING FACE
        // V0.1 STABLE
        // ============================================================

        private void CreateSelectFaceButton()
        {
            if (_inventorApplication == null)
            {
                return;
            }


            _selectFaceButton =
                _inventorApplication
                .CommandManager
                .ControlDefinitions
                .AddButtonDefinition(
                    "Select Working Face",
                    "AWIS_SelectWorkingFace",
                    CommandTypesEnum.kShapeEditCmdType,
                    "{653272b1-7ff2-4700-8e4b-7e6cc8e1e5fa}",
                    "Selecciona una cara del tanque para analizarla con AWIS.",
                    "Seleccionar cara de trabajo");


            _selectFaceButton.OnExecute +=
                SelectFaceButton_OnExecute;


            _selectFaceButton.AutoAddToGUI();
        }


        private void SelectFaceButton_OnExecute(
            NameValueMap context)
        {
            if (_inventorApplication == null)
            {
                return;
            }


            try
            {
                object selectedObject =
                    _inventorApplication
                    .CommandManager
                    .Pick(
                        SelectionFilterEnum.kPartFaceFilter,
                        "AWIS: selecciona una cara del tanque");


                if (selectedObject == null)
                {
                    _inventorApplication.StatusBarText =
                        "AWIS: selección cancelada.";

                    return;
                }


                if (selectedObject
                    is not Face face)
                {
                    _inventorApplication.StatusBarText =
                        "AWIS: el objeto seleccionado no fue reconocido como una cara.";

                    return;
                }


                double areaMm2 =
                    face.Evaluator.Area *
                    100.0;


                string surfaceType =
                    face.SurfaceType.ToString();


                string componentName =
                    "Native Face";


                if (selectedObject
                    is FaceProxy faceProxy)
                {
                    componentName =
                        faceProxy
                        .ContainingOccurrence?
                        .Name
                        ??
                        "Assembly Face";
                }


                string normalText =
                    "N/A";


                if (face.Geometry
                    is Inventor.Plane plane)
                {
                    UnitVector normal =
                        plane.Normal;


                    normalText =
                        $"({normal.X:F6}, " +
                        $"{normal.Y:F6}, " +
                        $"{normal.Z:F6})";
                }


                _inventorApplication.StatusBarText =
                    $"AWIS | " +
                    $"Component: {componentName} | " +
                    $"Surface: {surfaceType} | " +
                    $"Area: {areaMm2:F2} mm² | " +
                    $"Normal: {normalText}";
            }
            catch (Exception ex)
            {
                _inventorApplication.StatusBarText =
                    $"AWIS ERROR: {ex.Message}";
            }
        }


        // ============================================================
        // SCAN GEOMETRY
        // V0.2A STABLE
        // ============================================================

        private void CreateScanGeometryButton()
        {
            if (_inventorApplication == null)
            {
                return;
            }


            _scanGeometryButton =
                _inventorApplication
                .CommandManager
                .ControlDefinitions
                .AddButtonDefinition(
                    "Scan Geometry",
                    "AWIS_ScanGeometry",
                    CommandTypesEnum.kShapeEditCmdType,
                    "{653272b1-7ff2-4700-8e4b-7e6cc8e1e5fa}",
                    "Escanea automáticamente la geometría del tanque.",
                    "AWIS Geometry Inventory");


            _scanGeometryButton.OnExecute +=
                ScanGeometryButton_OnExecute;


            _scanGeometryButton.AutoAddToGUI();
        }


        private void ScanGeometryButton_OnExecute(
            NameValueMap context)
        {
            if (_inventorApplication == null)
            {
                return;
            }


            try
            {
                _inventorApplication.StatusBarText =
                    "AWIS: escaneando geometría...";


                InventorGeometryScanner scanner =
                    new InventorGeometryScanner(
                        _inventorApplication);


                var scan =
                    scanner.ScanActiveAssembly();


                string outputPath =
                    JsonExporter.ExportGeometryScan(
                        scan);


                _inventorApplication.StatusBarText =
                    $"AWIS V0.2A | " +
                    $"Occurrences: {scan.OccurrencesScanned} | " +
                    $"Faces: {scan.TotalFacesScanned} | " +
                    $"Planar: {scan.PlanarFacesFound} | " +
                    $"JSON: {outputPath}";
            }
            catch (Exception ex)
            {
                _inventorApplication.StatusBarText =
                    $"AWIS ERROR: {ex.Message}";
            }
        }


        // ============================================================
        // DETECT TANK
        // V0.2B.2 + FACE PREVIEW V0.4.0 + WELD INTERFACES + COLLISION GEOMETRY V0.1.0
        //
        // 1. Geometry Scan
        // 2. Tank Frame Detection
        // 3. Official V0 JSON
        // 4. Face Preview Companion JSON
        // 5. Weld Interface Companion JSON
        // 6. Collision Geometry Companion JSON
        // 7. Full Boundary Visualization
        //
        // IMPORTANTE:
        // - V0.2B.2 sigue siendo la detección oficial.
        // - El Face Preview Companion es independiente.
        // - Si el companion falla, NO se invalida V0.
        // - La visualización sigue sin depender de FrameValid.
        // ============================================================

        private void CreateDetectTankButton()
        {
            if (_inventorApplication == null)
            {
                return;
            }


            _detectTankButton =
                _inventorApplication
                .CommandManager
                .ControlDefinitions
                .AddButtonDefinition(
                    "Detect Tank",
                    "AWIS_DetectTank",
                    CommandTypesEnum.kShapeEditCmdType,
                    "{653272b1-7ff2-4700-8e4b-7e6cc8e1e5fa}",
                    "Detecta y visualiza automáticamente el frame estructural del tanque.",
                    "AWIS Automatic Tank Detection");


            _detectTankButton.OnExecute +=
                DetectTankButton_OnExecute;


            _detectTankButton.AutoAddToGUI();
        }


        private void DetectTankButton_OnExecute(
            NameValueMap context)
        {
            if (_inventorApplication == null)
            {
                return;
            }


            try
            {
                _inventorApplication.StatusBarText =
                    "AWIS: detectando estructura del tanque...";


                // ====================================================
                // CLEAR PREVIOUS VISUALIZATION
                // ====================================================

                ClearTankDetectionHighlights();


                // ====================================================
                // GEOMETRY SCAN
                // ====================================================

                InventorGeometryScanner scanner =
                    new InventorGeometryScanner(
                        _inventorApplication);


                var scan =
                    scanner.ScanActiveAssembly();


                // ====================================================
                // TANK FRAME DETECTION
                // ====================================================

                TankFrameDetector detector =
                    new TankFrameDetector();


                var detection =
                    detector.Detect(
                        scan);


                // ====================================================
                // OFFICIAL V0 JSON
                // V0.2B.2 - NO MODIFICAR
                // ====================================================

                string outputPath =
                    JsonExporter.ExportTankDetection(
                        detection);


                outputPath =
                    AwisOutputNaming.EnsureTankSpecificCopy(
                        outputPath,
                        "AWIS_TANK_DETECTION",
                        detection.TankName);


                // ====================================================
                // FACE PREVIEW COMPANION V0.1
                //
                // Este bloque consume el JSON oficial que V0 acaba
                // de producir. No vuelve a detectar el tanque.
                //
                // Cualquier excepción queda aislada aquí y NO se
                // propaga hacia V0.
                // ====================================================

                string previewStatus =
                    "NOT_GENERATED";


                string previewOutputPath =
                    "";


                int previewFaceCount =
                    0;


                int previewWarningCount =
                    0;


                int previewSegmentCount =
                    0;


                int previewSeamCount =
                    0;


                try
                {
                    if (_inventorApplication.ActiveDocument
                        is not AssemblyDocument previewAssemblyDocument)
                    {
                        previewStatus =
                            "SKIPPED_NO_ASSEMBLY";
                    }
                    else
                    {
                        FacePreviewBuilder previewBuilder =
                            new FacePreviewBuilder();


                        FacePreviewPackage previewPackage =
                            previewBuilder.Build(
                                previewAssemblyDocument,
                                outputPath);


                        string outputDirectory =
                            System.IO.Path.GetDirectoryName(
                                outputPath)
                            ??
                            EfortWeldDirectory.Require();


                        previewOutputPath =
                            AwisOutputNaming.BuildPath(
                                outputDirectory,
                                "AWIS_FACE_PREVIEWS",
                                detection.TankName);


                        FacePreviewExporter.Export(
                            previewPackage,
                            previewOutputPath);


                        previewFaceCount =
                            previewPackage.Faces.Count;


                        previewWarningCount =
                            previewPackage.Warnings.Count;


                        foreach (FacePreviewRecord previewFace
                                 in previewPackage.Faces)
                        {
                            previewSegmentCount +=
                                previewFace.PhysicalWall.Segments.Count;

                            previewSeamCount +=
                                previewFace.PhysicalWall.StructuralSeams.Count;
                        }


                        previewStatus =
                            previewWarningCount > 0
                                ? "WARNING"
                                : "OK";
                    }
                }
                catch (Exception previewEx)
                {
                    previewStatus =
                        "FAILED";


                    // IMPORTANTE:
                    // No hacer "throw".
                    //
                    // El companion es informativo y NO forma parte
                    // del criterio de éxito de V0.2B.2.

                    try
                    {
                        _inventorApplication.StatusBarText =
                            "AWIS V0 OK | " +
                            "Face Preview FAILED: " +
                            previewEx.Message;
                    }
                    catch
                    {
                        // Incluso el aviso visual es no crítico.
                    }
                }


                // ====================================================
                // WELD INTERFACE COMPANION
                // V1.1-A / V0.1
                //
                // Consume:
                // - AssemblyDocument activo
                // - AWIS_TANK_DETECTION oficial
                // - AWIS_FACE_PREVIEWS V0.4.0
                //
                // No vuelve a detectar el tanque.
                // Si falla, NO invalida V0 ni Face Preview.
                // ====================================================

                string weldInterfaceStatus =
                    "NOT_GENERATED";


                string weldInterfaceOutputPath =
                    "";


                int weldInterfaceCount =
                    0;


                int weldInterfaceWarningCount =
                    0;


                int weldStructuralSeamCount =
                    0;


                try
                {
                    if (_inventorApplication.ActiveDocument
                        is not AssemblyDocument weldAssemblyDocument)
                    {
                        weldInterfaceStatus =
                            "SKIPPED_NO_ASSEMBLY";
                    }
                    else if (string.IsNullOrWhiteSpace(
                                 previewOutputPath)
                             ||
                             !System.IO.File.Exists(
                                 previewOutputPath))
                    {
                        weldInterfaceStatus =
                            "SKIPPED_NO_PREVIEW";
                    }
                    else
                    {
                        WeldInterfaceBuilder weldBuilder =
                            new WeldInterfaceBuilder();


                        WeldInterfacePackage weldPackage =
                            weldBuilder.Build(
                                weldAssemblyDocument,
                                outputPath,
                                previewOutputPath);


                        string weldOutputDirectory =
                            System.IO.Path.GetDirectoryName(
                                outputPath)
                            ??
                            EfortWeldDirectory.Require();


                        weldInterfaceOutputPath =
                            WeldInterfaceExporter.Export(
                                weldPackage,
                                weldOutputDirectory);


                        weldInterfaceOutputPath =
                            AwisOutputNaming.EnsureTankSpecificCopy(
                                weldInterfaceOutputPath,
                                "AWIS_WELD_INTERFACES",
                                detection.TankName);


                        foreach (WeldInterfaceFaceRecord weldFace
                                 in weldPackage.Faces)
                        {
                            weldInterfaceCount +=
                                weldFace.Interfaces.Count;
                        }


                        weldInterfaceWarningCount =
                            weldPackage.Warnings.Count;


                        weldStructuralSeamCount =
                            weldPackage.Statistics.StructuralSeamsImported;


                        weldInterfaceStatus =
                            weldInterfaceWarningCount > 0
                                ? "WARNING"
                                : "OK";
                    }
                }
                catch (Exception weldEx)
                {
                    weldInterfaceStatus =
                        "FAILED";


                    try
                    {
                        _inventorApplication.StatusBarText =
                            "AWIS V0 + Face Preview OK | " +
                            "Weld Interfaces FAILED: " +
                            weldEx.Message;
                    }
                    catch
                    {
                        // Companion no crítico.
                    }
                }


                // ====================================================
                // COLLISION GEOMETRY COMPANION V0.3.0
                //
                // Exporta dos companions para la futura Tool Collision Layer:
                // - AWIS_COLLISION_GEOMETRY: índice espacial ligero.
                // - AWIS_COLLISION_MESHES: mallas solo para MESH_REQUIRED.
                //
                // AABB/OBB/cilindros conservadores se mantienen como fallback.
                // Los TANK_BOUNDARY_SOURCE no se mallan en V0.3.
                //
                // Si falla, NO invalida V0, Face Preview ni Weld
                // Interfaces.
                // ====================================================

                string collisionGeometryStatus =
                    "NOT_GENERATED";


                string collisionGeometryOutputPath =
                    "";


                string collisionMeshOutputPath =
                    "";


                int collisionMeshCount =
                    0;


                long collisionTriangleCount =
                    0;


                int collisionComponentCount =
                    0;


                int collisionBodyCount =
                    0;


                int collisionWarningCount =
                    0;


                try
                {
                    if (_inventorApplication.ActiveDocument
                        is not AssemblyDocument collisionAssemblyDocument)
                    {
                        collisionGeometryStatus =
                            "SKIPPED_NO_ASSEMBLY";
                    }
                    else
                    {
                        CollisionGeometryBuilder collisionBuilder =
                            new CollisionGeometryBuilder();


                        CollisionGeometryPackage collisionPackage =
                            collisionBuilder.Build(
                                collisionAssemblyDocument,
                                detection);


                        string collisionOutputDirectory =
                            System.IO.Path.GetDirectoryName(
                                outputPath)
                            ??
                            EfortWeldDirectory.Require();


                        try
                        {
                            collisionMeshOutputPath =
                                CollisionMeshExporter.Export(
                                    collisionPackage,
                                    collisionOutputDirectory);
                        }
                        catch (Exception meshExportEx)
                        {
                            collisionPackage.Warnings.Add(
                                "Collision Mesh companion: no fue posible escribir AWIS_COLLISION_MESHES (" +
                                meshExportEx.Message +
                                "). El índice conservará OBB/AABB como fallback.");


                            foreach (CollisionComponentRecord meshComponent
                                     in collisionPackage.Components)
                            {
                                foreach (CollisionBodyRecord meshBody
                                         in meshComponent.Bodies)
                                {
                                    if (meshBody.MeshReference == null ||
                                        meshBody.MeshReference.Status != "EXPORTED")
                                    {
                                        continue;
                                    }


                                    meshBody.MeshReference.Status =
                                        "FILE_EXPORT_FAILED";

                                    meshBody.MeshReference.CompanionFileName =
                                        string.Empty;

                                    meshBody.MeshReference.Message =
                                        "Mesh was generated in memory but the companion file could not be written. Use conservative OBB/AABB fallback.";
                                }
                            }
                        }


                        // Export the light index after the mesh companion so
                        // each MeshReference contains the final companion file
                        // status/name seen by AWIS.
                        collisionGeometryOutputPath =
                            CollisionGeometryExporter.Export(
                                collisionPackage,
                                collisionOutputDirectory);


                        collisionComponentCount =
                            collisionPackage.Components.Count;


                        collisionBodyCount =
                            collisionPackage.Statistics.SurfaceBodiesExported;


                        collisionMeshCount =
                            collisionPackage.Statistics.MeshExportedBodies;


                        collisionTriangleCount =
                            collisionPackage.Statistics.MeshTriangleCount;


                        collisionWarningCount =
                            collisionPackage.Warnings.Count;


                        collisionGeometryStatus =
                            collisionWarningCount > 0
                                ? "WARNING"
                                : "OK";
                    }
                }
                catch (Exception collisionEx)
                {
                    collisionGeometryStatus =
                        "FAILED";


                    try
                    {
                        _inventorApplication.StatusBarText =
                            "AWIS core outputs OK | " +
                            "Collision Geometry FAILED: " +
                            collisionEx.Message;
                    }
                    catch
                    {
                        // Companion no crítico.
                    }
                }


                // ====================================================
                // VISUALIZATION
                //
                // B.2 CORRECTION:
                //
                // Aunque FrameValid == false,
                // mostramos todas las boundaries que sí
                // fueron confirmadas.
                // ====================================================

                int highlightedFaces =
                    0;


                if (detection.DetectedBoundaryCount > 0)
                {
                    if (_inventorApplication.ActiveDocument
                        is not AssemblyDocument assemblyDocument)
                    {
                        throw new InvalidOperationException(
                            "El documento activo dejó de ser un ensamblaje.");
                    }


                    List<HighlightSet> newHighlightSets =
                        TankDetectionVisualizer
                        .HighlightDetectedTank(
                            _inventorApplication,
                            assemblyDocument,
                            detection,
                            scan);


                    foreach (HighlightSet highlightSet
                             in newHighlightSets)
                    {
                        _tankDetectionHighlightSets.Add(
                            highlightSet);


                        highlightedFaces +=
                            highlightSet.Count;
                    }
                }


                // ====================================================
                // STATUS BAR
                // ====================================================

                string frameStatus =
                    detection.FrameValid
                        ? "VALID"
                        : "INVALID";


                string previewSummary =
                    previewStatus == "OK"
                        ? $"Preview: OK ({previewFaceCount} faces, {previewSegmentCount} segments, {previewSeamCount} seams)"
                        : previewStatus == "WARNING"
                            ? $"Preview: WARNING ({previewFaceCount} faces, {previewSegmentCount} segments, {previewSeamCount} seams, {previewWarningCount} warnings)"
                            : $"Preview: {previewStatus}";


                string weldInterfaceSummary =
                    weldInterfaceStatus == "OK"
                        ? $"Interfaces: OK ({weldInterfaceCount} candidates, {weldStructuralSeamCount} structural seams)"
                        : weldInterfaceStatus == "WARNING"
                            ? $"Interfaces: WARNING ({weldInterfaceCount} candidates, {weldStructuralSeamCount} structural seams, {weldInterfaceWarningCount} warnings)"
                            : $"Interfaces: {weldInterfaceStatus}";


                string collisionGeometrySummary =
                    collisionGeometryStatus == "OK"
                        ? $"Collision: OK ({collisionComponentCount} components, {collisionBodyCount} bodies, {collisionMeshCount} meshes, {collisionTriangleCount} triangles)"
                        : collisionGeometryStatus == "WARNING"
                            ? $"Collision: WARNING ({collisionComponentCount} components, {collisionBodyCount} bodies, {collisionMeshCount} meshes, {collisionWarningCount} warnings)"
                            : $"Collision: {collisionGeometryStatus}";


                _inventorApplication.StatusBarText =
                    $"AWIS V0.2B.2 | " +
                    $"Tank: {detection.TankName} | " +
                    $"Frame: {frameStatus} | " +
                    $"Boundaries: {detection.DetectedBoundaryCount}/6 | " +
                    $"Highlighted Faces: {highlightedFaces} | " +
                    $"{previewSummary} | " +
                    $"{weldInterfaceSummary} | " +
                    $"{collisionGeometrySummary} | " +
                    $"Model: {detection.ModelClosureStatus} | " +
                    $"Confidence: {detection.Confidence:P1} | " +
                    $"JSON: {outputPath}" +
                    (
                        string.IsNullOrWhiteSpace(
                            previewOutputPath)
                            ? ""
                            : $" | Preview JSON: {previewOutputPath}"
                    )
                    +
                    (
                        string.IsNullOrWhiteSpace(
                            weldInterfaceOutputPath)
                            ? ""
                            : $" | Interfaces JSON: {weldInterfaceOutputPath}"
                    )
                    +
                    (
                        string.IsNullOrWhiteSpace(
                            collisionGeometryOutputPath)
                            ? ""
                            : $" | Collision JSON: {collisionGeometryOutputPath}"
                    )
                    +
                    (
                        string.IsNullOrWhiteSpace(
                            collisionMeshOutputPath)
                            ? ""
                            : $" | Collision Meshes: {collisionMeshOutputPath}"
                    );
            }
            catch (Exception ex)
            {
                ClearTankDetectionHighlights();


                _inventorApplication.StatusBarText =
                    $"AWIS ERROR: {ex.Message}";
            }
        }


        // ============================================================
        // CLEAR TANK DETECTION HIGHLIGHTS
        // ============================================================

        private void ClearTankDetectionHighlights()
        {
            foreach (HighlightSet highlightSet
                     in _tankDetectionHighlightSets)
            {
                try
                {
                    highlightSet.Delete();
                }
                catch
                {
                    // Inventor puede eliminar internamente los
                    // HighlightSet al cerrar/cambiar documentos.
                }
            }


            _tankDetectionHighlightSets.Clear();
        }


        // ============================================================
        // DEACTIVATE
        // ============================================================

        public void Deactivate()
        {
            ClearTankDetectionHighlights();


            if (_selectFaceButton != null)
            {
                _selectFaceButton.OnExecute -=
                    SelectFaceButton_OnExecute;


                _selectFaceButton =
                    null;
            }


            if (_scanGeometryButton != null)
            {
                _scanGeometryButton.OnExecute -=
                    ScanGeometryButton_OnExecute;


                _scanGeometryButton =
                    null;
            }


            if (_detectTankButton != null)
            {
                _detectTankButton.OnExecute -=
                    DetectTankButton_OnExecute;


                _detectTankButton =
                    null;
            }


            _inventorApplication =
                null;
        }


        // ============================================================
        // REQUIRED BY ApplicationAddInServer
        // ============================================================

        public void ExecuteCommand(
            int commandID)
        {
        }


        public object? Automation =>
            null;
    }
}
