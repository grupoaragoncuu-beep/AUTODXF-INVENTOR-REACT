"""JOB de compañía: el ingeniero lo corrige en el módulo y lo usan todos los procesos."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "config" / "job_override.json"


def assembly_stem(name: str = "", path: str = "") -> str:
    raw = Path(path or name or "JOB")
    stem = raw.stem or str(name or "JOB")
    return clean_job(stem)


def clean_job(text: str) -> str:
    value = " ".join(str(text or "").split())
    for ch in '<>:"/\\|?*':
        value = value.replace(ch, "-")
    value = value.strip(" .")
    return value or "JOB"


def _key(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lower()


def load_store() -> dict:
    try:
        raw = json.loads(STORE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"job": "", "assemblyPath": "", "byPath": {}}
    if not isinstance(raw, dict):
        return {"job": "", "assemblyPath": "", "byPath": {}}
    by_path = raw.get("byPath") if isinstance(raw.get("byPath"), dict) else {}
    return {
        "job": str(raw.get("job") or ""),
        "assemblyPath": str(raw.get("assemblyPath") or ""),
        "byPath": {str(k): str(v) for k, v in by_path.items() if str(v).strip()},
    }


def save_job(job: str, assembly_path: str = "", assembly_name: str = "") -> dict:
    data = load_store()
    cleaned = clean_job(job) if str(job or "").strip() else assembly_stem(assembly_name, assembly_path)
    path_key = _key(assembly_path)
    if path_key:
        data["byPath"][path_key] = cleaned
    data["job"] = cleaned
    data["assemblyPath"] = assembly_path
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "job": cleaned, "message": f"JOB: {cleaned}"}


def resolve_job(explicit: str = "", name: str = "", path: str = "") -> str:
    if str(explicit or "").strip():
        return clean_job(explicit)
    data = load_store()
    path_key = _key(path)
    by_path = data.get("byPath") or {}
    if path_key and by_path.get(path_key):
        return clean_job(str(by_path[path_key]))
    current = _key(str(data.get("assemblyPath") or ""))
    if path_key and current == path_key and str(data.get("job") or "").strip():
        return clean_job(str(data["job"]))
    return assembly_stem(name, path)
