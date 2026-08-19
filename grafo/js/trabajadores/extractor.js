/* Worker de extracción. Todo el cómputo pesado vive aquí: la interfaz nunca
   lee, descomprime, ni tokeniza. Worker clásico a propósito — importScripts es
   lo que funciona sin excepciones en Safari de iPadOS. */
'use strict';

self.GC = self.GC || {};

importScripts(
  '../../vendor/fflate.umd.js',
  '../../vendor/pdf.min.js',
  '../../vendor/mammoth.browser.min.js',
  '../nucleo/hash.js',
  '../nucleo/bytes.js',
  '../nucleo/vacias.js',
  '../nucleo/terminos.js',
  '../parsers/texto.js',
  '../parsers/rtf.js',
  '../parsers/html.js',
  '../parsers/datos.js',
  '../parsers/pdf.js',
  '../parsers/docx.js',
  '../parsers/binario.js',
  '../parsers/registro.js'
);

// pdf.js ya está dentro de un worker. Su respaldo interno ("fake worker")
// construye un <script>, y aquí no hay document: falla. La vía que sí funciona
// es crear el worker anidado nosotros y entregárselo como puerto.
var pdfDisponible = false, pdfMotivo = 'sin inicializar';
try {
  if (self.pdfjsLib && self.pdfjsLib.GlobalWorkerOptions) {
    self.pdfjsLib.GlobalWorkerOptions.workerPort = new Worker('../../vendor/pdf.worker.min.js');
    pdfDisponible = true; pdfMotivo = 'worker anidado';
  } else pdfMotivo = 'pdf.js no se cargó';
} catch (e) {
  // Sin workers anidados no hay lectura de PDF: se dice, no se disimula.
  pdfMotivo = 'este navegador no admite workers anidados: ' + String(e && e.message || e);
}

var GC = self.GC;
var TOPE_TEXTO = 2 * 1024 * 1024;   // 2 MB de texto guardado por documento
var TOPE_TERMINOS = 400;            // términos guardados por documento
var vaciasSet = GC.vacias.conjuntoBase();
var zips = new Map();               // id -> mapa de entradas descomprimidas

function responder(mensaje, transferibles) {
  self.postMessage(mensaje, transferibles || []);
}

function progreso(id, ruta, fase, pct) {
  responder({ t: 'progreso', id: id, ruta: ruta, fase: fase, pct: pct });
}

async function leerBytes(entrada) {
  if (entrada.bytes) return entrada.bytes;
  if (entrada.archivo) return new Uint8Array(await entrada.archivo.arrayBuffer());
  throw new Error('Sin contenido que leer.');
}

function construirDocumento(base, resultado, hash, bytesLargo) {
  var texto = resultado.texto || '';
  var truncado = false;
  if (texto.length > TOPE_TEXTO) { texto = texto.slice(0, TOPE_TEXTO); truncado = true; }

  var terminos = [], idioma = 'indeterminado', nOraciones = 0, nTokens = 0;
  if (texto.trim()) {
    var tk = GC.terminos.tokenizar(texto, { vacias: vaciasSet });
    idioma = tk.idioma;
    nOraciones = tk.oraciones.length;
    nTokens = tk.tokens.length;
    var frec = GC.terminos.frecuencias(tk.tokens);
    terminos = frec.slice(0, TOPE_TERMINOS).map(function (t) {
      return { lema: t.lema, forma: t.forma, n: t.n };
    });
  }

  // Los términos de la ruta entran siempre, también cuando no hay texto:
  // son lo único que sostiene a los nodos huérfanos.
  var deRuta = GC.terminos.terminosDeRuta(base.ruta, vaciasSet);

  return {
    ruta: base.ruta,
    nombre: base.nombre,
    ext: resultado.ext || '',
    tamano: base.tamano != null ? base.tamano : bytesLargo,
    modificado: base.modificado || 0,
    hash: hash,
    estado: resultado.estado,
    parser: resultado.parser,
    texto: texto,
    textoTruncado: truncado,
    terminos: terminos,
    terminosRuta: deRuta,
    idioma: idioma,
    oraciones: nOraciones,
    tokens: nTokens,
    palabras: texto ? (texto.match(/\S+/g) || []).length : 0,
    aviso: resultado.aviso || null,
    error: resultado.error || null,
    meta: resultado.meta || null,
    indexado: Date.now()
  };
}

async function analizarEntrada(id, base, previo) {
  try {
    if (base.noDescargado) {
      responder({
        t: 'resultado', id: id, saltado: false,
        doc: construirDocumento(base, {
          estado: 'error', ext: GC.registro.extensionDe(base.nombre), parser: 'ninguno',
          error: 'No descargado de iCloud: en el iPad sólo existe el marcador. Ábrelo una vez en la app Archivos para descargarlo.'
        }, 'sin-contenido', 0)
      });
      return;
    }

    progreso(id, base.ruta, 'leyendo', 0.1);
    var bytes = await leerBytes(base);

    progreso(id, base.ruta, 'huella', 0.25);
    var hash = await GC.hash.huella(bytes);

    if (previo && previo.hash === hash) {
      // Cambió la fecha o el tamaño declarado, pero el contenido es idéntico.
      responder({ t: 'resultado', id: id, saltado: true, ruta: base.ruta, hash: hash, modificado: base.modificado, tamano: base.tamano });
      return;
    }

    progreso(id, base.ruta, 'analizando', 0.45);
    var resultado = await GC.registro.analizar(
      { nombre: base.nombre, ruta: base.ruta, bytes: bytes, tamano: base.tamano },
      { alProgresar: function (p, total) { progreso(id, base.ruta, 'página ' + p + '/' + total, 0.45 + 0.4 * (p / total)); } }
    );

    progreso(id, base.ruta, 'términos', 0.9);
    var doc = construirDocumento(base, resultado, hash, bytes.length);
    responder({ t: 'resultado', id: id, saltado: false, doc: doc });
  } catch (err) {
    responder({
      t: 'resultado', id: id, saltado: false,
      doc: construirDocumento(base, {
        estado: 'error', ext: GC.registro.extensionDe(base.nombre), parser: 'ninguno',
        error: String(err && err.message || err)
      }, 'error', 0)
    });
  }
}

