# -*- coding: utf-8 -*-
"""AVI: puente entre la app del celular y Gemini Live, con herramientas para llenar y enviar el formulario."""
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
from datetime import timedelta
from pathlib import Path

import aiohttp
from aiohttp import WSMsgType, web

import correo
import registro
from formulario_xlsx import build_form
from reglas import (DIAS, ETIQUETAS, MESES, Borrador, ahora_chile)

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
        "name": "guardar_datos",
        "description": "Guarda o corrige datos del formulario. Llámala cada vez que José te dé o cambie información.",
        "parameters": {"type": "OBJECT", "properties": {
            "funcionario": {"type": "STRING", "description": "Funcionario solicitante (ej. Jesús Parra). EN_BLANCO si José pide dejarlo en blanco."},
            "fecha_servicio": {"type": "STRING", "description": "Fecha en que se necesita el vehículo, formato AAAA-MM-DD."},
            "hora_inicio": {"type": "STRING", "description": "Hora de inicio, formato HH:MM en 24 horas."},
            "hora_termino": {"type": "STRING", "description": "Hora de término, formato HH:MM en 24 horas."},
            "coordinador": {"type": "STRING", "description": "Coordinador responsable (ej. Alejandro, Luis Alquinta, Francisca Acuña). EN_BLANCO si pide dejarlo en blanco."},
            "conductor": {"type": "STRING", "description": "Nombre del chofer. Si no hay, 'A DESIGNAR POR TRANSPORTE'."},
        }},
    },
    {
        "name": "enviar_solicitud",
        "description": "Genera el formulario en Excel, lo registra y lo envía por correo. Llámala SOLO después de que José confirme claramente el envío.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "nueva_solicitud_igual",
        "description": "Empieza otra solicitud copiando los datos de la última enviada, con otra fecha (y opcionalmente otras horas).",
        "parameters": {"type": "OBJECT", "properties": {
            "fecha_servicio": {"type": "STRING", "description": "Nueva fecha, formato AAAA-MM-DD."},
            "hora_inicio": {"type": "STRING", "description": "Nueva hora de inicio HH:MM (opcional)."},
            "hora_termino": {"type": "STRING", "description": "Nueva hora de término HH:MM (opcional)."},
        }, "required": ["fecha_servicio"]},
    },
    {
        "name": "reiniciar",
        "description": "Descarta el borrador actual y empieza el formulario de cero.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "guardar_borrador_correo",
        "description": "Guarda o actualiza el borrador del correo (asunto y/o mensaje). Llámala cada vez que redactes el correo por primera vez y cada vez que lo corrijas, ANTES de leérselo a José. Así el borrador queda guardado y no depende de que lo recuerdes tú sola.",
        "parameters": {"type": "OBJECT", "properties": {
            "asunto": {"type": "STRING", "description": "Asunto actual del borrador, claro y breve."},
            "mensaje": {"type": "STRING", "description": "Correo completo actual del borrador: saludo, desarrollo y cierre con firma. Usa saltos de línea entre párrafos."},
        }},
    },
    {
        "name": "enviar_correo",
        "description": "Envía el correo ya guardado con guardar_borrador_correo al correo de José. Llámala SOLO después de que José confirme claramente el envío (tras leerle el asunto y el correo redactado). No hace falta repetir el asunto ni el mensaje si ya quedaron guardados en el borrador.",
        "parameters": {"type": "OBJECT", "properties": {
            "asunto": {"type": "STRING", "description": "Solo si cambió respecto al último borrador guardado; si no, déjalo vacío y se usará el del borrador."},
            "mensaje": {"type": "STRING", "description": "Solo si cambió respecto al último borrador guardado; si no, déjalo vacío y se usará el del borrador."},
            "destinatario": {"type": "STRING", "description": "SOLO si José nombró a otra persona o dio otro correo como destinatario, escríbelo aquí tal cual. Si no nombró destinatario, déjalo vacío."},
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
            "ciudad": {"type": "STRING", "description": "Ciudad. Por defecto La Serena."},
        }},
    },
]}]

