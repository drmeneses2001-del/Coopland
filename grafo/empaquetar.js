#!/usr/bin/env node
'use strict';
/* Empaqueta la aplicación completa (fases 1-7) en un solo archivo HTML
 * autocontenido: sin service worker, sin manifest separado, sin peticiones
 * de red salvo la capa de IA opcional que el usuario activa a mano.
 *
 * Los tres workers (extractor, grafista, simulador) no pueden seguir
 * cargándose por ruta relativa ni por importScripts: dentro de un Blob URL
 * esas rutas no resuelven a nada. Se resuelven en el momento de construir
 * este archivo: cada worker se arma como una sola cadena de texto con sus
 * dependencias ya concatenadas delante, y en tiempo de ejecución se convierte
 * en un Worker vía Blob + URL.createObjectURL. Lo mismo para el worker
 * anidado de pdf.js dentro del extractor, y para el módulo ESM del SDK de
 * Anthropic, que se importa dinámicamente desde su propio Blob URL.
 */
const fs = require('fs');
const path = require('path');

const RAIZ = __dirname;

function leer(rel) { return fs.readFileSync(path.join(RAIZ, rel), 'utf8'); }

function quitarImportScripts(codigo) {
  const m = codigo.match(/importScripts\s*\([\s\S]*?\)\s*;\s*\n/);
  if (!m) throw new Error('No se encontró importScripts() para quitar.');
  return codigo.slice(0, m.index) + codigo.slice(m.index + m[0].length);
}

// Convierte un texto arbitrario en un literal de cadena JS seguro para vivir
// dentro de una etiqueta <script> real: JSON.stringify escapa comillas,
// barras invertidas y saltos de línea; el reemplazo adicional impide que la
// secuencia "</script" cierre la etiqueta contenedora antes de tiempo.
function comoLiteralJS(texto) {
  return JSON.stringify(texto).replace(/<\/script/gi, '<\\/script');
}

function comprobarSinCierre(nombre, texto) {
  if (/<\/script/i.test(texto)) throw new Error('«</script» sin escapar en ' + nombre);
}

// ---------------------------------------------------------------- workers ---

const pdfWorkerSrc = leer('vendor/pdf.worker.min.js');

let extractor = quitarImportScripts(leer('js/trabajadores/extractor.js'));
extractor = extractor.replace(
  "new Worker('../../vendor/pdf.worker.min.js')",
  "new Worker(URL.createObjectURL(new Blob([__FUENTE_PDF_WORKER__], {type:'text/javascript'})))"
);
if (extractor.indexOf('__FUENTE_PDF_WORKER__') === -1) throw new Error('No se pudo parchear el worker anidado de pdf.js');

const fuenteExtractor = [
  'var __FUENTE_PDF_WORKER__ = ' + comoLiteralJS(pdfWorkerSrc) + ';',
  leer('vendor/fflate.umd.js'),
  leer('vendor/pdf.min.js'),
  leer('vendor/mammoth.browser.min.js'),
  leer('js/nucleo/hash.js'),
  leer('js/nucleo/bytes.js'),
  leer('js/nucleo/vacias.js'),
  leer('js/nucleo/terminos.js'),
  leer('js/parsers/texto.js'),
  leer('js/parsers/rtf.js'),
  leer('js/parsers/html.js'),
  leer('js/parsers/datos.js'),
  leer('js/parsers/pdf.js'),
  leer('js/parsers/docx.js'),
  leer('js/parsers/binario.js'),
  leer('js/parsers/registro.js'),
  extractor
].join('\n;\n');

const grafistaSinImport = quitarImportScripts(leer('js/trabajadores/grafista.js'));
const fuenteGrafista = [
  leer('js/nucleo/vacias.js'),
  leer('js/nucleo/terminos.js'),
  leer('js/nucleo/almacen.js'),
  leer('js/grafo/coocurrencia.js'),
  leer('js/grafo/louvain.js'),
  leer('js/grafo/metricas.js'),
  leer('js/grafo/documentos.js'),
  leer('js/grafo/mixta.js'),
  leer('js/grafo/brechas.js'),
  leer('js/grafo/preguntas.js'),
  grafistaSinImport
].join('\n;\n');

const fuenteSimulador = leer('js/trabajadores/simulador.js');
const fuenteAnthropic = leer('vendor/anthropic.browser.min.mjs');

[fuenteExtractor, fuenteGrafista, fuenteSimulador, fuenteAnthropic].forEach(function (t, i) {
  // Ya se verificó que ninguno de estos archivos contiene "</script" en el
  // repositorio (comprobado con grep antes de escribir este script); esto es
  // un cinturón de seguridad si algún vendor cambia en el futuro.
  comprobarSinCierre('worker/módulo #' + i, t);
});

// --------------------------------------------------------- módulos de UI ---

