# -*- coding: utf-8 -*-
"""Reglas de la 'Solicitud de Móvil Municipal': qué se pregunta, qué es fijo y qué va en blanco."""
import re
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Santiago")

UNIDAD = "DIRECCIÓN DE SERVICIOS A LA COMUNIDAD"
CARGO_BASE = "DIRECTOR DE SERVICIOS A LA COMUNIDAD"
LUGAR = "BODEGA DE DISERCO, CALLE RENGIFO"
COMETIDO = "MANTENCIÓN AREAS VERDES NO CONCESIONADAS ."
CONDUCTOR_DEFECTO = "A DESIGNAR POR TRANSPORTE"

FUNCIONARIOS = {
    "JESUS PARRA PARRAGUEZ": ["jesus parra", "parra parraguez", "jesus", "parra"],
    "ALEJANDRO GALLEGUILLOS RIVERA": ["alejandro galleguillos", "alejandro", "galleguillos rivera"],
    "LUIS ALQUINTA VARAS": ["luis alquinta", "alquinta", "luis"],
}
COORDINADORES = {
    "ALEJANDRO GALLEGUILLOS RIVERA": ["alejandro galleguillos", "alejandro", "galleguillos rivera"],
    "LUIS ALQUINTA VARAS": ["luis alquinta", "alquinta", "luis"],
    "FRANCISCA ACUÑA ROBLEDO": ["francisca acuna", "acuna robledo", "francisca", "acuna"],
}

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
         "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

CAMPOS = ("funcionario", "fecha_servicio", "hora_inicio", "hora_termino", "coordinador", "conductor")
ETIQUETAS = {
    "funcionario": "Funcionario",
    "fecha_servicio": "Fecha del servicio",
    "hora_inicio": "Hora de inicio",
    "hora_termino": "Hora de término",
    "coordinador": "Coordinador",
    "conductor": "Conductor",
}

_BLANCOS = {"EN_BLANCO", "EN BLANCO", "BLANCO", "VACIO", "VACÍO"}


def _sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _palabras(s):
    return set(re.findall(r"[a-z0-9]+", _sin_acentos(s or "").lower()))


def _resolver_nombre(texto, catalogo):
    t = (texto or "").strip()
    if t.upper() in _BLANCOS or t == "":
        return ""
    pal = _palabras(t)
    for canon, alias in catalogo.items():
        for a in alias:
            if _palabras(a) <= pal:
                return canon
    return t.upper()


def _resolver_conductor(texto):
    t = (texto or "").strip()
    n = " ".join(sorted(_palabras(t)))
    pal = _palabras(t)
    if t == "" or "designar" in pal or "transporte" in pal:
        return CONDUCTOR_DEFECTO
    if pal & {"ninguno", "ninguna", "nadie"} or t.lower() in ("no", "no hay", "no tiene"):
        return CONDUCTOR_DEFECTO
    if "sin" in pal and (pal & {"chofer", "conductor"}):
        return CONDUCTOR_DEFECTO
    return t.upper()


def fmt_hora(v):
    m = re.match(r"^\s*(\d{1,2})(?:[:.hH](\d{2}))?(?::(\d{2}))?\s*$", str(v))
    if not m:
        raise ValueError("no entendí la hora '%s'; usa el formato HH:MM" % v)
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59:
        raise ValueError("la hora '%s' no es válida" % v)
    return "%d:%02d:00" % (h, mi)


def _hora_a_min(h):
    a, b, _ = h.split(":")
    return int(a) * 60 + int(b)


def parse_fecha(v):
    s = str(v).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    try:
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        pass
    raise ValueError("no entendí la fecha '%s'; usa el formato AAAA-MM-DD" % v)


def fmt_fecha(d):
    return d.strftime("%d-%m-%Y")


def ahora_chile():
    return datetime.now(TZ)


def fmt_hora_dia(dt):
    return "%d:%02d:%02d" % (dt.hour, dt.minute, dt.second)


def cargo_para(funcionario):
    if not funcionario or funcionario.startswith("JESUS PARRA"):
        return CARGO_BASE
    return CARGO_BASE + " (S)"


