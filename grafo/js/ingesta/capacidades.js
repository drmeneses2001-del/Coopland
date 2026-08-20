(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; raiz.GC.capacidades = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  // Detección en tiempo de ejecución. Nada se deduce del user-agent: se prueba.
  //
  // El caso crítico es `webkitdirectory` en Safari de iPadOS, donde las fuentes
  // se contradicen. Aquí se sondea la propiedad, y además la interfaz ofrece una
  // verificación empírica (ver `registrarVerificacion`) cuyo resultado se guarda:
  // a partir de la segunda apertura la app ya sabe la verdad de ESTE dispositivo.

  function sondearDirectoryPicker() {
    if (typeof window === 'undefined') return { disponible: false, motivo: 'sin objeto window' };
    if (typeof window.showDirectoryPicker !== 'function') return { disponible: false, motivo: 'showDirectoryPicker no existe' };
    try {
      if (window.self !== window.top) return { disponible: false, motivo: 'dentro de un iframe' };
    } catch (e) { return { disponible: false, motivo: 'iframe de origen cruzado' }; }
    return { disponible: true, motivo: 'File System Access API presente' };
  }

  function sondearWebkitDirectory() {
    if (typeof document === 'undefined') return { disponible: false, motivo: 'sin DOM' };
    var entrada = document.createElement('input');
    entrada.type = 'file';
    if (!('webkitdirectory' in entrada)) return { disponible: false, motivo: 'la propiedad no existe' };
    try {
      entrada.webkitdirectory = true;
      if (entrada.webkitdirectory !== true) return { disponible: false, motivo: 'la propiedad no acepta el valor' };
    } catch (e) { return { disponible: false, motivo: 'la propiedad lanzó al asignarse' }; }
    // La propiedad existe y acepta el valor. En iPadOS eso NO garantiza que el
    // selector muestre carpetas: sólo la verificación empírica lo confirma.
    return { disponible: true, verificado: false, motivo: 'la propiedad existe y acepta el valor (falta verificación real)' };
  }

  function sondearZip() {
    return { disponible: true, motivo: 'descompresión en el cliente con fflate' };
  }

  function detectar() {
    var A = sondearDirectoryPicker();
    var B = sondearWebkitDirectory();
    var C = sondearZip();

    var entorno = {
      worker: typeof Worker !== 'undefined',
      indexedDB: typeof indexedDB !== 'undefined',
      cryptoSubtle: !!(typeof crypto !== 'undefined' && crypto.subtle),
      contextoSeguro: typeof isSecureContext !== 'undefined' ? isSecureContext : null,
      serviceWorker: typeof navigator !== 'undefined' && 'serviceWorker' in navigator,
      nucleos: (typeof navigator !== 'undefined' && navigator.hardwareConcurrency) || 2,
      offscreenCanvas: typeof OffscreenCanvas !== 'undefined',
      webgl: (function () {
        if (typeof document === 'undefined') return false;
        try {
          var c = document.createElement('canvas');
          return !!(c.getContext('webgl2') || c.getContext('webgl'));
        } catch (e) { return false; }
      })(),
      puntero: (typeof matchMedia !== 'undefined' && matchMedia('(pointer: coarse)').matches) ? 'grueso (táctil)' : 'fino'
    };

    return { rutas: { A: A, B: B, C: C }, entorno: entorno };
  }

  // Selección de la mejor ruta disponible, respetando lo ya verificado en
  // este dispositivo: una verificación fallida degrada la ruta para siempre.
  function elegirRuta(deteccion, verificaciones) {
    verificaciones = verificaciones || {};
    if (deteccion.rutas.A.disponible && verificaciones.A !== false) return 'A';
    if (deteccion.rutas.B.disponible && verificaciones.B !== false) return 'B';
    return 'C';
  }

  var IMPLICACIONES = {
    A: {
      titulo: 'Ruta A · Selector de carpeta con permiso persistente',
      reescaneo: 'Al abrir la app, un solo toque de reconfirmación y el re-escaneo es automático e incremental.',
      detalle: 'La carpeta queda guardada como referencia. El navegador puede pedir reconfirmar el permiso tras un tiempo sin uso.'
    },
    B: {
      titulo: 'Ruta B · Selección de carpeta completa',
      reescaneo: 'Al abrir la app hay que volver a elegir la carpeta; a partir de ahí el diff y el re-parseo son automáticos.',
      detalle: 'Se conservan las rutas relativas dentro de la carpeta, así que la jerarquía del grafo se mantiene entre sesiones.'
    },
    C: {
      titulo: 'Ruta C · Archivos sueltos o ZIP',
      reescaneo: 'Al abrir la app hay que volver a elegir los archivos, o cargar de nuevo el ZIP.',
      detalle: 'Es la red de seguridad: funciona siempre. Con ZIP se conserva la jerarquía de carpetas; con archivos sueltos, no.'
    }
  };

  return {
    detectar: detectar, elegirRuta: elegirRuta, IMPLICACIONES: IMPLICACIONES,
    sondearDirectoryPicker: sondearDirectoryPicker,
    sondearWebkitDirectory: sondearWebkitDirectory,
    sondearZip: sondearZip
  };
});
