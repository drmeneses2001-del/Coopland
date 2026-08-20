(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.lienzo = raiz.GC.lienzo || {}).gestos = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Gestos táctiles del lienzo, sobre Pointer Events —que en iPadOS cubren dedo,
  // Apple Pencil y ratón con el mismo código—.
  //
  //   un dedo sobre el fondo   arrastrar el lienzo
  //   un dedo sobre un nodo    arrastrar el nodo, con la simulación viva
  //   dos dedos                pellizcar para zoom y desplazar a la vez
  //   toque                    seleccionar
  //   doble toque              desplegar los vecinos ocultos
  //   toque sostenido          menú contextual
  //
  // Las tres cifras que definen el tacto están arriba y son deliberadas: en un
  // iPad el dedo siempre se mueve un poco, así que un toque que exija cero
  // desplazamiento nunca se reconoce.

  var TOQUE_MAX_MS = 320;
  var TOQUE_MAX_PX = 12;
  var DOBLE_MAX_MS = 320;
  var DOBLE_MAX_PX = 32;
  var SOSTENIDO_MS = 520;

  function conectar(canvas, manejadores, ayuda) {
    manejadores = manejadores || {};
    var punteros = new Map();
    var arrastreNodo = -1;
    var arrastrandoLienzo = false;
    var movido = 0;
    var inicio = { x: 0, y: 0, t: 0 };
    var ultimoToque = { x: 0, y: 0, t: 0 };
    var temporizadorSostenido = null;
    var pellizco = null;

    function pos(ev) {
      var r = canvas.getBoundingClientRect();
      return { x: ev.clientX - r.left, y: ev.clientY - r.top };
    }

    function cancelarSostenido() {
      if (temporizadorSostenido) { clearTimeout(temporizadorSostenido); temporizadorSostenido = null; }
    }

    function centroYSeparacion() {
      var lista = Array.from(punteros.values());
      var a = lista[0], b = lista[1];
      return {
        cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2,
        sep: Math.hypot(a.x - b.x, a.y - b.y)
      };
    }

    canvas.addEventListener('pointerdown', function (ev) {
      canvas.setPointerCapture(ev.pointerId);
      var p = pos(ev);
      punteros.set(ev.pointerId, p);

      if (punteros.size === 2) {
        // Empieza el pellizco: se abandona cualquier arrastre en curso para que
        // el gesto no haga dos cosas a la vez.
        cancelarSostenido();
        if (arrastreNodo >= 0 && manejadores.alSoltarNodo) manejadores.alSoltarNodo(arrastreNodo, false);
        arrastreNodo = -1;
        arrastrandoLienzo = false;
        pellizco = centroYSeparacion();
        return;
      }
      if (punteros.size > 2) return;

      inicio = { x: p.x, y: p.y, t: Date.now() };
      movido = 0;
      var id = ayuda.nodoEn(p.x, p.y);
      if (id >= 0) {
        arrastreNodo = id;
        if (manejadores.alTomarNodo) manejadores.alTomarNodo(id, p);
      } else {
        arrastrandoLienzo = true;
      }

      cancelarSostenido();
      temporizadorSostenido = setTimeout(function () {
        temporizadorSostenido = null;
        if (movido > TOQUE_MAX_PX) return;
        // El menú contextual cancela el arrastre: si el dedo se quedó quieto,
        // el usuario no quería mover nada.
        if (arrastreNodo >= 0 && manejadores.alSoltarNodo) manejadores.alSoltarNodo(arrastreNodo, false);
        var nodo = arrastreNodo;
        arrastreNodo = -1; arrastrandoLienzo = false;
        if (manejadores.alSostener) manejadores.alSostener(nodo, p);
      }, SOSTENIDO_MS);

      ev.preventDefault();
    }, { passive: false });

    canvas.addEventListener('pointermove', function (ev) {
      if (!punteros.has(ev.pointerId)) return;
      var p = pos(ev);
      var previo = punteros.get(ev.pointerId);
      punteros.set(ev.pointerId, p);

      if (punteros.size >= 2 && pellizco) {
        var ahora = centroYSeparacion();
        var factor = ahora.sep / (pellizco.sep || 1);
        if (isFinite(factor) && factor > 0) {
          ayuda.zoom(factor, ahora.cx, ahora.cy);
          ayuda.desplazar(ahora.cx - pellizco.cx, ahora.cy - pellizco.cy);
        }
        pellizco = ahora;
        if (manejadores.alCambiarVista) manejadores.alCambiarVista();
        ev.preventDefault();
        return;
      }

      var dx = p.x - previo.x, dy = p.y - previo.y;
      movido = Math.max(movido, Math.hypot(p.x - inicio.x, p.y - inicio.y));
      if (movido > TOQUE_MAX_PX) cancelarSostenido();

      if (arrastreNodo >= 0) {
        if (manejadores.alArrastrarNodo) manejadores.alArrastrarNodo(arrastreNodo, p);
      } else if (arrastrandoLienzo) {
        ayuda.desplazar(dx, dy);
        if (manejadores.alCambiarVista) manejadores.alCambiarVista();
      }
      ev.preventDefault();
    }, { passive: false });

    function terminar(ev) {
      if (!punteros.has(ev.pointerId)) return;
      var p = punteros.get(ev.pointerId);
      punteros.delete(ev.pointerId);
      cancelarSostenido();

      if (punteros.size === 1) {
        // Se levantó un dedo del pellizco: el que queda no debe dar un salto.
        pellizco = null;
        var restante = Array.from(punteros.values())[0];
        inicio = { x: restante.x, y: restante.y, t: Date.now() };
        movido = 999;   // ya no puede contar como toque
        arrastrandoLienzo = true;
        return;
      }
      if (punteros.size > 0) return;
      pellizco = null;

      var duracion = Date.now() - inicio.t;
      var distancia = Math.hypot(p.x - inicio.x, p.y - inicio.y);
      var fueToque = duracion <= TOQUE_MAX_MS && distancia <= TOQUE_MAX_PX;

      if (arrastreNodo >= 0) {
        if (manejadores.alSoltarNodo) manejadores.alSoltarNodo(arrastreNodo, !fueToque);
      }

      if (fueToque) {
        var ahora = Date.now();
        var esDoble = (ahora - ultimoToque.t) <= DOBLE_MAX_MS &&
                      Math.hypot(p.x - ultimoToque.x, p.y - ultimoToque.y) <= DOBLE_MAX_PX;
        var id = ayuda.nodoEn(p.x, p.y);
        if (esDoble) {
          ultimoToque = { x: 0, y: 0, t: 0 };
          if (manejadores.alDobleToque) manejadores.alDobleToque(id, p);
        } else {
          ultimoToque = { x: p.x, y: p.y, t: ahora };
          if (manejadores.alToque) manejadores.alToque(id, p);
        }
      }

      arrastreNodo = -1;
      arrastrandoLienzo = false;
    }

    canvas.addEventListener('pointerup', terminar);
    canvas.addEventListener('pointercancel', function (ev) {
      punteros.delete(ev.pointerId);
      cancelarSostenido();
      if (arrastreNodo >= 0 && manejadores.alSoltarNodo) manejadores.alSoltarNodo(arrastreNodo, false);
      arrastreNodo = -1; arrastrandoLienzo = false; pellizco = null;
    });

    // Rueda y trackpad, para cuando esto se abre en un equipo de escritorio.
    canvas.addEventListener('wheel', function (ev) {
      var p = pos(ev);
      var factor = Math.pow(0.999, ev.deltaY);
      ayuda.zoom(factor, p.x, p.y);
      if (manejadores.alCambiarVista) manejadores.alCambiarVista();
      ev.preventDefault();
    }, { passive: false });

    // Safari de iPadOS interpreta el doble toque como zoom de la página si no
    // se le dice explícitamente que no.
    canvas.addEventListener('dblclick', function (ev) { ev.preventDefault(); });
    canvas.addEventListener('contextmenu', function (ev) { ev.preventDefault(); });
    canvas.style.touchAction = 'none';

    return {
      desconectar: function () { cancelarSostenido(); punteros.clear(); },
      constantes: { TOQUE_MAX_MS: TOQUE_MAX_MS, TOQUE_MAX_PX: TOQUE_MAX_PX, DOBLE_MAX_MS: DOBLE_MAX_MS, SOSTENIDO_MS: SOSTENIDO_MS }
    };
  }

  return { conectar: conectar, TOQUE_MAX_MS: TOQUE_MAX_MS, TOQUE_MAX_PX: TOQUE_MAX_PX, DOBLE_MAX_MS: DOBLE_MAX_MS, SOSTENIDO_MS: SOSTENIDO_MS };
});
