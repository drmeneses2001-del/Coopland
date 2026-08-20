#!/usr/bin/env node
/* Corredor de pruebas en Node. Cubre todo lo que no necesita navegador.
   Los parsers de PDF y DOCX dependen de bibliotecas empaquetadas para el
   navegador: se intentan cargar aquí y, si el entorno no las admite, se
   marcan como omitidas — el corredor de `pruebas/index.html` sí las ejecuta
   en el dispositivo real, que es donde importa que funcionen. */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const raiz = path.join(__dirname, '..');
const muestras = path.join(__dirname, 'muestras');

function cargarUmdNavegador(archivoRelativo, nombreGlobal) {
  // Ejecuta un bundle UMD de navegador en un contexto con `self`/`window`.
  const codigo = fs.readFileSync(path.join(raiz, archivoRelativo), 'utf8');
  const contexto = {
    console, setTimeout, clearTimeout, setInterval, clearInterval,
    queueMicrotask, TextDecoder, TextEncoder, URL, URLSearchParams,
    Uint8Array, ArrayBuffer, Promise, Math, JSON, Date, RegExp, Error,
    process, Buffer, crypto: globalThis.crypto,
    navigator: { userAgent: 'node', platform: 'node', language: 'es' },
    location: { href: 'file:///', protocol: 'file:' },
    document: undefined
  };
  contexto.self = contexto;
  contexto.window = contexto;
  contexto.globalThis = contexto;
  vm.createContext(contexto);
  try {
    vm.runInContext(codigo, contexto, { filename: archivoRelativo });
  } catch (e) {
    return { error: e.message };
  }
  return { lib: contexto[nombreGlobal], contexto };
}

let pdfjsLib = null, mammoth = null, motivoPdf = '', motivoDocx = '';
// pdf.js legacy es UMD: en Node se carga con require. Avisa de que no puede
// rellenar DOMMatrix, algo que sólo afecta al dibujado — la capa de texto no.
try {
  const silenciar = console.warn;
  console.warn = () => {};
  pdfjsLib = require(path.join(raiz, 'vendor/pdf.min.js'));
  console.warn = silenciar;
  // En Node el 'fake worker' carga el worker como módulo: hay que darle la ruta real.
  if (pdfjsLib && pdfjsLib.GlobalWorkerOptions) pdfjsLib.GlobalWorkerOptions.workerSrc = path.join(raiz, 'vendor/pdf.worker.min.js');
  if (!pdfjsLib || !pdfjsLib.getDocument) { pdfjsLib = null; motivoPdf = 'el bundle no expuso getDocument'; }
} catch (e) {
  motivoPdf = e.message;
  const r = cargarUmdNavegador('vendor/pdf.min.js', 'pdfjsLib');
  if (r.lib && r.lib.getDocument) { pdfjsLib = r.lib; motivoPdf = ''; }
}
try {
  const r = cargarUmdNavegador('vendor/mammoth.browser.min.js', 'mammoth');
  if (r.error) motivoDocx = r.error;
  else if (!r.lib) motivoDocx = 'el bundle no expuso mammoth';
  else mammoth = r.lib;
} catch (e) { motivoDocx = e.message; }

const entorno = {
  muestra: async (nombre) => new Uint8Array(fs.readFileSync(path.join(muestras, nombre))),
  pdfjsLib, mammoth
};

const disponible = { pdf: !!pdfjsLib, docx: !!mammoth };
const motivos = { pdf: motivoPdf, docx: motivoDocx };

// Comprobación de coherencia del service worker. Va aquí, en el corredor de
// Node, porque necesita leer el sistema de archivos: si un módulo se carga en
// index.html o se abre con `new Worker()` pero no está en la lista del service
// worker, la aplicación se rompe en avión o —peor— sirve una mezcla de dos
// versiones al desplegar. Ese fallo ya ocurrió una vez.
function revisarServiceWorker() {
  const html = fs.readFileSync(path.join(raiz, 'index.html'), 'utf8');
  const sw = fs.readFileSync(path.join(raiz, 'sw.js'), 'utf8');
  const enSw = new Set((sw.match(/'\.\/[^']+'/g) || []).map(x => x.slice(3, -1)));

  const enHtml = (html.match(/src="([^"]+\.js)"/g) || []).map(x => x.slice(5, -1));
  const workers = fs.readdirSync(path.join(raiz, 'js/trabajadores'))
    .filter(f => f.endsWith('.js')).map(f => 'js/trabajadores/' + f);
  const css = (html.match(/href="([^"]+\.css)"/g) || []).map(x => x.slice(6, -1));

  const faltan = [...enHtml, ...workers, ...css].filter(f => !enSw.has(f));
  return { faltan, total: enHtml.length + workers.length + css.length };
}

(async function () {
  const { casos } = require('./casos.js');
  let ok = 0, fallos = 0, omitidos = 0, grupoActual = '';
  const errores = [];

  for (const c of casos) {
    if (c.grupo !== grupoActual) { grupoActual = c.grupo; console.log('\n  ' + grupoActual); }
    if (c.requiere && !disponible[c.requiere]) {
      omitidos++;
      console.log('    ○ ' + c.nombre + '  (omitida en Node: ' + (motivos[c.requiere] || 'sin biblioteca') + ')');
      continue;
    }
    try {
      await c.fn(entorno);
      ok++;
      console.log('    ✓ ' + c.nombre);
    } catch (e) {
      fallos++;
      console.log('    ✗ ' + c.nombre);
      console.log('        ' + e.message);
      errores.push({ grupo: c.grupo, nombre: c.nombre, error: e.message, pila: e.stack });
    }
  }

  // --- coherencia del service worker ---
  console.log('\n  service worker');
  const sw = revisarServiceWorker();
  if (sw.faltan.length) {
    fallos++;
    console.log('    ✗ todos los módulos cargados están en la caché del service worker');
    console.log('        faltan en sw.js: ' + sw.faltan.join(', '));
  } else {
    ok++;
    console.log('    ✓ todos los módulos cargados están en la caché del service worker (' + sw.total + ')');
  }

  console.log('\n  ' + ok + ' correctas · ' + fallos + ' fallidas · ' + omitidos + ' omitidas\n');
  if (omitidos) console.log('  Las omitidas se ejecutan abriendo pruebas/index.html en el iPad.\n');
  if (fallos) { process.exitCode = 1; }
})();
