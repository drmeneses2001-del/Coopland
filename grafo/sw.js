/* Service worker: modo avión.
   Cachea el armazón y las bibliotecas en la primera carga; después la app abre
   y funciona sin red. No cachea nada del contenido del usuario — los documentos
   nunca pasan por aquí.

   Estrategia deliberada, y la razón importa:

     código propio (HTML, CSS, JS)  →  red primero, caché de respaldo
     vendor/ (pdf.js, mammoth…)     →  caché primero

   El código propio va por red primero porque «caché primero» actualiza cada
   archivo por su cuenta: al desplegar una versión nueva se puede acabar con un
   index.html nuevo y un app.js viejo, que es un fallo mucho peor que ir un poco
   más lento. Las bibliotecas de vendor/ son inmutables y pesan dos megas: ésas
   sí van de la caché siempre. Sin red, todo cae a la caché y la app abre igual. */
'use strict';

var VERSION = 'grafo-v7';   // sube con cada despliegue: invalida la caché anterior

var ARMAZON = [
  './',
  './index.html',
  './manifest.webmanifest',
  './css/estilo.css',

  './js/app.js',

  './js/nucleo/hash.js',
  './js/nucleo/bytes.js',
  './js/nucleo/vacias.js',
  './js/nucleo/terminos.js',
  './js/nucleo/almacen.js',
  './js/nucleo/diff.js',
  './js/nucleo/indice.js',
  './js/nucleo/pool.js',
  './js/nucleo/indexador.js',

  './js/ingesta/capacidades.js',
  './js/ingesta/ingesta.js',

  './js/parsers/registro.js',
  './js/parsers/texto.js',
  './js/parsers/rtf.js',
  './js/parsers/html.js',
  './js/parsers/datos.js',
  './js/parsers/pdf.js',
  './js/parsers/docx.js',
  './js/parsers/binario.js',

  './js/grafo/coocurrencia.js',
  './js/grafo/louvain.js',
  './js/grafo/metricas.js',
  './js/grafo/documentos.js',
  './js/grafo/mixta.js',
  './js/grafo/brechas.js',
  './js/grafo/preguntas.js',
  './js/grafo/ruta.js',

  './js/lienzo/camara.js',
  './js/lienzo/lienzo.js',
  './js/lienzo/gestos.js',

  './js/ia/carga.js',
  './js/ia/proveedor.js',
  './js/ia/acciones.js',

  './js/exportar/exportar.js',

  './js/ui/formato.js',
  './js/ui/colores.js',
  './js/ui/vistas.js',
  './js/ui/vistas-grafo.js',
  './js/ui/visor.js',
  './js/ui/ia.js',
  './js/ui/mapa.js',

  // Los workers no los pide el documento: los pide `new Worker()`. Si faltan de
  // esta lista, en avión no arranca ni la indexación ni el grafo ni el lienzo.
  './js/trabajadores/extractor.js',
  './js/trabajadores/grafista.js',
  './js/trabajadores/simulador.js',

  './vendor/fflate.umd.js',
  './vendor/pdf.min.js',
  './vendor/pdf.worker.min.js',
  './vendor/mammoth.browser.min.js'
];

function esInmutable(url) {
  return url.pathname.indexOf('/vendor/') !== -1;
}

self.addEventListener('install', function (ev) {
  ev.waitUntil(
    caches.open(VERSION)
      // addAll falla entero si falla un recurso; se piden de uno en uno para
      // que un archivo ausente no deje la app sin caché ninguna.
      .then(function (cache) {
        return Promise.all(ARMAZON.map(function (url) {
          return cache.add(new Request(url, { cache: 'reload' })).catch(function () { return null; });
        }));
      })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (ev) {
  ev.waitUntil(
    caches.keys().then(function (claves) {
      return Promise.all(claves.map(function (k) { return k === VERSION ? null : caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
      .then(function () {
        // Avisa a las pestañas abiertas de que hay versión nueva mandando.
        return self.clients.matchAll({ type: 'window' }).then(function (clientes) {
          clientes.forEach(function (c) { c.postMessage({ t: 'sw-activado', version: VERSION }); });
        });
      })
  );
});

self.addEventListener('message', function (ev) {
  if (ev.data && ev.data.t === 'saltar-espera') self.skipWaiting();
});

self.addEventListener('fetch', function (ev) {
  var peticion = ev.request;
  if (peticion.method !== 'GET') return;
  var url = new URL(peticion.url);
  if (url.origin !== self.location.origin) return;   // nada externo pasa por aquí

  if (esInmutable(url)) {
    // Bibliotecas: caché primero, y si no están, red.
    ev.respondWith(
      caches.match(peticion).then(function (guardado) {
        return guardado || fetch(peticion).then(function (respuesta) {
          if (respuesta && respuesta.ok) {
            var copia = respuesta.clone();
            caches.open(VERSION).then(function (c) { c.put(peticion, copia); });
          }
          return respuesta;
        });
      })
    );
    return;
  }

  // Código propio: red primero. Así un despliegue nuevo entra completo en la
  // siguiente carga en lugar de mezclarse a trozos con el anterior.
  ev.respondWith(
    fetch(peticion).then(function (respuesta) {
      if (respuesta && respuesta.ok) {
        var copia = respuesta.clone();
        caches.open(VERSION).then(function (c) { c.put(peticion, copia); });
      }
      return respuesta;
    }).catch(function () {
      return caches.match(peticion).then(function (guardado) {
        if (guardado) return guardado;
        // Navegación sin red y sin caché: al menos el armazón.
        if (peticion.mode === 'navigate') return caches.match('./index.html');
        return Response.error();
      });
    })
  );
});
