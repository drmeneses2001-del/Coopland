(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.ui = raiz.GC.ui || {}).colores = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Color de comunidad derivado de una rueda perceptualmente uniforme (OKLCH),
  // no de una paleta fija. Con doce clústeres una paleta fija ya se repite; con
  // OKLCH los tonos se reparten por la rueda y todos mantienen la misma
  // luminosidad percibida, de modo que ninguno grita más que otro sobre el
  // lienzo oscuro y ninguno desaparece.
  //
  // El ángulo áureo evita que dos comunidades consecutivas —que en el grafo
  // suelen ser vecinas— caigan en tonos contiguos.

  var ANGULO_AUREO = 137.508;
  var TONO_INICIAL = 258;      // arranca en el azul del propio instrumento
  var LUZ = [0.74, 0.66, 0.82];
  var CROMA = [0.145, 0.125, 0.11];

  function tono(indice) {
    return (TONO_INICIAL + indice * ANGULO_AUREO) % 360;
  }

  function color(indice, opciones) {
    opciones = opciones || {};
    var vuelta = Math.floor(indice / 12) % LUZ.length;
    var l = (opciones.luz || LUZ[vuelta]) * 100;
    var c = opciones.croma || CROMA[vuelta];
    var h = tono(indice);
    if (opciones.alfa != null) return 'oklch(' + l.toFixed(1) + '% ' + c.toFixed(3) + ' ' + h.toFixed(1) + ' / ' + opciones.alfa + ')';
    return 'oklch(' + l.toFixed(1) + '% ' + c.toFixed(3) + ' ' + h.toFixed(1) + ')';
  }

  // Respaldo para navegadores sin oklch(): conversión a sRGB por OKLab.
  function aRgb(indice, opciones) {
    opciones = opciones || {};
    var vuelta = Math.floor(indice / 12) % LUZ.length;
    var L = opciones.luz || LUZ[vuelta];
    var C = opciones.croma || CROMA[vuelta];
    var h = tono(indice) * Math.PI / 180;
    var a = C * Math.cos(h), b = C * Math.sin(h);

    var l_ = L + 0.3963377774 * a + 0.2158037573 * b;
    var m_ = L - 0.1055613458 * a - 0.0638541728 * b;
    var s_ = L - 0.0894841775 * a - 1.2914855480 * b;
    var l = l_ * l_ * l_, m = m_ * m_ * m_, s = s_ * s_ * s_;

    var r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
    var g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
    var bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s;

    function gamma(x) {
      x = x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(Math.max(x, 0), 1 / 2.4) - 0.055;
      return Math.round(Math.min(1, Math.max(0, x)) * 255);
    }
    return 'rgb(' + gamma(r) + ',' + gamma(g) + ',' + gamma(bb) + ')';
  }

  var soportaOklch = (function () {
    if (typeof CSS === 'undefined' || !CSS.supports) return false;
    try { return CSS.supports('color', 'oklch(70% 0.1 200)'); } catch (e) { return false; }
  })();

  function deComunidad(indice, opciones) {
    return soportaOklch ? color(indice, opciones) : aRgb(indice, opciones);
  }

  return { deComunidad: deComunidad, color: color, aRgb: aRgb, tono: tono, soportaOklch: soportaOklch, ANGULO_AUREO: ANGULO_AUREO };
});
