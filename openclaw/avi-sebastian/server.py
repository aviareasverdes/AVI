# -*- coding: utf-8 -*-
"""AVI: puente entre la app del celular y Gemini Live. Asistente general (fecha/hora, clima, correo libre)."""
import array
import asyncio
import base64
import re
import json
import logging
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from aiohttp import WSMsgType, web

import arbolado
import correo
import informe
from reglas import (DIAS, MESES, ahora_chile)

BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
STATIC = BASE / "static"
SALIDA = BASE / "salida"
LIVE_URL = ("wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta."
            "GenerativeService.BidiGenerateContent")
log = logging.getLogger("avi")

PERMITIDOS = {
    "index.html": "text/html; charset=utf-8",
    "manifest.webmanifest": "application/manifest+json",
    "sw.js": "application/javascript",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
}

TOOLS = [{"functionDeclarations": [
    {
        "name": "guardar_borrador_correo",
        "description": "Guarda o actualiza el borrador del correo (asunto y/o mensaje). Llámala cada vez que redactes el correo por primera vez y cada vez que lo corrijas, ANTES de leérselo a la persona. Así el borrador queda guardado y no depende de que lo recuerdes tú sola.",
        "parameters": {"type": "OBJECT", "properties": {
            "asunto": {"type": "STRING", "description": "Asunto actual del borrador, claro y breve."},
            "mensaje": {"type": "STRING", "description": "Correo completo actual del borrador: saludo, desarrollo y cierre con firma. Usa saltos de línea entre párrafos."},
        }},
    },
    {
        "name": "enviar_correo",
        "description": "Envía el correo ya guardado con guardar_borrador_correo a la persona dueña de esta AVI. Llámala SOLO después de que confirme claramente el envío (tras leerle el asunto y el correo redactado). No hace falta repetir el asunto ni el mensaje si ya quedaron guardados en el borrador.",
        "parameters": {"type": "OBJECT", "properties": {
            "asunto": {"type": "STRING", "description": "Solo si cambió respecto al último borrador guardado; si no, déjalo vacío y se usará el del borrador."},
            "mensaje": {"type": "STRING", "description": "Solo si cambió respecto al último borrador guardado; si no, déjalo vacío y se usará el del borrador."},
            "destinatario": {"type": "STRING", "description": "SOLO si nombró a otra persona o dio otro correo como destinatario, escríbelo aquí tal cual. Si no nombró destinatario, déjalo vacío."},
        }},
    },
    {
        "name": "obtener_fecha_hora",
        "description": "Devuelve la fecha y la hora actuales en Chile, el día de la semana y los próximos 7 días. Úsala cuando pregunten qué día es, qué hora es, o para calcular fechas como 'el viernes'.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "obtener_clima",
        "description": "Devuelve el clima actual y el pronóstico de hoy y los próximos días para una ciudad.",
        "parameters": {"type": "OBJECT", "properties": {
            "ciudad": {"type": "STRING", "description": "Ciudad. Si no la dicen, pregúntala (no hay una por defecto)."},
        }},
    },
    {
        "name": "solicitudes_arbolado_pendientes",
        "description": "Devuelve las solicitudes de arbolado (podas, cortes, etc.) que todavía NO tienen un trabajo realizado, con su ubicación GPS. Se puede pedir todas, o filtradas por sector/zona (por ejemplo 'Las Compañías' o 'Casco Histórico').",
        "parameters": {"type": "OBJECT", "properties": {
            "zona": {"type": "STRING", "description": "Nombre del sector o zona para filtrar. Déjalo vacío si pide todas."},
        }},
    },
    {
        "name": "informe_trabajos_ejecutados",
        "description": "Genera y envía por correo un informe en Excel de los trabajos de arbolado YA EJECUTADOS/REALIZADOS en un rango de fechas (fotos reales, minimapa con ubicación y enlace a Google Maps de cada trabajo). Úsala solo cuando pida un informe o reporte de trabajos ejecutados/realizados/hechos (no de solicitudes pendientes, para eso usa solicitudes_arbolado_pendientes). Si no dio el rango de fechas, PREGÚNTASELO ANTES de llamar a esta herramienta; no asumas fechas.",
        "parameters": {"type": "OBJECT", "properties": {
            "desde": {"type": "STRING", "description": "Fecha de inicio del rango, formato AAAA-MM-DD. Obligatoria."},
            "hasta": {"type": "STRING", "description": "Fecha de término del rango, formato AAAA-MM-DD. Obligatoria."},
            "zona": {"type": "STRING", "description": "Sector o zona para filtrar. Déjalo vacío si pidió todos los sectores."},
        }, "required": ["desde", "hasta"]},
    },
]}]

