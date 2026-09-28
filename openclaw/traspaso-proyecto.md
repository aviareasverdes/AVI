# Áreas Verdes La Serena — resumen completo del proyecto

## Qué es esto

App para el equipo de Áreas Verdes de la Municipalidad de La Serena (Chile). El equipo reporta trabajo de terreno (solicitudes, poda de árboles, mobiliario dañado, etc.) por WhatsApp. Esta app junta esos mensajes de WhatsApp en Google Sheets, los organiza por conversación, calcula la ubicación real de cada foto (leyendo el sello que la cámara quema en la imagen), la cruza contra el catastro municipal de sectores y áreas verdes, y arma un cruce automático entre "Solicitudes" y "Trabajos Realizados".

Tres piezas, todas conectadas:

1. **App móvil Android** (React Native / Expo, TypeScript) — sube los ZIPs exportados de WhatsApp, muestra Chat y "IDs agrupados" por conversación, permite corregir/borrar fotos.
2. **`Código.gs`** — Apps Script pegado en el Google Sheet **"Mensajes en bruto"** (capa cruda: un mensaje por fila).
3. **`ResultadoFinal.gs`** — Apps Script pegado en el Google Sheet **"Resultado Final"** (capa resumida: una fila por conversación, con match automático, sector y área verde más cercana).

Hay además un **cuarto Sheet externo**, el catastro municipal de sectores/áreas verdes, que `ResultadoFinal.gs` lee EN VIVO (no es una copia).

## IDs, secrets y URLs (todo lo necesario para reconectar todo)

| Qué | Valor |
|---|---|
| Spreadsheet "Mensajes en bruto" (ID) | `1vFtSoNv1Mw-3wxrQhUjRkGHaMjDmww1IJGOFjbuXHG0` |
| Web app de Código.gs — secret | `a03565204d5b1ea58a628acec119a94e` |
| Web app de Código.gs — URL `/exec` | `https://script.google.com/macros/s/AKfycbwDckyMIHnDmj08q1DQK8E3reWViOv4kRMaqUDWt7egpKUaqOjpCb0d31IKsdoUD1JrgA/exec` |
| Web app de ResultadoFinal.gs — secret | `b7e2f5a19c3d4e6f8091a2b3c4d5e6f7` |
| Web app de ResultadoFinal.gs — URL `/exec` (también sirve de galería de fotos) | `https://script.google.com/macros/s/AKfycbxSbgK5IEzqEjEXVt2cLu4ubqjpG0ZFfhMvzJZWZXKN4r5UaQRotLhWbIZRp5VAlzOU/exec` |
| Sheet de sectores/áreas verdes municipales (ID) | `1bPpTtRWeGWvPE2mDKFIhoyuaLGIcDUDvZKl74bt_e5I` (pestaña gid=0) |
| Package Android | `com.avi.enviowhatsapp` |
| Carpeta de Drive donde se guardan las fotos originales | `WhatsApp Archivo - Fotos` (subcarpetas: grupo → fecha) |

Las URLs/secrets de los dos primeros ya están hardcodeadas como default en `src/sheets/sheetsSettings.ts` (`DEFAULT_CONFIG` y `DEFAULT_RESULT_CONFIG`) — la app las usa solas, no hace falta configurarlas a mano salvo que cambien.

**Nota sobre el Sheet de áreas verdes:** viene de otro proyecto del usuario (una web de gestión municipal más grande, carpeta `paginafinallll` en el Desktop, con su propio backend). Ese Sheet tiene columnas `ID, Nombre, Categoria (Sector|AreaVerde), Direccion, Descripcion, Poligono, Latitud, Longitud` — el polígono de cada área/sector viene como texto tipo `[[lat,lng],[lat,lng],...]`. Tiene que estar compartido (al menos como lector) con la cuenta de Google dueña del script `ResultadoFinal.gs`, si no, la lectura falla.

## Arquitectura de datos (por qué hay dos Sheets)

