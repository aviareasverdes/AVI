# Contexto para continuar este proyecto (AVI Juan José)

## Qué es esto
AVI es la asistente de voz/texto (PWA) personal de Juan José Galleguillos Castillo
(municipalidad de La Serena). Es la primera de estas apps; `avi-sebastian` es su hermana,
para otra persona (Sebastián, Áreas Verdes), separada y más simple.

## Servidor
- Oracle Cloud, IP `147.224.229.186`, usuario `ubuntu`.
- Llave SSH: **no está copiada en esta carpeta** (el sistema de seguridad de Claude Code
  bloqueó esa copia como "Credential Leakage" al intentarlo). Si la necesitas aquí, cópiala
  tú mismo desde `$HOME\.ssh\oracle_key` en tu PC, o pídesela a quien tenga acceso.
- Corre como servicio systemd de usuario: `avi-vehiculos.service`, puerto 8200,
  en `/home/ubuntu/avi-vehiculos/`.
- Desplegar cambios: `./deploy.ps1` desde esta carpeta.
- `config.json` vive solo en el servidor (nunca en este repo) — `setup_config.py` lo genera.

## Qué hace hoy
1. Fecha/hora, clima.
2. Correo libre (dictado, redactado por AVI, se envía SIEMPRE solo al propio correo de
   Juan José: `juan.galleguillos@laserena.cl`; si piden otro destinatario, se rechaza).
3. Solicitud de vehículos municipales: junta fecha, hora inicio/fin, chofer, funcionario,
   coordinador por conversación, arma un Excel (`formulario_xlsx.py`, plantilla
   `plantilla_movil.xlsx`) y lo envía por correo. **Confirmado (hoy) que esto es 100% Python,
   no usa n8n para nada** — se probó en vivo con `test_ws.py` y funciona perfecto.
4. Modo voz por defecto al abrir, botón de mute, switch Voz/Texto en el header.

## Cosas sensibles con el nombre (importante, no volver a tocar sin que lo pidan)
El usuario se puso MUY molesto una vez porque cambié el apodo de Juan José a "Juancho" sin
que lo pidiera. La forma correcta y definitiva, dicha explícitamente por el usuario, es usar
siempre **"Juan José"** y **"Juan Ho"** (no "Juancho", no otras variantes). No cambiar esto
por iniciativa propia bajo ninguna circunstancia.

## Sobre n8n
Se investigó si esta app (o su función de vehículos) dependía de n8n. Conclusión: no, nunca
dependió de n8n — todo el envío de correo usa `smtplib` directo (`correo.py`). Ver
`avi-sebastian/CONTEXTO.md` para el detalle completo de esa investigación (incluye el estado
de la instancia de n8n que sí existe en el mismo servidor, sin workflows guardados).

## Cómo probar sin micrófono
`test_ws.py` simula una conversación por texto (pensado para correr EN el servidor, contra
`127.0.0.1:8200`).

## Estilo de trabajo pedido por el usuario (Isabel)
Ver `avi-sebastian/CONTEXTO.md` (mismas reglas: máxima autonomía, sin recomendaciones no
pedidas, español de Chile con tuteo, explicaciones simples paso a paso, no improvisar
estructuras nuevas cuando ya existe una que funciona).
