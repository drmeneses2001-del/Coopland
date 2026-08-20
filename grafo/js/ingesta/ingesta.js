(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; raiz.GC.ingesta = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  // Recolección del inventario por las tres rutas. Ninguna ruta lee contenido:
  // sólo produce la lista {ruta, nombre, tamaño, fecha, origen}. El contenido
  // se lee después, y sólo para lo que el diff marque como candidato.

  var IGNORAR_CARPETAS = new Set(['.git', '.obsidian', '.trash', '.smart-env', 'node_modules', '.svn', '__macosx', '.stfolder', '.stversions']);
  var IGNORAR_NOMBRES = new Set(['.ds_store', 'thumbs.db', 'desktop.ini', '.localized']);
  var PROFUNDIDAD_MAXIMA = 12;

  function ignorable(nombre, esCarpeta) {
    var n = nombre.toLowerCase();
    if (esCarpeta) return IGNORAR_CARPETAS.has(n) || (n[0] === '.' && n !== '.');
    if (IGNORAR_NOMBRES.has(n)) return true;
    if (n[0] === '.' && !/\.(md|txt|json)$/.test(n)) return true;
    return false;
  }

  // Marcador de iCloud: el archivo real todavía no está descargado en el iPad.
  // Es el fallo más común y más desconcertante en esta plataforma, así que se
  // reporta como tal en vez de contarse como archivo ilegible.
  function marcadorICloud(nombre) {
    var m = /^\.(.+)\.icloud$/i.exec(nombre);
    return m ? m[1] : null;
  }

  // --- Ruta A: File System Access API --------------------------------------
  async function recorrerDirectorio(handle, prefijo, salida, profundidad, alAvanzar) {
    if (profundidad > PROFUNDIDAD_MAXIMA) return salida;
    for await (var entrada of handle.values()) {
      if (entrada.kind === 'directory') {
        if (ignorable(entrada.name, true)) continue;
        await recorrerDirectorio(entrada, prefijo + entrada.name + '/', salida, profundidad + 1, alAvanzar);
        continue;
      }
      var pendiente = marcadorICloud(entrada.name);
      if (pendiente) {
        salida.push({ ruta: prefijo + pendiente, nombre: pendiente, tamano: 0, modificado: 0, origen: 'A', noDescargado: true });
        continue;
      }
      if (ignorable(entrada.name, false)) continue;
      var archivo = await entrada.getFile();
      salida.push({
        ruta: prefijo + entrada.name, nombre: entrada.name,
        tamano: archivo.size, modificado: archivo.lastModified,
        origen: 'A', handle: entrada
      });
      if (alAvanzar && salida.length % 50 === 0) alAvanzar(salida.length);
    }
    return salida;
  }

  async function elegirCarpetaA() {
    var handle = await raiz.showDirectoryPicker({ id: 'grafo-conocimiento', mode: 'read' });
    return handle;
  }

  async function permisoA(handle, pedir) {
    if (!handle || typeof handle.queryPermission !== 'function') return 'granted';
    var estado = await handle.queryPermission({ mode: 'read' });
    if (estado === 'granted' || !pedir) return estado;
    return await handle.requestPermission({ mode: 'read' });
  }

  async function inventarioA(handle, alAvanzar) {
    var salida = [];
    await recorrerDirectorio(handle, '', salida, 0, alAvanzar);
    return salida;
  }

  // --- Rutas B y C: elemento <input> ---------------------------------------
  function pedirArchivos(opciones) {
    opciones = opciones || {};
    return new Promise(function (resolver) {
      var entrada = document.createElement('input');
      entrada.type = 'file';
      if (opciones.directorio) { entrada.webkitdirectory = true; entrada.multiple = true; }
      else entrada.multiple = opciones.multiple !== false;
      if (opciones.aceptar) entrada.accept = opciones.aceptar;
      entrada.style.position = 'fixed';
      entrada.style.left = '-9999px';
      document.body.appendChild(entrada);
      var resuelto = false;
      function terminar(lista) {
        if (resuelto) return; resuelto = true;
        entrada.remove();
        resolver(lista);
      }
      entrada.addEventListener('change', function () { terminar(Array.from(entrada.files || [])); });
      // Safari no dispara ningún evento al cancelar; el respaldo evita colgar la
      // promesa para siempre si el usuario cierra el selector.
      window.addEventListener('focus', function alVolver() {
        window.removeEventListener('focus', alVolver);
        setTimeout(function () { if (!entrada.files || !entrada.files.length) terminar([]); }, 1200);
      });
      entrada.click();
    });
  }

  function inventarioDesdeArchivos(archivos, origen) {
    var salida = [];
    for (var i = 0; i < archivos.length; i++) {
      var f = archivos[i];
      var relativa = f.webkitRelativePath || '';
      var ruta = relativa || f.name;
      // La primera carpeta de webkitRelativePath es la carpeta elegida:
      // se recorta para que la raíz del índice sea estable entre sesiones.
      if (relativa && relativa.indexOf('/') !== -1) ruta = relativa.slice(relativa.indexOf('/') + 1);
      var partes = ruta.split('/');
      var nombre = partes[partes.length - 1];
      if (partes.slice(0, -1).some(function (p) { return ignorable(p, true); })) continue;
      var pendiente = marcadorICloud(nombre);
      if (pendiente) {
        salida.push({ ruta: partes.slice(0, -1).concat(pendiente).join('/'), nombre: pendiente, tamano: 0, modificado: 0, origen: origen, noDescargado: true });
        continue;
      }
      if (ignorable(nombre, false)) continue;
      salida.push({ ruta: ruta, nombre: nombre, tamano: f.size, modificado: f.lastModified, origen: origen, archivo: f });
    }
    return salida;
  }

  // --- Ruta C: ZIP ---------------------------------------------------------
  // La descompresión ocurre en el worker (fflate); aquí sólo se prepara.
  function esZip(archivo) { return /\.zip$/i.test(archivo.name); }

  function resumirInventario(inventario) {
    var porExtension = new Map();
    var bytes = 0, noDescargados = 0;
    inventario.forEach(function (f) {
      var m = /\.([A-Za-z0-9]{1,10})$/.exec(f.nombre);
      var ext = m ? m[1].toLowerCase() : '(sin extensión)';
      porExtension.set(ext, (porExtension.get(ext) || 0) + 1);
      bytes += f.tamano || 0;
      if (f.noDescargado) noDescargados++;
    });
    var lista = Array.from(porExtension.entries())
      .map(function (e) { return { ext: e[0], n: e[1] }; })
      .sort(function (a, b) { return b.n - a.n; });
    return { total: inventario.length, bytes: bytes, noDescargados: noDescargados, porExtension: lista };
  }

  return {
    ignorable: ignorable, marcadorICloud: marcadorICloud,
    elegirCarpetaA: elegirCarpetaA, permisoA: permisoA, inventarioA: inventarioA,
    recorrerDirectorio: recorrerDirectorio,
    pedirArchivos: pedirArchivos, inventarioDesdeArchivos: inventarioDesdeArchivos,
    esZip: esZip, resumirInventario: resumirInventario,
    IGNORAR_CARPETAS: IGNORAR_CARPETAS, PROFUNDIDAD_MAXIMA: PROFUNDIDAD_MAXIMA
  };
});
