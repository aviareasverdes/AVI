# -*- coding: utf-8 -*-
"""Genera los íconos de la app: círculo turquesa con el texto 'AVI'."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

destino = Path(__file__).parent / "static"


def fuente(px):
    for ruta in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(ruta, px)
        except OSError:
            pass
    return ImageFont.load_default()


for n in (192, 512):
    img = Image.new("RGB", (n, n), "#0f1720")
    d = ImageDraw.Draw(img)
    m = int(n * 0.10)
    d.ellipse([m, m, n - m, n - m], fill="#2dd4bf")
    f = fuente(int(n * 0.31))
    d.text((n / 2, n / 2), "AVI", font=f, fill="#04211e", anchor="mm")
    img.save(destino / ("icon-%d.png" % n))
    print("icon-%d.png listo" % n)