class Borrador:
    """Un formulario (un día). None = todavía no se preguntó; '' = se dejó en blanco a propósito."""

    def __init__(self):
        self.d = {c: None for c in CAMPOS}

    def copiar(self):
        b = Borrador()
        b.d = dict(self.d)
        return b

    def actualizar(self, **kw):
        errores = {}
        previo = dict(self.d)
        for k, v in kw.items():
            if k not in CAMPOS or v is None:
                continue
            try:
                self.d[k] = self._normalizar(k, v)
            except ValueError as e:
                errores[k] = str(e)
        hoy = ahora_chile().date()
        if self.d["fecha_servicio"] and "fecha_servicio" in kw and "fecha_servicio" not in errores:
            if date.fromisoformat(self.d["fecha_servicio"]) < hoy:
                errores["fecha_servicio"] = "esa fecha ya pasó (hoy es %s)" % fmt_fecha(hoy)
                self.d["fecha_servicio"] = previo["fecha_servicio"]
        hi, ht = self.d["hora_inicio"], self.d["hora_termino"]
        if hi and ht and _hora_a_min(ht) <= _hora_a_min(hi):
            errores["hora_termino"] = "la hora de término debe ser posterior a la de inicio"
            self.d["hora_termino"] = previo["hora_termino"] if previo["hora_termino"] != ht else None
        return errores

    def _normalizar(self, campo, v):
        if campo == "funcionario":
            return _resolver_nombre(v, FUNCIONARIOS)
        if campo == "coordinador":
            return _resolver_nombre(v, COORDINADORES)
        if campo == "conductor":
            return _resolver_conductor(v)
        if campo == "fecha_servicio":
            return parse_fecha(v).isoformat()
        return fmt_hora(v)

    def faltan(self):
        return [c for c in CAMPOS if self.d[c] is None]

    def _mostrar(self, campo, v):
        return fmt_fecha(date.fromisoformat(v)) if campo == "fecha_servicio" else v

    def vista(self):
        filas = []
        for c in CAMPOS:
            v = self.d[c]
            if v is None:
                estado, txt = "falta", ""
            elif v == "":
                estado, txt = "blanco", "(en blanco)"
            else:
                estado, txt = "ok", self._mostrar(c, v)
            filas.append({"campo": c, "etiqueta": ETIQUETAS[c], "valor": txt, "estado": estado})
        f = [ETIQUETAS[c] for c in self.faltan()]
        return {"campos": filas, "faltan": f, "completo": not f}

    def resumen(self):
        return {ETIQUETAS[c]: (self._mostrar(c, self.d[c]) if self.d[c] else ("(en blanco)" if self.d[c] == "" else "(falta)"))
                for c in CAMPOS}

    def a_form(self, ahora=None):
        ahora = ahora or ahora_chile()
        d = self.d
        fun = d["funcionario"] or ""
        return {
            "creado_fecha": ahora.strftime("%d-%m-%Y"),
            "creado_hora": fmt_hora_dia(ahora),
            "unidad": UNIDAD,
            "funcionario": fun,
            "cargo": cargo_para(fun),
            "srv_fecha": self._mostrar("fecha_servicio", d["fecha_servicio"]),
            "hora_inicio": d["hora_inicio"],
            "hora_termino": d["hora_termino"],
            "coordinador": d["coordinador"] or "",
            "conductor": d["conductor"] or CONDUCTOR_DEFECTO,
            "lugar_inicio": LUGAR,
            "lugar_termino": LUGAR,
            "cometido": COMETIDO,
        }

    def nombre_archivo(self):
        f = date.fromisoformat(self.d["fecha_servicio"])
        return "Móvil AV %02d %s %d.xlsx" % (f.day, MESES[f.month - 1], f.year)


if __name__ == "__main__":
    b = Borrador()
    print(b.actualizar(funcionario="Alejandro", fecha_servicio="2099-01-05", hora_inicio="8:00",
                       hora_termino="12", coordinador="sin nada", conductor="no hay"))
    print(b.resumen(), b.faltan())
    print(b.a_form()["cargo"], b.nombre_archivo())
