(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.grafo = raiz.GC.grafo || {}).documentos = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Capa de documentos. Dos clases de arista que NO se mezclan:
  //
  //   dependencia — alguien escribió el enlace. Es un hecho.
  //   afinidad    — dos textos comparten vocabulario. Es una estadística.
  //
  // Confundirlas es la diferencia entre un mapa y una nube de palabras: la
  // afinidad dice «esto se parece»; la dependencia dice «esto lo escribí yo
  // pensando en aquello». Se calculan por separado y se dibujan distinto.

  // ---------------------------------------------------------------- rutas ---
  function carpetaDe(ruta) {
    var i = ruta.lastIndexOf('/');
    return i === -1 ? '' : ruta.slice(0, i + 1);
  }
  function nombreDe(ruta) {
    var i = ruta.lastIndexOf('/');
    return i === -1 ? ruta : ruta.slice(i + 1);
  }
  function sinExtension(nombre) {
    return nombre.replace(/\.[A-Za-z0-9]{1,10}$/, '');
  }
  function normalizar(ruta) {
    var partes = ruta.replace(/\\/g, '/').split('/');
    var salida = [];
    for (var i = 0; i < partes.length; i++) {
      var p = partes[i];
      if (p === '' && i > 0) continue;
      if (p === '.') continue;
      if (p === '..') { salida.pop(); continue; }
      salida.push(p);
    }
    return salida.join('/');
  }

  // Índice de resolución: por ruta exacta y por nombre sin extensión, que es
  // como funcionan los wikilinks de Obsidian.
  function indiceDeRutas(rutas) {
    var porRuta = new Map(), porNombre = new Map();
    rutas.forEach(function (r, i) {
      porRuta.set(r, i);
      porRuta.set(r.toLowerCase(), i);
      var clave = sinExtension(nombreDe(r)).toLowerCase();
      if (!porNombre.has(clave)) porNombre.set(clave, []);
      porNombre.get(clave).push(i);
    });
    return { porRuta: porRuta, porNombre: porNombre };
  }

  function resolver(destino, desdeRuta, indice) {
    if (!destino) return { indice: -1, motivo: 'vacío' };
    var limpio = destino.replace(/^<|>$/g, '').split('#')[0].split('?')[0].trim();
    if (!limpio) return { indice: -1, motivo: 'vacío' };

    var candidatos = [];
    var relativo = normalizar(carpetaDe(desdeRuta) + limpio);
    candidatos.push(relativo, normalizar(limpio));
    if (!/\.[A-Za-z0-9]{1,10}$/.test(limpio)) {
      ['.md', '.txt', '.pdf', '.docx', '.html'].forEach(function (ext) {
        candidatos.push(relativo + ext, normalizar(limpio) + ext);
      });
    }
    for (var i = 0; i < candidatos.length; i++) {
      var c = candidatos[i];
      if (indice.porRuta.has(c)) return { indice: indice.porRuta.get(c), motivo: 'ruta' };
      if (indice.porRuta.has(c.toLowerCase())) return { indice: indice.porRuta.get(c.toLowerCase()), motivo: 'ruta' };
    }

    // Wikilink por nombre. Si hay varios con el mismo nombre, gana el de la
    // misma carpeta; si sigue habiendo empate, se declara ambiguo en vez de
    // elegir uno al azar y dibujar una dependencia que quizá no existe.
    var porNombre = indice.porNombre.get(sinExtension(nombreDe(limpio)).toLowerCase());
    if (porNombre && porNombre.length === 1) return { indice: porNombre[0], motivo: 'nombre' };
    if (porNombre && porNombre.length > 1) return { indice: -1, motivo: 'ambiguo', opciones: porNombre.length };
    return { indice: -1, motivo: 'sin destino' };
  }

  // ------------------------------------------------------------ versiones ---
  // Secuencias de versión detectadas por nombre: borrador v1 / v2 / final,
  // «copia», «(1)», y sellos de fecha al final del nombre.
  var MARCAS_VERSION = [
    { re: /[ _-]*\bv(?:er|ers|ersion)?[ _-]?(\d{1,3})\b/i, orden: function (m) { return parseInt(m[1], 10); } },
    { re: /[ _-]*\brev(?:isi[oó]n)?[ _-]?(\d{1,3})\b/i, orden: function (m) { return parseInt(m[1], 10); } },
    { re: /[ _-]*\((\d{1,3})\)\s*$/, orden: function (m) { return parseInt(m[1], 10); } },
    { re: /[ _-]*\b(\d{4})[-_.](\d{2})[-_.](\d{2})\b/, orden: function (m) { return parseInt(m[1] + m[2] + m[3], 10); } },
    { re: /[ _-]*\b(copia|copy|borrador|draft)\b/i, orden: function () { return 0; } },
    { re: /[ _-]*\b(final|definitiv[oa])\b/i, orden: function () { return 9999; } }
  ];

  function analizarVersion(ruta) {
    var base = sinExtension(nombreDe(ruta));
    var orden = null, encontrado = false;
    var raizNombre = base;
    for (var i = 0; i < MARCAS_VERSION.length; i++) {
      var m = MARCAS_VERSION[i].re.exec(raizNombre);
      if (!m) continue;
      encontrado = true;
      var valor = MARCAS_VERSION[i].orden(m);
      if (orden === null || valor > orden) orden = valor;
      raizNombre = raizNombre.replace(MARCAS_VERSION[i].re, ' ');
    }
    if (!encontrado) return null;
    var clave = carpetaDe(ruta) + raizNombre.replace(/[ _-]+/g, ' ').trim().toLowerCase();
    return { clave: clave, orden: orden == null ? 1 : orden };
  }

  function secuenciasDeVersion(rutas) {
    var grupos = new Map();
    rutas.forEach(function (r, i) {
      var v = analizarVersion(r);
      if (!v) return;
      if (!grupos.has(v.clave)) grupos.set(v.clave, []);
      grupos.get(v.clave).push({ indice: i, orden: v.orden, ruta: r });
    });
    var aristas = [];
    grupos.forEach(function (lista, clave) {
      if (lista.length < 2) return;
      lista.sort(function (a, b) { return a.orden - b.orden || a.ruta.localeCompare(b.ruta); });
      for (var i = 1; i < lista.length; i++) {
        aristas.push({
          a: lista[i - 1].indice, b: lista[i].indice, tipo: 'version',
          peso: 1, detalle: 'secuencia de versión: ' + clave
        });
      }
    });
    return aristas;
  }

  // ---------------------------------------------------------- referencias ---
  var RE_DOI = /\b10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+/g;
  // (Apellido, 2019) · Apellido et al., 2019 · Apellido y Otro (2020)
  var RE_CITA = /\b([A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,}(?:\s+(?:et\s+al\.?|y\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,}))?)[,\s]+\(?((?:19|20)\d{2})\)?/g;

  function clavesBibliograficas(texto) {
    var claves = new Set();
    if (!texto) return claves;
    var m;
    RE_DOI.lastIndex = 0;
    while ((m = RE_DOI.exec(texto)) !== null) claves.add('doi:' + m[0].toLowerCase().replace(/[.,;)]+$/, ''));
    RE_CITA.lastIndex = 0;
    while ((m = RE_CITA.exec(texto)) !== null) {
      var autor = m[1].toLowerCase().replace(/\s+et\s+al\.?/, '').replace(/\s+y\s+.*/, '').trim();
      claves.add('cita:' + autor + ':' + m[2]);
    }
    return claves;
  }

  function aristasPorReferencia(clavesPorDoc, minimoCompartido) {
    minimoCompartido = minimoCompartido || 2;
    var porClave = new Map();
    clavesPorDoc.forEach(function (claves, i) {
      claves.forEach(function (c) {
        if (!porClave.has(c)) porClave.set(c, []);
        porClave.get(c).push(i);
      });
    });

    var compartidas = new Map();
    porClave.forEach(function (docs, clave) {
      if (docs.length < 2 || docs.length > 40) return;   // una cita en 40 documentos no distingue nada
      for (var i = 0; i < docs.length; i++) {
        for (var j = i + 1; j < docs.length; j++) {
          var k = docs[i] + ':' + docs[j];
          if (!compartidas.has(k)) compartidas.set(k, []);
          compartidas.get(k).push(clave);
        }
      }
    });

    var aristas = [];
    compartidas.forEach(function (claves, k) {
      if (claves.length < minimoCompartido) return;
      var partes = k.split(':');
      aristas.push({
        a: +partes[0], b: +partes[1], tipo: 'referencia', peso: claves.length,
        detalle: claves.length + ' referencias compartidas: ' + claves.slice(0, 3).join(', ')
      });
    });
    return aristas;
  }

  // ------------------------------------------------------------- afinidad ---
  // Coseno TF-IDF por índice invertido. Los términos que están en más de la
  // mitad del corpus se descartan: su idf es casi cero y sólo aportan coste.
  function afinidad(docs, opciones) {
    opciones = opciones || {};
    var suelo = opciones.suelo != null ? opciones.suelo : 0.12;
    var maxPares = opciones.maxPares || 40000;
    var N = docs.length;
    if (N < 2) return { pares: [], suelo: suelo, terminosIgnorados: 0 };

    var df = new Map();
    docs.forEach(function (d) {
      var vistos = new Set();
      (d.terminos || []).forEach(function (t) { vistos.add(t.lema); });
      vistos.forEach(function (l) { df.set(l, (df.get(l) || 0) + 1); });
    });

    var limiteDf = Math.max(2, Math.floor(N * 0.5));
    var ignorados = 0;
    var vectores = docs.map(function (d) {
      var v = new Map(), norma = 0;
      (d.terminos || []).forEach(function (t) {
        var frecuenciaDoc = df.get(t.lema) || 1;
        if (frecuenciaDoc > limiteDf) return;
        var idf = Math.log(N / frecuenciaDoc);
        if (idf <= 0) return;
        var peso = (1 + Math.log(t.n)) * idf;
        v.set(t.lema, peso);
        norma += peso * peso;
      });
      norma = Math.sqrt(norma) || 1;
      v.forEach(function (p, l) { v.set(l, p / norma); });
      return v;
    });
    df.forEach(function (c) { if (c > limiteDf) ignorados++; });

    var invertido = new Map();
    vectores.forEach(function (v, i) {
      v.forEach(function (p, l) {
        if (!invertido.has(l)) invertido.set(l, []);
        invertido.get(l).push([i, p]);
      });
    });

    var acumulado = new Map();
    invertido.forEach(function (lista) {
      if (lista.length < 2) return;
      for (var i = 0; i < lista.length; i++) {
        for (var j = i + 1; j < lista.length; j++) {
          var a = lista[i][0], b = lista[j][0];
          var k = a < b ? a + ':' + b : b + ':' + a;
          acumulado.set(k, (acumulado.get(k) || 0) + lista[i][1] * lista[j][1]);
        }
      }
    });

    var pares = [];
    acumulado.forEach(function (coseno, k) {
      if (coseno < suelo) return;
      var partes = k.split(':');
      pares.push({ a: +partes[0], b: +partes[1], tipo: 'afinidad', coseno: Math.round(coseno * 1000) / 1000 });
    });
    pares.sort(function (x, y) { return y.coseno - x.coseno; });
    var recortados = 0;
    if (pares.length > maxPares) { recortados = pares.length - maxPares; pares = pares.slice(0, maxPares); }

    return { pares: pares, suelo: suelo, terminosIgnorados: ignorados, recortados: recortados };
  }

  // ------------------------------------------------------------ ensamblaje ---
  function construir(docs, opciones) {
    opciones = opciones || {};
    var rutas = docs.map(function (d) { return d.ruta; });
    var indice = indiceDeRutas(rutas);

    var dependencias = [];
    var sinResolver = [];
    var clavesPorDoc = [];

    docs.forEach(function (d, i) {
      var enlaces = (d.meta && d.meta.enlaces) || [];
      enlaces.forEach(function (e) {
        var r = resolver(e.destino, d.ruta, indice);
        if (r.indice < 0) {
          sinResolver.push({ desde: d.ruta, destino: e.destino, tipo: e.tipo, motivo: r.motivo });
          return;
        }
        if (r.indice === i) return;
        dependencias.push({
          a: i, b: r.indice, tipo: 'enlace', peso: 1,
          detalle: e.tipo + ': ' + e.destino, resolucion: r.motivo
        });
      });
      // El texto completo puede no estar en memoria: el worker extrae las claves
      // durante su recorrido y las entrega ya calculadas.
      clavesPorDoc.push(d.clavesBib ? new Set(d.clavesBib) : clavesBibliograficas(d.texto || ''));
    });

    // Los enlaces repetidos entre el mismo par se suman en una sola arista.
    var fusionadas = new Map();
    dependencias.concat(secuenciasDeVersion(rutas)).concat(
      aristasPorReferencia(clavesPorDoc, opciones.minimoReferencias || 2)
    ).forEach(function (e) {
      var menor = Math.min(e.a, e.b), mayor = Math.max(e.a, e.b);
      var k = menor + ':' + mayor + ':' + e.tipo;
      var previa = fusionadas.get(k);
      if (previa) { previa.peso += e.peso; previa.veces++; return; }
      fusionadas.set(k, { a: menor, b: mayor, tipo: e.tipo, peso: e.peso, veces: 1, detalle: e.detalle, resolucion: e.resolucion });
    });

    var af = afinidad(docs, opciones);

    var nodos = docs.map(function (d, i) {
      return {
        id: i, ruta: d.ruta, nombre: d.nombre, ext: d.ext, estado: d.estado,
        palabras: d.palabras || 0, terminos: (d.terminos || []).length,
        idioma: d.idioma, modificado: d.modificado, tamano: d.tamano
      };
    });

    return {
      nodos: nodos,
      dependencias: Array.from(fusionadas.values()),
      afinidades: af.pares,
      sinResolver: sinResolver.slice(0, 200),
      totales: {
        documentos: nodos.length,
        dependencias: fusionadas.size,
        afinidades: af.pares.length,
        enlacesSinResolver: sinResolver.length,
        afinidadesRecortadas: af.recortados,
        terminosDemasiadoComunes: af.terminosIgnorados,
        sueloAfinidad: af.suelo
      }
    };
  }

  return {
    construir: construir, afinidad: afinidad, resolver: resolver,
    indiceDeRutas: indiceDeRutas, secuenciasDeVersion: secuenciasDeVersion,
    analizarVersion: analizarVersion, clavesBibliograficas: clavesBibliograficas,
    aristasPorReferencia: aristasPorReferencia, normalizar: normalizar
  };
});
