# -*- coding: utf-8 -*-
"""Prueba de punta a punta sin micrófono: simula a José escribiendo. Se ejecuta en el servidor."""
import asyncio
import json
import sys

import aiohttp

import os
URL = os.environ.get("AVI_URL", "http://127.0.0.1:8200/ws?modo=voz")
MENSAJES = sys.argv[1:] or [
    "Necesito un vehículo para mañana de 8 a 12, el chofer es Jaime Rojas.",
    "El funcionario es Alejandro y el coordinador también.",
    "Sí, envíalo.",
]


async def turno(ws, texto=None, espera=75):
    if texto:
        print("\nJOSÉ:", texto)
        await ws.send_json({"type": "text", "text": texto})
    avi, estado, extra, audio = "", None, [], 0
    completo = False
    try:
        async with asyncio.timeout(espera):
            while True:
                try:
                    m = await ws.receive(timeout=7 if completo else espera)
                except asyncio.TimeoutError:
                    break
                if m.type == aiohttp.WSMsgType.BINARY:
                    audio += len(m.data)
                    completo = False
                elif m.type == aiohttp.WSMsgType.TEXT:
                    j = json.loads(m.data)
                    t = j.get("type")
                    if t == "transcripcion" and j["rol"] == "avi":
                        avi += j["texto"]
                        completo = False
                    elif t == "estado":
                        estado = j
                    elif t in ("enviado", "error", "aviso", "listo"):
                        extra.append(j)
                    elif t == "turno_completo":
                        completo = True
                else:
                    break
    except TimeoutError:
        print("  (tiempo agotado esperando respuesta)")
    print("AVI:", avi.strip(), "| audio bytes:", audio)
    if estado:
        print("  formulario:", {c["etiqueta"]: (c["valor"] or "-") for c in estado["campos"]}, "| completo:", estado["completo"])
    for e in extra:
        print("  evento:", e)


async def main():
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(URL, max_msg_size=0) as ws:
            await turno(ws)  # saludo inicial
            for t in MENSAJES:
                await turno(ws, t)


asyncio.run(main())
