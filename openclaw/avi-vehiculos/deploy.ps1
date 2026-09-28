# Sube AVI al servidor de Oracle y (re)inicia el servicio.
$key = "$HOME\.ssh\oracle_key"
$srv = "ubuntu@147.224.229.186"
$dir = "C:\Users\isabe\OneDrive\Desktop\openclaw\avi-vehiculos"

ssh -i $key $srv "mkdir -p /home/ubuntu/avi-vehiculos/static /home/ubuntu/avi-vehiculos/salida /home/ubuntu/.config/systemd/user"
foreach ($f in "server.py","reglas.py","correo.py","registro.py","formulario_xlsx.py","plantilla_movil.xlsx","setup_config.py","make_icons.py") {
  scp -i $key "$dir\$f" "${srv}:/home/ubuntu/avi-vehiculos/$f"
}
foreach ($f in Get-ChildItem "$dir\static" -File) {
  scp -i $key $f.FullName "${srv}:/home/ubuntu/avi-vehiculos/static/$($f.Name)"
}
scp -i $key "$dir\avi-vehiculos.service" "${srv}:/home/ubuntu/.config/systemd/user/avi-vehiculos.service"
ssh -i $key $srv "cd /home/ubuntu/avi-vehiculos && ./venv/bin/pip install -q aiohttp pillow openpyxl 2>&1 | tail -n 2; ./venv/bin/python make_icons.py && ./venv/bin/python setup_config.py && ./venv/bin/python reglas.py && systemctl --user daemon-reload && systemctl --user enable avi-vehiculos.service 2>&1 | tail -n 1; systemctl --user restart avi-vehiculos.service; sleep 3; systemctl --user is-active avi-vehiculos.service"