- **Mensajes en bruto**: una fila por mensaje de WhatsApp. Necesaria para la vista Chat/IDs agrupados de la app, reasignar el ID de conversación de un mensaje, detectar duplicados, y guardar el ID del archivo de Drive de cada foto (para poder borrarla después).
- **Resultado Final**: una fila por conversación, calculada a partir de la de arriba. Tiene el indicador de Match, Sector, Área Verde Cercana, fotos, ubicación, horas, etc. Se recalcula sola (por pestaña) cuando la app agrega/edita algo, o completa cuando alguien aprieta "Actualizar resultado final" en el menú del Sheet.
- Eliminar la capa cruda rompería el Chat — es necesaria, no es redundancia.

## Cómo viven los datos en "Resultado Final"

Cada conversación vive **siempre en la misma fila** (nunca se borra la hoja entera para recalcular — eso se decidió explícitamente como peligroso, hay que evitarlo). El mapeo `conversación → fila` se guarda invisible vía `PropertiesService` (`rowMap`). Si alguien edita una celda a mano directo en el Sheet, esa celda queda "protegida" (también vía `PropertiesService`, `protectedCells`) y nunca más se sobreescribe automáticamente al recalcular — pero se puede volver a editar a mano cuantas veces se quiera, y el último valor manual siempre gana.

Función de reparación puntual (por si algún día se duplican filas): `limpiarFilasDuplicadas()` en `ResultadoFinal.gs`, se corre a mano desde el editor de Apps Script (elegirla arriba y "Ejecutar", sin desplegar).

## Columnas de "Resultado Final" — pestañas tipo "Trabajo Realizado"

En este orden: **Solicitud** (link a la solicitud que hizo match con este trabajo) · Conversación · Fecha · Remitente · Texto · Mensaje Agregado · Ubicación · **Sector** · **Área Verde Cercana** · Ubicación Agregada · Hora Inicio · Hora Fin · Duración · Estado · Foto 1, Foto 2... · Ver Fotos.

- **Sector**: en qué sector municipal (de los 12 del catastro) cae la ubicación de la conversación.
- **Área Verde Cercana**: "En [nombre]" si la ubicación cae dentro del polígono de un área verde, o "A [X] m al [Norte/Sur/Este/Oeste/etc.] de [nombre]" si no cae dentro de ninguna pero hay una cerca.
- **Solicitud**: el reverso del Match que tienen las pestañas de Solicitud — link "Ir a solicitud". Si varias solicitudes hacen match con el mismo trabajo, por ahora solo queda la última procesada (mostrar todas las reiteraciones queda pendiente, ver abajo).

Pestañas tipo "Solicitud": Match (círculo de color: rojo=sin match, verde=match completo, amarillo=match incompleto, con nota explicando el motivo si es rojo) · link "Ir a trabajo" · Conversación · Fecha · Remitente · Quien Solicita · Texto · Mensaje Agregado · Ubicación · Ubicación Agregada · Estado · Fotos · Ver Fotos.

**"Mensaje Agregado" / "Ubicación Agregada"** = lo que se agrega desde la app o a mano en el Sheet (separado de "Texto"/"Ubicación", que es lo original de WhatsApp).

## El "sello" de las fotos (feature central de esta última fase)

Las fotos suelen venir de una app tipo "GPS Map Camera" que quema visualmente la fecha/hora/coordenadas sobre la imagen (no es metadata EXIF, es texto dibujado en los píxeles). Flujo:

1. **En el teléfono, antes de subir cada foto** (`src/media/readWatermark.ts`), se usa OCR (`@react-native-ml-kit/text-recognition`) para leer ese texto quemado.
2. **Al subir** (`Código.gs`, `handleAppendMessage`/`handleCrearMensaje`), el texto leído se parsea (`extractSelloTimestamp`/`extractSelloUbicacion`) y se guarda en columnas nuevas "Hora Sello"/"Ubicacion Sello" — en vivo, no hace falta ningún paso extra.
3. **Apenas termina de subir un ZIP completo**, la app llama a la acción `procesar_fotos_grupo` (solo para las fotos recién subidas, nunca toca fotos viejas ya corregidas a mano) — que rellena sellos faltantes, actualiza la columna Fecha con la hora del sello, y **reclasifica conversaciones por cercanía GPS real** (si dos fotos del mismo remitente quedan a más de 50m entre sí, se separan en conversaciones distintas aunque hayan llegado juntas).
4. **Corrección manual**: si el OCR leyó mal una foto (letra borrosa, etc.), desde Chat o "IDs agrupados" se puede corregir a mano la fecha/ubicación de esa foto puntual (`EditPhotoDataModal.tsx`), incluso copiando el dato de otra foto cercana en el orden de subida (el número de fila = orden real de subida). Esa corrección queda fija para siempre (acción `actualizar_sello_mensaje`, nunca se vuelve a tocar automáticamente).

