(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.lienzo = raiz.GC.lienzo || {}).camara = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Cámara del lienzo: pura aritmética, sin tocar el DOM, para poder probarla
  // en consola. Convierte entre coordenadas del grafo («mundo») y píxeles de
  // pantalla, y en modo 3D proyecta con una perspectiva sencilla.
  //
  // El zoom siempre se hace *alrededor de un punto*: al pellizcar con dos
  // dedos, el punto entre ellos debe quedarse quieto bajo la piel. Cualquier
  // otra cosa se siente rota aunque las cifras cuadren.

  var ESCALA_MIN = 0.02;
  var ESCALA_MAX = 24;

  function crear(opciones) {
    opciones = opciones || {};
    var c = {
      x: 0, y: 0,               // centro del mundo que se ve en pantalla
      escala: 1,
      ancho: opciones.ancho || 800,
      alto: opciones.alto || 600,
      dim: opciones.dim === 3 ? 3 : 2,
      giro: 0,                  // rotación alrededor del eje vertical, sólo 3D
      inclinacion: 0.35,
      distancia: 900            // distancia del ojo, sólo 3D
    };

    function tamano(ancho, alto) { c.ancho = ancho; c.alto = alto; }

    // --- proyección ---------------------------------------------------------
    // En 2D es una traslación y una escala. En 3D se gira alrededor del eje Y,
    // se inclina y se divide por la profundidad; `k` sale también hacia fuera
    // para que el radio del nodo y el grosor de la arista se encojan con él.
    function proyectar(mx, my, mz) {
      if (c.dim === 2) {
        return {
          x: (mx - c.x) * c.escala + c.ancho / 2,
          y: (my - c.y) * c.escala + c.alto / 2,
          k: 1, z: 0
        };
      }
      var cosG = Math.cos(c.giro), sinG = Math.sin(c.giro);
      var rx = mx * cosG + (mz || 0) * sinG;
      var rz = -mx * sinG + (mz || 0) * cosG;
      var cosI = Math.cos(c.inclinacion), sinI = Math.sin(c.inclinacion);
      var ry = my * cosI - rz * sinI;
      var rz2 = my * sinI + rz * cosI;
      var prof = c.distancia + rz2;
      if (prof < 1) prof = 1;
      var k = c.distancia / prof;
      return {
        x: (rx - c.x) * c.escala * k + c.ancho / 2,
        y: (ry - c.y) * c.escala * k + c.alto / 2,
        k: k, z: rz2
      };
    }

    // Inversa exacta sólo en 2D: en 3D la pantalla no determina la profundidad,
    // así que se devuelve el plano z = 0, que es donde el usuario cree tocar.
    function aMundo(px, py) {
      if (c.dim === 2) {
        return { x: (px - c.ancho / 2) / c.escala + c.x, y: (py - c.alto / 2) / c.escala + c.y, z: 0 };
      }
      var rx = (px - c.ancho / 2) / c.escala + c.x;
      var ry = (py - c.alto / 2) / c.escala + c.y;
      var cosI = Math.cos(c.inclinacion), sinI = Math.sin(c.inclinacion);
      var my = ry * cosI;                    // con rz = 0
      var rz = -ry * sinI;
      var cosG = Math.cos(c.giro), sinG = Math.sin(c.giro);
      return { x: rx * cosG - rz * sinG, y: my, z: rx * sinG + rz * cosG };
    }

    // --- gestos -------------------------------------------------------------
    function desplazar(dxPantalla, dyPantalla) {
      c.x -= dxPantalla / c.escala;
      c.y -= dyPantalla / c.escala;
    }

    function zoom(factor, pxAncla, pyAncla) {
      var antes = aMundo(pxAncla, pyAncla);
      c.escala = Math.max(ESCALA_MIN, Math.min(ESCALA_MAX, c.escala * factor));
      var despues = aMundo(pxAncla, pyAncla);
      c.x += antes.x - despues.x;
      c.y += antes.y - despues.y;
    }

    function girar(delta) {
      if (c.dim !== 3) return;
      c.giro = (c.giro + delta) % (Math.PI * 2);
    }

    // --- encuadre -----------------------------------------------------------
    function ajustarA(caja, margen) {
      margen = margen == null ? 60 : margen;
      var anchoMundo = Math.max(1, caja.maxX - caja.minX);
      var altoMundo = Math.max(1, caja.maxY - caja.minY);
      var escalaX = (c.ancho - margen * 2) / anchoMundo;
      var escalaY = (c.alto - margen * 2) / altoMundo;
      c.escala = Math.max(ESCALA_MIN, Math.min(ESCALA_MAX, Math.min(escalaX, escalaY)));
      c.x = (caja.minX + caja.maxX) / 2;
      c.y = (caja.minY + caja.maxY) / 2;
    }

    function centrarEn(mx, my) { c.x = mx; c.y = my; }

    // Rectángulo del mundo visible, con holgura. Sirve para no dibujar lo que
    // queda fuera: es el recorte que sostiene los cuadros por segundo.
    function ventana(holgura) {
      holgura = holgura || 0;
      var semiAncho = (c.ancho / 2) / c.escala + holgura;
      var semiAlto = (c.alto / 2) / c.escala + holgura;
      return { minX: c.x - semiAncho, maxX: c.x + semiAncho, minY: c.y - semiAlto, maxY: c.y + semiAlto };
    }

    return {
      estado: c, tamano: tamano, proyectar: proyectar, aMundo: aMundo,
      desplazar: desplazar, zoom: zoom, girar: girar,
      ajustarA: ajustarA, centrarEn: centrarEn, ventana: ventana,
      dimension: function (d) { c.dim = d === 3 ? 3 : 2; }
    };
  }

  // Caja envolvente de un arreglo empaquetado de posiciones.
  function cajaDe(pos, n, dim, visible) {
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (var i = 0; i < n; i++) {
      if (visible && !visible[i]) continue;
      var x = pos[i * dim], y = pos[i * dim + 1];
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
    }
    if (!isFinite(minX)) return { minX: -1, maxX: 1, minY: -1, maxY: 1, vacia: true };
    return { minX: minX, maxX: maxX, minY: minY, maxY: maxY, vacia: false };
  }

  return { crear: crear, cajaDe: cajaDe, ESCALA_MIN: ESCALA_MIN, ESCALA_MAX: ESCALA_MAX };
});
