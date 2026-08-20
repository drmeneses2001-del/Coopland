(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else ((raiz.GC = raiz.GC || {}).diff = api);
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Diferencia entre el inventario de la carpeta y el índice guardado.
  // Criterio en dos tiempos: primero (ruta, tamaño, fecha), que es gratis;
  // el hash sólo se calcula para los candidatos, ya dentro del worker.

  var TOLERANCIA_FECHA_MS = 1500; // iCloud reescribe fechas con ruido de ~1s

  function comparar(inventario, guardados) {
    var indice = new Map();
    guardados.forEach(function (d) { indice.set(d.ruta, d); });

    var sinCambios = [], candidatos = [], nuevos = [];

    inventario.forEach(function (f) {
      var previo = indice.get(f.ruta);
      if (!previo) { nuevos.push(f); candidatos.push({ archivo: f, previo: null, motivo: 'nuevo' }); return; }
      indice.delete(f.ruta);
      var mismoTamano = previo.tamano === f.tamano;
      var mismaFecha = Math.abs((previo.modificado || 0) - (f.modificado || 0)) <= TOLERANCIA_FECHA_MS;
      if (mismoTamano && mismaFecha) sinCambios.push(previo);
      else candidatos.push({ archivo: f, previo: previo, motivo: !mismoTamano ? 'tamaño' : 'fecha' });
    });

    var eliminados = Array.from(indice.values());
    return { nuevos: nuevos, candidatos: candidatos, sinCambios: sinCambios, eliminados: eliminados };
  }

  // Segundo tiempo: con el hash ya calculado, decide si hubo cambio real.
  function cambioReal(previo, hashNuevo) {
    if (!previo || !previo.hash) return true;
    return previo.hash !== hashNuevo;
  }

  // Resumen de lo que cambió, para el panel "Qué cambió".
  function resumir(antes, despues) {
    var mapaAntes = new Map(), mapaDespues = new Map();
    (antes || []).forEach(function (d) { mapaAntes.set(d.ruta, d); });
    (despues || []).forEach(function (d) { mapaDespues.set(d.ruta, d); });

    var nuevos = [], modificados = [], eliminados = [];
    mapaDespues.forEach(function (d, ruta) {
      var p = mapaAntes.get(ruta);
      if (!p) nuevos.push(d);
      else if (p.hash !== d.hash) modificados.push({ ruta: ruta, antes: p, despues: d });
    });
    mapaAntes.forEach(function (d, ruta) { if (!mapaDespues.has(ruta)) eliminados.push(d); });

    // Conceptos: primera aparición y desaparición completa del corpus.
    var lemasAntes = new Set(), lemasDespues = new Set();
    (antes || []).forEach(function (d) { (d.terminos || []).forEach(function (t) { lemasAntes.add(t.lema); }); });
    (despues || []).forEach(function (d) { (d.terminos || []).forEach(function (t) { lemasDespues.add(t.lema); }); });

    var conceptosNuevos = [], conceptosIdos = [];
    lemasDespues.forEach(function (l) { if (!lemasAntes.has(l)) conceptosNuevos.push(l); });
    lemasAntes.forEach(function (l) { if (!lemasDespues.has(l)) conceptosIdos.push(l); });

    return {
      nuevos: nuevos, modificados: modificados, eliminados: eliminados,
      conceptosNuevos: conceptosNuevos.sort(), conceptosIdos: conceptosIdos.sort(),
      totalAntes: mapaAntes.size, totalDespues: mapaDespues.size
    };
  }

  return { comparar: comparar, cambioReal: cambioReal, resumir: resumir, TOLERANCIA_FECHA_MS: TOLERANCIA_FECHA_MS };
});