NOMBRE = CFG.get("usuario_llamado", "")
NOMBRE_COMPLETO = CFG.get("usuario_completo", NOMBRE)


def nombre(s):
    """Cambia el marcador 'PERSONA' de los textos por el nombre real del usuario."""
    s = s.replace("PERSONA_COMPLETO", NOMBRE_COMPLETO)
    return s.replace("PERSONA", NOMBRE)


TOOLS = json.loads(nombre(json.dumps(TOOLS, ensure_ascii=False)))

WMO = {0: "despejado", 1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado", 45: "con neblina",
       48: "con neblina", 51: "con llovizna ligera", 53: "con llovizna", 55: "con llovizna intensa",
       56: "con llovizna helada", 57: "con llovizna helada", 61: "con lluvia ligera", 63: "con lluvia",
       65: "con lluvia fuerte", 66: "con lluvia helada", 67: "con lluvia helada", 71: "con nieve ligera",
       73: "con nieve", 75: "con nieve fuerte", 77: "con granizo fino", 80: "con chubascos ligeros",
       81: "con chubascos", 82: "con chubascos fuertes", 85: "con chubascos de nieve",
       86: "con chubascos de nieve", 95: "con tormenta", 96: "con tormenta y granizo", 99: "con tormenta y granizo"}


def _http_json(url, timeout=10, intentos=3):
    ultimo = None
    for _ in range(intentos):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(0.5)
    raise ultimo


def fecha_hora_sync():
    a = ahora_chile()
    proximos = []
    for i in range(0, 8):
        d = a.date() + timedelta(days=i)
        proximos.append({"fecha": d.isoformat(), "dia": DIAS[d.weekday()],
                         "referencia": "hoy" if i == 0 else ("mañana" if i == 1 else "")})
    return {"ok": True, "fecha": "%s %d de %s de %d" % (DIAS[a.weekday()], a.day, MESES[a.month - 1].lower(), a.year),
            "hora": a.strftime("%H:%M"), "dia_semana": DIAS[a.weekday()], "iso": a.isoformat(),
            "zona_horaria": "America/Santiago (Chile)", "proximos_dias": proximos}


