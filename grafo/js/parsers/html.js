(function (raiz, fabrica) {
  var bytesMod = (typeof module === 'object' && module.exports) ? require('../nucleo/bytes.js') : (raiz.GC && raiz.GC.bytes);
  var api = fabrica(bytesMod);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.parsers = raiz.GC.parsers || {}).html = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (bytesMod) {
  'use strict';

  // Texto visible de un HTML. Sin DOMParser: este parser corre dentro de un
  // Web Worker clásico, donde no existe. Recorrido por expresiones regulares
  // acotadas, suficiente para documentos guardados desde el navegador.

  var ENTIDADES = {
    amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', ndash: '–',
    mdash: '—', hellip: '…', laquo: '«', raquo: '»', ldquo: '“', rdquo: '”',
    lsquo: '‘', rsquo: '’', deg: '°', middot: '·', bull: '•', eacute: 'é',
    aacute: 'á', iacute: 'í', oacute: 'ó', uacute: 'ú', ntilde: 'ñ', Ntilde: 'Ñ',
    uuml: 'ü', Aacute: 'Á', Eacute: 'É', Iacute: 'Í', Oacute: 'Ó', Uacute: 'Ú'
  };

  function decodificar(s) {
    return s.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, function (todo, cuerpo) {
      if (cuerpo[0] === '#') {
        var cp = cuerpo[1] === 'x' || cuerpo[1] === 'X'
          ? parseInt(cuerpo.slice(2), 16) : parseInt(cuerpo.slice(1), 10);
        return isFinite(cp) && cp > 0 ? String.fromCodePoint(cp) : todo;
      }
      return Object.prototype.hasOwnProperty.call(ENTIDADES, cuerpo) ? ENTIDADES[cuerpo] : todo;
    });
  }

  var BLOQUE = /<\/?(?:p|div|section|article|h[1-6]|li|tr|br|hr|blockquote|pre|table|ul|ol|header|footer|main|aside|nav|figcaption)\b[^>]*>/gi;

  function aTexto(html) {
    var titulo = '';
    var mt = /<title[^>]*>([\s\S]*?)<\/title>/i.exec(html);
    if (mt) titulo = decodificar(mt[1]).trim();

    var enlaces = [];
    var re = /<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>/gi, m;
    while ((m = re.exec(html)) !== null) {
      var d = m[1].trim();
      if (/^(?:https?|mailto|tel|javascript|#)/i.test(d)) continue;
      enlaces.push({ tipo: 'html', destino: decodeURIComponent(decodificar(d)), pos: m.index });
    }

    var texto = html
      .replace(/<!--[\s\S]*?-->/g, ' ')
      .replace(/<(script|style|noscript|svg|template)\b[^>]*>[\s\S]*?<\/\1>/gi, ' ')
      .replace(/<head\b[^>]*>[\s\S]*?<\/head>/gi, ' ')
      .replace(BLOQUE, '\n')
      .replace(/<[^>]+>/g, ' ');

    texto = decodificar(texto)
      .replace(/[ \t ]+/g, ' ')
      .replace(/\n\s*\n\s*\n+/g, '\n\n')
      .replace(/^[ \t]+|[ \t]+$/gm, '')
      .trim();

    return { titulo: titulo, texto: (titulo ? titulo + '\n\n' : '') + texto, enlaces: enlaces };
  }

  async function analizar(entrada) {
    var d = bytesMod.aTexto(entrada.bytes);
    var r = aTexto(d.texto);
    if (!r.texto.trim()) return { estado: 'sin-texto', texto: '', aviso: 'HTML sin texto visible.' };
    return { estado: 'ok', texto: r.texto, meta: { codificacion: d.codificacion, titulo: r.titulo, enlaces: r.enlaces, formato: 'html' } };
  }

  return { nombre: 'html', extensiones: ['html', 'htm', 'xhtml'], analizar: analizar, aTexto: aTexto, decodificar: decodificar };
});