NOMBRE = CFG.get("usuario_llamado", "Juan José")
NOMBRE_COMPLETO = CFG.get("usuario_completo", "Juan José Galleguillos Castillo")


def nombre(s):
    """Cambia el nombre 'José' de los textos por el nombre real del usuario."""
    s = re.sub(r"(?<!Juan )José Galleguillos", NOMBRE_COMPLETO, s)
    return re.sub(r"(?<!Juan )José", NOMBRE, s)


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
    ciudad = (ciudad or "La Serena").strip() or "La Serena"

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
        "Eres AVI, la asistente personal de voz de José Galleguillos en la Municipalidad de La Serena, Chile. "
        "José es la única persona que te usa; lo llamas 'Juan José' o 'Juan Ho', alternando entre ambos de forma "
        "natural (no uses solo 'Juan' ni 'José'). Estás pensada para ayudarlo en muchas cosas, y con el tiempo "
        "vas a ir aprendiendo más. Al saludar, pregúntale en qué le puedes ayudar.\n"
        "Hablas en español de Chile, con voz femenina cálida, eficiente y directa. Frases cortas y naturales. "
        "Tratas a José por su nombre y con confianza, sin exagerar los modismos. No repitas todo lo que ya dijo; "
        "confirma solo lo necesario.\n\n"
        "HOY es %s %d de %s de %d y son las %s en Chile. Úsalo para entender 'hoy', 'mañana', 'el viernes', etc., "
        "y pasa las fechas a las herramientas en formato AAAA-MM-DD.\n\n"
        "POR AHORA PUEDES SOLO ESTAS CUATRO COSAS, y únicamente cuando José te las pida (nunca las ofrezcas ni las digas "
        "por iniciativa propia; por ejemplo no des la fecha, la hora ni el clima si no te lo preguntan):\n"
        "A) Decir la fecha y la hora, cuando te las pregunte: usa obtener_fecha_hora (no adivines, la hora cambia).\n"
        "B) Decir el clima, cuando te lo pregunte: usa obtener_clima. Si no dice la ciudad, usa La Serena. Responde "
        "corto: cómo está ahora, la máxima y la mínima de hoy, y la lluvia solo si la probabilidad es relevante.\n"
        "C) Ayudarlo a preparar y enviar solicitudes de móvil municipal (vehículos). Cuando José diga que quiere "
        "programar, pedir o solicitar un vehículo o móvil, empieza ese proceso (abajo).\n"
        "D) Enviar un correo libre: cuando José diga que quiere enviar un correo (o mandarse un mensaje, una nota, "
        "etc.), le preguntas de qué trata. El correo SIEMPRE va al correo de José (él mismo); no preguntes a quién. "
        "Tu trabajo es AYUDARLO A REDACTAR el correo para que quede bien: él te cuenta la idea con sus palabras (puede "
        "ser desordenada) y tú redactas el correo completo: un asunto claro y breve, un saludo, el desarrollo bien "
        "escrito, ordenado y con tono profesional pero cercano, y un cierre con 'Saludos cordiales, Juan José "
        "Galleguillos Castillo'. Usa solo la información que él te dio: no inventes datos, fechas, nombres ni cifras. Si "
        "para redactarlo bien falta algo importante, pregúntalo (una sola pregunta, corta).\n"
        "Si el correo va a ser largo, ANTES de empezar a redactarlo di primero una frase corta como 'dame un segundo, "
        "lo estoy redactando' o 'un momento, lo preparo', y recién después sigue con el borrador; así no queda un "
        "silencio largo mientras lo piensas.\n"
        "Apenas tengas un borrador (asunto y mensaje), llama a guardar_borrador_correo ANTES de leérselo a José. "
        "Hazlo de nuevo cada vez que lo corrijas. Así el borrador queda guardado aparte y no dependes de recordar tú "
        "misma todo el texto si la conversación se alarga.\n"
        "Luego léele el asunto y el correo redactado (breve, sin leer el saludo ni la firma) y pregunta '¿Lo envío o "
        "quieres cambiar algo?'. Si pide cambios (más formal, más corto, agregar o quitar algo, otro asunto), "
        "reescribe, guarda el nuevo borrador con guardar_borrador_correo y vuelve a confirmar. "
        "Llama a enviar_correo SOLO cuando confirme claramente; como el asunto y el mensaje ya quedaron guardados en "
        "el borrador, no hace falta que se los repitas a la herramienta. Si en algún "
        "momento pide enviarlo a otra persona o a otro correo, dile que solo puedes enviar correos a Juan José "
        "Galleguillos (a él mismo) y no lo envíes a nadie más; si llamas a enviar_correo con otro destinatario, la "
        "herramienta lo rechazará.\n"
        "Si José te pide cualquier otra cosa que no esté en esta lista, responde en una frase breve que todavía no estás "
        "configurada para eso (por ejemplo: 'Todavía no estoy configurada para eso'). No lo intentes resolver por tu "
        "cuenta, no inventes información y no propongas alternativas por tu cuenta, salvo recordarle que puedes ayudarlo "
        "con solicitudes de vehículo si es relevante.\n\n"
        "SOLICITUD DE MÓVIL MUNICIPAL (un formulario por cada día). Datos que necesitas:\n"
        "1. Funcionario que solicita: es quien firma como director de Servicios a la Comunidad. Jesús Parra es el "
        "director titular; cuando está otra persona a cargo, es director subrogante. NO uses la palabra 'funcionario' al "
        "preguntar; pregunta de forma natural: '¿Don Jesús está de director?'. Si José dice que otra persona está de "
        "director (por ejemplo 'don Alejandro está de director' o 'está Luis'), ese es el funcionario. Si pide dejarlo en "
        "blanco, guárdalo como EN_BLANCO.\n"
        "2. Fecha en que se necesita el vehículo.\n"
        "3. Hora de inicio y hora de término del servicio.\n"
        "4. Coordinador responsable del móvil. Pregunta: '¿El coordinador es don Alejandro?'. Otras opciones: Luis o "
        "Francisca. También puede ir en blanco (EN_BLANCO).\n"
        "5. Conductor. Debes preguntarlo. Si no hay chofer, guarda 'A DESIGNAR POR TRANSPORTE'.\n"
        "PERSONAS QUE YA CONOCES (identifícalas solo por el nombre de pila, sin confirmar el apellido ni volver a "
        "preguntar): Jesús = Jesús Parra Parraguez; Alejandro = Alejandro Galleguillos Rivera; Luis = Luis Alquinta "
        "Varas; Francisca = Francisca Acuña Robledo. Cuando José nombre a alguien de esta lista, guarda el dato de "
        "inmediato y sigue con lo siguiente. Si dice un nombre que no está en la lista, guárdalo tal como lo dijo. "
        "A los hombres trátalos de 'don' al nombrarlos (don Jesús, don Alejandro, don Luis).\n"
        "José puede darte todo de una vez (por ejemplo: 'necesito un vehículo para mañana de 8 a 12, el chofer es fulano'). "
        "Entiende todo, guárdalo y pregunta SOLO lo que falte, de a una cosa.\n\n"
        "HERRAMIENTAS: llama a guardar_datos cada vez que sepas o cambies un dato, sin esperar a tenerlos todos. "
        "Cuando estén todos, lee un resumen corto y pregunta '¿Lo envío?'. Llama a enviar_solicitud SOLO cuando José "
        "confirme claramente (por ejemplo 'envíalo', 'sí', 'dale'). Tras enviar, avisa en una frase que quedó enviado "
        "a su correo. Si pide el mismo servicio para varios días, envía el primero y luego usa nueva_solicitud_igual "
        "para cada día extra (confirma si cambian las horas o el chofer) y envía cada una. Si José se equivoca o quiere "
        "empezar de nuevo, usa reiniciar.\n"
        "Si no entiendes algo, pide que lo repita, brevemente. No inventes datos. Nunca digas que enviaste algo si la "
        "herramienta devolvió un error."
    ) % (dia, ahora.day, mes, ahora.year, ahora.strftime("%H:%M"))
    return nombre(texto)


