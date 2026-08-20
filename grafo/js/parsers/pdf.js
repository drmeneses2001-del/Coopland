(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.parsers = raiz.GC.parsers || {}).pdf = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  // PDF vía pdf.js, capa de texto únicamente. No hay OCR: si el documento es
  // una digitalización, se registra como "escaneado, no indexado" y aparece en
  // el panel de errores. Nunca se rellena con contenido plausible.

  var MIN_CARACTERES_TOTAL = 80;   // por debajo de esto no hay capa de texto útil
  var MIN_CARACTERES_PAGINA = 12;  // promedio por página

  function biblioteca(raizLocal) {
    var r = raizLocal || raiz;
    return r.pdfjsLib || (r.globalThis && r.globalThis.pdfjsLib) || null;
  }

  function juntarElementos(elementos) {
    // Reconstruye líneas usando los saltos que declara pdf.js y la posición Y.
    var partes = [], ultimaY = null;
    for (var i = 0; i < elementos.length; i++) {
      var it = elementos[i];
      if (typeof it.str !== 'string') continue;
      var y = it.transform ? Math.round(it.transform[5]) : null;
      if (ultimaY !== null && y !== null && Math.abs(y - ultimaY) > 2) partes.push('\n');
      partes.push(it.str);
      if (it.hasEOL) partes.push('\n');
      ultimaY = y;
    }
    return partes.join('').replace(/[ \t]{2,}/g, ' ').replace(/\n{3,}/g, '\n\n');
  }

  async function analizar(entrada, opciones) {
    opciones = opciones || {};
    var pdfjs = opciones.pdfjsLib || biblioteca();
    if (!pdfjs) return { estado: 'error', texto: '', error: 'pdf.js no está cargado en este contexto.' };

    var doc;
    try {
      doc = await pdfjs.getDocument({
        data: entrada.bytes,
        isEvalSupported: false,
        useWorkerFetch: false,
        disableFontFace: true,
        useSystemFonts: false,
        stopAtErrors: false,
        verbosity: 0,
        // `standardFontDataUrl` se deja sin definir a propósito: sin esa URL,
        // pdf.js aborta la descarga de fuentes estándar en lugar de intentarla.
        // Es la garantía de que abrir un PDF no dispara ninguna petición.
        standardFontDataUrl: null
      }).promise;
    } catch (e) {
      var msg = String(e && e.message || e);
      if (/password/i.test(msg)) return { estado: 'error', texto: '', error: 'PDF protegido con contraseña.' };
      return { estado: 'error', texto: '', error: 'PDF ilegible: ' + msg };
    }

    var paginas = doc.numPages;
    var trozos = [], porPagina = [], fallos = 0;
    for (var p = 1; p <= paginas; p++) {
      try {
        var pagina = await doc.getPage(p);
        var contenido = await pagina.getTextContent();
        var t = juntarElementos(contenido.items);
        trozos.push(t);
        porPagina.push({ pagina: p, caracteres: t.length });
        if (typeof pagina.cleanup === 'function') pagina.cleanup();
      } catch (e) { fallos++; porPagina.push({ pagina: p, caracteres: 0, error: String(e && e.message || e) }); }
      if (opciones.alProgresar) opciones.alProgresar(p, paginas);
    }

    var metadatos = null;
    try { var md = await doc.getMetadata(); metadatos = md && md.info ? md.info : null; } catch (e) { /* opcional */ }
    if (typeof doc.destroy === 'function') doc.destroy();

    var texto = trozos.join('\n\n').trim();
    var meta = {
      formato: 'pdf', paginas: paginas, paginasConFallo: fallos,
      caracteresPorPagina: porPagina,
      titulo: metadatos && metadatos.Title ? String(metadatos.Title).trim() : '',
      autor: metadatos && metadatos.Author ? String(metadatos.Author).trim() : ''
    };

    if (texto.length < MIN_CARACTERES_TOTAL || (texto.length / Math.max(1, paginas)) < MIN_CARACTERES_PAGINA) {
      return {
        estado: 'sin-texto', texto: '', meta: meta,
        aviso: 'Escaneado, no indexado: el PDF no tiene capa de texto (' + texto.length + ' caracteres en ' + paginas + ' páginas).'
      };
    }
    if (fallos > 0) meta.avisoParcial = fallos + ' de ' + paginas + ' páginas no pudieron leerse.';
    return { estado: 'ok', texto: texto, meta: meta };
  }

  return { nombre: 'pdf', extensiones: ['pdf'], analizar: analizar, juntarElementos: juntarElementos, MIN_CARACTERES_TOTAL: MIN_CARACTERES_TOTAL, MIN_CARACTERES_PAGINA: MIN_CARACTERES_PAGINA };
});
