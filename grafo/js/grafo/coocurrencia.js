(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.grafo = raiz.GC.grafo || {}).coocurrencia = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Capa de conceptos: el método de red de texto.
  //
  // Ventana deslizante de cuatro tokens sobre el flujo ya lematizado y sin
  // palabras vacías. Cada par dentro de la ventana suma peso; el par que ocurre
  // dentro de la misma oración pesa más que el que cruza un punto, porque una
  // frase es una afirmación y un salto de oración es sólo vecindad.
  //
  // De cada arista se guardan además unas pocas oraciones de origen. Ése es el
  // material de la trazabilidad: poder abrir el documento y ver subrayada la
  // línea exacta que produjo la conexión, en vez de creerle al panel.

  var VENTANA = 4;
  var PESO_MISMA_ORACION = 1.0;
  var PESO_ENTRE_ORACIONES = 0.4;
  var MUESTRAS_POR_ARISTA = 3;

  function crear(opciones) {
    opciones = opciones || {};
    var ventana = opciones.ventana || VENTANA;
    var pesoDentro = opciones.pesoMismaOracion != null ? opciones.pesoMismaOracion : PESO_MISMA_ORACION;
    var pesoFuera = opciones.pesoEntreOraciones != null ? opciones.pesoEntreOraciones : PESO_ENTRE_ORACIONES;
    var maxMuestras = opciones.muestrasPorArista != null ? opciones.muestrasPorArista : MUESTRAS_POR_ARISTA;

    var nodos = new Map();   // lema -> {lema, formas, frecuencia, docs}
    var aristas = new Map(); // clave -> {a, b, peso, docs, muestras}
    var documentos = 0;

    function tocarNodo(lema, forma, ruta) {
      var n = nodos.get(lema);
      if (!n) { n = { lema: lema, formas: new Map(), frecuencia: 0, docs: new Set() }; nodos.set(lema, n); }
      n.frecuencia++;
      n.formas.set(forma, (n.formas.get(forma) || 0) + 1);
      n.docs.add(ruta);
      return n;
    }

    function tocarArista(a, b, peso, ruta, oracion) {
      if (a === b) return;
      var menor = a < b ? a : b, mayor = a < b ? b : a;
      var clave = menor + ' ' + mayor;
      var e = aristas.get(clave);
      if (!e) { e = { a: menor, b: mayor, peso: 0, docs: new Set(), muestras: [] }; aristas.set(clave, e); }
      e.peso += peso;
      e.docs.add(ruta);
      if (e.muestras.length < maxMuestras) {
        var repetida = e.muestras.some(function (m) { return m.ruta === ruta && m.oracion === oracion; });
        if (!repetida) e.muestras.push({ ruta: ruta, oracion: oracion });
      }
    }

    // `tokens` es la salida de terminos.tokenizar(): lleva lema, forma y el
    // índice de oración de cada aparición.
    function agregar(ruta, tokens) {
      documentos++;
      for (var i = 0; i < tokens.length; i++) {
        var t = tokens[i];
        tocarNodo(t.lema, t.forma, ruta);
        var hasta = Math.min(i + ventana, tokens.length);
        for (var j = i + 1; j < hasta; j++) {
          var u = tokens[j];
          var mismaOracion = t.oracion === u.oracion;
          tocarArista(t.lema, u.lema, mismaOracion ? pesoDentro : pesoFuera, ruta, t.oracion);
        }
      }
    }

    // Los términos de la ruta de un archivo sin texto no tienen oraciones: se
    // conectan entre sí para que el huérfano no quede como polvo suelto.
    function agregarRuta(ruta, terminosRuta) {
      documentos++;
      var lemas = [];
      for (var i = 0; i < terminosRuta.length; i++) {
        tocarNodo(terminosRuta[i].lema, terminosRuta[i].forma, ruta);
        lemas.push(terminosRuta[i].lema);
      }
      for (var a = 0; a < lemas.length; a++) {
        for (var b = a + 1; b < lemas.length; b++) tocarArista(lemas[a], lemas[b], pesoFuera, ruta, -1);
      }
    }

    function formaMasUsada(n) {
      var mejor = n.lema, mejorN = -1;
      n.formas.forEach(function (c, f) { if (c > mejorN) { mejorN = c; mejor = f; } });
      return mejor;
    }

    // Corte del grafo. Dos filtros, en este orden: primero los nodos por
    // frecuencia, luego las aristas por peso. Lo descartado se cuenta y se
    // informa; el grafo nunca calla lo que no está mostrando.
    function construir(corte) {
      corte = corte || {};
      // `!= null` y no `||`: un cero pedido a propósito («no filtres nada») es un
      // valor legítimo, y con `||` se convertía en silencio en el valor por defecto.
      var maxNodos = corte.maxNodos != null ? corte.maxNodos : 3000;
      var minFrecuencia = corte.minFrecuencia != null ? corte.minFrecuencia : 2;
      var minPeso = corte.minPeso != null ? corte.minPeso : 1;
      var minDocs = corte.minDocs != null ? corte.minDocs : 1;

      var candidatos = [];
      nodos.forEach(function (n) {
        if (n.frecuencia < minFrecuencia) return;
        if (n.docs.size < minDocs) return;
        candidatos.push(n);
      });
      candidatos.sort(function (x, y) {
        return y.frecuencia - x.frecuencia || y.docs.size - x.docs.size || x.lema.localeCompare(y.lema);
      });

      var nodosDescartados = nodos.size - candidatos.length;
      if (candidatos.length > maxNodos) {
        nodosDescartados += candidatos.length - maxNodos;
        candidatos = candidatos.slice(0, maxNodos);
      }

      var indice = new Map();
      var salidaNodos = candidatos.map(function (n, i) {
        indice.set(n.lema, i);
        return {
          id: i, lema: n.lema, forma: formaMasUsada(n),
          frecuencia: n.frecuencia, docs: n.docs.size,
          rutas: Array.from(n.docs).slice(0, 50)
        };
      });

      var salidaAristas = [];
      var aristasDescartadas = 0;
      aristas.forEach(function (e) {
        var ia = indice.get(e.a), ib = indice.get(e.b);
        if (ia === undefined || ib === undefined) { aristasDescartadas++; return; }
        if (e.peso < minPeso) { aristasDescartadas++; return; }
        salidaAristas.push({
          a: ia, b: ib,
          peso: Math.round(e.peso * 100) / 100,
          docs: e.docs.size,
          muestras: e.muestras
        });
      });
      salidaAristas.sort(function (x, y) { return y.peso - x.peso; });

      return {
        nodos: salidaNodos,
        aristas: salidaAristas,
        totales: {
          documentos: documentos,
          conceptosVistos: nodos.size,
          aristasVistas: aristas.size,
          nodosDescartados: nodosDescartados,
          aristasDescartadas: aristasDescartadas
        },
        corte: { maxNodos: maxNodos, minFrecuencia: minFrecuencia, minPeso: minPeso, minDocs: minDocs }
      };
    }

    return {
      agregar: agregar, agregarRuta: agregarRuta, construir: construir,
      tamano: function () { return { nodos: nodos.size, aristas: aristas.size, documentos: documentos }; }
    };
  }

  return { crear: crear, VENTANA: VENTANA, PESO_MISMA_ORACION: PESO_MISMA_ORACION, PESO_ENTRE_ORACIONES: PESO_ENTRE_ORACIONES };
});
