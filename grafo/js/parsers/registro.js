(function (raiz, fabrica) {
  var deps;
  if (typeof module === 'object' && module.exports) {
    deps = {
      texto: require('./texto.js'), rtf: require('./rtf.js'), html: require('./html.js'),
      datos: require('./datos.js'), pdf: require('./pdf.js'), docx: require('./docx.js'),
      binario: require('./binario.js')
    };
  } else deps = (raiz.GC && raiz.GC.parsers) || {};
  var api = fabrica(deps);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; raiz.GC.registro = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (parsers) {
  'use strict';

  // Enrutador de extensión a parser. El respaldo nunca es "omitir": es el
  // parser binario, que produce un nodo huérfano con metadatos.

  var LISTA = ['texto', 'rtf', 'html', 'datos', 'pdf', 'docx'];

  function extensionDe(nombre) {
    var m = /\.([A-Za-z0-9]{1,10})$/.exec(String(nombre || ''));
    return m ? m[1].toLowerCase() : '';
  }

  function parserPara(ext) {
    for (var i = 0; i < LISTA.length; i++) {
      var p = parsers[LISTA[i]];
      if (p && p.extensiones.indexOf(ext) !== -1) return p;
    }
    return parsers.binario;
  }

  var LIMITE_BYTES = 64 * 1024 * 1024; // 64 MB: por encima, no se lee en el iPad

  async function analizar(entrada, opciones) {
    var ext = entrada.ext || extensionDe(entrada.nombre || entrada.ruta);
    var e = { nombre: entrada.nombre, ruta: entrada.ruta, ext: ext, bytes: entrada.bytes, tamano: entrada.tamano };
    if (e.bytes && e.bytes.length > LIMITE_BYTES) {
      return { estado: 'error', texto: '', parser: 'ninguno', ext: ext, error: 'Archivo de ' + Math.round(e.bytes.length / 1048576) + ' MB: supera el límite de 64 MB.' };
    }
    var p = parserPara(ext);
    try {
      var r = await p.analizar(e, opciones);
      r.parser = p.nombre; r.ext = ext;
      return r;
    } catch (err) {
      return { estado: 'error', texto: '', parser: p.nombre, ext: ext, error: String(err && err.message || err) };
    }
  }

  function extensionesSoportadas() {
    var s = [];
    LISTA.forEach(function (n) { if (parsers[n]) s = s.concat(parsers[n].extensiones); });
    return s;
  }

  return { analizar: analizar, parserPara: parserPara, extensionDe: extensionDe, extensionesSoportadas: extensionesSoportadas, LIMITE_BYTES: LIMITE_BYTES };
});