## Borrado de fotos (definitivo, no es el borrado "blando" de mensajes)

- Mensajes normales: `marcar_borrado`/`marcar_borrado_conversacion` — NO borran nada, solo dejan una nota en Estado pidiendo revisión manual.
- **Fotos**: desde Chat o "IDs agrupados" hay un botón 🗑 con confirmación obligatoria que sí borra la fila de verdad (de "Mensajes en bruto", pestaña de grupo y hoja maestra) y manda el archivo a la papelera de Drive (acción `borrar_foto_definitivo`, usa el ID de Drive guardado en la columna "Drive File Id" al momento de subir la foto — fotos subidas ANTES de esta columna no se pueden limpiar de Drive automáticamente, solo se borra su fila).

## Gotchas aprendidos (no repetir los mismos errores)

- **Apps Script no se actualiza solo al pegar código.** Después de pegar y guardar, hay que ir a Implementar → Administrar implementaciones → editar ✏️ → Nueva versión → Implementar. Si no, la app/Sheet sigue viendo la versión vieja.
- Al pegar código largo en el editor de Apps Script, usar el botón de copiar del bloque de código (o `Set-Clipboard` desde PowerShell), nunca selección manual — se corta en archivos largos.
- `SpreadsheetApp.getUi()` **falla si se corre una función directo desde el editor** (sin pasar por un menú de Sheets). Usar `Logger.log(...)` en vez de `.alert(...)` para funciones de diagnóstico/reparación que se corren a mano.
- **Cuando se agrega/mueve una columna en `buildLayout` de ResultadoFinal.gs**, las filas viejas quedan con los datos "corridos" hasta que se recalculan — siempre correr "Actualizar resultado final" después de un cambio de columnas.
- La primera vez que corre una versión nueva del script en una pestaña ya existente, si el mapa de filas (`rowMap`) está vacío puede duplicar filas — usar `limpiarFilasDuplicadas()` si pasa.
- Instalar un WebView de Google Sheets logueado (para edición) **no funciona** — Google bloquea login dentro de WebViews embebidos. El endpoint `htmlview` (solo lectura) tampoco sirve para mostrarlo en la app — no es responsivo en celular, se ve amontonado. Por eso la vista "IDs agrupados" la dibuja la app misma con los datos ya calculados, no un iframe de Sheets.
- El Sheet "Resultado Final" y el Sheet de áreas verdes deben estar compartidos (al menos como lector, o con la cuenta correcta) para que ciertas funciones (fotos, lectura en vivo del catastro) funcionen.
- ADB: el clon de Dual Messenger se instala solo en cada `adb install`; sacarlo con `adb shell pm uninstall --user 95 com.avi.enviowhatsapp` después de instalar.
- Cambiar el ícono de la app (`assets/icon.png` y variantes adaptive) no alcanza solo con reemplazar el PNG — hay que correr `npx expo prebuild --platform android` para que se regeneren los recursos nativos, y después recompilar.
- Al leer un Sheets como CSV/export desde afuera (para diagnosticar), usar un parser CSV de verdad (que respete comillas) — las columnas con polígonos tienen comas adentro y rompen un split ingenuo.
- Herramientas de red en este entorno (PowerShell `Invoke-RestMethod`, `curl.exe`, a veces hasta Node `fetch`) pueden fallar de forma intermitente o transformar POST en GET al seguir redirecciones — si una prueba directa contra un web app de Apps Script falla raro, probar con otra herramienta antes de asumir que el script está roto.

## Estructura del proyecto (carpeta `src/`, estado actual)

