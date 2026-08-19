/* Service worker: modo avión. Cachea el armazón y las bibliotecas en la
   primera carga; después la app abre y funciona sin red. No cachea nada del
   contenido del usuario — los documentos nunca pasan por aquí. */
'use strict';

var VERSION = 'grafo-v1';
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
  './js/trabajadores/extractor.js',
  './js/ui/formato.js',
  './js/ui/vistas.js',
  './vendor/fflate.umd.js',
  './vendor/pdf.min.js',
  './vendor/pdf.worker.min.js',
  './vendor/mammoth.browser.min.js'
];

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
  );
});

self.addEventListener('fetch', function (ev) {
  var peticion = ev.request;
  if (peticion.method !== 'GET') return;
  var url = new URL(peticion.url);
  if (url.origin !== self.location.origin) return;   // nada externo pasa por aquí

  // Caché primero: la app debe abrir igual con red y sin ella. La actualización
  // se recoge en segundo plano para la siguiente apertura.
  ev.respondWith(
    caches.match(peticion).then(function (guardado) {
      var red = fetch(peticion).then(function (respuesta) {
        if (respuesta && respuesta.ok) {
          var copia = respuesta.clone();
          caches.open(VERSION).then(function (c) { c.put(peticion, copia); });
        }
        return respuesta;
      }).catch(function () { return guardado; });
      return guardado || red;
    })
  );
});
