(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else ((raiz.GC = raiz.GC || {}).indice = api);
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Índice ligero: la proyección sin texto de todos los documentos, más el
  // vocabulario del corpus con su número de documentos por lema.
  //
  // Existe por una razón de arranque: leer los documentos completos (con su
  // texto) al abrir la app costaría segundos y megabytes. El índice ligero se
  // lee de una sola clave y basta para el diff, el panel "Qué cambió" y los
  // contadores. El texto se carga después, y sólo del documento que se abra.

  var CLAVE = 'indice-ligero';

  function proyectar(doc) {
    return {
      ruta: doc.ruta, nombre: doc.nombre, ext: doc.ext,
      tamano: doc.tamano, modificado: doc.modificado, hash: doc.hash,
      estado: doc.estado, parser: doc.parser, idioma: doc.idioma,
      palabras: doc.palabras, oraciones: doc.oraciones,
      nTerminos: (doc.terminos || []).length,
      aviso: doc.aviso || null, error: doc.error || null,
      indexado: doc.indexado
    };
  }

  function vacio() {
    return { id: CLAVE, fecha: 0, docs: [], vocabulario: [], origen: null, version: 2 };
  }

  function mapaVocabulario(indice) {
    var m = new Map();
    (indice.vocabulario || []).forEach(function (par) { m.set(par[0], par[1]); });
    return m;
  }

  function lemasDe(doc) {
    var s = new Set();
    (doc.terminos || []).forEach(function (t) { s.add(t.lema); });
    (doc.terminosRuta || []).forEach(function (t) { s.add(t.lema); });
    return s;
  }

  // Aplica altas, bajas y modificaciones al índice ligero, manteniendo el
  // vocabulario exacto por conteo de documentos (no aproximado).
  function aplicar(indice, cambios) {
    var docs = new Map();
    (indice.docs || []).forEach(function (d) { docs.set(d.ruta, d); });
    var vocab = mapaVocabulario(indice);

    function restar(lemas) {
      lemas.forEach(function (l) {
        var n = (vocab.get(l) || 0) - 1;
        if (n <= 0) vocab.delete(l); else vocab.set(l, n);
      });
    }
    function sumar(lemas) {
      lemas.forEach(function (l) { vocab.set(l, (vocab.get(l) || 0) + 1); });
    }

    (cambios.eliminados || []).forEach(function (e) {
      docs.delete(e.ruta);
      if (e.lemas) restar(e.lemas);
    });

    (cambios.actualizados || []).forEach(function (u) {
      if (u.lemasPrevios) restar(u.lemasPrevios);
      docs.set(u.doc.ruta, proyectar(u.doc));
      sumar(lemasDe(u.doc));
    });

    (cambios.tocados || []).forEach(function (t) {
      // Mismo contenido, otra fecha o tamaño declarado: sólo metadatos.
      var d = docs.get(t.ruta);
      if (d) { d.modificado = t.modificado; d.tamano = t.tamano; }
    });

    return {
      id: CLAVE, version: 2, fecha: Date.now(), origen: cambios.origen || indice.origen || null,
      docs: Array.from(docs.values()),
      vocabulario: Array.from(vocab.entries())
    };
  }

  function estadisticas(indice) {
    var porEstado = { ok: 0, 'sin-texto': 0, 'solo-metadatos': 0, error: 0 };
    var porExt = new Map(), palabras = 0, bytes = 0;
    (indice.docs || []).forEach(function (d) {
      porEstado[d.estado] = (porEstado[d.estado] || 0) + 1;
      porExt.set(d.ext || '(sin)', (porExt.get(d.ext || '(sin)') || 0) + 1);
      palabras += d.palabras || 0;
      bytes += d.tamano || 0;
    });
    return {
      documentos: (indice.docs || []).length,
      conceptos: (indice.vocabulario || []).length,
      palabras: palabras, bytes: bytes, porEstado: porEstado,
      porExtension: Array.from(porExt.entries()).map(function (e) { return { ext: e[0], n: e[1] }; })
        .sort(function (a, b) { return b.n - a.n; })
    };
  }

  return { CLAVE: CLAVE, proyectar: proyectar, vacio: vacio, aplicar: aplicar, lemasDe: lemasDe, mapaVocabulario: mapaVocabulario, estadisticas: estadisticas };
});
