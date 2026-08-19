/* Worker del grafo. Lee los documentos del índice, arma las tres capas, calcula
   las métricas y lo guarda todo. El hilo de la interfaz no toca nada de esto:
   sólo recibe avisos de progreso y, al final, el resumen para los paneles.
   Los arreglos completos de nodos y aristas se quedan en IndexedDB, listos para
   el lienzo de la Fase 5, en vez de cruzar el puente de mensajes. */
'use strict';

self.GC = self.GC || {};

importScripts(
  '../nucleo/vacias.js',
  '../nucleo/terminos.js',
  '../nucleo/almacen.js',
  '../grafo/coocurrencia.js',
  '../grafo/louvain.js',
  '../grafo/metricas.js',
  '../grafo/documentos.js',
  '../grafo/mixta.js',
  '../grafo/brechas.js',
  '../grafo/preguntas.js'
);

var GC = self.GC;
var CLAVE_CAPAS = 'capas';

function responder(m) { self.postMessage(m); }
function progreso(id, fase, hechos, total) {
  responder({ t: 'progreso', id: id, fase: fase, hechos: hechos, total: total });
}

async function construir(id, opciones) {
  opciones = opciones || {};
  var t0 = (typeof performance !== 'undefined' ? performance.now() : Date.now());

  // El worker abre su propia conexión a IndexedDB; si el corredor de pruebas
  // está usando su base aparte, hay que seguirle ahí.
  if (opciones.baseDeDatos) GC.almacen.usarBaseDeDatos(opciones.baseDeDatos);

  var vaciasSet = GC.vacias.conjuntoBase();
  (opciones.vaciasPropias || []).forEach(function (p) { vaciasSet.add(GC.terminos.clave(p)); });

  var acumulador = GC.grafo.coocurrencia.crear({
    ventana: opciones.ventana || 4,
    muestrasPorArista: opciones.muestrasPorArista || 3
  });

  // --- recorrido del índice ------------------------------------------------
  // De cada documento se toma lo que hace falta y se suelta el texto: si se
  // retuviera, un corpus mediano llenaría la memoria del iPad.
  var docsLigeros = [];
  var total = await GC.almacen.contar('documentos');
  var leidos = 0, conTexto = 0, sinTexto = 0;

  await GC.almacen.recorrer('documentos', function (d) {
    leidos++;
    if (leidos % 25 === 0) progreso(id, 'leyendo documentos', leidos, total);

    if (d.texto && d.texto.trim()) {
      var tk = GC.terminos.tokenizar(d.texto, { vacias: vaciasSet, idioma: d.idioma });
      acumulador.agregar(d.ruta, tk.tokens);
      conTexto++;
    } else {
      acumulador.agregarRuta(d.ruta, d.terminosRuta || []);
      sinTexto++;
    }

    docsLigeros.push({
      ruta: d.ruta, nombre: d.nombre, ext: d.ext, estado: d.estado,
      palabras: d.palabras || 0, idioma: d.idioma, modificado: d.modificado, tamano: d.tamano,
      terminos: d.terminos || [], terminosRuta: d.terminosRuta || [],
      meta: d.meta && d.meta.enlaces ? { enlaces: d.meta.enlaces } : { enlaces: [] },
      clavesBib: Array.from(GC.grafo.documentos.clavesBibliograficas(d.texto || ''))
    });
  });

  if (!leidos) {
    responder({ t: 'grafo-vacio', id: id, motivo: 'No hay documentos en el índice.' });
    return;
  }

  // --- capa de conceptos ---------------------------------------------------
  progreso(id, 'construyendo la capa de conceptos', 0, 1);
  var conceptos = acumulador.construir({
    maxNodos: opciones.maxNodos != null ? opciones.maxNodos : 3000,
    minFrecuencia: opciones.minFrecuencia != null ? opciones.minFrecuencia : 2,
    minPeso: opciones.minPeso != null ? opciones.minPeso : 1,
    minDocs: opciones.minDocs != null ? opciones.minDocs : 1
  });

  var n = conceptos.nodos.length;
  progreso(id, 'comunidades (Louvain)', 0, 1);
  var comunidades = GC.grafo.louvain.detectar(n, conceptos.aristas, { resolucion: opciones.resolucion || 1 });

  progreso(id, 'intermediación (Brandes)', 0, 1);
  var inter = GC.grafo.metricas.intermediacion(n, conceptos.aristas, {
    umbralExacto: opciones.umbralExacto, pivotes: opciones.pivotes
  });

  var gr = GC.grafo.metricas.grados(n, conceptos.aristas);
  var comps = GC.grafo.metricas.componentes(n, conceptos.aristas);
  var diversidad = GC.grafo.louvain.diversidad(comunidades.modularidad);
  var resumenComunidades = GC.grafo.metricas.resumirComunidades(conceptos.nodos, comunidades.comunidad, inter.normal, 8);
  var influyentes = GC.grafo.metricas.masInfluyentes(conceptos.nodos, inter.normal, gr.grado, 25);
  var conectores = GC.grafo.metricas.puntosConectores(conceptos.nodos, inter.normal, 20);

  // --- capa de documentos --------------------------------------------------
  progreso(id, 'capa de documentos', 0, 1);
  var capaDocs = GC.grafo.documentos.construir(docsLigeros, {
    suelo: opciones.sueloAfinidad != null ? opciones.sueloAfinidad : 0.12,
    minimoReferencias: opciones.minimoReferencias || 2
  });

  // --- capa mixta ----------------------------------------------------------
  progreso(id, 'capa mixta', 0, 1);
  var capaMixta = GC.grafo.mixta.construir(conceptos, capaDocs, docsLigeros, {
    terminosPorDocumento: opciones.terminosPorDocumento || 12
  });

  // --- brechas -------------------------------------------------------------
  progreso(id, 'buscando brechas', 0, 1);
  var brechas = GC.grafo.brechas.calcular({
    nodos: conceptos.nodos,
    aristas: conceptos.aristas,
    comunidad: comunidades.comunidad,
    intermediacion: inter.normal,
    docsPorLema: acumulador.indiceDocumentos(),
    capaDocumentos: capaDocs
  }, {
    percentilDensidad: opciones.percentilDensidad,
    minTamanoComunidad: opciones.minTamanoComunidad,
    maxBrechas: opciones.maxBrechas
  });
  GC.grafo.preguntas.poblar(brechas);

  // --- persistencia --------------------------------------------------------
  progreso(id, 'guardando', 0, 1);
  var registro = {
    id: CLAVE_CAPAS,
    fecha: Date.now(),
    version: 3,
    conceptos: {
      nodos: conceptos.nodos,
      aristas: conceptos.aristas,
      comunidad: Array.from(comunidades.comunidad),
      intermediacion: Array.from(inter.normal),
      grado: Array.from(gr.grado),
      fuerza: Array.from(gr.fuerza),
      totales: conceptos.totales,
      corte: conceptos.corte
    },
    documentos: capaDocs,
    mixta: capaMixta,
    brechas: brechas
  };
  await GC.almacen.guardarLote('grafo', [registro]);

  var ms = (typeof performance !== 'undefined' ? performance.now() : Date.now()) - t0;

  var resumen = {
    fecha: registro.fecha,
    duracionMs: Math.round(ms),
    lectura: { documentos: leidos, conTexto: conTexto, sinTexto: sinTexto },
    conceptos: {
      nodos: n,
      aristas: conceptos.aristas.length,
      totales: conceptos.totales,
      corte: conceptos.corte,
      comunidades: comunidades.comunidades,
      modularidad: comunidades.modularidad,
      diversidad: diversidad,
      componentes: { cuantas: comps.cuantas, mayor: comps.mayor },
      intermediacion: { exacta: inter.exacta, fuentes: inter.fuentes }
    },
    comunidades: resumenComunidades,
    influyentes: influyentes,
    conectores: conectores,
    documentos: {
      totales: capaDocs.totales,
      dependencias: capaDocs.dependencias.slice(0, 60).map(function (e) {
        return {
          desde: capaDocs.nodos[e.a].ruta, hasta: capaDocs.nodos[e.b].ruta,
          tipo: e.tipo, peso: e.peso, detalle: e.detalle
        };
      }),
      afinidades: capaDocs.afinidades.slice(0, 60).map(function (e) {
        return { desde: capaDocs.nodos[e.a].ruta, hasta: capaDocs.nodos[e.b].ruta, coseno: e.coseno };
      }),
      sinResolver: capaDocs.sinResolver.slice(0, 40),
      aislados: aislar(capaDocs)   // conteo rápido para la capa de documentos
    },
    mixta: capaMixta.totales,
    brechas: brechas
  };

  responder({ t: 'grafo-listo', id: id, resumen: resumen, instantanea: serializarParaInstantanea(conceptos, comunidades, inter, capaDocs) });
}

