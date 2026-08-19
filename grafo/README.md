# Grafo de conocimiento

Aplicación web local, sin servidor y sin conexión, que convierte una carpeta de
documentos en un grafo de conocimiento navegable. Pensada para un iPad Pro con
Safari, con documentos en español e inglés mezclados.

**Estado: fases 1 y 2 terminadas y validadas.** La visualización (fase 3 en
adelante) todavía no existe; el orden de entrega acordado es validar la ingesta
y el índice antes de tocar el grafo.

---

## Lo que ya funciona

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Ingesta por tres rutas, parsers modulares, extracción en Web Workers | terminada |
| 2 | Índice persistente e incremental en IndexedDB, diff, panel «Qué cambió», instantáneas | terminada |
| 3 | Grafo de tres capas (conceptos, documentos, mixta) | pendiente |
| 4 | Brechas estructurales, documentos aislados, conceptos puente ausentes | pendiente |
| 5 | Lienzo, panel lateral, deslizador temporal | pendiente |
| 6 | Capa de IA opcional | pendiente |
| 7 | Exportables | pendiente |

## Cómo se abre

No hay compilación ni dependencias que instalar: los archivos se sirven tal cual.

```sh
# desde la raíz del repositorio
python3 -m http.server 8000 --directory grafo
```

Después, en el iPad: `http://<ip-del-equipo>:8000/index.html`.

Para el uso real conviene servirlo desde **https** o desde un host estático
(GitHub Pages, iCloud + un servidor local, lo que sea): sin contexto seguro no
hay Service Worker (no habría modo avión), no hay `showDirectoryPicker` (ruta A)
y `crypto.subtle` no está disponible, de modo que la huella cae al respaldo en
JavaScript. La app funciona igualmente en las tres situaciones, pero lo dice en
el panel de entorno en vez de fallar en silencio.

## Pruebas

```sh
node grafo/pruebas/nodo.js        # 31 pruebas: lógica pura y todos los parsers
```

Y en el propio iPad, `grafo/pruebas/index.html`, que ejecuta las mismas 31 más
7 que sólo existen en el navegador: arranque de los workers con sus tres
bibliotecas, PDF de principio a fin dentro del worker, salto por hash idéntico,
descompresión de ZIP con jerarquía, almacén IndexedDB, ciclo completo de
indexación incremental (alta, sin cambios, modificación, baja) y el arranque por
debajo de 2 s.

---

## Las tres restricciones que definen el diseño

**1. Ninguna app puede leer «todo el iPad».** iPadOS aísla cada app en su
recinto. El alcance máximo es la carpeta que el usuario otorgue. Todo el diseño
asume ese modelo.

**2. El re-escaneo automático tiene dos niveles.** Por la vía web es
semiautomático: la ruta A guarda una referencia a la carpeta y basta un toque de
reconfirmación cuando el permiso caduca; el diff y el re-parseo sí son
automáticos e incrementales. El re-escaneo verdaderamente silencioso exige una
app nativa con marcadores de ámbito de seguridad, que es otro proyecto. El punto
exacto donde se sustituiría es `js/ingesta/ingesta.js`: el resto del sistema
sólo consume el inventario `{ruta, nombre, tamaño, fecha}` que ese módulo
produce.

**3. `webkitdirectory` en iPadOS es contradictorio en las fuentes.** Por eso la
app no lo da por hecho: sondea la propiedad en tiempo de ejecución y, además,
ofrece una **verificación empírica** — abre el selector una vez y comprueba si
de verdad llegan rutas relativas. El resultado se guarda, así que a partir de la
segunda apertura la app conoce la verdad de *ese* dispositivo. Una verificación
fallida degrada la ruta permanentemente y la app pasa a la siguiente.

---

## Arquitectura

```
grafo/
  index.html            armazón de la interfaz
  sw.js                 service worker: modo avión
  css/estilo.css        lenguaje visual (instrumento, no panel de analítica)
  js/
    nucleo/
      hash.js           huella de contenido (SHA-256 nativo, respaldo FNV-1a)
      bytes.js          bytes -> texto: BOM, UTF-8 estricto, respaldo cp1252
      vacias.js         palabras vacías ES/EN, ampliables desde la interfaz
      terminos.js       oraciones, idioma, lematización ligera, frecuencias
      almacen.js        IndexedDB
      indice.js         índice ligero: proyección sin texto + vocabulario
      diff.js           comparación (ruta, tamaño, fecha) y por hash
      pool.js           reparto entre workers
      indexador.js      orquestación de la indexación incremental
    ingesta/
      capacidades.js    sondeo de rutas y del entorno
      ingesta.js        recorrido de carpeta, <input>, ZIP
    parsers/            un módulo por formato + registro enrutador
    trabajadores/
      extractor.js      worker clásico: lee, descomprime, analiza, tokeniza
    ui/                 formato y vistas
  pruebas/              corredores de Node y de navegador + archivos de muestra
  vendor/               pdf.js 3.11 · mammoth 1.9 · fflate 0.8 (empaquetados)
```

### Decisiones que conviene conocer

