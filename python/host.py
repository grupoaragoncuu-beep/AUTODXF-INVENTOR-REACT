"""Ventana propia de AutoDXF, conectada a Inventor. No abre el navegador."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import webview

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui"
DIST_INDEX = UI_DIR / "dist" / "index.html"
DEV_URL = "http://127.0.0.1:4173"

if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from catalog import load_catalog
from inventor_session import PICK_STATUS, PICK_STOP, read_pick_status, update_pick_class
from job_id import resolve_job, save_job
from dossier_arbol import atender as dossier_atender
from morphology import export_lists, remember_rows, stock_catalog
from acotacion import classify_assembly, ensure_dir, load_acotacion, local_jpg_dir, save_acotacion
from acotacion_progress import read_progress, reset_progress, write_progress
from weld_anotation import read_weld_progress, reset_weld_progress, scan_weld_drawing
from colorimetria import load_colorimetria, save_colorimetria
from sheet_rules import load_rule_catalog, run_sheet_rules, save_rule_catalog
from awis_run import run_awis


class ToolbarApi:
    def __init__(self) -> None:
        self._window = None
        self.page_url = ""
        self._pick = None
        self._acotacion = None
        self._weld = None

    def attach(self, window) -> None:
        self._window = window

    def snapshot(self) -> dict:
        catalog = _safe_catalog()
        session = _with_job(_inventor_process("snapshot"))
        return {**session, "catalog": catalog}

    def parts(self) -> dict:
        return _with_job(_inventor_process("parts"))

    def dossier_consulta(self, payload: str = "") -> dict:
        return dossier_atender(payload)

    def job_save(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            incoming = {}
        if not isinstance(incoming, dict):
            incoming = {}
        return save_job(
            str(incoming.get("job") or incoming.get("jobName") or ""),
            str(incoming.get("assemblyPath") or ""),
            str(incoming.get("assemblyName") or ""),
        )

    def pick_folder(self) -> str:
        if self._window is None:
            return ""
        dialog = getattr(webview, "FOLDER_DIALOG", None)
        if dialog is None:
            dialog = webview.FileDialog.FOLDER
        chosen = self._window.create_file_dialog(dialog)
        if not chosen:
            return ""
        return str(chosen[0])

    def export_dxf(self, payload: str) -> dict:
        try:
            options = json.loads(payload or "{}")
        except json.JSONDecodeError:
            options = {}
        _safe_catalog()
        result = _inventor_process("export", options)
        result["catalog"] = _safe_catalog()
        if "session" not in result:
            result["session"] = _inventor_process("snapshot")
        result["session"] = _with_job(
            result.get("session"),
            str(options.get("job") or options.get("jobName") or ""),
        )
        return result

    def sheet_rules_load(self) -> dict:
        return load_rule_catalog()

    def sheet_rules_save(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "message": "No se pudo leer el catálogo.", "catalog": load_rule_catalog()}
        return save_rule_catalog(incoming)

    def sheet_rules(self, payload: str = "") -> dict:
        if payload:
            try:
                incoming = json.loads(payload)
            except json.JSONDecodeError:
                return {"ok": False, "message": "No se pudo leer el catálogo.", "missing": [], "withFlat": 0, "log": ""}
            saved = save_rule_catalog(incoming)
            if not saved.get("ok"):
                saved["missing"] = []
                saved["withFlat"] = 0
                saved["log"] = ""
                return saved
        report = run_sheet_rules()
        report["session"] = _with_job(_inventor_process("snapshot"))
        report["catalog"] = _safe_catalog()
        report["rules"] = load_rule_catalog()
        return report

    def multibody(self) -> dict:
        return _inventor_process("multibody")

    def awis_run(self, payload: str = "") -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "message": "No se pudo leer el paso de AWIS.", "log": ""}
        return run_awis(str(incoming.get("paso") or ""))

    def scan_shapes(self) -> dict:
        return _inventor_process("shapes")

    def start_pick(self, mode: str) -> dict:
        if self._pick is not None and self._pick.poll() is None:
            return {"ok": False, "message": "La selección ya está activa. Pulsa Terminar."}
        incoming: dict = {"mode": mode or "lengths"}
        try:
            parsed = json.loads(mode or "")
            if isinstance(parsed, dict):
                incoming = parsed
                incoming["mode"] = str(parsed.get("mode") or "lengths")
        except json.JSONDecodeError:
            pass
        PICK_STOP.parent.mkdir(parents=True, exist_ok=True)
        if PICK_STOP.exists():
            PICK_STOP.unlink()
        PICK_STATUS.write_text(
            '{"picking": true, "count": 0, "paths": [], "names": []}',
            encoding="utf-8",
        )
        worker = Path(__file__).with_name("inventor_worker.py")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        self._pick = subprocess.Popen(
            [sys.executable, str(worker), "pick"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=0x08000000,
        )
        assert self._pick.stdin is not None
        self._pick.stdin.write(json.dumps(incoming).encode("utf-8"))
        self._pick.stdin.close()
        kind = str(incoming.get("mode") or "lengths")
        class_name = str(incoming.get("className") or incoming.get("classification") or "")
        if kind == "accessories" and "assy loose" in class_name.strip().casefold():
            hint = (
                f"Selector activo ({class_name}): clic en el .iam. "
                "El kit queda Assy Loose; cada pieza, Accesorios Sueltos."
            )
        elif kind == "accessories" and class_name.strip().casefold().startswith("assy"):
            hint = (
                f"Selector activo ({class_name}): clic en un subensamble .iam "
                "(o en una pieza del kit). Esc o Terminar."
            )
        elif kind == "roles":
            hint = (
                f"Selector de muros ({class_name or 'cara'}): clic en el modelo para sumar piezas. "
                "Esc o Terminar. No escribe Clasificación."
            )
        elif kind == "accessories":
            hint = "Selector activo. Clic en cada pieza .ipt. Esc o Terminar para salir."
        else:
            hint = "Selector activo. Haz clic en los componentes dentro de Inventor."
        return {"ok": True, "message": hint}

    def update_pick(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            incoming = {}
        if not isinstance(incoming, dict):
            incoming = {}
        smart = incoming.get("smart")
        return update_pick_class(
            str(incoming.get("className") or incoming.get("classification") or ""),
            str(incoming.get("color") or ""),
            smart=None if smart is None else bool(smart),
        )

    def colorimetria_load(self) -> dict:
        return load_colorimetria()

    def colorimetria_save(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "message": "No se pudo leer la paleta.", "catalog": load_colorimetria()}
        if not isinstance(incoming, dict):
            return {"ok": False, "message": "No se pudo leer la paleta.", "catalog": load_colorimetria()}
        return save_colorimetria(incoming)

    def pick_status(self) -> dict:
        status = read_pick_status()
        status["running"] = self._pick is not None and self._pick.poll() is None
        return status

    def stop_pick(self) -> dict:
        PICK_STOP.parent.mkdir(parents=True, exist_ok=True)
        PICK_STOP.write_text("1", encoding="utf-8")
        proc = self._pick
        if proc is None:
            return {"ok": False, "message": "No hay una selección activa.", "rows": []}
        try:
            out, err = proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            proc.kill()
            self._pick = None
            return {"ok": False, "message": "La selección no cerró.", "rows": []}
        self._pick = None
        raw = _decode_output(out).strip()
        if not raw:
            detail = " ".join(_decode_output(err).split())[:300]
            return {"ok": False, "message": detail or "El selector no respondió.", "rows": []}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "message": raw[:300], "rows": []}
        return parsed if isinstance(parsed, dict) else {"ok": False, "message": "Respuesta inválida.", "rows": []}

    def paint_shapes(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            incoming = {}
        if not isinstance(incoming, dict):
            incoming = {}
        return _inventor_process("paint", incoming)

    def roles_action(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            incoming = {}
        if not isinstance(incoming, dict):
            incoming = {}
        return _inventor_process("roles", incoming)

    def blocks_action(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            incoming = {}
        if not isinstance(incoming, dict):
            incoming = {}
        if self._pick is not None and self._pick.poll() is None:
            return {"ok": False, "message": "La selección sigue activa. Pulsa Terminar primero."}
        return _inventor_process("blocks", incoming)

    def shape_stock(self) -> dict:
        return {"stock": stock_catalog()}

    def remember_shapes(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "message": "No se pudo leer el ajuste."}
        rows = incoming.get("rows") if isinstance(incoming, dict) else incoming
        if not isinstance(rows, list):
            return {"ok": False, "message": "No se pudo leer el ajuste."}
        return remember_rows(rows)

    def acotacion_load(self) -> dict:
        return load_acotacion()

    def acotacion_save(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "message": "No se pudo leer la configuración."}
        if not isinstance(incoming, dict):
            return {"ok": False, "message": "No se pudo leer la configuración."}
        return save_acotacion(incoming)

    def acotacion_open(self, folder: str = "") -> dict:
        raw = str(folder or "").strip()
        resolved, note = local_jpg_dir(raw)
        target = Path(raw) if raw and not note else resolved
        try:
            ensure_dir(target)
        except OSError as ex:
            return {"ok": False, "message": str(ex), "folder": str(target)}
        try:
            os.startfile(str(target))
        except OSError as ex:
            return {"ok": False, "message": str(ex), "folder": str(target)}
        return {"ok": True, "message": note or str(target), "folder": str(target)}

    def acotacion_run(self, payload: str) -> dict:
        if self._acotacion is not None and self._acotacion.poll() is None:
            deadline = time.time() + 90
            while self._acotacion.poll() is None and time.time() < deadline:
                time.sleep(0.35)
            if self._acotacion.poll() is None:
                return {"ok": False, "started": False, "message": "Ya hay una exportación JPG en curso."}
            self._acotacion = None
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            incoming = {}
        if not isinstance(incoming, dict):
            incoming = {}
        reset_progress(0, "Iniciando exportación JPG…")
        worker = Path(__file__).with_name("inventor_worker.py")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        self._acotacion = subprocess.Popen(
            [sys.executable, str(worker), "acotacion"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=0x08000000,
        )
        assert self._acotacion.stdin is not None
        self._acotacion.stdin.write(json.dumps(incoming).encode("utf-8"))
        self._acotacion.stdin.close()
        return {"ok": True, "started": True, "message": "Exportando JPG…"}

    def acotacion_progress(self) -> dict:
        status = read_progress()
        proc = self._acotacion
        running = proc is not None and proc.poll() is None
        status["running"] = running
        if proc is not None and not running:
            try:
                out, err = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                out, err = b"", b""
            self._acotacion = None
            if not status.get("done"):
                raw = _decode_output(out).strip()
                detail = " ".join(_decode_output(err).split())[:300]
                try:
                    parsed = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    parsed = {}
                if isinstance(parsed, dict) and parsed:
                    status["done"] = True
                    status["result"] = parsed
                    status["message"] = str(parsed.get("message") or detail)
                else:
                    status["done"] = True
                    status["message"] = detail or "La exportación JPG se detuvo."
                    status["result"] = {"ok": False, "message": status["message"]}
                try:
                    write_progress(
                        current=int(status.get("current") or 0),
                        total=max(1, int(status.get("total") or 1)),
                        piece="Terminado con avisos",
                        phase="listo",
                        done=True,
                        result=status.get("result"),
                        message=str(status.get("message") or ""),
                    )
                except Exception:
                    pass
        return status

    def acotacion_classify(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            incoming = {}
        if not isinstance(incoming, dict):
            incoming = {}
        catalog = incoming.get("config") if isinstance(incoming.get("config"), dict) else load_acotacion()
        return classify_assembly(
            str(incoming.get("name") or ""),
            str(incoming.get("path") or ""),
            catalog,
            str(incoming.get("job") or incoming.get("jobName") or ""),
        )

    def weld_scan(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            incoming = {}
        if not isinstance(incoming, dict):
            incoming = {}
        return scan_weld_drawing(incoming)

    def weld_run(self, payload: str) -> dict:
        if self._weld is not None and self._weld.poll() is None:
            return {"ok": False, "started": False, "message": "Ya hay una exportación de soldadura en curso."}
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            incoming = {}
        if not isinstance(incoming, dict):
            incoming = {}
        reset_weld_progress(0, "Preparando cordones 3D…")
        worker = Path(__file__).with_name("inventor_worker.py")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        self._weld = subprocess.Popen(
            [sys.executable, str(worker), "weld"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=0x08000000,
        )
        assert self._weld.stdin is not None
        self._weld.stdin.write(json.dumps(incoming).encode("utf-8"))
        self._weld.stdin.close()
        return {"ok": True, "started": True, "message": "Dibujando JPG de soldadura…"}

    def weld_progress(self) -> dict:
        status = read_weld_progress()
        proc = self._weld
        running = proc is not None and proc.poll() is None
        status["running"] = running
        if proc is not None and not running:
            try:
                out, err = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                out, err = b"", b""
            self._weld = None
            if not status.get("done"):
                raw = _decode_output(out).strip()
                detail = " ".join(_decode_output(err).split())[:300]
                try:
                    parsed = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    parsed = {}
                if isinstance(parsed, dict) and parsed:
                    status["done"] = True
                    status["result"] = parsed
                    status["message"] = str(parsed.get("message") or detail)
                else:
                    status["done"] = True
                    status["message"] = detail or "La exportación de soldadura se detuvo."
                    status["result"] = {"ok": False, "message": status["message"]}
                try:
                    from weld_anotation import write_weld_progress

                    write_weld_progress(
                        current=int(status.get("current") or 0),
                        total=max(1, int(status.get("total") or 1)),
                        piece="Terminado con avisos",
                        phase="listo",
                        done=True,
                        result=status.get("result") if isinstance(status.get("result"), dict) else None,
                        message=str(status.get("message") or ""),
                    )
                except Exception:
                    pass
        return status

    def weld_nom_list(self, payload: str) -> dict:
        from weld_nomenclatura import listar

        incoming = _json_dict(payload)
        return listar(str(incoming.get("assemblyPath") or ""))

    def weld_nom_apply(self, payload: str) -> dict:
        from weld_nomenclatura import aplicar

        incoming = _json_dict(payload)
        spec = incoming.get("spec") if isinstance(incoming.get("spec"), dict) else {}
        result, cambio = aplicar(
            str(incoming.get("assemblyPath") or ""),
            str(incoming.get("id") or ""),
            str(incoming.get("clasificacion") or ""),
            spec,
        )
        if cambio is not None:
            pintado = _inventor_process(
                "weld_nom",
                {"action": "color", "cuerpos": cambio.get("cuerpos") or [], "clasificacion": cambio.get("clasificacion")},
            )
            result["message"] = f"{result.get('message', '')} · {pintado.get('message', '')}".strip(" ·")
        return result

    def weld_nom_select(self, payload: str) -> dict:
        incoming = _json_dict(payload)
        return _inventor_process("weld_nom", {"action": "select", "cuerpos": incoming.get("cuerpos") or []})

    def weld_nom_pick(self) -> dict:
        return _inventor_process("weld_nom", {"action": "pick"})

    def weld_nom_mira(self) -> dict:
        return _inventor_process("weld_nom", {"action": "mira"})

    def weld_nom_armar(self) -> dict:
        return _inventor_process("weld_nom", {"action": "armar"})

    def weld_nom_soltar(self) -> dict:
        return _inventor_process("weld_nom", {"action": "soltar"})

    def weld_nom_drop(self, payload: str) -> dict:
        from weld_nomenclatura import excluir

        incoming = _json_dict(payload)
        result = excluir(str(incoming.get("assemblyPath") or ""), str(incoming.get("id") or ""))
        if not result.get("ok"):
            return result
        borrado = _inventor_process("weld_nom", {"action": "drop", "cuerpos": result.get("cuerpos") or []})
        if borrado.get("message"):
            result["message"] = f"{result.get('message', '')} {borrado.get('message', '')}".strip()
        if borrado.get("ok") is False:
            result["ok"] = False
        return result

    def weld_tool_open(self) -> dict:
        titulo = "Nomenclatura"
        for ventana in list(webview.windows):
            if str(getattr(ventana, "title", "") or "") != titulo:
                continue
            try:
                ventana.show()
            except Exception:
                pass
            return {"ok": True, "message": "Nomenclatura abierta."}
        base = str(self.page_url or "").split("#", 1)[0]
        if not base:
            return {"ok": False, "message": "Cierra la barra y ábrela de nuevo para usar Nomenclatura."}
        try:
            _inventor_process("weld_nom", {"action": "armar"})
        except Exception:
            pass
        try:
            ventana = webview.create_window(
                titulo,
                base + "#cordon",
                js_api=self,
                width=420,
                height=640,
                min_size=(360, 480),
                on_top=True,
                background_color="#FFFFFF",
                text_select=True,
            )
            def _al_cerrar() -> None:
                try:
                    _inventor_process("weld_nom", {"action": "soltar"})
                except Exception:
                    pass
            try:
                ventana.events.closed += _al_cerrar
            except Exception:
                pass
        except Exception as ex:
            return {"ok": False, "message": f"No se abrió Nomenclatura: {ex}"}
        return {"ok": True, "message": "Nomenclatura abierta."}

    def export_shapes(self, payload: str) -> dict:
        try:
            incoming = json.loads(payload or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "message": "No se pudo leer la lista."}
        if not isinstance(incoming, dict):
            return {"ok": False, "message": "No se pudo leer la lista."}
        rows = incoming.get("rows") if isinstance(incoming.get("rows"), list) else []
        job = str(incoming.get("job") or incoming.get("jobName") or "").strip()
        return export_lists(str(incoming.get("folder") or ""), rows, job)


def _json_dict(payload: str) -> dict:
    try:
        incoming = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return {}
    return incoming if isinstance(incoming, dict) else {}


def _abort_stale_pick() -> None:
    """Si Colorimetría/largos quedó en Iniciar, Inventor no responde al COM."""
    try:
        PICK_STOP.parent.mkdir(parents=True, exist_ok=True)
        PICK_STOP.write_text("1", encoding="utf-8")
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Barra flotante AutoDXF")
    parser.add_argument("--dev", action="store_true", help="Carga el servidor de Vite en la ventana")
    args = parser.parse_args()
    _abort_stale_pick()
    _kill_stale_snapshot_workers()

    url = _start_dev_server() if args.dev else _dist_url()
    api = ToolbarApi()
    api.page_url = url
    window = webview.create_window(
        "AutoDXF",
        url,
        js_api=api,
        width=1080,
        height=760,
        min_size=(880, 620),
        on_top=True,
        background_color="#FFFFFF",
        text_select=True,
    )
    api.attach(window)
    webview.start()


def _dist_url() -> str:
    if not DIST_INDEX.exists():
        raise SystemExit("Falta ui/dist. Ejecuta Iniciar AutoDXF.bat para construir la barra.")
    return DIST_INDEX.resolve().as_uri()


def _start_dev_server() -> str:
    if not _url_up(DEV_URL):
        subprocess.Popen(
            ["pnpm", "dev", "--host", "127.0.0.1", "--port", "4173", "--strictPort"],
            cwd=UI_DIR,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        for _ in range(40):
            if _url_up(DEV_URL):
                break
            time.sleep(0.25)
    return DEV_URL


def _url_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.4) as response:
            return int(response.status) < 500
    except Exception:
        return False


def _kill_stale_snapshot_workers() -> None:
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*inventor_worker.py*snapshot*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            timeout=8,
            creationflags=0x08000000,
        )
    except Exception:
        pass


def _inventor_process(command: str, payload: dict | None = None) -> dict:
    """Inventor se consulta en otro proceso: WebView2 rompe el COM de este."""
    worker = Path(__file__).with_name("inventor_worker.py")
    if command == "snapshot":
        _kill_stale_snapshot_workers()
    timeout = (
        12
        if command == "snapshot"
        else 1800
        if command in {"export", "shapes", "acotacion", "parts", "roles", "blocks", "weld", "multibody"}
        else 180
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.Popen(
            [sys.executable, str(worker), command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=0x08000000,
        )
    except Exception as ex:
        return _inventor_failure(str(ex))
    try:
        out, err = proc.communicate(json.dumps(payload or {}).encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=3)
        except Exception:
            pass
        if command == "snapshot":
            return _inventor_failure(
                "Inventor está ocupado (selector de Colorimetría o un guardado). "
                "Pulsa Esc en Inventor, Terminar en Colorimetría y Actualizar. No cierres Inventor."
            )
        return _inventor_failure("Inventor tardó demasiado en responder.")

    raw = _decode_output(out).strip()
    if not raw:
        detail = " ".join(_decode_output(err).split())[:300]
        if proc.returncode == 3:
            detail = detail or "Inventor no contestó (COM bloqueado)."
        return _inventor_failure(detail or "Inventor no respondió.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _inventor_failure(raw[:300])
    if not isinstance(parsed, dict):
        return _inventor_failure("Respuesta inválida de Inventor.")
    return parsed


def _decode_output(data: bytes | None) -> str:
    blob = data or b""
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("cp1252", errors="replace")


def _with_job(session, explicit: str = "") -> dict:
    if not isinstance(session, dict):
        session = {}
    session["jobName"] = resolve_job(
        explicit,
        str(session.get("assemblyName") or ""),
        str(session.get("assemblyPath") or ""),
    )
    return session


def _inventor_failure(message: str) -> dict:
    return {
        "inventorConnected": False,
        "inventorVersion": "",
        "assemblyName": "",
        "assemblyPath": "",
        "jobName": "",
        "parts": [],
        "ok": False,
        "exported": 0,
        "csvPath": "",
        "message": message,
    }


def _safe_catalog() -> dict:
    try:
        return load_catalog()
    except Exception as ex:
        return {
            "connected": False,
            "source": "FALLBACK",
            "message": str(ex),
            "materials": [],
            "herinoxConnected": False,
            "nestingConnected": False,
        }


if __name__ == "__main__":
    main()
