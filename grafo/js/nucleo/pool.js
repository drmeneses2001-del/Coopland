(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else ((raiz.GC = raiz.GC || {}).pool = api);
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Reparto de trabajo entre varios workers de extracción. El hilo principal
  // sólo despacha y recoge; nunca lee ni analiza.
  //
  // Todo mensaje lleva un `id` que el worker devuelve intacto. Las respuestas
  // parciales ('progreso') no cierran la petición; el resto sí.

  var PARCIALES = { progreso: true };

  function crear(opciones) {
    opciones = opciones || {};
    var ruta = opciones.ruta || 'js/trabajadores/extractor.js';
    var n = Math.max(1, Math.min(opciones.n || 3, 6));
    var trabajadores = [];
    var pendientes = new Map();   // id -> {resolver, alProgresar, encolado}
    var libres = [];              // índices de workers disponibles para la cola
    var cola = [];
    var siguienteId = 1;

    function resolverPendiente(id, mensaje) {
      var e = pendientes.get(id);
      if (!e) return;
      pendientes.delete(id);
      if (e.encolado) { libres.push(e.worker); vaciarCola(); }
      e.resolver(mensaje);
    }

    function alMensaje(ev) {
      var m = ev.data;
      if (!m || m.id == null) return;
      if (PARCIALES[m.t]) {
        var e = pendientes.get(m.id);
        if (e && e.alProgresar) e.alProgresar(m);
        return;
      }
      resolverPendiente(m.id, m);
    }

    for (var i = 0; i < n; i++) {
      var w = new Worker(ruta);
      w.onmessage = alMensaje;
      w.onerror = (function (indice) {
        return function (err) {
          // Un worker caído no puede tragarse la cola en silencio: se resuelven
          // sus pendientes como error para que el panel de errores los muestre.
          var mensaje = 'Worker caído: ' + (err && (err.message || err.filename) || 'error desconocido');
          Array.from(pendientes.keys()).forEach(function (id) {
            var e = pendientes.get(id);
            if (e.worker === indice) resolverPendiente(id, { t: 'resultado', id: id, error: mensaje });
          });
        };
      })(i);
      trabajadores.push(w);
      libres.push(i);
    }

    function vaciarCola() {
      while (cola.length && libres.length) {
        var tarea = cola.shift();
        var idx = libres.shift();
        var e = pendientes.get(tarea.id);
        if (!e) { libres.push(idx); continue; }
        e.worker = idx;
        trabajadores[idx].postMessage(tarea.mensaje, tarea.transferibles);
      }
    }

    // Encola una tarea; se enviará al primer worker que quede libre.
    function encolar(mensaje, alProgresar, transferibles) {
      var id = siguienteId++;
      mensaje.id = id;
      return new Promise(function (resolver) {
        pendientes.set(id, { resolver: resolver, alProgresar: alProgresar, encolado: true, worker: null });
        cola.push({ id: id, mensaje: mensaje, transferibles: transferibles || [] });
        vaciarCola();
      });
    }

    // Envía a un worker concreto sin pasar por la cola (no ocupa turno).
    function enviarA(indice, mensaje, alProgresar, transferibles) {
      var id = siguienteId++;
      mensaje.id = id;
      return new Promise(function (resolver) {
        pendientes.set(id, { resolver: resolver, alProgresar: alProgresar, encolado: false, worker: indice });
        trabajadores[indice].postMessage(mensaje, transferibles || []);
      });
    }

    // El ZIP descomprimido vive en un solo worker: sus bytes no se copian.
    var INDICE_ZIP = 0;
    function enviarAlZip(mensaje, alProgresar, transferibles) {
      return enviarA(INDICE_ZIP, mensaje, alProgresar, transferibles);
    }

    function difundir(mensaje) {
      return Promise.all(trabajadores.map(function (_, idx) {
        return enviarA(idx, Object.assign({}, mensaje));
      }));
    }

    function terminar() {
      trabajadores.forEach(function (w) { w.terminate(); });
      trabajadores.length = 0; libres.length = 0; cola.length = 0; pendientes.clear();
    }

    return {
      n: n, INDICE_ZIP: INDICE_ZIP,
      encolar: encolar, enviarA: enviarA, enviarAlZip: enviarAlZip, difundir: difundir,
      terminar: terminar, pendientes: function () { return pendientes.size + cola.length; }
    };
  }

  return { crear: crear };
});
