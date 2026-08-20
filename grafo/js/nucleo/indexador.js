(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else ((raiz.GC = raiz.GC || {}).indexador = api);
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  var GC = raiz.GC || {};

  // Orquestador de la indexación incremental.
  //
  // Secuencia: diff barato por (ruta, tamaño, fecha) -> despacho a los workers
  // sólo de los candidatos -> segundo filtro por hash dentro del worker ->
  // escritura por lotes -> índice ligero actualizado -> instantánea.

  var LOTE_ESCRITURA = 40;

  async function indexar(opciones) {
    var inventario = opciones.inventario;
    var pool = opciones.pool;
    var indicePrevio = opciones.indicePrevio || GC.indice.vacio();
    var alProgresar = opciones.alProgresar || function () {};
    var zipId = opciones.zipId || null;
    var origen = opciones.origen || null;
    var t0 = (typeof performance !== 'undefined' ? performance.now() : Date.now());

    var comparacion = GC.diff.comparar(inventario, indicePrevio.docs || []);
    alProgresar({ fase: 'diff', total: inventario.length, candidatos: comparacion.candidatos.length, eliminados: comparacion.eliminados.length });

    var docsNuevos = [];       // registros completos a guardar
    var actualizados = [];     // {doc, lemasPrevios}
    var tocados = [];          // mismo hash, metadatos distintos
    var errores = [];
    var hechos = 0;
    var total = comparacion.candidatos.length;
    var enCurso = new Map();

    function informar() {
      alProgresar({
        fase: 'analizando', hechos: hechos, total: total,
        enCurso: Array.from(enCurso.values())
      });
    }

    async function procesar(candidato) {
      var f = candidato.archivo;
      var base = {
        ruta: f.ruta, nombre: f.nombre, tamano: f.tamano, modificado: f.modificado,
        noDescargado: !!f.noDescargado, rutaZip: f.rutaZip || null
      };
      var mensaje;
      if (zipId != null && f.origen === 'C-zip') {
        mensaje = { t: 'zip-analizar', zipId: zipId, base: base, previo: candidato.previo ? { hash: candidato.previo.hash } : null };
      } else {
        if (f.handle && !f.archivo) {
          try { f.archivo = await f.handle.getFile(); }
          catch (e) { errores.push({ ruta: f.ruta, error: 'No se pudo abrir desde la carpeta: ' + e.message }); hechos++; informar(); return; }
        }
        base.archivo = f.archivo;
        mensaje = { t: 'analizar', base: base, previo: candidato.previo ? { hash: candidato.previo.hash } : null };
      }

      var enviar = (zipId != null && f.origen === 'C-zip') ? pool.enviarAlZip : pool.encolar;
      var respuesta = await enviar.call(pool, mensaje, function (p) {
        enCurso.set(p.id, { ruta: p.ruta, fase: p.fase, pct: p.pct });
        informar();
      });

      enCurso.delete(respuesta.id);
      hechos++;

      if (respuesta.error) {
        errores.push({ ruta: f.ruta, error: respuesta.error });
      } else if (respuesta.saltado) {
        tocados.push({ ruta: respuesta.ruta, modificado: respuesta.modificado, tamano: respuesta.tamano });
      } else if (respuesta.doc) {
        var previoCompleto = candidato.previo ? await GC.almacen.leer('documentos', f.ruta) : null;
        actualizados.push({
          doc: respuesta.doc,
          lemasPrevios: previoCompleto ? GC.indice.lemasDe(previoCompleto) : null
        });
        docsNuevos.push(respuesta.doc);
        if (respuesta.doc.estado === 'error') errores.push({ ruta: f.ruta, error: respuesta.doc.error });
        if (docsNuevos.length >= LOTE_ESCRITURA) {
          var lote = docsNuevos.splice(0, docsNuevos.length);
          await GC.almacen.guardarLote('documentos', lote);
        }
      }
      informar();
    }

    // Concurrencia limitada: el pool ya serializa, pero limitar aquí evita
    // materializar cientos de File a la vez en memoria del iPad.
    var enParalelo = Math.max(2, pool.n);
    var cursor = 0;
    async function corredor() {
      while (cursor < comparacion.candidatos.length) {
        var i = cursor++;
        await procesar(comparacion.candidatos[i]);
      }
    }
    await Promise.all(new Array(enParalelo).fill(0).map(corredor));

    if (docsNuevos.length) await GC.almacen.guardarLote('documentos', docsNuevos);

    // Bajas: primero se leen sus lemas, luego se borran.
    var eliminados = [];
    for (var e = 0; e < comparacion.eliminados.length; e++) {
      var ruta = comparacion.eliminados[e].ruta;
      var completo = await GC.almacen.leer('documentos', ruta);
      eliminados.push({ ruta: ruta, lemas: completo ? GC.indice.lemasDe(completo) : null, doc: comparacion.eliminados[e] });
    }
    if (eliminados.length) await GC.almacen.borrarLote('documentos', eliminados.map(function (x) { return x.ruta; }));

    // Los metadatos que cambiaron sin cambiar el contenido se persisten también.
    if (tocados.length) {
      var registros = [];
      for (var t = 0; t < tocados.length; t++) {
        var d = await GC.almacen.leer('documentos', tocados[t].ruta);
        if (d) { d.modificado = tocados[t].modificado; d.tamano = tocados[t].tamano; registros.push(d); }
      }
      if (registros.length) await GC.almacen.guardarLote('documentos', registros);
    }

    var indiceNuevo = GC.indice.aplicar(indicePrevio, {
      eliminados: eliminados, actualizados: actualizados, tocados: tocados, origen: origen
    });
    await GC.almacen.guardarLote('grafo', [indiceNuevo]);

    var ms = (typeof performance !== 'undefined' ? performance.now() : Date.now()) - t0;

    return {
      indice: indiceNuevo,
      cambios: resumirCambios(indicePrevio, indiceNuevo, { eliminados: eliminados, actualizados: actualizados, tocados: tocados }),
      errores: errores,
      duracionMs: Math.round(ms),
      analizados: actualizados.length,
      sinCambios: comparacion.sinCambios.length + tocados.length
    };
  }

  // Panel "Qué cambió". Lo que la Fase 2 puede afirmar con certeza son las
  // altas, bajas, modificaciones y el vocabulario. Las fusiones de clúster y
  // las brechas cerradas requieren el grafo: se declaran pendientes de fase,
  // no se rellenan con conjeturas.
  function resumirCambios(antes, despues, detalle) {
    var vocabAntes = GC.indice.mapaVocabulario(antes);
    var vocabDespues = GC.indice.mapaVocabulario(despues);

    var conceptosNuevos = [], conceptosIdos = [], conceptosCrecidos = [];
    vocabDespues.forEach(function (n, lema) {
      if (!vocabAntes.has(lema)) conceptosNuevos.push({ lema: lema, docs: n });
      else if (n - vocabAntes.get(lema) >= 2) conceptosCrecidos.push({ lema: lema, antes: vocabAntes.get(lema), despues: n });
    });
    vocabAntes.forEach(function (n, lema) { if (!vocabDespues.has(lema)) conceptosIdos.push({ lema: lema, docs: n }); });

    conceptosNuevos.sort(function (a, b) { return b.docs - a.docs || a.lema.localeCompare(b.lema); });
    conceptosCrecidos.sort(function (a, b) { return (b.despues - b.antes) - (a.despues - a.antes); });

    var mapaAntes = new Map();
    (antes.docs || []).forEach(function (d) { mapaAntes.set(d.ruta, d); });

    var nuevos = [], modificados = [];
    (detalle.actualizados || []).forEach(function (u) {
      var previo = mapaAntes.get(u.doc.ruta);
      if (!previo) nuevos.push({ ruta: u.doc.ruta, estado: u.doc.estado, palabras: u.doc.palabras, ext: u.doc.ext });
      else modificados.push({
        ruta: u.doc.ruta, estado: u.doc.estado,
        palabrasAntes: previo.palabras || 0, palabrasDespues: u.doc.palabras || 0,
        delta: (u.doc.palabras || 0) - (previo.palabras || 0)
      });
    });

    return {
      primeraVez: (antes.docs || []).length === 0,
      nuevos: nuevos,
      modificados: modificados,
      eliminados: (detalle.eliminados || []).map(function (e) { return { ruta: e.ruta }; }),
      sinCambios: (despues.docs || []).length - nuevos.length - modificados.length,
      conceptosNuevos: conceptosNuevos,
      conceptosIdos: conceptosIdos,
      conceptosCrecidos: conceptosCrecidos,
      pendientesDeFase: [
        'Clústeres fusionados o partidos — requiere la capa de conceptos (Fase 3).',
        'Brechas cerradas — requiere el cálculo de brechas (Fase 4).'
      ]
    };
  }

  // Instantánea de la apertura: alimenta el deslizador temporal de la Fase 5.
  // En Fase 2 guarda el estado del índice; cuando exista el grafo, se añade.
  async function guardarInstantanea(indice, extra) {
    var est = GC.indice.estadisticas(indice);
    var top = (indice.vocabulario || [])
      .slice()
      .sort(function (a, b) { return b[1] - a[1]; })
      .slice(0, 300);
    var instantanea = {
      fecha: Date.now(),
      version: 'fase2',
      origen: indice.origen || null,
      documentos: est.documentos,
      conceptos: est.conceptos,
      palabras: est.palabras,
      porEstado: est.porEstado,
      vocabularioTop: top,
      hashes: (indice.docs || []).map(function (d) { return [d.ruta, d.hash]; }),
      grafo: null   // lo rellenará la Fase 3
    };
    if (extra) Object.assign(instantanea, extra);
    var id = await GC.almacen.guardarInstantanea(instantanea);
    await GC.almacen.podarInstantaneas(60);
    return id;
  }

  return { indexar: indexar, resumirCambios: resumirCambios, guardarInstantanea: guardarInstantanea, LOTE_ESCRITURA: LOTE_ESCRITURA };
});