def clima_sync(ciudad):
    ciudad = (ciudad or "").strip()
    if not ciudad:
        return {"ok": False, "error": "no dijiste la ciudad"}

    def geo(cc):
        p = {"name": ciudad, "count": 1, "language": "es", "format": "json"}
        if cc:
            p["countryCode"] = cc
        r = _http_json("https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(p))
        return (r.get("results") or [None])[0]

    lugar = geo("CL") or geo(None)
    if not lugar:
        return {"ok": False, "error": "no encontré la ciudad '%s'" % ciudad}
    p = {"latitude": lugar["latitude"], "longitude": lugar["longitude"], "timezone": "America/Santiago",
         "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
         "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
         "forecast_days": 4}
    d = _http_json("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(p))
    c, dia = d["current"], d["daily"]
    pron = []
    for i, f in enumerate(dia["time"]):
        pron.append({"fecha": f, "referencia": "hoy" if i == 0 else ("mañana" if i == 1 else ""),
                     "cielo": WMO.get(dia["weather_code"][i], "variable"),
                     "maxima": round(dia["temperature_2m_max"][i]), "minima": round(dia["temperature_2m_min"][i]),
                     "probabilidad_lluvia_pct": dia["precipitation_probability_max"][i]})
    return {"ok": True, "lugar": "%s, %s" % (lugar["name"], lugar.get("admin1", "Chile")),
            "ahora": {"temperatura": round(c["temperature_2m"]), "sensacion": round(c["apparent_temperature"]),
                      "humedad_pct": c["relative_humidity_2m"], "cielo": WMO.get(c["weather_code"], "variable"),
                      "viento_kmh": round(c["wind_speed_10m"]), "lluvia_mm": c["precipitation"]},
            "pronostico": pron, "fuente": "Open-Meteo"}


def instruccion(ahora):
    dia = DIAS[ahora.weekday()]
    mes = MESES[ahora.month - 1].lower()
    texto = (
        "Eres AVI, la asistente personal de voz de PERSONA, en Chile. "
        "PERSONA es la única persona que te usa; la llamas 'PERSONA' siempre. Estás pensada para ayudarla en "
        "muchas cosas, y con el tiempo vas a ir aprendiendo más. Al saludar, pregúntale en qué le puedes ayudar.\n"
        "Hablas en español de Chile, con voz femenina cálida, eficiente y directa. Frases cortas y naturales. "
        "La tratas por su nombre y con confianza, sin exagerar los modismos. No repitas todo lo que ya dijo; "
        "confirma solo lo necesario.\n\n"
        "HOY es %s %d de %s de %d y son las %s en Chile. Úsalo para entender 'hoy', 'mañana', 'el viernes', etc., "
        "y pasa las fechas a las herramientas en formato AAAA-MM-DD.\n\n"
        "POR AHORA PUEDES SOLO ESTAS CINCO COSAS, y únicamente cuando te las pida (nunca las ofrezcas ni las digas "
        "por iniciativa propia; por ejemplo no des la fecha, la hora ni el clima si no te lo preguntan):\n"
        "A) Decir la fecha y la hora, cuando te las pregunte: usa obtener_fecha_hora (no adivines, la hora cambia).\n"
        "B) Decir el clima, cuando te lo pregunte: usa obtener_clima. Si no dice la ciudad, pregúntasela (no asumas "
        "ninguna por defecto). Responde corto: cómo está ahora, la máxima y la mínima de hoy, y la lluvia solo si la "
        "probabilidad es relevante.\n"
        "C) Enviar un correo libre: cuando diga que quiere enviar un correo (o mandarse un mensaje, una nota, etc.), "
        "le preguntas de qué trata. El correo SIEMPRE va a su propio correo; no preguntes a quién. "
        "Tu trabajo es AYUDARLA A REDACTAR el correo para que quede bien: te cuenta la idea con sus palabras (puede "
        "ser desordenada) y tú redactas el correo completo: un asunto claro y breve, un saludo, el desarrollo bien "
        "escrito, ordenado y con tono profesional pero cercano, y un cierre con 'Saludos cordiales, PERSONA_COMPLETO'. "
        "Usa solo la información que te dio: no inventes datos, fechas, nombres ni cifras. Si para redactarlo bien "
        "falta algo importante, pregúntalo (una sola pregunta, corta).\n"
        "Si el correo va a ser largo, ANTES de empezar a redactarlo di primero una frase corta como 'dame un segundo, "
        "lo estoy redactando' o 'un momento, lo preparo', y recién después sigue con el borrador; así no queda un "
        "silencio largo mientras lo piensas.\n"
        "Apenas tengas un borrador (asunto y mensaje), llama a guardar_borrador_correo ANTES de leérselo. Hazlo de "
        "nuevo cada vez que lo corrijas. Así el borrador queda guardado aparte y no dependes de recordar tú misma "
        "todo el texto si la conversación se alarga.\n"
        "Luego léele el asunto y el correo redactado (breve, sin leer el saludo ni la firma) y pregunta '¿Lo envío o "
        "quieres cambiar algo?'. Si pide cambios (más formal, más corto, agregar o quitar algo, otro asunto), "
        "reescribe, guarda el nuevo borrador con guardar_borrador_correo y vuelve a confirmar. "
        "Llama a enviar_correo SOLO cuando confirme claramente; como el asunto y el mensaje ya quedaron guardados en "
        "el borrador, no hace falta que se los repitas a la herramienta. Si en algún momento pide enviarlo a otra "
        "persona o a otro correo, dile que solo puedes enviar correos a PERSONA_COMPLETO (a ella misma) y no lo "
        "envíes a nadie más; si llamas a enviar_correo con otro destinatario, la herramienta lo rechazará.\n"
        "D) Solicitudes de arbolado pendientes: cuando te pida las solicitudes que faltan, las que no tienen trabajo, "
        "o las de un sector/zona en particular (por ejemplo 'las de Las Compañías' o 'las del Casco Histórico'), usa "
        "solicitudes_arbolado_pendientes (con 'zona' si la nombró, vacío si pidió todas). NO leas la lista en voz "
        "alta, ni una por una: el detalle numerado (con el link de Google Maps de cada una) ya se muestra solo en la "
        "pantalla de la app. Tú solo dile, en una frase corta: cuántas solicitudes hay en total (y en qué zona "
        "buscó, si dio una zona, para que pueda corregirte si no era esa) y que le enviaste el detalle a la pantalla. "
        "Después pregúntale si quiere que además se lo mandes a su correo. Si dice que sí, usa "
        "guardar_borrador_correo con asunto 'Solicitudes pendientes' + la zona si había, y como mensaje el texto de "
        "la lista tal cual viene en 'texto_detalle' (no lo reescribas como carta, es un listado, mándalo tal cual con "
        "un cierre breve), y luego enviar_correo. Si la herramienta no encuentra la zona, dile que no la encontró, "
        "sin inventar datos.\n"
        "E) Informe de trabajos ejecutados: cuando pida un informe o reporte de los trabajos YA ejecutados/realizados "
        "(por ejemplo 'necesito los trabajos ejecutados en el Casco Histórico' o 'mándame un informe de lo hecho la "
        "semana pasada'), usa informe_trabajos_ejecutados. Si no te dio el rango de fechas, PREGÚNTASELO primero (no "
        "asumas un rango); si dio una zona, pásala. Esta herramienta genera el Excel (con fotos, minimapa y ubicación "
        "de cada trabajo) y lo envía por correo en un solo paso; no hace falta guardar_borrador_correo para esto, y "
        "la herramienta puede tardar unos segundos en responder (armando el archivo), así que si te pide el informe "
        "dile brevemente algo como 'dame un momento, lo estoy preparando' antes de llamarla. Cuando responda, dile "
        "cuántos trabajos incluyó y que se lo enviaste por correo; si hubo avisos menores al generarlo, no se los "
        "leas uno por uno, solo menciona si hubo alguno.\n\n"
        "Si te pide cualquier otra cosa que no esté en esta lista, responde en una frase breve que todavía no estás "
        "configurada para eso (por ejemplo: 'Todavía no estoy configurada para eso'). No lo intentes resolver por tu "
        "cuenta, no inventes información y no propongas alternativas por tu cuenta.\n"
        "Si no entiendes algo, pide que lo repita, brevemente. No inventes datos. Nunca digas que enviaste algo si la "
        "herramienta devolvió un error."
    ) % (dia, ahora.day, mes, ahora.year, ahora.strftime("%H:%M"))
    return nombre(texto)


class Sesion:
    def __init__(self, cli, voz=False):
        self.cli = cli
        self.voz = voz  # True = modo voz (se reenvía el audio de AVI y se saluda); False = modo texto
        self.correo_borrador = {"asunto": None, "mensaje": None}
        self.enviados = {}
        self.http = None
        self.gws = None

    async def a_cli(self, obj):
        if not self.cli.closed:
            await self.cli.send_json(obj)

    async def correo_estado(self):
        await self.a_cli({"type": "correo_estado", "asunto": self.correo_borrador.get("asunto") or "",
                           "mensaje": self.correo_borrador.get("mensaje") or ""})

    # ---------- herramientas ----------
    async def herramienta(self, nombre, args):
        args = args or {}
        try:
            if nombre == "guardar_borrador_correo":
                if args.get("asunto"):
                    self.correo_borrador["asunto"] = args["asunto"]
                if args.get("mensaje"):
                    self.correo_borrador["mensaje"] = args["mensaje"]
                await self.correo_estado()
                return {"ok": True}
            if nombre == "enviar_correo":
                return await self.enviar_correo(args)
            if nombre == "solicitudes_arbolado_pendientes":
                try:
                    res = await asyncio.to_thread(
                        arbolado.solicitudes_pendientes, CFG["google_sa_file"], args.get("zona") or None)
                except Exception as e:  # noqa: BLE001
                    log.warning("arbolado: %r", e)
                    return {"ok": False, "error": "no pude consultar las solicitudes en este momento"}
                if res.get("ok") and res.get("solicitudes"):
                    await self.a_cli({"type": "detalle_solicitudes", "zona": res.get("zona"),
                                       "total": res["total"], "html": res["html_detalle"]})
                return res
            if nombre == "informe_trabajos_ejecutados":
                try:
                    desde = datetime.strptime((args.get("desde") or "").strip(), "%Y-%m-%d").date()
                    hasta = datetime.strptime((args.get("hasta") or "").strip(), "%Y-%m-%d").date()
                except ValueError:
                    return {"ok": False, "error": "el rango de fechas no es válido; pídeselo de nuevo en formato AAAA-MM-DD"}
                try:
                    res = await asyncio.to_thread(
                        informe.generar_informe, CFG["google_sa_file"], desde, hasta, args.get("zona") or None)
                except Exception as e:  # noqa: BLE001
                    log.exception("informe")
                    return {"ok": False, "error": "no pude generar el informe en este momento"}
                if not res.get("ok"):
                    return res
                prueba = bool(CFG.get("modo_prueba", True))
                para = CFG["destinatario_prueba"] if prueba else CFG["destinatario"]
                cuerpo = "Adjunto el informe de trabajos ejecutados entre %s y %s%s." % (
                    desde.strftime("%d-%m-%Y"), hasta.strftime("%d-%m-%Y"),
                    (" en '%s'" % args["zona"]) if args.get("zona") else "")
                if res.get("errores"):
                    cuerpo += "\n\nAvisos al generarlo:\n" + "\n".join(res["errores"])
                try:
                    await asyncio.to_thread(correo.enviar, CFG["smtp"], para,
                        ("[PRUEBA] " if prueba else "") + res["nombre"], cuerpo, [(res["nombre"], res["bytes"])])
                except Exception as e:  # noqa: BLE001
                    log.exception("informe correo")
                    return {"ok": False, "error": "el informe se generó pero no se pudo enviar por correo: %s" % e}
                return {"ok": True, "mensaje": "Informe generado y enviado, con %d trabajos." % res["filas"],
                        "filas": res["filas"], "avisos": len(res.get("errores") or [])}
            if nombre == "obtener_fecha_hora":
                return fecha_hora_sync()
            if nombre == "obtener_clima":
                try:
                    return await asyncio.to_thread(clima_sync, args.get("ciudad"))
                except Exception as e:  # noqa: BLE001
                    log.warning("clima: %r", e)
                    return {"ok": False, "error": "no pude consultar el clima en este momento"}
            return {"ok": False, "error": "herramienta desconocida: %s" % nombre}
        except Exception as e:  # noqa: BLE001
            log.exception("herramienta %s", nombre)
            return {"ok": False, "error": str(e)}

    async def enviar_correo(self, args):
        asunto = (args.get("asunto") or "").strip() or (self.correo_borrador.get("asunto") or "").strip()
        mensaje = (args.get("mensaje") or "").strip() or (self.correo_borrador.get("mensaje") or "").strip()
        dest = (args.get("destinatario") or "").strip()
        prueba = bool(CFG.get("modo_prueba", True))
        para = CFG["destinatario_prueba"] if prueba else CFG["destinatario"]
        if dest:
            d = re.sub(r"[^a-z0-9@. ]", " ", unicodedata.normalize("NFD", dest.lower()).encode("ascii", "ignore").decode())
            palabras_yo = _sin_acentos(NOMBRE).lower().split() + ["yo", "mi", "mismo", "mia", "misma"]
            es_el = ("@" not in d and any(p and p in d.split() for p in palabras_yo)) \
                or d.strip() in (CFG["destinatario"].lower(), para.lower())
            if not es_el:
                return {"ok": False, "error": "destinatario no permitido",
                        "instruccion": "Dile que solo puedes enviar correos a %s. No lo envíes a nadie más." % NOMBRE_COMPLETO}
        if not asunto or not mensaje:
            return {"ok": False, "error": "falta el asunto o el mensaje"}
        clave = "correo|" + asunto + "|" + mensaje
        if time.time() - self.enviados.get(clave, 0) < 120:
            return {"ok": True, "mensaje": "Ese correo ya se había enviado hace un momento."}
        cuerpo = mensaje + "\n\n--\nEnviado por AVI."
        try:
            await asyncio.to_thread(correo.enviar, CFG["smtp"], para, ("[PRUEBA] " if prueba else "") + asunto, cuerpo, [])
        except Exception as e:  # noqa: BLE001
            log.exception("correo libre")
            return {"ok": False, "error": "no se pudo enviar el correo: %s" % e}
        self.enviados[clave] = time.time()
        self.correo_borrador = {"asunto": None, "mensaje": None}
        await self.correo_estado()
        try:
            SALIDA.mkdir(exist_ok=True)
            with open(SALIDA / "correos.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"fecha": ahora_chile().isoformat(), "asunto": asunto, "mensaje": mensaje,
                                    "enviado_a": para, "modo": "prueba" if prueba else "real"}, ensure_ascii=False) + "\n")
        except OSError:
            log.warning("no pude guardar el registro del correo")
        return {"ok": True, "mensaje": "Correo enviado al correo de %s." % NOMBRE, "modo_prueba": prueba}

    # ---------- conexión con Gemini ----------
    def _setup(self, modelo):
        return {"setup": {
            "model": "models/" + modelo,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": CFG.get("voz", "Kore")}}},
            },
            "systemInstruction": {"parts": [{"text": instruccion(ahora_chile())}]},
            "tools": TOOLS,
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }}

    async def conectar_gemini(self):
        clave = Path(CFG["gemini_key_file"]).read_text().strip()
        self.http = aiohttp.ClientSession()
        for modelo in CFG.get("modelos", ["gemini-3.8-live"]):
            try:
                g = await self.http.ws_connect(LIVE_URL + "?key=" + clave, max_msg_size=0, heartbeat=20)
                await g.send_json(self._setup(modelo))
                m = await asyncio.wait_for(g.receive(), timeout=20)
                raw = m.data if isinstance(m.data, (bytes, bytearray)) else str(m.data).encode()
                if m.type in (WSMsgType.TEXT, WSMsgType.BINARY) and b"setupComplete" in raw:
                    log.info("Gemini Live conectado con %s", modelo)
                    self.gws = g
                    return modelo
                log.warning("modelo %s rechazado: %r", modelo, raw[:200])
                await g.close()
            except Exception as e:  # noqa: BLE001
                log.warning("modelo %s falló: %r", modelo, e)
        return None

    async def correr(self):
        modelo = await self.conectar_gemini()
        if not modelo:
            await self.a_cli({"type": "error", "mensaje": "No pude conectar con el servicio de voz. Intenta de nuevo en un momento."})
            return
        await self.a_cli({"type": "listo", "modelo": modelo})
        if self.voz:
            await self.gws.send_json({"realtimeInput": {"text": nombre(
                "(Sistema) PERSONA acaba de abrir la app. Salúdala en una sola frase corta y pregunta en qué le puedes ayudar.")}})
        t1 = asyncio.create_task(self.cli_a_gemini())
        t2 = asyncio.create_task(self.gemini_a_cli())
        hecho, pendiente = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        for t in pendiente:
            t.cancel()
        for t in hecho:
            if t.exception():
                log.error("tarea terminó con error: %r", t.exception())

    async def cerrar(self):
        try:
            if self.gws is not None and not self.gws.closed:
                await self.gws.close()
            if self.http is not None:
                await self.http.close()
        except Exception:  # noqa: BLE001
            pass

    async def cli_a_gemini(self):
        n_chunks, pico = 0, 0
        async for msg in self.cli:
            if msg.type == WSMsgType.BINARY:
                n_chunks += 1
                a = array.array("h")
                a.frombytes(msg.data[: len(msg.data) & ~1])
                if a:
                    pico = max(pico, max(abs(x) for x in a))
                if n_chunks == 1:
                    log.info("audio del micrófono: llegó el primer paquete (%d bytes)", len(msg.data))
                if n_chunks % 20 == 0:
                    log.info("audio del micrófono: %d paquetes, volumen máximo reciente %d/32767", n_chunks, pico)
                    pico = 0
                await self.gws.send_json({"realtimeInput": {"audio": {
                    "data": base64.b64encode(msg.data).decode(), "mimeType": "audio/pcm;rate=16000"}}})
            elif msg.type == WSMsgType.TEXT:
                j = json.loads(msg.data)
                t = j.get("type")
                if t == "text" and j.get("text"):
                    await self.gws.send_json({"realtimeInput": {"text": j["text"]}})
                elif t == "modo":
                    self.voz = j.get("valor") == "voz"
                elif t == "repregunta":
                    await self.gws.send_json({"realtimeInput": {"text": nombre(
                        "(Sistema) PERSONA no respondió en unos segundos. Repite tu última pregunta de forma breve y "
                        "natural, sin disculparte.")}})
            elif msg.type == WSMsgType.ERROR:
                break

    async def gemini_a_cli(self):
        async for msg in self.gws:
            if msg.type not in (WSMsgType.TEXT, WSMsgType.BINARY):
                if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
                continue
            data = json.loads(msg.data)
            sc = data.get("serverContent")
            if sc:
                for p in (sc.get("modelTurn") or {}).get("parts", []):
                    d = p.get("inlineData")
                    if d and self.voz:
                        await self.cli.send_bytes(base64.b64decode(d["data"]))
                if sc.get("interrupted"):
                    await self.a_cli({"type": "interrumpido"})
                it = sc.get("inputTranscription")
                if it and it.get("text"):
                    log.info("PERSONA dijo: %s", it["text"])
                    await self.a_cli({"type": "transcripcion", "rol": "user", "texto": it["text"]})
                ot = sc.get("outputTranscription")
                if ot and ot.get("text"):
                    log.info("AVI dijo: %s", ot["text"])
                    await self.a_cli({"type": "transcripcion", "rol": "avi", "texto": ot["text"]})
                if sc.get("turnComplete"):
                    await self.a_cli({"type": "turno_completo"})
            tc = data.get("toolCall")
            if tc:
                respuestas = []
                for fc in tc.get("functionCalls", []):
                    log.info("herramienta %s %s", fc.get("name"), json.dumps(fc.get("args"), ensure_ascii=False))
                    res = await self.herramienta(fc.get("name"), fc.get("args"))
                    log.info("  -> %s", json.dumps(res, ensure_ascii=False)[:300])
                    respuestas.append({"id": fc.get("id"), "name": fc.get("name"), "response": res})
                await self.gws.send_json({"toolResponse": {"functionResponses": respuestas}})
            if data.get("goAway"):
                await self.a_cli({"type": "aviso", "mensaje": "La sesión de voz está por terminar; vuelve a tocar el micrófono."})
        log.info("conexión con Gemini terminada")


