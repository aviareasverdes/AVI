# Contexto para continuar este proyecto (AVI Sebastian)

## Qué es esto
AVI Sebastian es un asistente de voz/texto (PWA) para Sebastián, de Áreas Verdes de la
Municipalidad de La Serena. Es una app hermana de otra AVI (para Juan José Galleguillos,
en el proyecto `avi-vehiculos`), pero separada: propio servicio, propio puerto, propia URL.

## Servidor
- Oracle Cloud, IP `147.224.229.186`, usuario `ubuntu`.
- Llave SSH: `oracle_key` en esta misma carpeta (usar `ssh -i oracle_key ubuntu@147.224.229.186`).
- AVI Sebastian corre como servicio systemd de usuario: `avi-sebastian.service`, puerto 8300,
  en `/home/ubuntu/avi-sebastian/`.
- Desplegar cambios: `./deploy.ps1` desde esta carpeta (sube los .py, reinstala dependencias,
  reinicia el servicio).
- `config.json` y la llave de la cuenta de servicio de Google (`.google-sa.json`) viven SOLO
  en el servidor, nunca en este repo — `setup_config.py` los genera/conserva al desplegar.

## Qué hace hoy
1. Fecha/hora, clima (Open-Meteo).
2. Correo libre (dictado, redactado por AVI, se envía siempre al propio correo de Sebastian).
3. Solicitudes de arbolado pendientes (sin trabajo realizado), por sector/zona, con lista
   numerada + enlaces de Google Maps mostrados en la pantalla de la app (`arbolado.py`).
4. **Nuevo (recién probado con éxito):** informe de trabajos YA ejecutados/realizados, en
   Excel, con fotos reales incrustadas, minimapa con punto rojo y enlace a Google Maps de
   cada trabajo — igual a lo que hace el botón "Crear Informe" de la planilla de Google
   Sheets (Apps Script, archivo `Informe.gs`), pero replicado en Python (`informe.py`), sin
   pasar por ese botón ni por Apps Script. Se dispara por voz ("necesito los trabajos
   ejecutados en el Casco Histórico") y se envía por correo automáticamente.

## Decisión importante: por qué está en Python y no en n8n
Se evaluó armar el informe como workflow de n8n en vez de en Python. Se descartó porque:
- La otra AVI (`avi-vehiculos`) tiene una función parecida (armar y enviar un Excel) y se
  confirmó que **nunca usó n8n** — está 100% en Python, y funciona perfecto. Es el patrón
  de referencia a seguir: cosas de este tipo van directo en el código, no en n8n.
- Insertar fotos dentro de celdas específicas de un Excel y generar el minimapa no lo hace
  ningún nodo de n8n de todas formas — se necesitaría un Code node con JS igual, sin
  ganar nada y agregando un salto de red extra.
- Hay una preferencia explícita del usuario (Isabel) de NO improvisar estructuras nuevas:
  replicar exactamente una lógica que ya funciona (en este caso, `Informe.gs`) en vez de
  diseñar algo distinto desde cero.

**No reabrir esta discusión sin que el usuario lo pida.**

## Sobre n8n (para no repetir el lío de hoy)
- Sí existe una instancia de n8n corriendo en el mismo servidor Oracle (Docker, puerto 5678,
  solo accesible desde el servidor o por túnel SSH).
- Se perdió el login anterior (no se sabe por qué no quedó guardado en su momento) y hubo
  que resetearlo. Cuenta nueva creada hoy: revisar si el usuario guardó esas credenciales
  (se le indicó guardarlas en `openclaw\n8n-credenciales.txt`, en su PC, no en el servidor).
- **Al revisar, n8n no tenía ningún workflow guardado** (ni antes ni después del reset). No
  se confirmó la causa. El supuesto workflow de "vehículos en n8n" no se encontró — y como
  se explica arriba, `avi-vehiculos` resultó no depender de n8n para nada.
- Conclusión operativa: por ahora n8n no es parte de la arquitectura de ninguna AVI. Si en
  el futuro se quiere usar para algo nuevo, hay que armarlo de cero ahí.

## Cómo probar sin usar el micrófono
`test_ws.py` en este mismo proyecto simula una conversación por texto contra el servidor
corriendo (pensado para ejecutarse EN el servidor, contra `127.0.0.1:8300`).

## Estilo de trabajo pedido por el usuario (Isabel)
- Máxima autonomía: proceder sin pedir permiso salvo en acciones destructivas/irreversibles.
- No dar recomendaciones no pedidas; responder solo lo que se pregunta.
- Español de Chile, tuteo (no "vos" argentino).
- Explicaciones simples, un paso a la vez, sin analogías (usuario de terminal).
- No improvisar estructuras nuevas cuando ya existe una que funciona: replicarla.