```
src/
  screens/
    HomeScreen.tsx            - lista de grupos (estilo WhatsApp), maneja ZIP/share-intent, dispara procesar_fotos_grupo al terminar de subir
    ConversationScreen.tsx    - pantalla principal: tabs Chat / IDs agrupados
  components/
    ChatBubbleRow.tsx         - burbuja de mensaje; para fotos muestra fecha/GPS + botones Corregir/Borrar
    GroupedConversationCard.tsx - una tarjeta por conversación (fotos + textos + agregar mensaje), reemplaza a la vieja "Tabla"
    EditConversationModal.tsx - selector de conversación (mover mensaje / agregar nueva / borrar mensaje)
    EditPhotoDataModal.tsx    - corregir fecha/ubicación de una foto puntual, copiando de otra si hace falta
    PhotoViewerModal.tsx      - visor de fotos a pantalla completa con flechas
    CreateMessageModal.tsx    - agregar texto/foto/ubicación a una conversación
    MapPickerModal.tsx        - selector de ubicación (Leaflet/OpenStreetMap en WebView, sin API key)
    ShareIntentConfirmModal.tsx - confirmar mensaje/foto compartido individualmente desde WhatsApp
  sheets/
    sheetsClient.ts           - todas las llamadas a los dos web apps (doPost)
    sheetsSettings.ts         - URLs y secrets (AsyncStorage + defaults)
  sync/
    syncEngine.ts             - sube el ZIP mensaje por mensaje (dedup por hash), hace OCR de cada foto antes de subirla
    syncStore.ts / messageId.ts
  parser/
    zipReader.ts / chatParser.ts - parsea el ZIP exportado de WhatsApp
  media/
    compressPhoto.ts          - comprime fotos antes de subir (55% calidad, 70% tamaño)
    readWatermark.ts          - OCR del sello de la cámara (@react-native-ml-kit/text-recognition)
  utils/
    conversationColor.ts / photoLocation.ts
  types/index.ts               - todos los tipos compartidos (GroupMessage, ResultRow, etc.)
```

**Ya NO existen** (se sacaron en esta fase): `ResultTableRow.tsx` / `ResultTableHeader.tsx` (la vieja "Tabla" que mostraba Resultado Final directo — se reemplazó por "IDs agrupados", que trabaja sobre los mensajes crudos en vez de sobre Resultado Final).

## Acciones del backend (`doPost`, campo `action`)

**Código.gs** (Mensajes en bruto) — default `append` si no se manda `action` (compatibilidad vieja):
`append`, `listar_grupos`, `leer_grupo`, `listar_conversaciones`, `actualizar_conversacion`, `crear_mensaje` (detecta duplicados, calcula conversación sola por cercanía GPS+hora si no se manda), `marcar_borrado`, `marcar_borrado_conversacion`, `procesar_fotos_grupo` (rellenar sello + reclasificar por GPS, solo para IDs de mensaje puntuales), `actualizar_sello_mensaje` (corrección manual permanente), `borrar_foto_definitivo` (borrado real + Drive).

**ResultadoFinal.gs** (Resultado Final): `leer_pestana` (lo que lee la app), `actualizar_pestana` (recalcula una sola pestaña). Menú manual en el Sheet: "Actualizar resultado final" (recalcula todo), reparación `limpiarFilasDuplicadas`.

## Qué falta / pendiente

- **Reiteraciones de Solicitud**: cuando un mismo Trabajo Realizado responde a varias Solicitudes, hoy la columna "Solicitud" solo muestra la última que hizo match. Falta mostrar todas (la primera como "principal", las demás como "reiteraciones") — pospuesto a propósito, el usuario lo pidió dejar para después.
- Compartir varias fotos sueltas seleccionadas desde WhatsApp a la vez (hoy solo se puede compartir una foto suelta, o el ZIP completo) — mencionado, no implementado.
- Revisar a mano una fila con dato corrupto ("●") en la pestaña "Trabajos en Mobiliario" de Resultado Final (herencia de una versión vieja del script, no se autolimpia porque no está duplicada).
- Fotos subidas ANTES de que existiera la columna "Drive File Id" no se pueden limpiar de Drive automáticamente al borrarlas (sí se borra su fila igual).

## Para seguir desarrollando en otro PC

```
npm install
npx expo prebuild --platform android
cd android
./gradlew assembleRelease
```

El código de los dos Apps Script también vive dentro del proyecto en `sheets-apps-script/Code.gs` y `sheets-apps-script/ResultadoFinal.gs` (copias sincronizadas de lo que está pegado en Google, por si hace falta reinstalarlos).
