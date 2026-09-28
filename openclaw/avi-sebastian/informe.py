# -*- coding: utf-8 -*-
"""Informe de trabajos ejecutados (Excel con fotos reales, minimapa con punto rojo y
enlace a Google Maps), replicando en Python lo que ya hace el botón "Crear Informe" del
Apps Script de la planilla (Informe.gs / generarInformeExcelDesdeFilas_), sin pasar por
ese botón ni por Apps Script. Solo lee la planilla y Drive; nunca escribe en ellos."""
import io
import re
from datetime import date, datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage

import arbolado  # reutiliza buscar_zona / parse_gps / _calza / _norm / maps_link

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]

SHEET_ARBOLADO = arbolado.SHEET_ARBOLADO
HOJA_TRABAJOS = "Trabajos Realizados Arbolado"

# Columnas de ORIGEN en 'Trabajos Realizados Arbolado' (Informe.gs COL_*_I), 0-indexadas.
COL_FECHA = 2    # C
COL_SECTOR = 12  # M
COL_FOTO1 = 15   # P
COL_FOTO2 = 16   # Q
COL_FOTO3 = 17   # R
COL_VERFOTOS = 18  # S
COL_GPS = 21     # V
COL_TEXTO_HASTA = 15  # A..O (15 columnas) se copian tal cual como texto

# Columnas de SALIDA en el Excel que se arma (1-indexadas, para openpyxl): las 15 de
# texto, y después Foto1, Foto2, Foto3, Mini-mapa, Ver fotos, GPS en ese orden.
OUT_FOTO1 = COL_TEXTO_HASTA + 1    # 16
OUT_FOTO2 = COL_TEXTO_HASTA + 2    # 17
OUT_FOTO3 = COL_TEXTO_HASTA + 3    # 18
OUT_MAPA = COL_TEXTO_HASTA + 4     # 19
OUT_VERFOTOS = COL_TEXTO_HASTA + 5  # 20
OUT_GPS = COL_TEXTO_HASTA + 6      # 21

ANCHO_FOTO_PX = 128
ALTO_FOTO_PX = 96
MAX_FILAS_INFORME = 150

MAPS_STATIC_KEY = "AIzaSyBJ2Ks2Kyfsqvp3znejTsSSyS6d7JtT1Is"  # misma clave que usa Ejecutar.gs/Code.gs en la planilla

MESES_ABREV = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
               "jul": 7, "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12}

_svc_sheets = None
_svc_drive = None


def _creds(sa_file):
    return service_account.Credentials.from_service_account_file(str(sa_file), scopes=SCOPES)


def _sheets(sa_file):
    global _svc_sheets
    if _svc_sheets is None:
        _svc_sheets = build("sheets", "v4", credentials=_creds(sa_file), cache_discovery=False)
    return _svc_sheets


def _drive(sa_file):
    global _svc_drive
    if _svc_drive is None:
        _svc_drive = build("drive", "v3", credentials=_creds(sa_file), cache_discovery=False)
    return _svc_drive


def _leer(sa_file, rango, render="FORMATTED_VALUE"):
    r = _sheets(sa_file).spreadsheets().values().get(
        spreadsheetId=SHEET_ARBOLADO, range=rango, valueRenderOption=render).execute()
    return r.get("values", [])


def parsear_fecha_celda(valor, anio_defecto=None):
    """Replica parsearFechaCelda_ de Informe.gs: fechas en texto, formatos mezclados
    ('11-ago', '8-sept', '14/09/2026', '13-ago y 14-ago' -> toma la primera). None si no calza."""
    if not valor:
        return None
    texto = str(valor).strip().lower().split(" y ")[0].strip()
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", texto)
    if m:
        d, mo, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a < 100:
            a += 2000
        try:
            return date(a, mo, d)
        except ValueError:
            return None
    m = re.match(r"^(\d{1,2})\s*(?:de\s*)?[-\s]?\s*([a-zñáéíóú]+)\.?(?:\s*(?:de\s*)?[-\s]?\s*(\d{2,4}))?$", texto)
    if m:
        d = int(m.group(1))
        mes = MESES_ABREV.get(m.group(2)[:4].rstrip(".")) or MESES_ABREV.get(m.group(2)[:3])
        if not mes:
            return None
        anio = int(m.group(3)) if m.group(3) else (anio_defecto or datetime.now().year)
        if anio < 100:
            anio += 2000
        try:
            return date(anio, mes, d)
        except ValueError:
            return None
    return None


def _extraer_id_imagen(formula):
    if not formula:
        return None
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", str(formula))
    return m.group(1) if m else None


def _extraer_hyperlink(formula):
    if not formula:
        return None
    m = re.search(r'HYPERLINK\("([^"]+)"\s*[;,]\s*"([^"]+)"\)', str(formula), re.IGNORECASE)
    if not m:
        return None
    return {"url": m.group(1), "texto": m.group(2)}


def _descargar_foto_reducida(sa_file, file_id):
    """Baja la foto original vía Drive API (autenticado) y la reduce con PIL. A diferencia
    de Apps Script (que usa el thumbnailLink por el límite de 1 megapíxel de insertImage()),
    openpyxl no tiene ese límite, así que basta con bajar y reescalar."""
    return _drive(sa_file).files().get_media(fileId=file_id).execute()


def _descargar_minimapa(gps):
    import urllib.request
    url = ("https://maps.googleapis.com/maps/api/staticmap?center=%s,%s&zoom=16&size=300x300"
           "&markers=color:red%%7C%s,%s&key=%s") % (gps[0], gps[1], gps[0], gps[1], MAPS_STATIC_KEY)
    with urllib.request.urlopen(url, timeout=20) as r:
        if r.status != 200:
            return None
        return r.read()


