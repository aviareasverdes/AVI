# -*- coding: utf-8 -*-
"""Registro de cada solicitud: archivo local (siempre) y Google Sheets (si está configurado)."""
import json
import urllib.request
from pathlib import Path


def agregar(carpeta, fila, sheets_url="", sheets_secret=""):
    """Guarda la fila en registro.jsonl y, si hay URL de Sheets, la manda al Apps Script.
    Devuelve 'sheet_ok', 'sheet_error: ...' o 'solo_local'."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    with open(carpeta / "registro.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    if not sheets_url:
        return "solo_local"
    try:
        cuerpo = json.dumps({"secret": sheets_secret, "action": "agregar_solicitud", "fila": fila}).encode("utf-8")
        req = urllib.request.Request(sheets_url, data=cuerpo, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            texto = r.read().decode("utf-8", "replace")
        return "sheet_ok" if '"ok":true' in texto.replace(" ", "") else "sheet_error: " + texto[:200]
    except Exception as e:  # noqa: BLE001
        return "sheet_error: %r" % e
