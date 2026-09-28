# -*- coding: utf-8 -*-
"""Consulta de solicitudes de arbolado pendientes (sin trabajo realizado), con filtro
por sector/zona usando los polígonos de la planilla Areas_Verdes. Lectura sola, nunca escribe."""
import re
import unicodedata
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

SHEET_ARBOLADO = "1Q6LY-XFkSukhabMrqKVILINqvvTlVj6ynoYADpuohts"
HOJA_SOLICITUDES = "Solicitudes Arbolados"
SHEET_AREAS_VERDES = "1bPpTtRWeGWvPE2mDKFIhoyuaLGIcDUDvZKl74bt_e5I"
HOJA_AREAS_VERDES = "Areas_Verdes"

_svc = None


def _servicio(sa_file):
    global _svc
    if _svc is None:
        creds = service_account.Credentials.from_service_account_file(str(sa_file), scopes=SCOPES)
        _svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return _svc


def _leer(sa_file, spreadsheet_id, rango):
    r = _servicio(sa_file).spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=rango).execute()
    return r.get("values", [])


def _sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def _norm(s):
    return _sin_acentos(str(s or "")).lower().strip()


# Sinónimos con los que Sebastian nombra cada zona, hacia el nombre real que usan las
# planillas (Areas_Verdes / columna Sector de Solicitudes). "Las Compañías" junta las
# dos mitades del sector (Oriente y Poniente).
ALIAS_ZONAS = {
    "las companias": ["las companias", "comp oriente", "comp poniente", "compañias"],
    "compania baja": ["comp poniente", "caleta san pedro"],
    "san pedro": ["caleta san pedro", "comp poniente"],
    "compania alta": ["comp oriente"],
    "ceres": ["la antena", "la florida"],
    "18 de septiembre": ["la antena", "la florida"],
    "aeropuerto": ["la antena", "la florida"],
    "avenida de aguirre": ["centro", "prtas del mar"],
    "avenida francisco de aguirre": ["centro", "prtas del mar"],
}


def _terminos(zona_norm):
    return ALIAS_ZONAS.get(zona_norm, [zona_norm])


def _calza(zona_norm, valor_norm):
    if not valor_norm:
        return False
    return any(t in valor_norm or valor_norm in t for t in _terminos(zona_norm))


