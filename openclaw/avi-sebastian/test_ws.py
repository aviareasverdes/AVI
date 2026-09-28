# -*- coding: utf-8 -*-
"""Prueba de punta a punta sin micrófono: simula a la persona escribiendo. Se ejecuta en el servidor."""
import asyncio
import json
import os
import sys

import aiohttp

URL = os.environ.get("AVI_URL", "http://127.0.0.1:8300/ws?modo=voz")
MENSAJES = sys.argv[1:] or ["Hola"]


async def turno(ws, texto=None, espera=75):
    if texto:
        print("\nPERSONA:", texto)
        await ws.send_json({"type": "text", "text": texto})
    avi, extra, audio = "", [], 0
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
                    elif t in ("error", "aviso", "listo", "correo_estado"):
                        extra.append(j)
                    elif t == "turno_completo":
                        completo = True
                else:
                    break
    except TimeoutError:
        print("  (tiempo agotado esperando respuesta)")
    print("AVI:", avi.strip(), "| audio bytes:", audio)
    for e in extra:
        print("  evento:", e)


async def main():
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(URL, max_msg_size=0) as ws:
            await turno(ws)  # saludo inicial
            for t in MENSAJES:
                await turno(ws, t)


asyncio.run(main())
