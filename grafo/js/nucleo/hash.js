(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else ((raiz.GC = raiz.GC || {}).hash = api);
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Huella de contenido. Sirve para detectar cambios, no para seguridad.
  // Preferimos SHA-256 nativo (rápido); si no hay contexto seguro,
  // caemos a FNV-1a de 64 bits implementado en JS puro.

  function hex32(n) { return (n >>> 0).toString(16).padStart(8, '0'); }

  function fnv1a64(bytes) {
    // FNV-1a de 64 bits con aritmética de 32 bits en dos mitades.
    var altoH = 0xcbf29ce4 >>> 0, bajoH = 0x84222325 >>> 0;
    for (var i = 0; i < bytes.length; i++) {
      bajoH = (bajoH ^ bytes[i]) >>> 0;
      // multiplicación por el primo FNV 0x100000001b3
      var b0 = bajoH & 0xffff, b1 = bajoH >>> 16;
      var a0 = altoH & 0xffff, a1 = altoH >>> 16;
      // primo = 0x00000100_000001b3
      var p0 = 0x01b3, p1 = 0x0000, p2 = 0x0100, p3 = 0x0000;
      var c0 = b0 * p0;
      var c1 = b1 * p0 + b0 * p1 + (c0 >>> 16);
      var c2 = a0 * p0 + b1 * p1 + b0 * p2 + (c1 >>> 16);
      var c3 = a1 * p0 + a0 * p1 + b1 * p2 + b0 * p3 + (c2 >>> 16);
      bajoH = (((c1 & 0xffff) << 16) | (c0 & 0xffff)) >>> 0;
      altoH = (((c3 & 0xffff) << 16) | (c2 & 0xffff)) >>> 0;
    }
    return hex32(altoH) + hex32(bajoH);
  }

  function aBytes(entrada) {
    if (entrada instanceof Uint8Array) return entrada;
    if (typeof ArrayBuffer !== 'undefined' && entrada instanceof ArrayBuffer) return new Uint8Array(entrada);
    if (typeof entrada === 'string') {
      if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(entrada);
      var salida = new Uint8Array(entrada.length);
      for (var i = 0; i < entrada.length; i++) salida[i] = entrada.charCodeAt(i) & 0xff;
      return salida;
    }
    throw new TypeError('hash: entrada no soportada');
  }

  async function huella(entrada) {
    var bytes = aBytes(entrada);
    var subtle = (typeof crypto !== 'undefined' && crypto.subtle) ? crypto.subtle : null;
    if (subtle) {
      try {
        // Copia al buffer exacto: Uint8Array puede ser una vista parcial.
        var copia = bytes.byteOffset === 0 && bytes.byteLength === bytes.buffer.byteLength
          ? bytes.buffer : bytes.slice().buffer;
        var resumen = await subtle.digest('SHA-256', copia);
        var vista = new Uint8Array(resumen), salida = '';
        for (var i = 0; i < vista.length; i++) salida += vista[i].toString(16).padStart(2, '0');
        return 'sha256:' + salida;
      } catch (e) { /* sin contexto seguro: seguimos al respaldo */ }
    }
    return 'fnv64:' + fnv1a64(bytes) + ':' + bytes.length.toString(16);
  }

  return { huella: huella, fnv1a64: fnv1a64, aBytes: aBytes };
});
