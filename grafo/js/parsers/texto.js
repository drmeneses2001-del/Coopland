(function (raiz, fabrica) {
  var bytesMod = (typeof module === 'object' && module.exports) ? require('../nucleo/bytes.js') : (raiz.GC && raiz.GC.bytes);
  var api = fabrica(bytesMod);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.parsers = raiz.GC.parsers || {}).texto = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (bytesMod) {
  'use strict';

  // Markdown y texto plano. Además del texto, recoge los enlaces explícitos,
  // que son la materia prima de las aristas de dependencia (capa de documentos).

  function extraerEnlaces(texto) {
    var enlaces = [];
    var m, re;

    re = /\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]/g;          // wikilink [[nota]]
    while ((m = re.exec(texto)) !== null) enlaces.push({ tipo: 'wikilink', destino: m[1].trim(), pos: m.index });

    re = /\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;      // [texto](destino)
    while ((m = re.exec(texto)) !== null) {
      var d = m[1].trim();
      if (/^(?:https?|mailto|tel):/i.test(d)) continue;  // externo: no es dependencia local
      enlaces.push({ tipo: 'markdown', destino: decodeURIComponent(d), pos: m.index });
    }

    re = /(?:^|\s)((?:\.{0,2}\/)?[\w\-. ]+\/[\w\-. \/]*[\w\-]+\.(?:md|txt|pdf|docx|rtf|csv|json|html?))\b/gi;
    while ((m = re.exec(texto)) !== null) enlaces.push({ tipo: 'ruta', destino: m[1].trim(), pos: m.index });

    return enlaces;
  }

  function limpiarMarkdown(texto) {
    return texto
      .replace(/```[\s\S]*?```/g, ' ')            // bloques de código
      .replace(/`[^`\n]*`/g, ' ')                 // código en línea
      .replace(/^\s{0,3}(#{1,6})\s+/gm, '')       // almohadillas de título
      .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')      // imágenes
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')    // enlaces -> su texto
      .replace(/\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]/g, '$1')
      .replace(/^\s{0,3}>\s?/gm, '')              // citas
      .replace(/(\*\*|__|\*|_|~~)/g, '')          // énfasis
      .replace(/^\s*[-*+]\s+/gm, '')              // viñetas
      .replace(/^\s*\|.*\|\s*$/gm, function (f) { return f.replace(/\|/g, ' '); })
      .replace(/^\s*[-:|\s]{3,}\s*$/gm, ' ');     // separadores de tabla
  }

  async function analizar(entrada) {
    var d = bytesMod.aTexto(entrada.bytes);
    var crudo = d.texto;
    var esMd = entrada.ext === 'md' || entrada.ext === 'markdown' || entrada.ext === 'mdown';
    var enlaces = esMd ? extraerEnlaces(crudo) : extraerEnlaces(crudo).filter(function (e) { return e.tipo === 'ruta'; });
    return {
      estado: 'ok',
      texto: esMd ? limpiarMarkdown(crudo) : crudo,
      meta: { codificacion: d.codificacion, enlaces: enlaces, formato: esMd ? 'markdown' : 'texto plano' }
    };
  }

  return { nombre: 'texto', extensiones: ['md', 'markdown', 'mdown', 'txt', 'text', 'log'], analizar: analizar, extraerEnlaces: extraerEnlaces, limpiarMarkdown: limpiarMarkdown };
});
