# Sube AVI Sebastian al servidor de Oracle y (re)inicia el servicio.
$key = "$HOME\.ssh\oracle_key"
$srv = "ubuntu@147.224.229.186"
$dir = "C:\Users\isabe\OneDrive\Desktop\openclaw\avi-sebastian"

ssh -i $key $srv "mkdir -p /home/ubuntu/avi-sebastian/static /home/ubuntu/avi-sebastian/salida /home/ubuntu/.config/systemd/user"
foreach ($f in "server.py","arbolado.py","informe.py","reglas.py","correo.py","setup_config.py","make_icons.py") {
  scp -i $key "$dir\$f" "${srv}:/home/ubuntu/avi-sebastian/$f"
}
foreach ($f in Get-ChildItem "$dir\static" -File) {
  scp -i $key $f.FullName "${srv}:/home/ubuntu/avi-sebastian/static/$($f.Name)"
}
scp -i $key "$dir\avi-sebastian.service" "${srv}:/home/ubuntu/.config/systemd/user/avi-sebastian.service"
ssh -i $key $srv "cd /home/ubuntu/avi-sebastian && python3 -m venv venv 2>&1 | tail -n 1; ./venv/bin/pip install -q aiohttp pillow google-auth google-api-python-client openpyxl 2>&1 | tail -n 2; ./venv/bin/python make_icons.py && ./venv/bin/python setup_config.py && systemctl --user daemon-reload && systemctl --user enable avi-sebastian.service 2>&1 | tail -n 1; systemctl --user restart avi-sebastian.service; sleep 3; systemctl --user is-active avi-sebastian.service"
