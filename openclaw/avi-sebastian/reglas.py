# -*- coding: utf-8 -*-
"""Constantes de fecha/hora en español de Chile (sin nada de solicitudes de vehículo)."""
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Santiago")

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
         "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def ahora_chile():
    return datetime.now(TZ)