def parse_gps(texto):
    m = re.search(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", str(texto or ""))
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def parse_poligono(texto):
    return [(float(a), float(b)) for a, b in re.findall(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", str(texto or ""))]


def punto_en_poligono(lat, lon, poligono):
    dentro = False
    n = len(poligono)
    j = n - 1
    for i in range(n):
        yi, xi = poligono[i]
        yj, xj = poligono[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def buscar_zona(sa_file, nombre_zona):
    """Busca en Areas_Verdes los Sector/SubSector cuyo nombre calce (sin tildes/mayúsculas).
    Puede devolver más de un polígono (ej. 'Las Compañías' junta Oriente y Poniente)."""
    filas = _leer(sa_file, SHEET_AREAS_VERDES, HOJA_AREAS_VERDES + "!A2:F")
    objetivo = _norm(nombre_zona)
    nombres, poligonos = [], []
    for fila in filas:
        if len(fila) < 6:
            continue
        _id, nom, categoria = fila[0], fila[1], fila[2]
        if categoria not in ("Sector", "SubSector"):
            continue
        if _calza(objetivo, _norm(nom)):
            nombres.append(nom)
            poligonos.append(parse_poligono(fila[5]))
    if not poligonos:
        return None
    return {"nombre": " y ".join(dict.fromkeys(nombres)), "poligonos": poligonos}


def _en_alguno(lat, lon, poligonos):
    return any(punto_en_poligono(lat, lon, p) for p in poligonos)


def maps_link(gps_txt):
    p = parse_gps(gps_txt)
    if not p:
        return None
    return "https://www.google.com/maps/search/?api=1&query=%s,%s" % p


def _resumen(s):
    partes = [s["nombre"] or s["direccion"] or "(sin nombre)"]
    if s["direccion"] and s["direccion"] != s["nombre"]:
        partes.append(s["direccion"])
    if s["tipo_servicio"]:
        partes.append(s["tipo_servicio"])
    if s["telefono"]:
        partes.append("Tel: " + s["telefono"])
    if s["correo"]:
        partes.append(s["correo"])
    return " - ".join(p for p in partes if p)


def texto_detalle(solicitudes):
    """Lista numerada en texto plano, con el link de Maps de cada una (para el correo)."""
    lineas = []
    for i, s in enumerate(solicitudes, 1):
        l = "%d. %s" % (i, _resumen(s))
        if s["maps_link"]:
            l += "\n   " + s["maps_link"]
        lineas.append(l)
    return "\n".join(lineas)


def _escape_html(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def html_detalle(solicitudes):
    """Lista numerada en HTML (<ol> ya numera sola), con el link de Maps de cada una."""
    items = []
    for s in solicitudes:
        link = ('<a href="%s" target="_blank" rel="noopener">Ver en Google Maps</a>' % s["maps_link"]
                if s["maps_link"] else "(sin GPS)")
        items.append("<li>%s<br>%s</li>" % (_escape_html(_resumen(s)), link))
    return "<ol>%s</ol>" % "".join(items)


def solicitudes_pendientes(sa_file, zona=None, limite=30):
    """Solicitudes de Solicitudes Arbolados sin nada en la columna Match (columna B).
    Si se da `zona`, se filtra primero por texto contra la columna Sector de esta misma
    planilla (que es como el personal anota el sector, ej. 'Las Compañias', 'Centro'); si
    no calza ningún valor, se cae al polígono de Areas_Verdes (Sector o SubSector, ej.
    'Casco Historico'), comparando el GPS de la solicitud contra ese polígono."""
    filas = _leer(sa_file, SHEET_ARBOLADO, HOJA_SOLICITUDES + "!A2:U")
    filas = [f + [""] * (21 - len(f)) for f in filas]  # A..U, todas parejas

    zona_norm = _norm(zona) if zona else None
    zona_col_valores = {_norm(f[6]) for f in filas if f[6]}
    usar_columna_sector = bool(zona_norm) and any(_calza(zona_norm, v) for v in zona_col_valores)

    zona_info = None
    zona_mostrar = zona
    if zona_norm and not usar_columna_sector:
        zona_info = buscar_zona(sa_file, zona)
        if not zona_info:
            return {"ok": False, "error": "no encontré la zona '%s' ni en el Sector de las solicitudes ni en Areas_Verdes" % zona}
        zona_mostrar = zona_info["nombre"]

    resultado = []
    for fila in filas:
        _id = fila[0]
        match = fila[1]
        if not _id or str(match).strip():
            continue
        gps_txt = fila[19]  # columna T
        gps = parse_gps(gps_txt)
        if usar_columna_sector:
            if not _calza(zona_norm, _norm(fila[6])):
                continue
        elif zona_info:
            if not gps or not _en_alguno(gps[0], gps[1], zona_info["poligonos"]):
                continue
        resultado.append({
            "id": _id,
            "nombre": fila[3],
            "telefono": fila[4],
            "direccion": fila[5],
            "sector": fila[6],
            "correo": fila[7],
            "tipo_servicio": fila[10],
            "detalle": fila[11],
            "prioridad": fila[12],
            "estado": fila[14],
            "gps": gps_txt or None,
            "maps_link": maps_link(gps_txt),
        })

    mostrar = resultado[:limite]
    return {
        "ok": True,
        "zona": zona_mostrar,
        "total": len(resultado),
        "mostradas": len(mostrar),
        "solicitudes": mostrar,
        "texto_detalle": texto_detalle(mostrar),
        "html_detalle": html_detalle(mostrar),
    }
