(function (raiz) {
  'use strict';
  // Pruebas que sólo tienen sentido en el navegador: workers, IndexedDB y el
  // ciclo completo de indexación incremental. Son las que hay que ver en verde
  // en el iPad antes de dar por buenas las fases 1 y 2.

  var GC = raiz.GC;
  var A = GC.casos;
  var casos = [];
  function caso(grupo, nombre, fn) { casos.push({ grupo: grupo, nombre: nombre, fn: fn }); }

  function archivoDeMuestra(nombre, bytes, modificado) {
    return new File([bytes], nombre, { lastModified: modificado || 1700000000000 });
  }

  caso('navegador: workers', 'el worker arranca con sus tres bibliotecas', async function (E) {
    var p = GC.pool.crear({ ruta: '../js/trabajadores/extractor.js', n: 1 });
    try {
      var r = await p.enviarA(0, { t: 'ping' });
      A.afirmar(r.pdf === true, 'pdf.js no se cargó en el worker');
      A.afirmar(r.mammoth === true, 'mammoth no se cargó en el worker');
      A.afirmar(r.fflate === true, 'fflate no se cargó en el worker');
    } finally { p.terminar(); }
  });

  caso('navegador: workers', 'analiza un PDF de principio a fin fuera del hilo de UI', async function (E) {
    var p = GC.pool.crear({ ruta: '../js/trabajadores/extractor.js', n: 1 });
    try {
      var bytes = await E.muestra('revision.pdf');
      var fases = [];
      var r = await p.encolar({
        t: 'analizar',
        base: { ruta: 'revision.pdf', nombre: 'revision.pdf', tamano: bytes.length, modificado: 1, archivo: archivoDeMuestra('revision.pdf', bytes) },
        previo: null
      }, function (prog) { fases.push(prog.fase); });
      A.afirmar(!r.error, 'el worker devolvió error: ' + r.error);
      A.igual(r.doc.estado, 'ok', r.doc.error || '');
      A.contiene(r.doc.texto, 'hipertension arterial resistente');
      A.afirmar(r.doc.terminos.length > 5, 'deberían salir términos del PDF');
      A.afirmar(r.doc.hash && r.doc.hash.length > 10, 'falta la huella');
      A.afirmar(fases.length >= 3, 'el progreso debe informar por fases, llegaron: ' + fases.join(','));
    } finally { p.terminar(); }
  });

  caso('navegador: workers', 'el segundo análisis del mismo contenido se salta', async function (E) {
    var p = GC.pool.crear({ ruta: '../js/trabajadores/extractor.js', n: 1 });
    try {
      var bytes = await E.muestra('notas-clinicas.md');
      var base = { ruta: 'a.md', nombre: 'a.md', tamano: bytes.length, modificado: 1, archivo: archivoDeMuestra('a.md', bytes) };
      var r1 = await p.encolar({ t: 'analizar', base: base, previo: null });
      var r2 = await p.encolar({ t: 'analizar', base: base, previo: { hash: r1.doc.hash } });
      A.afirmar(r2.saltado === true, 'con el mismo hash no debe volver a analizarse');
    } finally { p.terminar(); }
  });

  caso('navegador: workers', 'descomprime un ZIP y conserva la jerarquía', async function (E) {
    var p = GC.pool.crear({ ruta: '../js/trabajadores/extractor.js', n: 1 });
    try {
      var bytes = await E.muestra('boveda.zip');
      var copia = bytes.slice().buffer;
      var r = await p.enviarAlZip({ t: 'zip-cargar', buffer: copia }, null, [copia]);
      A.afirmar(r.t === 'zip-inventario', 'el ZIP no se pudo abrir: ' + (r.error || ''));
      A.igual(r.entradas.length, 3, 'el ZIP de muestra tiene tres archivos');
      var rutas = r.entradas.map(function (e) { return e.ruta; }).sort();
      A.igual(rutas[0], 'clinica/notas-clinicas.md', 'la carpeta raíz del ZIP debe recortarse');
      var uno = r.entradas.filter(function (e) { return /notas-clinicas/.test(e.ruta); })[0];
      var doc = await p.enviarAlZip({ t: 'zip-analizar', zipId: r.id, base: uno, previo: null });
      A.igual(doc.doc.estado, 'ok');
      A.contiene(doc.doc.texto, 'espironolactona');
      await p.enviarAlZip({ t: 'zip-liberar', zipId: r.id });
    } finally { p.terminar(); }
  });

  caso('navegador: almacén', 'guarda y recupera documentos, config e instantáneas', async function () {
    var marca = 'prueba/' + Date.now() + '.md';
    await GC.almacen.guardarLote('documentos', [{ ruta: marca, nombre: 'x.md', ext: 'md', tamano: 1, modificado: 1, hash: 'h', estado: 'ok', texto: 'hola', terminos: [] }]);
    var leido = await GC.almacen.leer('documentos', marca);
    A.igual(leido.texto, 'hola');
    await GC.almacen.config('prueba-clave', { a: 1 });
    A.igual((await GC.almacen.config('prueba-clave')).a, 1);
    var antes = (await GC.almacen.listarInstantaneas()).length;
    await GC.almacen.guardarInstantanea({ fecha: Date.now(), version: 'prueba', documentos: 1, conceptos: 0, palabras: 0 });
    A.igual((await GC.almacen.listarInstantaneas()).length, antes + 1);
    await GC.almacen.borrarLote('documentos', [marca]);
    A.afirmar((await GC.almacen.leer('documentos', marca)) === undefined, 'el borrado debe ser efectivo');
  });

  caso('navegador: ciclo completo', 'indexa, reindexa sin cambios y detecta una modificación', async function (E) {
    // Se trabaja sobre rutas con prefijo propio para no tocar el índice real.
    var prefijo = 'PRUEBA-' + Date.now() + '/';
    var p = GC.pool.crear({ ruta: '../js/trabajadores/extractor.js', n: 2 });
    try {
      var md = await E.muestra('notas-clinicas.md');
      var txt = await E.muestra('lecture-notes.txt');
      var png = await E.muestra('ecocardiograma.png');

      function inventario(contenidoMd, modificado) {
        return [
          { ruta: prefijo + 'notas.md', nombre: 'notas.md', tamano: contenidoMd.length, modificado: modificado, archivo: archivoDeMuestra('notas.md', contenidoMd, modificado) },
          { ruta: prefijo + 'lecture.txt', nombre: 'lecture.txt', tamano: txt.length, modificado: 1, archivo: archivoDeMuestra('lecture.txt', txt) },
          { ruta: prefijo + 'eco.png', nombre: 'eco.png', tamano: png.length, modificado: 1, archivo: archivoDeMuestra('eco.png', png) }
        ];
      }

      var r1 = await GC.indexador.indexar({ inventario: inventario(md, 1), pool: p, indicePrevio: GC.indice.vacio(), origen: 'prueba' });
      A.igual(r1.indice.docs.length, 3, 'deben entrar los tres archivos');
      A.igual(r1.cambios.nuevos.length, 3);
      A.afirmar(r1.indice.vocabulario.length > 10, 'el vocabulario debe poblarse');
      var eco = r1.indice.docs.filter(function (d) { return /eco\.png$/.test(d.ruta); })[0];
      A.igual(eco.estado, 'solo-metadatos', 'la imagen entra como huérfano, no se omite');

      // Segunda pasada idéntica: nada debe re-analizarse.
      var r2 = await GC.indexador.indexar({ inventario: inventario(md, 1), pool: p, indicePrevio: r1.indice, origen: 'prueba' });
      A.igual(r2.analizados, 0, 'sin cambios no debe analizarse nada');
      A.igual(r2.cambios.nuevos.length, 0);
      A.igual(r2.indice.docs.length, 3);

      // Tercera pasada con el markdown modificado.
      var modificado = new TextEncoder().encode(
        new TextDecoder().decode(md) + '\n\nNuevo apartado sobre amiloidosis cardiaca y su diagnostico diferencial.\n');
      var r3 = await GC.indexador.indexar({ inventario: inventario(modificado, 999), pool: p, indicePrevio: r2.indice, origen: 'prueba' });
      A.igual(r3.analizados, 1, 'sólo el archivo modificado debe re-analizarse');
      A.igual(r3.cambios.modificados.length, 1);
      A.afirmar(r3.cambios.conceptosNuevos.some(function (c) { return c.lema === 'amiloidosis'; }),
        'el concepto añadido debe aparecer como nuevo');

      // Cuarta pasada con un archivo menos.
      var reducido = inventario(modificado, 999).slice(0, 2);
      var r4 = await GC.indexador.indexar({ inventario: reducido, pool: p, indicePrevio: r3.indice, origen: 'prueba' });
      A.igual(r4.cambios.eliminados.length, 1);
      A.igual(r4.indice.docs.length, 2);

      // Limpieza: el índice de prueba no debe quedar en el almacén.
      await GC.almacen.borrarLote('documentos', r3.indice.docs.map(function (d) { return d.ruta; }));
    } finally { p.terminar(); }
  });

  caso('navegador: rendimiento', 'la reconstrucción desde IndexedDB baja de 2 s', async function () {
    var t0 = performance.now();
    await GC.almacen.leer('grafo', GC.indice.CLAVE);
    var ms = performance.now() - t0;
    A.afirmar(ms < 2000, 'la lectura del índice tardó ' + Math.round(ms) + ' ms');
  });

  GC.casosNavegador = { casos: casos };
})(typeof self !== 'undefined' ? self : globalThis);