// Documentos ricos en contenido y pobres en enlaces: la firma estructural del
// texto que se escribió y nunca se volvió a conectar con nada. Es el material
// de la Fase 4; aquí se deja ya calculado el conteo, que sale gratis.
function aislar(capaDocs) {
  var conDependencia = new Set();
  capaDocs.dependencias.forEach(function (e) { conDependencia.add(e.a); conDependencia.add(e.b); });

  // «Rico en contenido» es relativo al corpus, no un número fijo: un umbral de
  // palabras absoluto declara aislado a medio archivo de notas breves y a
  // ninguno de un archivo de artículos. La mediana de términos propios del
  // propio corpus es la única referencia honesta.
  var leidos = capaDocs.nodos.filter(function (n) { return n.estado === 'ok'; });
  if (!leidos.length) return { cuantos: 0, muestra: [], umbral: 0, criterio: 'sin documentos legibles' };
  var ordenados = leidos.map(function (n) { return n.terminos; }).sort(function (a, b) { return a - b; });
  var mediana = ordenados[Math.floor(ordenados.length / 2)];

  var candidatos = leidos.filter(function (n) {
    return n.terminos >= mediana && !conDependencia.has(n.id);
  });
  candidatos.sort(function (a, b) { return b.terminos - a.terminos || b.palabras - a.palabras; });
  return {
    cuantos: candidatos.length,
    umbral: mediana,
    criterio: 'al menos ' + mediana + ' términos propios (la mediana del corpus) y ninguna dependencia explícita',
    muestra: candidatos.slice(0, 20).map(function (n) {
      return { ruta: n.ruta, palabras: n.palabras, terminos: n.terminos };
    })
  };
}

