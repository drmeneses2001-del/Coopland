(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.grafo = raiz.GC.grafo || {}).louvain = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Comunidades por el método de Louvain: optimización voraz de la modularidad
  // (modularity) en dos pasos que se repiten — mover cada nodo a la comunidad
  // vecina que más mejore Q, y después contraer cada comunidad en un solo nodo.
  //
  // La modularidad resultante es además el indicador de diversidad temática:
  // un corpus que trata un solo asunto da Q baja; uno con territorios separados
  // que no se hablan da Q alta.

  var MEJORA_MINIMA = 1e-7;

  // Grafo interno: listas de adyacencia con pesos, más los lazos propios que
  // aparecen al contraer comunidades.
  function armar(n, aristas) {
    var vecinos = new Array(n), pesos = new Array(n);
    var grados = new Float64Array(n), lazos = new Float64Array(n);
    var i;
    for (i = 0; i < n; i++) { vecinos[i] = []; pesos[i] = []; }
    var m = 0;
    for (i = 0; i < aristas.length; i++) {
      var e = aristas[i], w = e.peso || 1;
      if (e.a === e.b) { lazos[e.a] += w; grados[e.a] += 2 * w; m += w; continue; }
      vecinos[e.a].push(e.b); pesos[e.a].push(w);
      vecinos[e.b].push(e.a); pesos[e.b].push(w);
      grados[e.a] += w; grados[e.b] += w; m += w;
    }
    return { n: n, vecinos: vecinos, pesos: pesos, grados: grados, lazos: lazos, m: m };
  }

  function modularidadDe(g, comunidad) {
    if (g.m === 0) return 0;
    var dosM = 2 * g.m;
    var dentro = new Map(), total = new Map();
    var i, j;
    for (i = 0; i < g.n; i++) {
      var c = comunidad[i];
      total.set(c, (total.get(c) || 0) + g.grados[i]);
      dentro.set(c, (dentro.get(c) || 0) + 2 * g.lazos[i]);
    }
    for (i = 0; i < g.n; i++) {
      var vs = g.vecinos[i], ws = g.pesos[i];
      for (j = 0; j < vs.length; j++) {
        if (comunidad[vs[j]] === comunidad[i]) dentro.set(comunidad[i], dentro.get(comunidad[i]) + ws[j]);
      }
    }
    var q = 0;
    total.forEach(function (tot, c) {
      var din = dentro.get(c) || 0;
      q += din / dosM - (tot / dosM) * (tot / dosM);
    });
    return q;
  }

  // Paso 1: mover nodos de uno en uno mientras la modularidad mejore.
  function moverNodos(g, resolucion) {
    var comunidad = new Int32Array(g.n);
    var totalCom = new Float64Array(g.n);
    var i;
    for (i = 0; i < g.n; i++) { comunidad[i] = i; totalCom[i] = g.grados[i]; }
    if (g.m === 0) return { comunidad: comunidad, mejoro: false };

    var dosM = 2 * g.m;
    var pesoHacia = new Float64Array(g.n);
    var tocadas = [];
    var mejoroAlguna = false, sigue = true, vueltas = 0;

    // Orden fijo pero no trivial: recorrer por índice favorece a los nodos más
    // frecuentes, que ya vienen ordenados por frecuencia desde la capa anterior.
    while (sigue && vueltas < 50) {
      sigue = false; vueltas++;
      for (i = 0; i < g.n; i++) {
        var propia = comunidad[i];
        var vs = g.vecinos[i], ws = g.pesos[i];
        var k;

        tocadas.length = 0;
        for (k = 0; k < vs.length; k++) {
          var c = comunidad[vs[k]];
          if (pesoHacia[c] === 0) tocadas.push(c);
          pesoHacia[c] += ws[k];
        }

        totalCom[propia] -= g.grados[i];
        var mejorCom = propia;
        var mejorGanancia = (pesoHacia[propia] || 0) - resolucion * totalCom[propia] * g.grados[i] / dosM;

        for (k = 0; k < tocadas.length; k++) {
          var cand = tocadas[k];
          if (cand === propia) continue;
          var ganancia = pesoHacia[cand] - resolucion * totalCom[cand] * g.grados[i] / dosM;
          if (ganancia > mejorGanancia + MEJORA_MINIMA) { mejorGanancia = ganancia; mejorCom = cand; }
        }

        totalCom[mejorCom] += g.grados[i];
        comunidad[i] = mejorCom;
        if (mejorCom !== propia) { sigue = true; mejoroAlguna = true; }

        for (k = 0; k < tocadas.length; k++) pesoHacia[tocadas[k]] = 0;
      }
    }
    return { comunidad: comunidad, mejoro: mejoroAlguna };
  }

  // Paso 2: contraer cada comunidad en un nodo y sumar los pesos.
  function contraer(g, comunidad) {
    var mapa = new Map(), siguiente = 0;
    var renombrada = new Int32Array(g.n);
    var i, j;
    for (i = 0; i < g.n; i++) {
      var c = comunidad[i];
      if (!mapa.has(c)) mapa.set(c, siguiente++);
      renombrada[i] = mapa.get(c);
    }

    var acumulado = new Map();
    for (i = 0; i < g.n; i++) {
      var ci = renombrada[i];
      if (g.lazos[i]) {
        var claveLazo = ci + ':' + ci;
        acumulado.set(claveLazo, (acumulado.get(claveLazo) || 0) + g.lazos[i]);
      }
      var vs = g.vecinos[i], ws = g.pesos[i];
      for (j = 0; j < vs.length; j++) {
        var cj = renombrada[vs[j]];
        if (cj < ci) continue;                       // cada par una sola vez
        var clave = ci + ':' + cj;
        // Los pares internos se ven dos veces (i->v y v->i): media al sumar.
        acumulado.set(clave, (acumulado.get(clave) || 0) + (ci === cj ? ws[j] / 2 : ws[j]));
      }
    }

    var aristas = [];
    acumulado.forEach(function (w, clave) {
      var partes = clave.split(':');
      aristas.push({ a: +partes[0], b: +partes[1], peso: w });
    });
    return { grafo: armar(siguiente, aristas), renombrada: renombrada, n: siguiente };
  }

  // `n` nodos numerados 0..n-1, `aristas` con {a, b, peso}.
  function detectar(n, aristas, opciones) {
    opciones = opciones || {};
    var resolucion = opciones.resolucion || 1;
    var g = armar(n, aristas);
    if (g.m === 0) {
      var solos = new Int32Array(n);
      for (var s = 0; s < n; s++) solos[s] = s;
      return { comunidad: solos, modularidad: 0, niveles: 0, comunidades: n };
    }

    var asignacion = new Int32Array(n);
    for (var i = 0; i < n; i++) asignacion[i] = i;
    var actual = g, niveles = 0;

    while (niveles < 20) {
      var paso = moverNodos(actual, resolucion);
      var contraida = contraer(actual, paso.comunidad);
      // Reproyectar la partición sobre los nodos originales.
      for (var k = 0; k < n; k++) asignacion[k] = contraida.renombrada[asignacion[k]];
      niveles++;
      if (!paso.mejoro || contraida.n === actual.n) break;
      actual = contraida.grafo;
    }

    // Renumerar por tamaño: la comunidad 0 es siempre la mayor.
    var cuenta = new Map();
    for (var t = 0; t < n; t++) cuenta.set(asignacion[t], (cuenta.get(asignacion[t]) || 0) + 1);
    var orden = Array.from(cuenta.entries()).sort(function (x, y) { return y[1] - x[1] || x[0] - y[0]; });
    var traduccion = new Map();
    orden.forEach(function (par, indice) { traduccion.set(par[0], indice); });
    var final = new Int32Array(n);
    for (var u = 0; u < n; u++) final[u] = traduccion.get(asignacion[u]);

    return {
      comunidad: final,
      modularidad: modularidadDe(g, final),
      niveles: niveles,
      comunidades: orden.length
    };
  }

  // Lectura de la modularidad como diversidad temática. Los cortes son una
  // decisión de este proyecto, no una constante universal: por eso la cifra
  // siempre se muestra junto a la etiqueta.
  function diversidad(q) {
    if (q < 0.20) return { etiqueta: 'Enfocada', q: q, explicacion: 'Un solo territorio: casi todo se conecta con casi todo. Riesgo de estar dando vueltas sobre lo mismo.' };
    if (q < 0.40) return { etiqueta: 'Media', q: q, explicacion: 'Hay grupos, pero se hablan entre sí. Es la estructura de un corpus en desarrollo.' };
    if (q < 0.60) return { etiqueta: 'Diversa', q: q, explicacion: 'Varios territorios definidos con puentes entre ellos. Aquí es donde las brechas valen la pena.' };
    return { etiqueta: 'Dispersa', q: q, explicacion: 'Islas que casi no se tocan. O son temas realmente ajenos, o falta el texto que los una.' };
  }

  return { detectar: detectar, diversidad: diversidad, modularidadDe: modularidadDe, armar: armar };
});