def _filtrar_filas(sa_file, desde, hasta, zona=None):
    textos = _leer(sa_file, "'%s'!A2:V" % HOJA_TRABAJOS, "FORMATTED_VALUE")
    formulas = _leer(sa_file, "'%s'!P2:S" % HOJA_TRABAJOS, "FORMULA")
    textos = [f + [""] * (22 - len(f)) for f in textos]
    formulas = [f + [""] * (4 - len(f)) for f in formulas]

    zona_norm = arbolado._norm(zona) if zona else None
    zona_info = None
    if zona_norm:
        zona_col_valores = {arbolado._norm(f[COL_SECTOR]) for f in textos if f[COL_SECTOR]}
        if not any(arbolado._calza(zona_norm, v) for v in zona_col_valores):
            zona_info = arbolado.buscar_zona(sa_file, zona)

    filas = []
    for i, f in enumerate(textos):
        if not any(f):
            continue
        fecha = parsear_fecha_celda(f[COL_FECHA])
        if not fecha or fecha < desde or fecha > hasta:
            continue
        if zona_norm:
            if zona_info:
                gps = arbolado.parse_gps(f[COL_GPS])
                if not gps or not arbolado._en_alguno(gps[0], gps[1], zona_info["poligonos"]):
                    continue
            elif not arbolado._calza(zona_norm, arbolado._norm(f[COL_SECTOR])):
                continue
        filas.append({"datos": f, "formulas": formulas[i] if i < len(formulas) else ["", "", "", ""]})
    return filas


def generar_informe(sa_file, desde, hasta, zona=None):
    """desde/hasta: date. Devuelve {"ok", "nombre", "bytes", "filas", "errores"} o {"ok": False, "error"}."""
    filas = _filtrar_filas(sa_file, desde, hasta, zona)
    if not filas:
        return {"ok": False, "error": "no hay trabajos ejecutados entre esas fechas" +
                (" en '%s'" % zona if zona else "")}
    if len(filas) > MAX_FILAS_INFORME:
        return {"ok": False, "error": "ese rango tiene %d trabajos, el máximo por informe es %d; achica el rango de fechas" %
                (len(filas), MAX_FILAS_INFORME)}

    headers_fila = _leer(sa_file, "'%s'!A1:O1" % HOJA_TRABAJOS, "FORMATTED_VALUE")
    headers = (headers_fila[0] if headers_fila else []) + ["Foto 1", "Foto 2", "Foto 3", "Mini-mapa", "Ver fotos", "GPS"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Informe"
    ws.append(headers)
    for c in range(OUT_FOTO1, OUT_GPS + 1):
        ws.column_dimensions[get_column_letter(c)].width = 20
    ws.column_dimensions[get_column_letter(OUT_VERFOTOS)].width = 22
    ws.column_dimensions[get_column_letter(OUT_GPS)].width = 22

    errores = []
    fila_salida = 2
    for f in filas:
        datos = f["datos"][:COL_TEXTO_HASTA]
        ws.append(datos)
        ws.row_dimensions[fila_salida].height = max(ALTO_FOTO_PX, ALTO_FOTO_PX) * 0.75 + 10

        for col_destino, col_formula in ((OUT_FOTO1, 0), (OUT_FOTO2, 1), (OUT_FOTO3, 2)):
            file_id = _extraer_id_imagen(f["formulas"][col_formula])
            if not file_id:
                continue
            try:
                datos_img = _descargar_foto_reducida(sa_file, file_id)
                if not datos_img:
                    errores.append("Fila %d: no se pudo bajar la foto" % fila_salida)
                    continue
                pil = PILImage.open(io.BytesIO(datos_img)).convert("RGB")
                pil.thumbnail((ANCHO_FOTO_PX * 3, ALTO_FOTO_PX * 3))
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                buf.seek(0)
                img = XLImage(buf)
                img.width, img.height = ANCHO_FOTO_PX, ALTO_FOTO_PX
                ws.add_image(img, "%s%d" % (get_column_letter(col_destino), fila_salida))
            except Exception as e:  # noqa: BLE001
                errores.append("Fila %d [foto]: %s" % (fila_salida, e))

        link = _extraer_hyperlink(f["formulas"][3])
        celda_vf = ws.cell(row=fila_salida, column=OUT_VERFOTOS)
        if link:
            celda_vf.value = link["texto"]
            celda_vf.hyperlink = link["url"]

        gps_txt = f["datos"][COL_GPS] if COL_GPS < len(f["datos"]) else ""
        celda_gps = ws.cell(row=fila_salida, column=OUT_GPS)
        if gps_txt:
            celda_gps.value = gps_txt
            enlace = arbolado.maps_link(gps_txt)
            if enlace:
                celda_gps.hyperlink = enlace

        gps = arbolado.parse_gps(gps_txt)
        if gps:
            try:
                datos_mapa = _descargar_minimapa(gps)
                if not datos_mapa:
                    errores.append("Fila %d: no se pudo generar el minimapa" % fila_salida)
                else:
                    img = XLImage(io.BytesIO(datos_mapa))
                    img.width, img.height = ANCHO_FOTO_PX, ALTO_FOTO_PX
                    ws.add_image(img, "%s%d" % (get_column_letter(OUT_MAPA), fila_salida))
            except Exception as e:  # noqa: BLE001
                errores.append("Fila %d [minimapa]: %s" % (fila_salida, e))

        fila_salida += 1

    buf = io.BytesIO()
    wb.save(buf)
    nombre = "Informe Trabajos Arbolado (%s a %s%s).xlsx" % (
        desde.strftime("%d-%m-%Y"), hasta.strftime("%d-%m-%Y"), " - " + zona if zona else "")
    return {"ok": True, "nombre": nombre, "bytes": buf.getvalue(), "filas": len(filas), "errores": errores}