def _sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


ACTIVA = {"sesion": None}


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(request)
    previa = ACTIVA["sesion"]
    if previa is not None:
        await previa.cerrar()
    s = Sesion(ws, voz=request.query.get("modo") == "voz")
    ACTIVA["sesion"] = s
    try:
        await s.correr()
    except Exception:  # noqa: BLE001
        log.exception("sesión")
    finally:
        await s.cerrar()
        if ACTIVA["sesion"] is s:
            ACTIVA["sesion"] = None
        if not ws.closed:
            await ws.close()
    return ws


def _headers():
    return {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow",
            "Permissions-Policy": "microphone=(self)"}


async def estatico(request):
    nombre = request.match_info.get("name") or "index.html"
    if nombre not in PERMITIDOS:
        raise web.HTTPNotFound()
    cuerpo = (STATIC / nombre).read_bytes()
    if nombre == "index.html":
        cuerpo = cuerpo.replace(b"__MODO_PRUEBA__", b"1" if CFG.get("modo_prueba", True) else b"0")
    return web.Response(body=cuerpo, content_type=PERMITIDOS[nombre].split(";")[0],
                        charset="utf-8" if PERMITIDOS[nombre].startswith("text") else None, headers=_headers())


async def salud(request):
    return web.json_response({"ok": True, "prueba": CFG.get("modo_prueba", True)})


def crear_app():
    app = web.Application()
    secreto = "/" + CFG["secret_path"]

    async def redirigir(request):
        raise web.HTTPFound(secreto + "/")

    app.router.add_get(secreto, redirigir)
    for pref in ("", secreto):
        app.router.add_get(pref + "/", estatico)
        app.router.add_get(pref + "/ws", ws_handler)
        app.router.add_get(pref + "/salud", salud)
        app.router.add_get(pref + "/{name}", estatico)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    web.run_app(crear_app(), host="127.0.0.1", port=int(CFG.get("puerto", 8300)), print=None)
