"""Consulta en vivo el catálogo que AutoDXF usa para nombrar DXF."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = ROOT / "herinox_sync.local.json"
LOCAL_CONFIG = ROOT / "config" / "autodxf.local.json"
HERINOX_ENV = Path(r"E:\react-Herinox\server\.env")
SQLTOOLS_SETTINGS = Path.home() / "AppData" / "Roaming" / "Cursor" / "User" / "settings.json"

PLATE_SQL = """
SELECT DISTINCT btrim(material) AS material
FROM "Plate"
WHERE material IS NOT NULL
  AND btrim(material) <> ''
  AND codigo IS NOT NULL
  AND btrim(codigo) <> ''
  AND COALESCE("inventoryType", 'PLATE') IN ('PLATE', 'PLACA', 'LAMINA')
ORDER BY 1
"""

NESTING_GRADE_SQL = """
SELECT DISTINCT btrim(split_part(material, '|', 3)) AS grade
FROM material_requerido_ldg
WHERE material IS NOT NULL
  AND btrim(material) <> ''
  AND btrim(split_part(material, '|', 3)) <> ''
ORDER BY 1
"""


def load_catalog() -> dict:
    materials: list[str] = []
    notes: list[str] = []
    herinox_ok = False
    nesting_ok = False

    herinox = _herinox_target()
    if herinox is None:
        notes.append("Herinox: sin DATABASE_URL.")
    else:
        try:
            materials.extend(_query(herinox, PLATE_SQL))
            herinox_ok = True
            notes.append(f"Herinox Plate: {herinox['label']}")
        except Exception as ex:
            notes.append(f"Herinox no disponible: {_short(ex)}")

    nesting = _nesting_target()
    if nesting is None:
        notes.append("NestingPro: sin conexión guardada.")
    else:
        try:
            grades = _query(nesting, NESTING_GRADE_SQL)
            materials.extend(grades)
            nesting_ok = True
            notes.append(f"NestingPro en vivo: {nesting['label']} ({len(grades)} materiales)")
        except Exception as ex:
            notes.append(f"NestingPro no disponible: {_short(ex)}")

    unique = _unique(materials)
    canonical = _unique(normalize_material(name) for name in unique)
    source = "NESTINGPRO" if nesting_ok else "HERINOX" if herinox_ok else "FALLBACK"
    payload = {
        "enabled": True,
        "raw_materials_csv": "|".join(unique),
        "canonical_materials_csv": "|".join(canonical),
        "raw_materials_count": len(unique),
        "canonical_materials_count": len(canonical),
        "bridge_source": source if unique else "FALLBACK",
        "bridge_detail": " ".join(notes),
    }
    SYNC_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "connected": herinox_ok or nesting_ok,
        "source": payload["bridge_source"],
        "message": payload["bridge_detail"],
        "materials": canonical,
        "herinoxConnected": herinox_ok,
        "nestingConnected": nesting_ok,
    }


def normalize_material(raw: str) -> str:
    text = re.sub(r"\s+", " ", (raw or "").replace("_", " ")).strip().upper()
    if not text:
        return ""
    if "A 36" in text or "A36" in text:
        if "GALV" in text:
            return "A 36 GALV"
        return "A 36"
    if "CARBON" in text or ("ACERO" in text and "CARBONO" in text):
        return "A 36"
    if "GALVAN" in text:
        return "A 36 GALV"
    if "SSTL" in text and "304" in text:
        return "SSTL 304"
    if "INOX" in text or "STAINLESS" in text:
        return "SSTL 304"
    if "ALUMIN" in text or text.startswith("AL "):
        return "Aluminio"
    return text.title()


def _query(target: dict, sql: str) -> list[str]:
    conn = psycopg2.connect(
        host=target["host"],
        port=target["port"],
        dbname=target["dbname"],
        user=target["user"],
        password=target["password"],
        connect_timeout=6,
    )
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(sql)
            return [str(row[0]).strip() for row in cur.fetchall() if row and str(row[0]).strip()]
    finally:
        conn.close()


def _herinox_target() -> dict | None:
    local = _read_local()
    url = str(local.get("herinox_database_url") or "").strip()
    if not url:
        url = _database_url_from_env(HERINOX_ENV)
    if not url:
        return None
    return _target_from_url(url, "Herinox")


def _nesting_target() -> dict | None:
    local = _read_local()
    block = local.get("nestingpro")
    if isinstance(block, dict) and block.get("host"):
        return {
            "host": block.get("host"),
            "port": int(block.get("port") or 5432),
            "dbname": block.get("database") or block.get("dbname"),
            "user": block.get("username") or block.get("user"),
            "password": block.get("password") or "",
            "label": f"{block.get('host')}:{block.get('port')}/{block.get('database') or block.get('dbname')}",
        }
    return _sqltools_nesting()


def _sqltools_nesting() -> dict | None:
    if not SQLTOOLS_SETTINGS.exists():
        return None
    try:
        settings = json.loads(SQLTOOLS_SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return None
    for conn in settings.get("sqltools.connections", []):
        name = str(conn.get("name", ""))
        if "nest" not in name.lower():
            continue
        if not conn.get("server") or not conn.get("database"):
            continue
        return {
            "host": conn.get("server"),
            "port": int(conn.get("port") or 5432),
            "dbname": conn.get("database"),
            "user": conn.get("username") or "postgres",
            "password": conn.get("password") or "",
            "label": f"{name} {conn.get('server')}:{conn.get('port')}/{conn.get('database')}",
        }
    return None


def _target_from_url(url: str, label: str) -> dict | None:
    parsed = urlparse(url)
    if not parsed.hostname:
        return None
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/").split("?")[0],
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "label": f"{label} {parsed.hostname}:{parsed.port or 5432}{parsed.path}",
    }


def _database_url_from_env(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def _read_local() -> dict:
    if not LOCAL_CONFIG.exists():
        return {}
    try:
        data = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _unique(values) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = text.upper()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _short(ex: Exception) -> str:
    text = " ".join(str(ex).split())
    return text[:220]