function cargarZip(id, buffer) {
  try {
    var datos = new Uint8Array(buffer);
    var descomprimido = self.fflate.unzipSync(datos);
    var mapa = new Map();
    var inventario = [];
    Object.keys(descomprimido).forEach(function (nombreEntrada) {
      if (/\/$/.test(nombreEntrada)) return;                       // carpeta
      var partes = nombreEntrada.split('/');
      var nombre = partes[partes.length - 1];
      if (partes.some(function (p, i) { return i < partes.length - 1 && GC.ingestaIgnorar(p, true); })) return;
      if (GC.ingestaIgnorar(nombre, false)) return;
      // Un ZIP hecho desde iOS suele envolver todo en una carpeta raíz.
      mapa.set(nombreEntrada, descomprimido[nombreEntrada]);
      inventario.push({ ruta: nombreEntrada, nombre: nombre, tamano: descomprimido[nombreEntrada].length, modificado: 0, origen: 'C-zip' });
    });
    // Recorta el prefijo común (la carpeta raíz del ZIP) para que las rutas
    // coincidan con las de una ingesta por carpeta del mismo material.
    var prefijo = prefijoComun(inventario.map(function (e) { return e.ruta; }));
    if (prefijo) inventario.forEach(function (e) { e.rutaZip = e.ruta; e.ruta = e.ruta.slice(prefijo.length); });
    else inventario.forEach(function (e) { e.rutaZip = e.ruta; });

    zips.set(id, mapa);
    responder({ t: 'zip-inventario', id: id, entradas: inventario.map(function (e) { return { ruta: e.ruta, rutaZip: e.rutaZip, nombre: e.nombre, tamano: e.tamano, modificado: e.modificado, origen: e.origen }; }) });
  } catch (e) {
    responder({ t: 'zip-error', id: id, error: 'ZIP ilegible: ' + String(e && e.message || e) });
  }
}

function prefijoComun(rutas) {
  if (rutas.length < 2) return '';
  var primeras = rutas.map(function (r) { return r.split('/')[0]; });
  var raizComun = primeras[0];
  if (!raizComun || primeras.some(function (p) { return p !== raizComun; })) return '';
  if (rutas.some(function (r) { return r.indexOf('/') === -1; })) return '';
  return raizComun + '/';
}

// Las reglas de exclusión viven en ingesta.js (hilo principal); aquí se replica
// lo mínimo para el ZIP, cuyo contenido nunca pasa por ese módulo.
GC.ingestaIgnorar = function (nombre, esCarpeta) {
  var n = String(nombre || '').toLowerCase();
  var carpetas = ['.git', '.obsidian', '.trash', 'node_modules', '__macosx', '.svn'];
  if (esCarpeta) return carpetas.indexOf(n) !== -1 || (n[0] === '.' && n !== '.');
  if (['.ds_store', 'thumbs.db', 'desktop.ini'].indexOf(n) !== -1) return true;
  return n[0] === '.' && !/\.(md|txt|json)$/.test(n);
};

self.onmessage = async function (ev) {
  var m = ev.data;
  switch (m.t) {
    case 'vacias':
      vaciasSet = GC.vacias.conjuntoBase();
      (m.lista || []).forEach(function (p) { vaciasSet.add(GC.terminos.clave(p)); });
      responder({ t: 'vacias-ok', id: m.id, n: vaciasSet.size });
      break;
    case 'analizar':
      await analizarEntrada(m.id, m.base, m.previo);
      break;
    case 'zip-cargar':
      cargarZip(m.id, m.buffer);
      break;
    case 'zip-analizar': {
      var mapa = zips.get(m.zipId);
      var bytes = mapa && mapa.get(m.base.rutaZip || m.base.ruta);
      if (!bytes) {
        responder({ t: 'resultado', id: m.id, saltado: false, doc: construirDocumento(m.base, { estado: 'error', parser: 'ninguno', ext: GC.registro.extensionDe(m.base.nombre), error: 'Entrada ausente del ZIP en memoria.' }, 'error', 0) });
        break;
      }
      await analizarEntrada(m.id, Object.assign({}, m.base, { bytes: bytes }), m.previo);
      break;
    }
    case 'zip-liberar':
      zips.delete(m.zipId);
      responder({ t: 'zip-liberado', id: m.id, zipId: m.zipId });
      break;
    case 'ping':
      responder({ t: 'pong', id: m.id, pdf: pdfDisponible, pdfMotivo: pdfMotivo, mammoth: !!self.mammoth, fflate: !!self.fflate });
      break;
    default:
      responder({ t: 'error', id: m.id, error: 'Mensaje desconocido: ' + m.t });
  }
};
