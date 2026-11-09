"""Exporta el sólido de una pieza a STEP (AP214) con el traductor de Inventor."""

from __future__ import annotations

from pathlib import Path

STEP_ADDIN = "{90AF7F40-0C01-11D5-8E83-0010B541CD80}"
ARCHIVO = 13059


def exportar_step(doc, dest: str | Path) -> Path:
    """Guarda `doc` en `dest`. El archivo queda junto a los JPG de maquinado."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    app = doc.Parent
    try:
        import win32com.client

        addin = win32com.client.dynamic.Dispatch(app.ApplicationAddIns.ItemById(STEP_ADDIN))
        try:
            if not bool(addin.Activated):
                addin.Activate()
        except Exception:
            pass
        ctx = app.TransientObjects.CreateTranslationContext()
        ctx.Type = ARCHIVO
        opts = app.TransientObjects.CreateNameValueMap()
        try:
            opts.Add("ApplicationProtocolType", 3)
        except Exception:
            pass
        addin.SaveCopyAs(doc, ctx, opts, str(dest))
    except Exception:
        doc.SaveAs(str(dest), True)
    if not dest.is_file() or dest.stat().st_size < 64:
        raise RuntimeError(f"STEP vacío: {dest.name}")
    return dest
