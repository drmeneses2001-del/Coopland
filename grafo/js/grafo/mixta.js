(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.grafo = raiz.GC.grafo || {}).mixta = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Capa mixta: documentos y conceptos en el mismo lienzo, unidos por aristas
  // de pertenencia. Es la capa que permite el gesto que da sentido al resto —
  // tocar un concepto e iluminar los documentos que lo contienen, tocar un
  // documento y desplegar su subgrafo de conceptos.

  function construir(capaConceptos, capaDocumentos, docs, opciones) {
    opciones = opciones || {};
    var porConcepto = opciones.terminosPorDocumento != null ? opciones.terminosPorDocumento : 12;

    var indiceConcepto = new Map();
    capaConceptos.nodos.forEach(function (n) { indiceConcepto.set(n.lema, n.id); });

    var indiceDoc = new Map();
    capaDocumentos.nodos.forEach(function (n) { indiceDoc.set(n.ruta, n.id); });

    var pertenencias = [];
    docs.forEach(function (d) {
      var idDoc = indiceDoc.get(d.ruta);
      if (idDoc === undefined) return;
      var terminos = (d.terminos || []).slice(0, porConcepto);
      terminos.forEach(function (t) {
        var idConcepto = indiceConcepto.get(t.lema);
        if (idConcepto === undefined) return;
        pertenencias.push({ documento: idDoc, concepto: idConcepto, peso: t.n });
      });
      // Un documento sin texto sólo tiene los términos de su ruta: sin esto,
      // el huérfano no tocaría nada en la capa mixta.
      if (!terminos.length) {
        (d.terminosRuta || []).slice(0, porConcepto).forEach(function (t) {
          var idConcepto = indiceConcepto.get(t.lema);
          if (idConcepto === undefined) return;
          pertenencias.push({ documento: idDoc, concepto: idConcepto, peso: 1, deRuta: true });
        });
      }
    });

    // Índices inversos: son los que hacen instantáneo el gesto en el lienzo.
    var docsPorConcepto = new Map(), conceptosPorDoc = new Map();
    pertenencias.forEach(function (p) {
      if (!docsPorConcepto.has(p.concepto)) docsPorConcepto.set(p.concepto, []);
      docsPorConcepto.get(p.concepto).push(p.documento);
      if (!conceptosPorDoc.has(p.documento)) conceptosPorDoc.set(p.documento, []);
      conceptosPorDoc.get(p.documento).push(p.concepto);
    });

    var huerfanos = capaDocumentos.nodos.filter(function (n) {
      return !conceptosPorDoc.has(n.id);
    }).map(function (n) { return n.id; });

    return {
      pertenencias: pertenencias,
      docsPorConcepto: Array.from(docsPorConcepto.entries()),
      conceptosPorDoc: Array.from(conceptosPorDoc.entries()),
      totales: {
        pertenencias: pertenencias.length,
        conceptosConDocumento: docsPorConcepto.size,
        documentosConConcepto: conceptosPorDoc.size,
        documentosSinConcepto: huerfanos.length
      },
      huerfanos: huerfanos
    };
  }

  return { construir: construir };
});
