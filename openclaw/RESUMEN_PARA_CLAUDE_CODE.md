# Resumen para continuar (léelo antes de tocar nada)

Este resumen es para otra sesión de Claude Code que sigue este trabajo. El usuario (Isabel)
trabaja para la Municipalidad de La Serena / Áreas Verdes. Hay dos apps de voz (AVI) y una
planilla de Google Sheets con Apps Script detrás. Todo corre en el mismo servidor Oracle.

## Servidor (para ambas apps)
- Oracle Cloud, IP `147.224.229.186`, usuario `ubuntu`.
- Llave SSH: está copiada dentro de `avi-sebastian/oracle_key` (en `avi-vehiculos/` NO se
  pudo copiar, un bloqueo de seguridad lo impidió — si se necesita ahí, pedírsela al usuario).
- Cada app es un servicio systemd de usuario en el servidor, con su propio `deploy.ps1`.

## Las dos apps

### 1. `avi-vehiculos/` — AVI de Juan José Galleguillos Castillo
Ver `avi-vehiculos/CONTEXTO.md` (detalle completo). Resumen: fecha/hora, clima, correo libre
(solo a su propio correo), y solicitud de vehículos municipales (arma un Excel y lo envía).
**Hoy se confirmó, probándolo en vivo, que funciona perfecto y que nunca usó n8n** — todo es
Python directo. Ojo con el nombre: siempre "Juan José" / "Juan Ho", nunca otras variantes
(el usuario se puso muy molesto una vez por esto).

### 2. `avi-sebastian/` — AVI de Sebastián (Áreas Verdes)
Ver `avi-sebastian/CONTEXTO.md` (detalle completo). Resumen: fecha/hora, clima, correo libre,
solicitudes de arbolado pendientes por sector (`arbolado.py`), y lo más nuevo — un informe de
trabajos ya ejecutados en Excel con fotos reales, minimapa con punto rojo y enlace de Google
Maps (`informe.py`), que replica en Python lo que hace el botón "Crear Informe" de la
planilla de Google Sheets (Apps Script). **Se probó hoy de punta a punta con éxito**: generó
10 trabajos con fotos y minimapas, sin errores, y llegó el correo de prueba.

## Lo que se hizo en esta sesión (de hoy)
1. Se investigó a fondo el Apps Script de la planilla ("Crear Informe") para entender cómo
   arma el Excel con fotos y minimapa, y se replicó esa misma lógica en Python
   (`avi-sebastian/informe.py`), agregando la herramienta de voz correspondiente en
   `server.py` (`informe_trabajos_ejecutados`) y las instrucciones para que AVI la use.
2. Se probó exitosamente end-to-end (generó y envió un informe real por correo).
3. Hubo una larga discusión sobre si esto debía ir en n8n en vez de Python. Se investigó una
   instancia de n8n que corre en el mismo servidor (Docker, puerto 5678): se le había perdido
   el acceso (login), se reseteó y se creó una cuenta nueva (guardada en
   `openclaw/n8n-credenciales.txt` en el PC del usuario, no en el servidor). Al revisarla,
   **no tenía ningún workflow guardado**. Se determinó, probando `avi-vehiculos` en vivo, que
   esa app (la referencia de "algo que funciona bien") nunca dependió de n8n. Conclusión:
   n8n no es parte de la arquitectura de ninguna AVI por ahora; todo se hace directo en
   Python, siguiendo ese mismo patrón. **No reabrir esta discusión sin que el usuario lo pida.**
4. Se armaron los `CONTEXTO.md` de cada carpeta y se copió la llave SSH a `avi-sebastian/`
   para que un repositorio de git con estas carpetas tenga todo lo necesario para seguir
   trabajando (desplegar, probar, etc.) sin depender de esta conversación.

## Qué falta / qué buscar si hace falta más contexto
- El historial completo de esta conversación (incluye momentos de mucha frustración del
  usuario y correcciones de comportamiento importantes) vive en las transcripciones locales
  de Claude Code en este PC, no viaja con el repositorio. Si algo no calza o el usuario
  menciona algo que no está en estos resúmenes, preguntarle directo en vez de asumir.
- Hay un sistema de memoria persistente en este PC (`~/.claude/projects/.../memory/`) con
  reglas de cómo trabajar con este usuario (autonomía máxima, sin recomendaciones no
  pedidas, español de Chile con tuteo, explicaciones simples paso a paso, no improvisar
  estructuras nuevas). Esas reglas están resumidas al final de cada `CONTEXTO.md`, pero si
  esta sesión corre en el mismo PC, conviene leer esa carpeta de memoria directamente.
- Pendiente (no bloqueante, mencionado pero no pedido explícitamente todavía): revisar si el
  usuario quiere restringir el acceso público a n8n (quedó accesible por
  `http://147.224.229.186:5678`, protegido solo por contraseña, sin HTTPS).
- El `.git` del repositorio lo maneja el usuario directamente (Git no está instalado en este
  PC vía consola; el usuario dijo que ya tiene GitHub listo por su cuenta).
