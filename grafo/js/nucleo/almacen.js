(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else ((raiz.GC = raiz.GC || {}).almacen = api);
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Índice persistente en IndexedDB. Todo vive en el dispositivo.
  //
  // Almacenes según especificación:
  //   documentos   — ruta relativa, tamaño, fecha, hash, texto, términos
  //   grafo        — nodos, aristas y métricas del estado actual
  //   instantaneas — el grafo serializado de cada apertura, con fecha
  // Añadido:
  //   config       — preferencias y el handle de carpeta. Va aparte a propósito:
  //                  no es dato del grafo y no debe viajar en los exportables.

  var NOMBRE_BD = 'grafo-conocimiento';
  var VERSION_BD = 1;
  var bd = null;

  function promesa(peticion) {
    return new Promise(function (resolver, rechazar) {
      peticion.onsuccess = function () { resolver(peticion.result); };
      peticion.onerror = function () { rechazar(peticion.error); };
    });
  }

  function abrir() {
    if (bd) return Promise.resolve(bd);
    return new Promise(function (resolver, rechazar) {
      if (typeof indexedDB === 'undefined') { rechazar(new Error('IndexedDB no disponible (¿navegación privada?).')); return; }
      var pet = indexedDB.open(NOMBRE_BD, VERSION_BD);
      pet.onupgradeneeded = function (ev) {
        var b = ev.target.result;
        if (!b.objectStoreNames.contains('documentos')) {
          var d = b.createObjectStore('documentos', { keyPath: 'ruta' });
          d.createIndex('estado', 'estado', { unique: false });
          d.createIndex('ext', 'ext', { unique: false });
          d.createIndex('modificado', 'modificado', { unique: false });
        }
        if (!b.objectStoreNames.contains('grafo')) b.createObjectStore('grafo', { keyPath: 'id' });
        if (!b.objectStoreNames.contains('instantaneas')) {
          var i = b.createObjectStore('instantaneas', { keyPath: 'id', autoIncrement: true });
          i.createIndex('fecha', 'fecha', { unique: false });
        }
        if (!b.objectStoreNames.contains('config')) b.createObjectStore('config', { keyPath: 'clave' });
      };
      pet.onsuccess = function () {
        bd = pet.result;
        bd.onversionchange = function () { bd.close(); bd = null; };
        resolver(bd);
      };
      pet.onerror = function () { rechazar(pet.error); };
    });
  }

  function transaccion(almacenes, modo) {
    return abrir().then(function (b) { return b.transaction(almacenes, modo); });
  }

  async function leerTodos(almacen) {
    var tx = await transaccion([almacen], 'readonly');
    return promesa(tx.objectStore(almacen).getAll());
  }

  async function leer(almacen, clave) {
    var tx = await transaccion([almacen], 'readonly');
    return promesa(tx.objectStore(almacen).get(clave));
  }

  async function contar(almacen) {
    var tx = await transaccion([almacen], 'readonly');
    return promesa(tx.objectStore(almacen).count());
  }

  // Escritura por lotes en una sola transacción: en iPadOS abrir una
  // transacción por documento es la diferencia entre 2 s y 40 s.
  async function guardarLote(almacen, registros) {
    if (!registros || !registros.length) return 0;
    var b = await abrir();
    return new Promise(function (resolver, rechazar) {
      var tx = b.transaction([almacen], 'readwrite');
      var os = tx.objectStore(almacen);
      for (var i = 0; i < registros.length; i++) os.put(registros[i]);
      tx.oncomplete = function () { resolver(registros.length); };
      tx.onerror = function () { rechazar(tx.error); };
      tx.onabort = function () { rechazar(tx.error || new Error('Transacción abortada (¿cuota llena?).')); };
    });
  }

  async function borrarLote(almacen, claves) {
    if (!claves || !claves.length) return 0;
    var b = await abrir();
    return new Promise(function (resolver, rechazar) {
      var tx = b.transaction([almacen], 'readwrite');
      var os = tx.objectStore(almacen);
      for (var i = 0; i < claves.length; i++) os.delete(claves[i]);
      tx.oncomplete = function () { resolver(claves.length); };
      tx.onerror = function () { rechazar(tx.error); };
    });
  }

  async function vaciar(almacen) {
    var b = await abrir();
    return new Promise(function (resolver, rechazar) {
      var tx = b.transaction([almacen], 'readwrite');
      tx.objectStore(almacen).clear();
      tx.oncomplete = function () { resolver(true); };
      tx.onerror = function () { rechazar(tx.error); };
    });
  }

  // --- configuración -------------------------------------------------------
  async function config(clave, valor) {
    if (arguments.length === 1) {
      var r = await leer('config', clave);
      return r ? r.valor : undefined;
    }
    await guardarLote('config', [{ clave: clave, valor: valor, fecha: Date.now() }]);
    return valor;
  }

  // --- instantáneas --------------------------------------------------------
  async function guardarInstantanea(instantanea) {
    var b = await abrir();
    return new Promise(function (resolver, rechazar) {
      var tx = b.transaction(['instantaneas'], 'readwrite');
      var pet = tx.objectStore('instantaneas').add(instantanea);
      pet.onsuccess = function () { resolver(pet.result); };
      tx.onerror = function () { rechazar(tx.error); };
    });
  }

  async function listarInstantaneas() {
    var todas = await leerTodos('instantaneas');
    return todas.sort(function (a, b) { return a.fecha - b.fecha; });
  }

  // Poda: conservamos las 60 más recientes. Sin esto el deslizador temporal
  // acaba costando más espacio que los propios documentos.
  async function podarInstantaneas(maximo) {
    maximo = maximo || 60;
    var todas = await listarInstantaneas();
    if (todas.length <= maximo) return 0;
    var sobran = todas.slice(0, todas.length - maximo).map(function (i) { return i.id; });
    await borrarLote('instantaneas', sobran);
    return sobran.length;
  }

  async function espacio() {
    if (typeof navigator === 'undefined' || !navigator.storage || !navigator.storage.estimate) return null;
    try { return await navigator.storage.estimate(); } catch (e) { return null; }
  }

  async function borrarTodo() {
    await Promise.all(['documentos', 'grafo', 'instantaneas', 'config'].map(vaciar));
    return true;
  }

  return {
    NOMBRE_BD: NOMBRE_BD, VERSION_BD: VERSION_BD,
    abrir: abrir, leer: leer, leerTodos: leerTodos, contar: contar,
    guardarLote: guardarLote, borrarLote: borrarLote, vaciar: vaciar,
    config: config, guardarInstantanea: guardarInstantanea,
    listarInstantaneas: listarInstantaneas, podarInstantaneas: podarInstantaneas,
    espacio: espacio, borrarTodo: borrarTodo
  };
});
