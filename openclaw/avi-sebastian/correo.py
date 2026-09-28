# -*- coding: utf-8 -*-
"""Envío de correo (SMTP con contraseña de aplicación de Gmail)."""
import smtplib
import ssl
from email.message import EmailMessage


def enviar(smtp, para, asunto, cuerpo, adjuntos):
    """adjuntos: lista de (nombre_archivo, bytes). Esta versión de AVI no adjunta nada, pero se deja
    la opción por si más adelante se necesita."""
    msg = EmailMessage()
    msg["From"] = "%s <%s>" % (smtp.get("name", "AVI"), smtp["from"])
    msg["To"] = para
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    for nombre, datos in adjuntos:
        msg.add_attachment(datos, maintype="application", subtype="octet-stream", filename=nombre)
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp["host"], int(smtp.get("port", 465)), context=ctx, timeout=30) as s:
        s.login(smtp["username"], smtp["password"])
        s.send_message(msg)