class Sesion:
    def __init__(self, cli, voz=False):
        self.cli = cli
        self.voz = voz  # True = modo voz (se reenvía el audio de AVI y se saluda); False = modo texto
        self.b = Borrador()
        self.ultimo = None
        self.correo_borrador = {"asunto": None, "mensaje": None}
        self.enviados = {}
        self.http = None
        self.gws = None

    async def a_cli(self, obj):
        if not self.cli.closed:
            await self.cli.send_json(obj)

    async def estado(self):
        v = self.b.vista()
        v["type"] = "estado"
        v["modo_prueba"] = bool(CFG.get("modo_prueba", True))
        await self.a_cli(v)

    async def correo_estado(self):
        await self.a_cli({"type": "correo_estado", "asunto": self.correo_borrador.get("asunto") or "",
                           "mensaje": self.correo_borrador.get("mensaje") or ""})

    # ---------- herramientas ----------
    async def herramienta(self, nombre, args):
        args = args or {}
        try:
            if nombre == "guardar_datos":
                errores = self.b.actualizar(**args)
                await self.estado()
                return {"ok": not errores, "errores": errores,
                        "faltan": [ETIQUETAS[c] for c in self.b.faltan()], "borrador": self.b.resumen()}
            if nombre == "enviar_solicitud":
                return await self.enviar()
            if nombre == "nueva_solicitud_igual":
                if not self.ultimo:
                    return {"ok": False, "error": "todavía no hay una solicitud enviada para copiar"}
                nb = Borrador()
                nb.d = dict(self.ultimo)
                errores = nb.actualizar(**args)
                self.b = nb
                await self.estado()
                return {"ok": not errores, "errores": errores,
                        "faltan": [ETIQUETAS[c] for c in nb.faltan()], "borrador": nb.resumen()}
            if nombre == "reiniciar":
                self.b = Borrador()
                await self.estado()
                return {"ok": True}
            if nombre == "guardar_borrador_correo":
                if args.get("asunto"):
                    self.correo_borrador["asunto"] = args["asunto"]
                if args.get("mensaje"):
                    self.correo_borrador["mensaje"] = args["mensaje"]
                await self.correo_estado()
                return {"ok": True}
            if nombre == "enviar_correo":
                return await self.enviar_correo(args)
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

    async def enviar(self):
        b = self.b
        faltan = b.faltan()
        if faltan:
            return {"ok": False, "error": "faltan datos", "faltan": [ETIQUETAS[c] for c in faltan]}
        clave = json.dumps(b.d, sort_keys=True)
        if time.time() - self.enviados.get(clave, 0) < 120:
            return {"ok": True, "mensaje": "Esa solicitud ya se había enviado hace un momento."}
        try:
            res = await asyncio.to_thread(self._procesar, b.copiar(), ahora_chile())
        except Exception as e:  # noqa: BLE001
            log.exception("envio")
            return {"ok": False, "error": "no se pudo enviar el correo: %s" % e}
        self.enviados[clave] = time.time()
        self.ultimo = dict(b.d)
        self.b = Borrador()
        await self.estado()
        await self.a_cli({"type": "enviado", **res})
        return {"ok": True, "mensaje": "Solicitud enviada al correo de %s y guardada en el registro." % NOMBRE,
                "registro": res["registro"], "modo_prueba": res["prueba"]}

    async def enviar_correo(self, args):
        asunto = (args.get("asunto") or "").strip() or (self.correo_borrador.get("asunto") or "").strip()
        mensaje = (args.get("mensaje") or "").strip() or (self.correo_borrador.get("mensaje") or "").strip()
        dest = (args.get("destinatario") or "").strip()
        prueba = bool(CFG.get("modo_prueba", True))
        para = CFG["destinatario_prueba"] if prueba else CFG["destinatario"]
        if dest:
            d = re.sub(r"[^a-z0-9@. ]", " ", unicodedata.normalize("NFD", dest.lower()).encode("ascii", "ignore").decode())
            es_el = ("@" not in d and re.search(r"\b(juan ?jose|juanjo|yo|mi|mismo|mio|galleguillos castillo)\b", d)) \
                or d.strip() in (CFG["destinatario"].lower(), para.lower())
            if not es_el:
                return {"ok": False, "error": "destinatario no permitido",
                        "instruccion": "Dile a José que solo puedes enviar correos a Juan José Galleguillos. No lo envíes a nadie más."}
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
            with open(SALIDA / "correos.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"fecha": ahora_chile().isoformat(), "asunto": asunto, "mensaje": mensaje,
                                    "enviado_a": para, "modo": "prueba" if prueba else "real"}, ensure_ascii=False) + "\n")
        except OSError:
            log.warning("no pude guardar el registro del correo")
        return {"ok": True, "mensaje": "Correo enviado al correo de %s." % NOMBRE, "modo_prueba": prueba}

    def _procesar(self, b, ahora):
        datos = b.a_form(ahora)
        nombre = b.nombre_archivo()
        SALIDA.mkdir(exist_ok=True)
        if (SALIDA / nombre).exists():
            nombre = nombre[:-5] + " (%s).xlsx" % ahora.strftime("%H%M%S")
        ruta = SALIDA / nombre
        build_form(datos, str(ruta))
        prueba = bool(CFG.get("modo_prueba", True))
        para = CFG["destinatario_prueba"] if prueba else CFG["destinatario"]
        asunto = ("[PRUEBA] " if prueba else "") + "Solicitud de móvil municipal - " + datos["srv_fecha"]
        cuerpo = (
            "Solicitud de móvil municipal para el %s.\n\n"
            "Funcionario: %s\nCargo: %s\nHorario: %s a %s\nCoordinador: %s\nConductor: %s\n\n"
            "Solicitado por: %s\nEl formulario va adjunto en Excel.\nEnviado por AVI."
            % (datos["srv_fecha"], datos["funcionario"] or "(en blanco)", datos["cargo"],
               datos["hora_inicio"], datos["hora_termino"], datos["coordinador"] or "(en blanco)", datos["conductor"],
               NOMBRE_COMPLETO)
        )
        correo.enviar(CFG["smtp"], para, asunto, cuerpo, [(nombre, ruta.read_bytes())])
        fila = {
            "creado_fecha": datos["creado_fecha"], "creado_hora": datos["creado_hora"],
            "funcionario": datos["funcionario"], "cargo": datos["cargo"], "fecha_servicio": datos["srv_fecha"],
            "hora_inicio": datos["hora_inicio"], "hora_termino": datos["hora_termino"],
            "coordinador": datos["coordinador"], "conductor": datos["conductor"],
            "solicitado_por": NOMBRE_COMPLETO,
            "archivo": nombre, "enviado_a": para, "modo": "prueba" if prueba else "real",
        }
        estado_reg = registro.agregar(SALIDA, fila, CFG.get("sheets_url", ""), CFG.get("sheets_secret", ""))
        return {"para": para, "archivo": nombre, "registro": estado_reg, "prueba": prueba}

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
        await self.estado()
        if self.voz:
            await self.gws.send_json({"realtimeInput": {"text": nombre(
                "(Sistema) José acaba de abrir la app. Salúdalo en una sola frase corta y pregunta en qué le puedes ayudar.")}})
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
                elif t == "enviar":
                    r = await self.enviar()
                    aviso = ("(Sistema) José presionó el botón Enviar y la solicitud quedó enviada. Confírmaselo en una frase."
                             if r.get("ok") else
                             "(Sistema) José presionó Enviar pero falló: %s. Explícaselo brevemente." % (r.get("error") or r))
                    await self.gws.send_json({"realtimeInput": {"text": nombre(aviso)}})
                elif t == "nueva":
                    self.b = Borrador()
                    await self.estado()
                elif t == "modo":
                    self.voz = j.get("valor") == "voz"
                elif t == "repregunta":
                    await self.gws.send_json({"realtimeInput": {"text": nombre(
                        "(Sistema) José no respondió en unos segundos. Repite tu última pregunta de forma breve y "
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
                    log.info("JOSÉ dijo: %s", it["text"])
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
    web.run_app(crear_app(), host="127.0.0.1", port=int(CFG.get("puerto", 8200)), print=None)