// Serialización compacta para el deslizador temporal: lo justo para reanimar
// el estado del grafo en una fecha pasada sin guardar el grafo entero 60 veces.
function serializarParaInstantanea(conceptos, comunidades, inter, capaDocs) {
  var orden = conceptos.nodos.map(function (nodo, i) { return [i, inter.normal[i], nodo.frecuencia]; });
  orden.sort(function (a, b) { return b[1] - a[1] || b[2] - a[2]; });
  var cuantos = Math.min(500, orden.length);
  var elegidos = orden.slice(0, cuantos).map(function (o) { return o[0]; });
  var enInstantanea = new Map();
  elegidos.forEach(function (idx, nuevo) { enInstantanea.set(idx, nuevo); });

  return {
    nodos: elegidos.map(function (idx) {
      return {
        lema: conceptos.nodos[idx].lema,
        forma: conceptos.nodos[idx].forma,
        frecuencia: conceptos.nodos[idx].frecuencia,
        comunidad: comunidades.comunidad[idx],
        intermediacion: Math.round(inter.normal[idx] * 1e6) / 1e6
      };
    }),
    aristas: conceptos.aristas.filter(function (e) {
      return enInstantanea.has(e.a) && enInstantanea.has(e.b);
    }).slice(0, 2500).map(function (e) {
      return [enInstantanea.get(e.a), enInstantanea.get(e.b), e.peso];
    }),
    modularidad: comunidades.modularidad,
    comunidades: comunidades.comunidades,
    contadores: {
      conceptos: conceptos.nodos.length,
      aristasConceptos: conceptos.aristas.length,
      documentos: capaDocs.nodos.length,
      dependencias: capaDocs.dependencias.length,
      afinidades: capaDocs.afinidades.length
    }
  };
}

self.onmessage = async function (ev) {
  var m = ev.data;
  try {
    if (m.t === 'construir') { await construir(m.id, m.opciones); return; }
    if (m.t === 'ping') { responder({ t: 'pong', id: m.id, listo: true }); return; }
    responder({ t: 'error', id: m.id, error: 'Mensaje desconocido: ' + m.t });
  } catch (e) {
    responder({ t: 'error', id: m.id, error: String(e && e.message || e), pila: String(e && e.stack || '') });
  }
};
