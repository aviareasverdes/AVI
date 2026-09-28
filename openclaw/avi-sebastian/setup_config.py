# -*- coding: utf-8 -*-
"""Crea config.json en el servidor (solo la primera vez). Copia los datos del correo desde OpenClaw
sin mostrarlos. El archivo queda con permisos 600."""
import json
import os
import secrets
from pathlib import Path

aqui = Path(__file__).resolve().parent
destino = aqui / "config.json"

if destino.exists():
    cfg = json.loads(destino.read_text(encoding="utf-8"))
    print("config.json ya existe; se conserva (secret_path=%s)" % cfg["secret_path"])
else:
    oc = json.loads((Path.home() / ".openclaw" / "openclaw.json").read_text(encoding="utf-8"))
    smtp = oc["plugins"]["entries"]["email"]["config"]["smtp"]
    cfg = {
        "secret_path": "avi-sebastian-" + secrets.token_urlsafe(9).replace("_", "x").replace("-", "y"),
        "puerto": 8300,
        "gemini_key_file": str(aqui / ".gemini_key"),
        "modelos": ["gemini-3.8-live", "gemini-3.1-flash-live-preview", "gemini-2.5-flash-native-audio-latest"],
        "voz": "Kore",
        "modo_prueba": True,
        "destinatario": "",
        "destinatario_prueba": "avi.areasverdes@gmail.com",
        "usuario_llamado": "Sebastian",
        "usuario_completo": "Sebastian",
        "google_sa_file": str(aqui / ".google-sa.json"),
        "smtp": {k: smtp[k] for k in ("host", "port", "username", "password", "from", "name")},
    }
    destino.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(destino, 0o600)
    print("config.json creado; secret_path=%s" % cfg["secret_path"])
