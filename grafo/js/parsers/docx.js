(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.parsers = raiz.GC.parsers || {}).docx = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  // DOCX vía mammoth (extracción de texto sin formato).

  function biblioteca() { return raiz.mammoth || null; }

  async function analizar(entrada, opciones) {
    opciones = opciones || {};
    var mammoth = opciones.mammoth || biblioteca();
    if (!mammoth) return { estado: 'error', texto: '', error: 'mammoth no está cargado en este contexto.' };

    var buffer = entrada.bytes.byteOffset === 0 && entrada.bytes.byteLength === entrada.bytes.buffer.byteLength
      ? entrada.bytes.buffer : entrada.bytes.slice().buffer;

    var r;
    try { r = await mammoth.extractRawText({ arrayBuffer: buffer }); }
    catch (e) {
      var msg = String(e && e.message || e);
      if (/zip|end of central directory/i.test(msg)) {
        return { estado: 'error', texto: '', error: 'DOCX corrupto o no es un archivo Office válido (¿.doc antiguo renombrado?).' };
      }
      return { estado: 'error', texto: '', error: 'DOCX ilegible: ' + msg };
    }

    var texto = (r && r.value ? r.value : '').replace(/\n{3,}/g, '\n\n').trim();
    var avisos = (r && r.messages ? r.messages : []).map(function (m) { return m.message; }).slice(0, 10);
    if (!texto) return { estado: 'sin-texto', texto: '', aviso: 'DOCX sin texto (¿sólo imágenes?).', meta: { formato: 'docx', avisos: avisos } };
    return { estado: 'ok', texto: texto, meta: { formato: 'docx', avisos: avisos } };
  }

  return { nombre: 'docx', extensiones: ['docx'], analizar: analizar };
});
