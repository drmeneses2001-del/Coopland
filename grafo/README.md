# Grafo de conocimiento

Aplicación web local, sin servidor y sin conexión, que convierte una carpeta de
documentos en un grafo de conocimiento navegable. Pensada para un iPad Pro con
Safari, con documentos en español e inglés mezclados.

**Estado: fases 1, 2 y 3 terminadas y validadas.** El grafo y sus métricas ya
existen y se muestran en paneles; el lienzo interactivo llega en la fase 5.

---

## Lo que ya funciona

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Ingesta por tres rutas, parsers modulares, extracción en Web Workers | terminada |
| 2 | Índice persistente e incremental en IndexedDB, diff, panel «Qué cambió», instantáneas | terminada |
| 3 | Grafo de tres capas (conceptos, documentos, mixta), comunidades, intermediación, diversidad temática | terminada |
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
node grafo/pruebas/nodo.js        # 57 pruebas: lógica pura, parsers y grafo
```

Y en el propio iPad, `grafo/pruebas/index.html`, que ejecuta las mismas 57 más
10 que sólo existen en el navegador: arranque de los workers con sus tres
bibliotecas, PDF de principio a fin dentro del worker, salto por hash idéntico,
descompresión de ZIP con jerarquía, almacén IndexedDB, ciclo completo de
indexación incremental (alta, sin cambios, modificación, baja), construcción de
las tres capas del grafo desde el índice y el arranque por debajo de 2 s.

El corredor del navegador usa **su propia base de datos**
(`grafo-conocimiento-pruebas`): ejecutar las pruebas no toca el índice real.

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

> **Resultado en el dispositivo real** (iPad Pro, Safari de iPadOS, agosto de
> 2026): la ruta B **funciona**. El selector devuelve los archivos con su
> `webkitRelativePath`, de modo que la jerarquía de carpetas se conserva entre
> sesiones. Queda resuelta la contradicción de las fuentes en favor de MDN. La
> ruta A (`showDirectoryPicker`) sigue sin existir en Safari, así que el
> re-escaneo exige volver a elegir la carpeta; el diff y el re-parseo, no.

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
    grafo/
      coocurrencia.js   capa de conceptos: ventana deslizante y pesos
      louvain.js        comunidades y modularidad
      metricas.js       intermediación (Brandes), grados, componentes
      documentos.js     dependencias explícitas y afinidad TF-IDF
      mixta.js          pertenencia entre documentos y conceptos
    parsers/            un módulo por formato + registro enrutador
    trabajadores/
      extractor.js      worker clásico: lee, descomprime, analiza, tokeniza
      grafista.js       worker del grafo: arma las tres capas y las guarda
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

## La fase 3: cómo se construye el grafo

### Capa de conceptos

Ventana deslizante de **cuatro tokens** sobre el flujo ya lematizado y sin
palabras vacías. Cada par dentro de la ventana suma peso, y el par que ocurre
**dentro de la misma oración pesa 1.0 frente al 0.4** del que cruza un punto:
una frase es una afirmación, un salto de oración es sólo vecindad.

Las métricas y su papel:

| Métrica | Algoritmo | Para qué |
|---|---|---|
| Grado | suma de pesos incidentes | vecindad inmediata |
| Intermediación *(betweenness)* | Brandes sin pesos | **tamaño** del nodo |
| Comunidades | Louvain ponderado | **color** del nodo |
| Modularidad | Q de la partición final | diversidad temática |

Ambos algoritmos están validados contra un caso con respuesta publicada, el club
de kárate de Zachary: Louvain devuelve **cuatro comunidades con Q = 0.4188** y
Brandes da **231.07** para el nodo 0 y **160.55** para el 33. No son cifras
inventadas para que la prueba pase; son las que aparecen en la literatura.

**Los puntos conectores del discurso** son la razón intermediación/frecuencia:
conceptos que sostienen el puente sin ser los protagonistas. Es la lista que
ningún recuento de frecuencia puede producir, y suele ser lo más interesante del
grafo.

**Intermediación exacta o aproximada.** Hasta 1200 nodos, Brandes completo. Por
encima, muestreo de 400 pivotes con un generador de azar de semilla fija —
reproducible a propósito: si el muestreo variara entre aperturas, el deslizador
temporal mostraría cambios que nadie escribió. El panel dice siempre cuál de las
dos se usó.

### Capa de documentos: dependencia contra afinidad

La distinción es el argumento entero de esta capa, y la diferencia entre un mapa
y una nube de palabras:

- **Dependencia** (línea sólida): alguien escribió el enlace. Wikilinks
  `[[ ]]`, enlaces markdown relativos, rutas citadas en el texto, referencias
  bibliográficas repetidas (DOI y pares autor-año, exigiendo **dos o más**
  coincidencias) y secuencias de versión detectadas por el nombre
  (`v1`/`v2`, `borrador`/`final`, `(1)`, sellos de fecha).
- **Afinidad** (línea punteada): coseno TF-IDF sobre umbral ajustable en vivo.
  Los términos presentes en más de la mitad del corpus se descartan: su idf es
  casi cero y sólo aportan coste.

Cuando un wikilink apunta a dos documentos con el mismo nombre, **se declara
ambiguo y no se dibuja nada**. Los enlaces sin destino se listan en su propio
panel en vez de desaparecer.

### Trazabilidad

Cada arista de conceptos guarda hasta tres **oraciones de origen** con su
documento y su índice de oración. Es el material con el que la fase 5 abrirá el
documento y subrayará la línea exacta que produjo la conexión, en vez de pedirle
al usuario que le crea al panel.

### El color de las comunidades

Rueda **OKLCH** recorrida por el ángulo áureo (137.5°), no una paleta fija: con
doce clústeres una paleta se repite, y dos comunidades consecutivas —que en el
grafo suelen ser vecinas— caerían en tonos contiguos. Todos los tonos comparten
luminosidad percibida, así que ninguno grita más que otro sobre el lienzo
oscuro. Hay respaldo a sRGB calculado por OKLab para navegadores sin `oklch()`.

### Dos decisiones de calidad que salieron de mirar la salida real

**Los verbos de discurso se filtran.** En la primera ejecución sobre un corpus
de prueba, los conceptos más «influyentes» eran *exige* y *depende*. Son el
andamio con el que se escribe cualquier texto académico, aparecen en todas
partes y conectan todo con todo, de modo que encabezan la intermediación y tapan
lo que de verdad une el corpus. `vacias.js` enumera ahora esas formas — formas
reales, no un patrón morfológico, que se llevaría por delante sustantivos
legítimos. Quedan fuera a propósito las que también son sustantivos médicos:
*muestra, resultado, estado, mejora, control*. Al filtrarlas, la modularidad del
corpus de prueba subió de 0.488 a 0.540 y las comunidades pasaron a llamarse
*edema · cardiaca · insuficiencia* en vez de *exige · residente · depende*.

**«Rico en contenido» es relativo al corpus.** El umbral para declarar aislado a
un documento era un número fijo de palabras, y un número fijo declara aislado a
medio archivo de notas breves y a ninguno de un archivo de artículos. Ahora el
listón es la **mediana de términos propios del propio corpus**, y el panel
muestra qué umbral se usó.

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

El panel «Qué cambió» sigue declarando **pendientes de fase** los clústeres
fusionados o partidos y las brechas cerradas: lo primero exige comparar dos
particiones de Louvain entre instantáneas, lo segundo necesita el cálculo de
brechas de la fase 4. Ninguna de las dos se rellena con conjeturas.

Las instantáneas ya guardan el grafo serializado —hasta 500 nodos con su
comunidad e intermediación, y hasta 2500 aristas—, así que el deslizador
temporal de la fase 5 tendrá historia desde el primer día en lugar de empezar
vacío.

El grafo se reconstruye entero en cada indexación, no de forma incremental. Con
los corpus medidos cuesta decenas de milisegundos y la corrección está
garantizada; si un archivo real lo vuelve lento, el punto donde atacarlo es
`grafista.js`, guardando las parejas de co-ocurrencia por documento para poder
sumarlas en vez de re-tokenizar.