**Módulos UMD, no módulos ES.** Cada archivo de `js/` se registra igual en tres
entornos: hilo principal por `<script>`, worker clásico por `importScripts`, y
Node por `require` en las pruebas. Es lo que permite probar la misma unidad en
consola y en el iPad sin empaquetador, y evita los tropiezos de los módulos ES y
los workers de tipo módulo en Safari.

**El worker es clásico, no de tipo módulo.** `importScripts` funciona sin
excepciones en Safari de iPadOS; los workers de módulo tienen historial
irregular.

**pdf.js dentro del worker recibe un worker anidado por `workerPort`.** Su
respaldo interno construye un elemento `<script>`, y dentro de un worker no hay
`document`: falla. Crear nosotros el worker anidado y entregárselo como puerto
es la única vía que funciona. Si un navegador no admite workers anidados, la app
lo declara en la respuesta de `ping` en lugar de fingir que lee PDF.

**`standardFontDataUrl` se deja sin definir a propósito.** Sin esa URL, pdf.js
aborta la descarga de fuentes estándar en lugar de intentarla: abrir un PDF no
dispara ninguna petición de red.

**CSV y JSON son fuentes estructurales, no de contenido.** Se indexan sus
encabezados y sus claves; ningún valor de fila entra al índice. Un CSV de
pacientes aporta sus dimensiones al grafo sin que ningún dato clínico se
convierta en un nodo. Está declarado en `meta.soloEstructura` y hay pruebas que
lo verifican.

**Los archivos ilegibles entran como nodos huérfanos, no se omiten.** Una imagen
o un PDF escaneado se registran con `estado: 'solo-metadatos'` o `'sin-texto'`,
con los términos de su nombre y su ruta como única materia, y aparecen en el
panel «No leídos». Nunca se rellena con contenido plausible.

**Marcadores de iCloud.** Un archivo `.nombre.pdf.icloud` significa que el
original no está descargado en el iPad. Es el fallo más desconcertante de esta
plataforma, así que se detecta y se reporta como tal, no como archivo corrupto.

**Índice ligero aparte del índice completo.** Leer todos los documentos con su
texto al arrancar costaría segundos y megabytes. El índice ligero
(`js/nucleo/indice.js`) es la proyección sin texto de todos los documentos más
el vocabulario con su número de documentos por lema; se lee de una sola clave.
El texto se carga después y sólo del documento que se abra. La reconstrucción
medida es de **9 ms** con 10 documentos, muy por debajo del criterio de 2 s.

**Cuatro almacenes, no tres.** A los tres de la especificación (`documentos`,
`grafo`, `instantaneas`) se añade `config`, que guarda preferencias y la
referencia a la carpeta. Va aparte a propósito: no es dato del grafo y no debe
viajar en los exportables de la fase 7.

**El vocabulario se mantiene exacto, no aproximado.** Cada alta, baja y
modificación ajusta el conteo de documentos por lema leyendo los lemas previos
del documento afectado. Por eso «conceptos que aparecen por primera vez» y
«conceptos que desaparecieron» son afirmaciones exactas, no estimaciones.

### La lematización, que es donde estaba el riesgo

Es deliberadamente conservadora: ante la duda, dos nodos separados antes que
fusionar dos conceptos distintos. Tres reglas merecen mención porque las tres
salieron de pruebas que fallaron:

- **La eñe se protege antes de descomponer.** `NFD` fundía *año* y *ano* en el
  mismo lema.
- **Las terminaciones invariables se respetan.** Sin esa guarda, la regla de
  plural amputaba medio léxico clínico: *dosis, crisis, diagnosis, fibrosis,
  amiloidosis, estenosis, hepatitis, artritis, análisis, virus*.
- **El plural en `-es` decide por la consonante final del candidato.**
  *hospitales → hospital*, pero *pacientes → paciente*. La `-s` queda fuera del
  conjunto de consonantes finales válidas a propósito: los singulares en `-s`
  son raros (*mes, gas*) y los nombres en `-se` son constantes (*fase, base,
  clase, frase*); incluirla arruinaba más palabras de las que arreglaba.

---

## Privacidad

Todo el procesamiento ocurre en el dispositivo. La aplicación no hace ninguna
petición de red a ningún servidor: ni los documentos, ni sus fragmentos, ni sus
metadatos salen del navegador. El service worker sólo cachea el propio armazón
de la app y jamás toca contenido del usuario. La capa de IA de la fase 6 todavía
no existe; cuando exista estará apagada por defecto, requerirá activación
explícita por sesión, enviará únicamente listas de términos y nombres de clúster
—nunca texto crudo— y mostrará el contenido exacto de cada envío antes de
realizarlo.

## Lo que falta y por qué

El panel «Qué cambió» declara dos filas como **pendientes de fase** en lugar de
rellenarlas: los clústeres fusionados o partidos necesitan la capa de conceptos
(fase 3) y las brechas cerradas necesitan el cálculo de brechas (fase 4). Las
instantáneas ya se guardan con un campo `grafo: null` reservado para cuando ese
cálculo exista, de modo que el deslizador temporal de la fase 5 tenga historia
desde el primer día en lugar de empezar vacío.
