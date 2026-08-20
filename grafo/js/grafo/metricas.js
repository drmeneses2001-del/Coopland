(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.grafo = raiz.GC.grafo || {}).metricas = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Métricas estructurales del grafo no dirigido.
  //
  // La intermediación (betweenness) se calcula con el algoritmo de Brandes
  // sobre el grafo sin pesos: cuenta en cuántos caminos mínimos entre pares de
  // conceptos aparece cada nodo. Es la medida que decide el tamaño del nodo,
  // porque responde a la única pregunta que importa aquí: ¿por dónde pasa el
  // discurso? Sobre un umbral de tamaño se aproxima por muestreo de pivotes,
  // y el resultado dice siempre si es exacta o aproximada.

  var UMBRAL_EXACTO = 1200;   // nodos por encima de los cuales se muestrea
  var PIVOTES = 400;

  function adyacencia(n, aristas) {
    var vecinos = new Array(n), pesos = new Array(n);
    var i;
    for (i = 0; i < n; i++) { vecinos[i] = []; pesos[i] = []; }
    for (i = 0; i < aristas.length; i++) {
      var e = aristas[i];
      if (e.a === e.b) continue;
      vecinos[e.a].push(e.b); pesos[e.a].push(e.peso || 1);
      vecinos[e.b].push(e.a); pesos[e.b].push(e.peso || 1);
    }
    return { vecinos: vecinos, pesos: pesos };
  }

  function grados(n, aristas) {
    var grado = new Int32Array(n), fuerza = new Float64Array(n);
    for (var i = 0; i < aristas.length; i++) {
      var e = aristas[i];
      if (e.a === e.b) continue;
      grado[e.a]++; grado[e.b]++;
      fuerza[e.a] += e.peso || 1; fuerza[e.b] += e.peso || 1;
    }
    return { grado: grado, fuerza: fuerza };
  }

  // Generador reproducible: la misma carpeta debe dar el mismo grafo en cada
  // apertura, o el deslizador temporal mostraría cambios que nadie escribió.
  function azarFijo(semilla) {
    var s = semilla >>> 0 || 1;
    return function () {
      s ^= s << 13; s >>>= 0;
      s ^= s >>> 17;
      s ^= s << 5; s >>>= 0;
      return s / 4294967296;
    };
  }

  function intermediacion(n, aristas, opciones) {
    opciones = opciones || {};
    var ady = adyacencia(n, aristas);
    var vecinos = ady.vecinos;
    var exacta = n <= (opciones.umbralExacto != null ? opciones.umbralExacto : UMBRAL_EXACTO);
    var fuentes;

    if (exacta) {
      fuentes = new Int32Array(n);
      for (var f = 0; f < n; f++) fuentes[f] = f;
    } else {
      var cuantos = Math.min(n, opciones.pivotes != null ? opciones.pivotes : PIVOTES);
      var azar = azarFijo(opciones.semilla || 20240101);
      var mezcla = new Int32Array(n);
      for (var i = 0; i < n; i++) mezcla[i] = i;
      for (var j = n - 1; j > 0; j--) {
        var k = Math.floor(azar() * (j + 1));
        var tmp = mezcla[j]; mezcla[j] = mezcla[k]; mezcla[k] = tmp;
      }
      fuentes = mezcla.slice(0, cuantos);
    }

    var cb = new Float64Array(n);
    var sigma = new Float64Array(n);
    var dist = new Int32Array(n);
    var delta = new Float64Array(n);
    var cola = new Int32Array(n);
    var pila = new Int32Array(n);
    var predecesores = new Array(n);
    var p;
    for (p = 0; p < n; p++) predecesores[p] = [];

    for (var s = 0; s < fuentes.length; s++) {
      var origen = fuentes[s];
      for (p = 0; p < n; p++) { sigma[p] = 0; dist[p] = -1; delta[p] = 0; predecesores[p].length = 0; }
      sigma[origen] = 1; dist[origen] = 0;

      var cabeza = 0, cola_ = 0, tope = 0;
      cola[cola_++] = origen;
      while (cabeza < cola_) {
        var v = cola[cabeza++];
        pila[tope++] = v;
        var vs = vecinos[v];
        for (var w = 0; w < vs.length; w++) {
          var u = vs[w];
          if (dist[u] < 0) { dist[u] = dist[v] + 1; cola[cola_++] = u; }
          if (dist[u] === dist[v] + 1) { sigma[u] += sigma[v]; predecesores[u].push(v); }
        }
      }

      while (tope > 0) {
        var x = pila[--tope];
        var ps = predecesores[x];
        for (var q = 0; q < ps.length; q++) {
          var y = ps[q];
          delta[y] += (sigma[y] / sigma[x]) * (1 + delta[x]);
        }
        if (x !== origen) cb[x] += delta[x];
      }
    }

    // No dirigido: cada camino se cuenta dos veces. Y si se muestreó, se escala.
    var escala = exacta ? 0.5 : (0.5 * n / fuentes.length);
    for (var z = 0; z < n; z++) cb[z] *= escala;

    // Normalización a [0,1] por el número de pares posibles.
    var pares = (n - 1) * (n - 2) / 2;
    var normal = new Float64Array(n);
    if (pares > 0) for (var t = 0; t < n; t++) normal[t] = cb[t] / pares;

    return { valor: cb, normal: normal, exacta: exacta, fuentes: fuentes.length };
  }

  function componentes(n, aristas) {
    var ady = adyacencia(n, aristas).vecinos;
    var comp = new Int32Array(n).fill(-1);
    var tamanos = [];
    var cola = new Int32Array(n);
    for (var s = 0; s < n; s++) {
      if (comp[s] >= 0) continue;
      var id = tamanos.length, cuenta = 0, cabeza = 0, fin = 0;
      comp[s] = id; cola[fin++] = s;
      while (cabeza < fin) {
        var v = cola[cabeza++]; cuenta++;
        var vs = ady[v];
        for (var i = 0; i < vs.length; i++) if (comp[vs[i]] < 0) { comp[vs[i]] = id; cola[fin++] = vs[i]; }
      }
      tamanos.push(cuenta);
    }
    return { componente: comp, tamanos: tamanos, cuantas: tamanos.length, mayor: tamanos.length ? Math.max.apply(null, tamanos) : 0 };
  }

  // Puntos conectores del discurso: nodos con intermediación alta en relación a
  // lo poco que se repiten. Son los conceptos que sostienen el puente sin ser
  // los protagonistas, y suelen ser lo más interesante que hay en el grafo.
  function puntosConectores(nodos, intermediacionNormal, limite) {
    var n = nodos.length;
    if (!n) return [];
    var maxFrec = 0, maxInter = 0, i;
    for (i = 0; i < n; i++) {
      if (nodos[i].frecuencia > maxFrec) maxFrec = nodos[i].frecuencia;
      if (intermediacionNormal[i] > maxInter) maxInter = intermediacionNormal[i];
    }
    if (maxInter === 0) return [];

    var salida = [];
    for (i = 0; i < n; i++) {
      var inter = intermediacionNormal[i] / maxInter;
      if (inter <= 0) continue;
      var frec = maxFrec ? nodos[i].frecuencia / maxFrec : 0;
      // El +0.08 evita que un término que aparece dos veces y une por azar
      // se coloque por encima de un puente real.
      var razon = inter / (frec + 0.08);
      salida.push({
        id: nodos[i].id, lema: nodos[i].lema, forma: nodos[i].forma,
        frecuencia: nodos[i].frecuencia, docs: nodos[i].docs,
        intermediacion: intermediacionNormal[i], razon: razon
      });
    }
    salida.sort(function (a, b) { return b.razon - a.razon; });
    return salida.slice(0, limite || 20);
  }

  // Resumen por comunidad: tamaño, porcentaje y los conceptos que la definen.
  function resumirComunidades(nodos, comunidad, intermediacionNormal, cuantosTerminos) {
    var mapa = new Map();
    for (var i = 0; i < nodos.length; i++) {
      var c = comunidad[i];
      if (!mapa.has(c)) mapa.set(c, { id: c, miembros: [], frecuencia: 0, docs: new Set() });
      var g = mapa.get(c);
      g.miembros.push(i);
      g.frecuencia += nodos[i].frecuencia;
      (nodos[i].rutas || []).forEach(function (r) { g.docs.add(r); });
    }
    var total = nodos.length;
    var salida = [];
    mapa.forEach(function (g) {
      var ordenados = g.miembros.slice().sort(function (a, b) {
        return (intermediacionNormal[b] - intermediacionNormal[a]) ||
               (nodos[b].frecuencia - nodos[a].frecuencia);
      });
      salida.push({
        id: g.id,
        nodos: g.miembros.length,
        porcentaje: total ? (g.miembros.length / total) * 100 : 0,
        frecuencia: g.frecuencia,
        documentos: g.docs.size,
        terminos: ordenados.slice(0, cuantosTerminos || 8).map(function (i) {
          return { id: i, lema: nodos[i].lema, forma: nodos[i].forma, frecuencia: nodos[i].frecuencia };
        }),
        // Nombre por plantilla: los tres términos más centrales. La Fase 6
        // puede refinarlo con IA, pero esto ya es utilizable por sí solo.
        nombre: ordenados.slice(0, 3).map(function (i) { return nodos[i].forma; }).join(' · ')
      });
    });
    salida.sort(function (a, b) { return b.nodos - a.nodos; });
    return salida;
  }

  function masInfluyentes(nodos, intermediacionNormal, grado, limite) {
    var lista = nodos.map(function (n, i) {
      return {
        id: n.id, lema: n.lema, forma: n.forma, frecuencia: n.frecuencia, docs: n.docs,
        intermediacion: intermediacionNormal[i], grado: grado[i]
      };
    });
    lista.sort(function (a, b) { return b.intermediacion - a.intermediacion || b.frecuencia - a.frecuencia; });
    return lista.slice(0, limite || 25);
  }

  return {
    adyacencia: adyacencia, grados: grados, intermediacion: intermediacion,
    componentes: componentes, puntosConectores: puntosConectores,
    resumirComunidades: resumirComunidades, masInfluyentes: masInfluyentes,
    azarFijo: azarFijo, UMBRAL_EXACTO: UMBRAL_EXACTO, PIVOTES: PIVOTES
  };
});
