(function (raiz, fabrica) {
  var bytesMod = (typeof module === 'object' && module.exports) ? require('../nucleo/bytes.js') : (raiz.GC && raiz.GC.bytes);
  var api = fabrica(bytesMod);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.parsers = raiz.GC.parsers || {}).rtf = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (bytesMod) {
  'use strict';

  // RTF a texto. Recorre el flujo respetando grupos y descarta por completo
  // los grupos de destino que no son contenido (tablas de fuentes, colores,
  // estilos, imágenes incrustadas, campos de información).

  var DESTINOS_IGNORADOS = new Set([
    'fonttbl', 'colortbl', 'stylesheet', 'info', 'pict', 'object', 'header',
    'footer', 'headerl', 'headerr', 'footerl', 'footerr', 'themedata',
    'colorschememapping', 'latentstyles', 'datastore', 'listtable',
    'listoverridetable', 'rsidtbl', 'generator', 'xmlnstbl', 'mmathPr', 'upr'
  ]);

  function aTexto(rtf) {
    var salida = '';
    var pila = [];
    var estado = { ignorar: false, ucSalto: 1 };
    var i = 0, n = rtf.length;

    while (i < n) {
      var c = rtf[i];

      if (c === '{') { pila.push({ ignorar: estado.ignorar, ucSalto: estado.ucSalto }); i++; continue; }
      if (c === '}') { var p = pila.pop(); if (p) estado = { ignorar: p.ignorar, ucSalto: p.ucSalto }; i++; continue; }

      if (c === '\\') {
        var sig = rtf[i + 1];

        if (sig === '\\' || sig === '{' || sig === '}') {           // carácter escapado
          if (!estado.ignorar) salida += sig;
          i += 2; continue;
        }
        if (sig === "'") {                                           // \'hh byte literal
          var hex = rtf.substr(i + 2, 2);
          if (!estado.ignorar) salida += bytesMod.deCp1252(new Uint8Array([parseInt(hex, 16) || 32]));
          i += 4; continue;
        }
        if (sig === '*') { estado.ignorar = true; i += 2; continue; } // destino opcional

        var m = /^\\([a-zA-Z]+)(-?\d+)? ?/.exec(rtf.slice(i));
        if (!m) { i++; continue; }
        var palabra = m[1], parametro = m[2] ? parseInt(m[2], 10) : null;
        i += m[0].length;

        if (DESTINOS_IGNORADOS.has(palabra)) { estado.ignorar = true; continue; }
        if (estado.ignorar) continue;

        switch (palabra) {
          case 'par': case 'line': case 'sect': case 'page': salida += '\n'; break;
          case 'tab': salida += '\t'; break;
          case 'cell': case 'row': salida += '\n'; break;
          case 'uc': estado.ucSalto = parametro == null ? 1 : parametro; break;
          case 'u':
            if (parametro != null) {
              var cp = parametro < 0 ? parametro + 65536 : parametro;
              salida += String.fromCharCode(cp);
              // El carácter de respaldo que sigue debe descartarse.
              var saltar = estado.ucSalto;
              while (saltar > 0 && i < n) {
                if (rtf[i] === '\\' && rtf[i + 1] === "'") { i += 4; }
                else if (rtf[i] === '{' || rtf[i] === '}') { break; }
                else { i++; }
                saltar--;
              }
            }
            break;
          default: break; // control de formato sin contenido
        }
        continue;
      }

      if (c === '\n' || c === '\r') { i++; continue; }  // saltos del propio archivo RTF
      if (!estado.ignorar) salida += c;
      i++;
    }

    return salida.replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
  }

  async function analizar(entrada) {
    var d = bytesMod.aTexto(entrada.bytes);
    if (!/^\s*\{\\rtf/i.test(d.texto.slice(0, 200))) {
      return { estado: 'error', texto: '', error: 'No es un archivo RTF válido (falta la cabecera \\rtf).' };
    }
    var texto = aTexto(d.texto);
    if (!texto.trim()) return { estado: 'sin-texto', texto: '', aviso: 'RTF sin contenido de texto legible.' };
    return { estado: 'ok', texto: texto, meta: { formato: 'rtf' } };
  }

  return { nombre: 'rtf', extensiones: ['rtf'], analizar: analizar, aTexto: aTexto };
});
