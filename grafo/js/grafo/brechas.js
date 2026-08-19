(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.grafo = raiz.GC.grafo || {}).brechas = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Brechas: definidas por operación, no por intuición.
  //
  // Una brecha no es «dos cosas que no se tocan» — en un grafo grande eso son
  // millones de pares y ninguno significa nada. Una brecha es una ausencia
  // *estructuralmente improbable*: dos territorios densos por dentro que casi
  // no se hablan entre sí, un texto denso que nadie enlazó, o un concepto que
  // toca dos mundos sin que ningún documento los junte nunca.
  //
  // Las tres se calculan aparte, se puntúan aparte y se explican aparte.

  // ------------------------------------------------------------- utilidad ---
  function adyacencia(n, aristas) {
    var vecinos = new Array(n), pesos = new Array(n), i;
    for (i = 0; i < n; i++) { vecinos[i] = []; pesos[i] = []; }
    for (i = 0; i < aristas.length; i++) {
      var e = aristas[i];
      if (e.a === e.b) continue;
      vecinos[e.a].push(e.b); pesos[e.a].push(e.peso || 1);
      vecinos[e.b].push(e.a); pesos[e.b].push(e.peso || 1);
    }
    return { vecinos: vecinos, pesos: pesos };
  }

  // Distancias en saltos desde un origen. Se usa para estimar la facilidad de
  // tender el puente: dos saltos es una frase; seis es una tesis.
  function distanciasDesde(origen, n, vecinos) {
    var dist = new Int32Array(n).fill(-1);
    var cola = new Int32Array(n);
    var cabeza = 0, fin = 0;
    dist[origen] = 0; cola[fin++] = origen;
    while (cabeza < fin) {
      var v = cola[cabeza++];
      var vs = vecinos[v];
      for (var i = 0; i < vs.length; i++) {
        if (dist[vs[i]] < 0) { dist[vs[i]] = dist[v] + 1; cola[fin++] = vs[i]; }
      }
    }
    return dist;
  }

  function percentil(valores, p) {
    if (!valores.length) return 0;
    var orden = valores.slice().sort(function (a, b) { return a - b; });
    var i = (p / 100) * (orden.length - 1);
    var bajo = Math.floor(i), alto = Math.ceil(i);
    if (bajo === alto) return orden[bajo];
    return orden[bajo] + (orden[alto] - orden[bajo]) * (i - bajo);
  }

  function interseccion(a, b) {
    var chico = a.size <= b.size ? a : b;
    var grande = chico === a ? b : a;
    var salida = [];
    chico.forEach(function (x) { if (grande.has(x)) salida.push(x); });
    return salida;
  }

  // ----------------------------------------------------- brecha estructural ---
  function estructurales(entrada, opciones) {
    var nodos = entrada.nodos, aristas = entrada.aristas, comunidad = entrada.comunidad;
    var n = nodos.length;
    if (n < 4) return { lista: [], parametros: { motivo: 'grafo demasiado pequeño' } };

    var minTamano = opciones.minTamanoComunidad || 3;
    var percentilCorte = opciones.percentilDensidad != null ? opciones.percentilDensidad : 25;
    var maximo = opciones.maxBrechas || 12;

    // Miembros y frecuencia por comunidad.
    var miembros = new Map(), frecuencia = new Map(), frecuenciaTotal = 0;
    for (var i = 0; i < n; i++) {
      var c = comunidad[i];
      if (!miembros.has(c)) { miembros.set(c, []); frecuencia.set(c, 0); }
      miembros.get(c).push(i);
      frecuencia.set(c, frecuencia.get(c) + nodos[i].frecuencia);
      frecuenciaTotal += nodos[i].frecuencia;
    }

    var comunidades = Array.from(miembros.keys()).filter(function (c) {
      return miembros.get(c).length >= minTamano;
    });
    if (comunidades.length < 2) return { lista: [], parametros: { motivo: 'menos de dos comunidades con tamaño suficiente' } };

    // Aristas internas y cruzadas.
    var internas = new Map(), cruzadas = new Map(), pesoCruzado = new Map();
    comunidades.forEach(function (c) { internas.set(c, 0); });
    for (var e = 0; e < aristas.length; e++) {
      var ca = comunidad[aristas[e].a], cb = comunidad[aristas[e].b];
      if (ca === cb) {
        if (internas.has(ca)) internas.set(ca, internas.get(ca) + 1);
        continue;
      }
      if (!internas.has(ca) || !internas.has(cb)) continue;
      var k = Math.min(ca, cb) + ':' + Math.max(ca, cb);
      cruzadas.set(k, (cruzadas.get(k) || 0) + 1);
      pesoCruzado.set(k, (pesoCruzado.get(k) || 0) + (aristas[e].peso || 1));
    }

    var densidadInterna = new Map();
    comunidades.forEach(function (c) {
      var m = miembros.get(c).length;
      var posibles = m * (m - 1) / 2;
      densidadInterna.set(c, posibles ? internas.get(c) / posibles : 0);
    });

    // «Densa por dentro» se mide contra la densidad del grafo entero, no contra
    // la mediana de las comunidades: con dos comunidades la mediana deja fuera
    // a una por definición, y con tres deja fuera a la mitad. Una comunidad más
    // densa que el grafo completo es cohesiva; ésa es la comparación honesta.
    var densidadGlobal = n > 1 ? aristas.length / (n * (n - 1) / 2) : 0;
    var minimoInterno = Math.max(densidadGlobal, opciones.minDensidadInterna || 0);

    // Nodo más central de cada comunidad: el extremo por el que se tendería
    // el puente y desde el que se mide la distancia.
    var central = new Map();
    comunidades.forEach(function (c) {
      var mejor = miembros.get(c)[0];
      miembros.get(c).forEach(function (i) {
        if (entrada.intermediacion[i] > entrada.intermediacion[mejor] ||
           (entrada.intermediacion[i] === entrada.intermediacion[mejor] && nodos[i].frecuencia > nodos[mejor].frecuencia)) mejor = i;
      });
      central.set(c, mejor);
    });

    // Densidades cruzadas de todos los pares, para el corte por percentil.
    var pares = [];
    for (var x = 0; x < comunidades.length; x++) {
      for (var y = x + 1; y < comunidades.length; y++) {
        var A = comunidades[x], B = comunidades[y];
        var k2 = Math.min(A, B) + ':' + Math.max(A, B);
        var nA = miembros.get(A).length, nB = miembros.get(B).length;
        pares.push({
          A: A, B: B, nA: nA, nB: nB,
          aristas: cruzadas.get(k2) || 0,
          peso: pesoCruzado.get(k2) || 0,
          densidad: (cruzadas.get(k2) || 0) / (nA * nB)
        });
      }
    }
    var corte = percentil(pares.map(function (p) { return p.densidad; }), percentilCorte);

    var ady = adyacencia(n, aristas);
    var cacheDistancias = new Map();
    function distanciaEntre(A, B) {
      if (!cacheDistancias.has(A)) cacheDistancias.set(A, distanciasDesde(central.get(A), n, ady.vecinos));
      var d = cacheDistancias.get(A)[central.get(B)];
      return d < 0 ? null : d;
    }

    var candidatos = pares.filter(function (p) {
      if (p.densidad > corte) return false;
      return densidadInterna.get(p.A) >= minimoInterno && densidadInterna.get(p.B) >= minimoInterno;
    });

    var lista = candidatos.map(function (p) {
      var d = distanciaEntre(p.A, p.B);
      // Peso: cuánto del corpus está en juego. Facilidad: lo cerca que están
      // sus centros. Sin camino no es facilidad cero —es la brecha más honda—,
      // pero se puntúa por debajo de cualquier distancia real y se dice.
      var peso = (frecuencia.get(p.A) + frecuencia.get(p.B)) / (frecuenciaTotal || 1);
      var facilidad = d == null ? 1 / 12 : 1 / Math.max(1, d);
      return {
        tipo: 'estructural',
        comunidadA: p.A, comunidadB: p.B,
        nodosA: p.nA, nodosB: p.nB,
        aristasCruzadas: p.aristas,
        densidadCruzada: p.densidad,
        densidadInternaA: densidadInterna.get(p.A),
        densidadInternaB: densidadInterna.get(p.B),
        distancia: d,
        sinCamino: d == null,
        peso: peso,
        facilidad: facilidad,
        puntuacion: peso * facilidad,
        centralA: { id: central.get(p.A), forma: nodos[central.get(p.A)].forma },
        centralB: { id: central.get(p.B), forma: nodos[central.get(p.B)].forma },
        terminosA: miembros.get(p.A).slice().sort(function (a, b) {
          return entrada.intermediacion[b] - entrada.intermediacion[a] || nodos[b].frecuencia - nodos[a].frecuencia;
        }).slice(0, 6).map(function (i) { return nodos[i].forma; }),
        terminosB: miembros.get(p.B).slice().sort(function (a, b) {
          return entrada.intermediacion[b] - entrada.intermediacion[a] || nodos[b].frecuencia - nodos[a].frecuencia;
        }).slice(0, 6).map(function (i) { return nodos[i].forma; })
      };
    });

    lista.sort(function (a, b) { return b.puntuacion - a.puntuacion; });
    lista = lista.slice(0, maximo);

    return {
      lista: lista,
      parametros: {
        comunidadesConsideradas: comunidades.length,
        paresEvaluados: pares.length,
        corteDensidad: corte,
        percentil: percentilCorte,
        densidadGlobal: densidadGlobal,
        minimoDensidadInterna: minimoInterno,
        minTamanoComunidad: minTamano
      }
    };
  }

  // Documentos más cercanos a un lado de la brecha: los que más conceptos de
  // esa comunidad contienen. Son por dónde empezaría a leer quien quiera cruzar.
  function documentosDeComunidad(miembrosIds, nodos, docsPorLema, cuantos) {
    var cuenta = new Map();
    miembrosIds.forEach(function (i) {
      var docs = docsPorLema.get(nodos[i].lema);
      if (!docs) return;
      docs.forEach(function (ruta) { cuenta.set(ruta, (cuenta.get(ruta) || 0) + 1); });
    });
    return Array.from(cuenta.entries())
      .sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0]); })
      .slice(0, cuantos || 3)
      .map(function (e) { return { ruta: e[0], conceptos: e[1] }; });
  }

  // ------------------------------------------------------ documento aislado ---
  function aislados(capaDocumentos, opciones) {
    var conDependencia = new Set();
    capaDocumentos.dependencias.forEach(function (e) { conDependencia.add(e.a); conDependencia.add(e.b); });

    var leidos = capaDocumentos.nodos.filter(function (d) { return d.estado === 'ok' && d.terminos > 0; });
    if (!leidos.length) return { lista: [], parametros: { motivo: 'sin documentos legibles' } };

    // «Rico en contenido» es relativo al corpus, no un número fijo: un umbral
    // absoluto declara aislado a medio archivo de notas breves y a ninguno de
    // un archivo de artículos largos.
    var mediana = percentil(leidos.map(function (d) { return d.terminos; }), 50);

    // Vecinos por afinidad: con quién se parece aunque nadie lo haya enlazado.
    var afinesPorDoc = new Map();
    capaDocumentos.afinidades.forEach(function (e) {
      if (!afinesPorDoc.has(e.a)) afinesPorDoc.set(e.a, []);
      if (!afinesPorDoc.has(e.b)) afinesPorDoc.set(e.b, []);
      afinesPorDoc.get(e.a).push({ id: e.b, coseno: e.coseno });
      afinesPorDoc.get(e.b).push({ id: e.a, coseno: e.coseno });
    });

    var lista = leidos.filter(function (d) {
      return d.terminos >= mediana && !conDependencia.has(d.id);
    }).map(function (d) {
      var afines = (afinesPorDoc.get(d.id) || []).sort(function (a, b) { return b.coseno - a.coseno; }).slice(0, 3);
      return {
        tipo: 'aislado',
        id: d.id, ruta: d.ruta, nombre: d.nombre,
        palabras: d.palabras, terminos: d.terminos,
        // Un documento denso y sin ningún parecido es más aislado que uno denso
        // con vecinos evidentes que nadie enlazó: el segundo es fácil de coser.
        afines: afines.map(function (a) {
          return { ruta: capaDocumentos.nodos[a.id].ruta, coseno: a.coseno };
        }),
        puntuacion: d.terminos * (afines.length ? 1 : 1.5)
      };
    });

    lista.sort(function (a, b) { return b.puntuacion - a.puntuacion; });
    return {
      lista: lista.slice(0, opciones.maxAislados || 20),
      parametros: {
        umbralTerminos: mediana,
        criterio: 'al menos ' + mediana + ' términos propios (la mediana del corpus) y ninguna dependencia explícita',
        totalAislados: lista.length
      }
    };
  }

  // ------------------------------------------------ concepto puente ausente ---
  // Un término cuyos vecinos viven en dos comunidades distintas, pero que
  // ningún documento junta con ambos lados a la vez. El puente existe en el
  // agregado del corpus y no existe en ningún texto concreto.
  function puentesAusentes(entrada, opciones) {
    var nodos = entrada.nodos, comunidad = entrada.comunidad, docsPorLema = entrada.docsPorLema;
    var n = nodos.length;
    if (n < 6 || !docsPorLema) return { lista: [], parametros: { motivo: 'faltan datos' } };

    var ady = adyacencia(n, entrada.aristas);
    // Un concepto con un solo vecino a cada lado es justo la forma canónica de
    // un puente; exigirle dos lo descartaba precisamente en el caso que importa.
    // Lo que filtra el ruido no es el grado, es la intermediación: un puente de
    // verdad la tiene alta, y la puntuación la usa como factor.
    var minVecinos = opciones.minVecinosPorLado || 1;
    var minDocumentos = opciones.minDocumentosPuente || 2;
    var maxRevisados = opciones.maxRevisados || 400;

    // Sólo se revisan los nodos con más intermediación: son los únicos que
    // pueden estar sosteniendo un puente. Revisar los 3000 no cambiaría el
    // resultado y multiplicaría el coste por diez.
    var orden = [];
    for (var i = 0; i < n; i++) if (ady.vecinos[i].length >= 2 && entrada.intermediacion[i] > 0) orden.push(i);
    orden.sort(function (a, b) { return entrada.intermediacion[b] - entrada.intermediacion[a]; });
    orden = orden.slice(0, maxRevisados);

    var lista = [];
    for (var k = 0; k < orden.length; k++) {
      var c = orden[k];
      var docsC = docsPorLema.get(nodos[c].lema);
      if (!docsC || docsC.size < minDocumentos) continue;   // en un solo documento no hay nada que unir

      // Vecinos agrupados por comunidad.
      var porComunidad = new Map();
      var vs = ady.vecinos[c];
      for (var v = 0; v < vs.length; v++) {
        var cc = comunidad[vs[v]];
        if (!porComunidad.has(cc)) porComunidad.set(cc, []);
        porComunidad.get(cc).push(vs[v]);
      }
      var lados = Array.from(porComunidad.entries())
        .filter(function (e) { return e[1].length >= minVecinos; })
        .sort(function (a, b) { return b[1].length - a[1].length; });
      if (lados.length < 2) continue;

      // Documentos donde el concepto aparece junto a cada lado.
      function documentosDelLado(vecinos) {
        var s = new Set();
        vecinos.forEach(function (u) {
          var d = docsPorLema.get(nodos[u].lema);
          if (!d) return;
          d.forEach(function (ruta) { if (docsC.has(ruta)) s.add(ruta); });
        });
        return s;
      }

      var A = lados[0], B = lados[1];
      var docsA = documentosDelLado(A[1]);
      var docsB = documentosDelLado(B[1]);
      if (!docsA.size || !docsB.size) continue;
      var comunes = interseccion(docsA, docsB);
      if (comunes.length) continue;   // el puente sí existe en algún texto

      lista.push({
        tipo: 'puente-ausente',
        id: c, lema: nodos[c].lema, forma: nodos[c].forma,
        frecuencia: nodos[c].frecuencia,
        intermediacion: entrada.intermediacion[c],
        comunidadA: A[0], comunidadB: B[0],
        vecinosA: A[1].slice(0, 5).map(function (u) { return nodos[u].forma; }),
        vecinosB: B[1].slice(0, 5).map(function (u) { return nodos[u].forma; }),
        documentosA: Array.from(docsA).slice(0, 3),
        documentosB: Array.from(docsB).slice(0, 3),
        puntuacion: entrada.intermediacion[c] * Math.min(A[1].length, B[1].length)
      });
    }

    lista.sort(function (a, b) { return b.puntuacion - a.puntuacion; });
    return {
      lista: lista.slice(0, opciones.maxPuentes || 15),
      parametros: {
        revisados: orden.length, minVecinosPorLado: minVecinos,
        minDocumentosPuente: minDocumentos, encontrados: lista.length
      }
    };
  }

  // ------------------------------------------------------------- ensamblaje ---
  function calcular(entrada, opciones) {
    opciones = opciones || {};
    var est = estructurales(entrada, opciones);
    var ais = aislados(entrada.capaDocumentos, opciones);
    var pue = puentesAusentes(entrada, opciones);

    // Documentos más cercanos a cada lado de cada brecha estructural.
    if (entrada.docsPorLema) {
      var miembros = new Map();
      for (var i = 0; i < entrada.nodos.length; i++) {
        var c = entrada.comunidad[i];
        if (!miembros.has(c)) miembros.set(c, []);
        miembros.get(c).push(i);
      }
      est.lista.forEach(function (b) {
        b.documentosA = documentosDeComunidad(miembros.get(b.comunidadA) || [], entrada.nodos, entrada.docsPorLema, 3);
        b.documentosB = documentosDeComunidad(miembros.get(b.comunidadB) || [], entrada.nodos, entrada.docsPorLema, 3);
      });
    }

    return {
      estructurales: est.lista,
      aislados: ais.lista,
      puentesAusentes: pue.lista,
      parametros: {
        estructurales: est.parametros,
        aislados: ais.parametros,
        puentesAusentes: pue.parametros
      },
      totales: {
        estructurales: est.lista.length,
        aislados: ais.parametros.totalAislados || ais.lista.length,
        puentesAusentes: pue.parametros.encontrados || pue.lista.length
      }
    };
  }

  return {
    calcular: calcular, estructurales: estructurales, aislados: aislados,
    puentesAusentes: puentesAusentes, documentosDeComunidad: documentosDeComunidad,
    percentil: percentil, distanciasDesde: distanciasDesde, adyacencia: adyacencia
  };
});