const ORDEN_SCRIPTS = [
  'js/nucleo/hash.js', 'js/nucleo/bytes.js', 'js/nucleo/vacias.js', 'js/nucleo/terminos.js',
  'js/nucleo/almacen.js', 'js/nucleo/diff.js', 'js/nucleo/indice.js', 'js/nucleo/pool.js',
  'js/nucleo/indexador.js',
  'js/ingesta/capacidades.js', 'js/ingesta/ingesta.js',
  'js/grafo/coocurrencia.js', 'js/grafo/louvain.js', 'js/grafo/metricas.js',
  'js/grafo/documentos.js', 'js/grafo/mixta.js', 'js/grafo/brechas.js',
  'js/grafo/preguntas.js', 'js/grafo/ruta.js',
  'js/ia/carga.js', 'js/ia/proveedor.js', 'js/ia/acciones.js',
  'js/exportar/exportar.js',
  'js/ui/formato.js', 'js/ui/colores.js',
  'js/lienzo/camara.js', 'js/lienzo/lienzo.js', 'js/lienzo/gestos.js',
  'js/ui/vistas.js', 'js/ui/vistas-grafo.js', 'js/ui/visor.js', 'js/ui/ia.js', 'js/ui/mapa.js',
  'js/app.js'
];

const cuerpoScript = ORDEN_SCRIPTS.map(function (rel) {
  let codigo = leer(rel);

  if (rel === 'js/app.js') {
    codigo = codigo
      .replace("ruta: 'js/trabajadores/extractor.js'", 'ruta: __rutaTrabajador(__FUENTE_EXTRACTOR__)')
      .replace("ruta: 'js/trabajadores/grafista.js'", 'ruta: __rutaTrabajador(__FUENTE_GRAFISTA__)');
    if (codigo.indexOf('__rutaTrabajador') === -1) throw new Error('No se pudo parchear app.js');
  }
  if (rel === 'js/ui/mapa.js') {
    codigo = codigo.replace("new Worker('js/trabajadores/simulador.js')", 'new Worker(__rutaTrabajador(__FUENTE_SIMULADOR__))');
    if (codigo.indexOf('__rutaTrabajador') === -1) throw new Error('No se pudo parchear mapa.js');
  }
  if (rel === 'js/ia/proveedor.js') {
    codigo = codigo.replace(
      "await import('../../vendor/anthropic.browser.min.mjs')",
      'await import(__rutaTrabajador(__FUENTE_ANTHROPIC__))'
    );
    if (codigo.indexOf('__rutaTrabajador') === -1) throw new Error('No se pudo parchear proveedor.js');
  }
  comprobarSinCierre(rel, codigo);
  return '// ---- ' + rel + ' ----\n' + codigo;
}).join('\n;\n');

const preludio = [
  '// Fuentes de los tres workers y del módulo del SDK, incrustadas como texto.',
  '// __rutaTrabajador convierte cualquiera de ellas en una URL de Blob válida',
  '// para new Worker(...) o import(...); no hay ningún archivo por separado.',
  'function __rutaTrabajador(fuente) { return URL.createObjectURL(new Blob([fuente], {type:"text/javascript"})); }',
  'var __FUENTE_EXTRACTOR__ = ' + comoLiteralJS(fuenteExtractor) + ';',
  'var __FUENTE_GRAFISTA__ = ' + comoLiteralJS(fuenteGrafista) + ';',
  'var __FUENTE_SIMULADOR__ = ' + comoLiteralJS(fuenteSimulador) + ';',
  'var __FUENTE_ANTHROPIC__ = ' + comoLiteralJS(fuenteAnthropic) + ';'
].join('\n');

comprobarSinCierre('preludio', preludio);

// ------------------------------------------------------------------ HTML ---

const css = leer('css/estilo.css');
comprobarSinCierre('css', css);

const conCssYSinManifiesto = leer('index.html')
  .replace('<link rel="stylesheet" href="css/estilo.css">', '<style>\n' + css + '\n</style>')
  .replace('<link rel="manifest" href="manifest.webmanifest">\n', '');

// Se corta el documento justo antes del primer <script src=...> original y
// se descarta todo lo que había desde ahí hasta el final: esa cola de 34
// etiquetas <script src> se sustituye por un único bloque con todo inline.
const inicioScripts = conCssYSinManifiesto.indexOf('<script src="js/nucleo/hash.js">');
if (inicioScripts === -1) throw new Error('No se encontró el primer <script src> esperado.');
const cabeza = conCssYSinManifiesto.slice(0, inicioScripts);

const salida = cabeza + '<script>\n' + preludio + '\n;\n' + cuerpoScript + '\n</script>\n</body>\n</html>\n';

const destino = path.join(RAIZ, 'grafo-de-conocimiento.html');
fs.writeFileSync(destino, salida, 'utf8');

console.log('Escrito:', destino);
console.log('Tamaño:', (salida.length / (1024 * 1024)).toFixed(2), 'MB');
