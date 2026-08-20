(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.grafo = raiz.GC.grafo || {}).ruta = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Ruta de lectura: el camino más corto ponderado entre dos nodos.
  //
  // «Corto» aquí no es «pocos saltos»: una arista fuerte —dos conceptos que
  // aparecen juntos una y otra vez— es un paso *barato*, y una arista débil es
  // caro aunque sea un solo salto. Por eso el coste de cruzar una arista es
  // 1/peso. El resultado es un plan de lectura derivado de la topología: por
  // dónde pasar para ir de una idea a otra sin saltos al vacío.

  function adyacencia(n, aristas, umbralAfinidad) {
    var vecinos = new Array(n), costes = new Array(n), i;
    for (i = 0; i < n; i++) { vecinos[i] = []; costes[i] = []; }
    for (i = 0; i < aristas.length; i++) {
      var e = aristas[i];
      if (e.a === e.b) continue;
      var peso;
      if (e.tipo === 'afinidad') {
        if (umbralAfinidad != null && (e.coseno || 0) < umbralAfinidad) continue;
        peso = e.coseno || 0.01;
      } else peso = e.peso || 1;
      var coste = 1 / Math.max(0.01, peso);
      vecinos[e.a].push(e.b); costes[e.a].push(coste);
      vecinos[e.b].push(e.a); costes[e.b].push(coste);
    }
    return { vecinos: vecinos, costes: costes };
  }

  // Montículo binario mínimo. Con unos miles de nodos, una cola ordenada por
  // fuerza bruta se nota en el dedo; esto no.
  function monticulo() {
    var claves = [], valores = [];
    function subir(i) {
      while (i > 0) {
        var padre = (i - 1) >> 1;
        if (claves[padre] <= claves[i]) break;
        var ck = claves[padre]; claves[padre] = claves[i]; claves[i] = ck;
        var cv = valores[padre]; valores[padre] = valores[i]; valores[i] = cv;
        i = padre;
      }
    }
    function bajar(i) {
      var n = claves.length;
      for (;;) {
        var izq = 2 * i + 1, der = izq + 1, menor = i;
        if (izq < n && claves[izq] < claves[menor]) menor = izq;
        if (der < n && claves[der] < claves[menor]) menor = der;
        if (menor === i) break;
        var ck = claves[menor]; claves[menor] = claves[i]; claves[i] = ck;
        var cv = valores[menor]; valores[menor] = valores[i]; valores[i] = cv;
        i = menor;
      }
    }
    return {
      meter: function (clave, valor) { claves.push(clave); valores.push(valor); subir(claves.length - 1); },
      sacar: function () {
        var v = valores[0], c = claves[0];
        var ultimoV = valores.pop(), ultimoC = claves.pop();
        if (claves.length) { valores[0] = ultimoV; claves[0] = ultimoC; bajar(0); }
        return { clave: c, valor: v };
      },
      vacio: function () { return claves.length === 0; }
    };
  }

  function calcular(n, aristas, origen, destino, opciones) {
    opciones = opciones || {};
    if (origen === destino) return { camino: [origen], coste: 0, existe: true };
    var ady = adyacencia(n, aristas, opciones.umbralAfinidad);
    var dist = new Float64Array(n).fill(Infinity);
    var previo = new Int32Array(n).fill(-1);
    var listo = new Uint8Array(n);
    var cola = monticulo();
    dist[origen] = 0;
    cola.meter(0, origen);

    while (!cola.vacio()) {
      var t = cola.sacar();
      var v = t.valor;
      if (listo[v]) continue;
      listo[v] = 1;
      if (v === destino) break;
      var vs = ady.vecinos[v], cs = ady.costes[v];
      for (var i = 0; i < vs.length; i++) {
        var u = vs[i];
        if (listo[u]) continue;
        if (opciones.visible && !opciones.visible[u]) continue;
        var nd = dist[v] + cs[i];
        if (nd < dist[u]) { dist[u] = nd; previo[u] = v; cola.meter(nd, u); }
      }
    }

    if (!isFinite(dist[destino])) {
      return { camino: [], coste: Infinity, existe: false,
               motivo: 'No hay ningún camino entre los dos: están en componentes distintas del grafo.' };
    }
    var camino = [];
    for (var x = destino; x !== -1; x = previo[x]) camino.push(x);
    camino.reverse();
    return { camino: camino, coste: dist[destino], existe: true };
  }

  // Traduce un camino de conceptos a una secuencia ordenada de documentos:
  // el plan de lectura propiamente dicho. Cada paso trae el documento que mejor
  // cubre ese tramo del camino y que no se haya usado ya.
  function planDeLectura(camino, nodos, docsPorLema, opciones) {
    opciones = opciones || {};
    var usados = new Set();
    var pasos = [];
    for (var i = 0; i < camino.length; i++) {
      var nodo = nodos[camino[i]];
      var docs = docsPorLema ? docsPorLema.get(nodo.lema) : null;
      var candidatos = docs ? Array.from(docs) : (nodo.rutas || []);
      var elegido = null;
      for (var k = 0; k < candidatos.length; k++) {
        if (!usados.has(candidatos[k])) { elegido = candidatos[k]; break; }
      }
      // Si todos sus documentos ya están en el plan, no se repite: el tramo se
      // cubre con lo ya leído y se marca así.
      pasos.push({
        concepto: nodo.forma || nodo.lema,
        conceptoId: camino[i],
        documento: elegido,
        yaCubierto: !elegido && candidatos.length > 0,
        sinDocumento: candidatos.length === 0
      });
      if (elegido) usados.add(elegido);
    }
    return { pasos: pasos, documentos: Array.from(usados) };
  }

  return { calcular: calcular, planDeLectura: planDeLectura, adyacencia: adyacencia, monticulo: monticulo };
});
