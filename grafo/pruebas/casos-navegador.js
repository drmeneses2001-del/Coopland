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

// ============================ Fase 3: el grafo ============================
(function (raiz) {
  'use strict';
  var GC = raiz.GC;
  var A = GC.casos;
  var casos = GC.casosNavegador.casos;
  function caso(grupo, nombre, fn) { casos.push({ grupo: grupo, nombre: nombre, fn: fn }); }

  function archivo(nombre, texto, modificado) {
    return new File([texto], nombre, { lastModified: modificado || 1700000000000 });
  }

  // Corpus mínimo pero con estructura reconocible: dos territorios que apenas
  // se tocan y un documento que enlaza a otro. Basta para comprobar que las
  // tres capas dicen lo que deben decir.
  var CORPUS = [
    ['clinica/insuficiencia.md',
     '# Insuficiencia cardiaca\n\n' +
     'La insuficiencia cardiaca produce disnea de esfuerzo y edema maleolar. ' +
     'La disnea empeora con el edema pulmonar. El edema responde al diuretico. ' +
     'El diuretico alivia la disnea del paciente con insuficiencia cardiaca. ' +
     'Segun Perez, 2019 la insuficiencia cardiaca con edema exige diuretico.\n\n' +
     'Ver [[fisiopatologia]] para el mecanismo del edema.\n'],
    ['clinica/fisiopatologia.md',
     'El mecanismo del edema en la insuficiencia cardiaca depende de la presion. ' +
     'La presion venosa eleva el edema intersticial. La insuficiencia cardiaca eleva la presion. ' +
     'El edema intersticial produce disnea. Perez, 2019 describe la presion venosa y el edema.\n'],
    ['docencia/simulacion.md',
     'La simulacion clinica mejora la retencion de habilidades del residente. ' +
     'El residente entrena habilidades con simulacion de alta fidelidad. ' +
     'La retencion de habilidades depende de la repeticion del residente. ' +
     'La simulacion con repeticion mejora la retencion del residente.\n'],
    ['docencia/evaluacion.md',
     'La evaluacion del residente mide la retencion de habilidades clinicas. ' +
     'La simulacion permite la evaluacion objetiva del residente. ' +
     'La evaluacion objetiva del residente exige rubricas de habilidades.\n']
  ];

  async function sembrarCorpus(pool) {
    var inventario = CORPUS.map(function (par) {
      var bytes = new TextEncoder().encode(par[1]);
      var partes = par[0].split('/');
      return {
        ruta: par[0], nombre: partes[partes.length - 1],
        tamano: bytes.length, modificado: 1700000000000,
        archivo: archivo(partes[partes.length - 1], par[1])
      };
    });
    return await GC.indexador.indexar({
      inventario: inventario, pool: pool, indicePrevio: GC.indice.vacio(), origen: 'prueba-grafo'
    });
  }

  caso('navegador: grafo', 'construye las tres capas desde el índice guardado', async function () {
    var extractor = GC.pool.crear({ ruta: '../js/trabajadores/extractor.js', n: 2 });
    var grafista = GC.pool.crear({ ruta: '../js/trabajadores/grafista.js', n: 1 });
    try {
      await GC.almacen.vaciar('documentos');
      await GC.almacen.vaciar('grafo');
      var indexado = await sembrarCorpus(extractor);
      A.igual(indexado.indice.docs.length, 4, 'deben quedar cuatro documentos indexados');

      var fases = [];
      var r = await grafista.enviarA(0, {
        t: 'construir',
        opciones: { baseDeDatos: GC.bdPruebas, minFrecuencia: 2, minPeso: 1, sueloAfinidad: 0.05 }
      }, function (p) { fases.push(p.fase); });

      A.afirmar(r.t === 'grafo-listo', 'el worker respondió: ' + r.t + ' ' + (r.error || ''));
      A.afirmar(fases.length >= 3, 'debe informar del progreso por fases: ' + fases.join(', '));

      var c = r.resumen.conceptos;
      A.afirmar(c.nodos > 8, 'el grafo debería tener conceptos, y tiene ' + c.nodos);
      A.afirmar(c.aristas > 0, 'y aristas');
      A.afirmar(c.comunidades >= 2, 'dos territorios separados deben dar al menos dos comunidades, dio ' + c.comunidades);
      A.afirmar(c.modularidad > 0.2, 'con territorios separados Q no puede ser baja: ' + c.modularidad.toFixed(3));
      A.afirmar(!!c.diversidad.etiqueta, 'la diversidad temática debe traer etiqueta');
      A.igual(c.diversidad.q, c.modularidad, 'la cifra debe acompañar siempre a la etiqueta');

      // La partición debe separar lo clínico de lo docente.
      var capas = await GC.almacen.leer('grafo', 'capas');
      A.afirmar(!!capas, 'el grafo debe quedar guardado en IndexedDB');
      var comunidadDe = {};
      capas.conceptos.nodos.forEach(function (n, i) { comunidadDe[n.lema] = capas.conceptos.comunidad[i]; });
      if (comunidadDe.edema != null && comunidadDe.residente != null) {
        A.afirmar(comunidadDe.edema !== comunidadDe.residente,
          'el edema y el residente no pueden caer en la misma comunidad');
      }

      // Capa de documentos: el wikilink es dependencia; el parecido, afinidad.
      var d = r.resumen.documentos;
      A.afirmar(d.dependencias.some(function (e) {
        return /insuficiencia\.md/.test(e.desde + e.hasta) && /fisiopatologia\.md/.test(e.desde + e.hasta) && e.tipo === 'enlace';
      }), 'falta la dependencia por wikilink: ' + JSON.stringify(d.dependencias));
      A.afirmar(d.afinidades.length > 0, 'debe haber al menos un par con afinidad');
      A.afirmar(d.afinidades.every(function (e) { return e.desde !== e.hasta; }), 'ningún documento consigo mismo');

      // Capa mixta.
      A.afirmar(r.resumen.mixta.pertenencias > 0, 'la capa mixta debe unir documentos y conceptos');
      A.igual(r.resumen.mixta.documentosConConcepto, 4, 'los cuatro documentos tocan conceptos');

      // Trazabilidad: cada arista sabe de qué oración salió.
      var conMuestra = capas.conceptos.aristas.filter(function (e) { return e.muestras && e.muestras.length; });
      A.afirmar(conMuestra.length > 0, 'las aristas deben conservar su oración de origen');
      A.afirmar(typeof conMuestra[0].muestras[0].ruta === 'string', 'con la ruta del documento');
    } finally {
      extractor.terminar(); grafista.terminar();
      await GC.almacen.vaciar('documentos');
      await GC.almacen.vaciar('grafo');
    }
  });

  caso('navegador: grafo', 'la instantánea guarda lo justo para reanimar el pasado', async function () {
    var extractor = GC.pool.crear({ ruta: '../js/trabajadores/extractor.js', n: 2 });
    var grafista = GC.pool.crear({ ruta: '../js/trabajadores/grafista.js', n: 1 });
    try {
      await GC.almacen.vaciar('documentos');
      await sembrarCorpus(extractor);
      var r = await grafista.enviarA(0, {
        t: 'construir', opciones: { baseDeDatos: GC.bdPruebas, minFrecuencia: 2 }
      });
      var i = r.instantanea;
      A.afirmar(!!i, 'debe venir una instantánea');
      A.afirmar(i.nodos.length > 0 && i.nodos.length <= 500, 'la instantánea se recorta a 500 nodos');
      A.afirmar(typeof i.modularidad === 'number', 'con su modularidad');
      A.afirmar(i.nodos[0].comunidad != null, 'y la comunidad de cada nodo, que es el color al reanimar');
      i.aristas.forEach(function (e) {
        A.afirmar(e[0] < i.nodos.length && e[1] < i.nodos.length,
          'las aristas de la instantánea deben apuntar dentro de sus propios nodos');
      });
      A.afirmar(i.contadores.documentos === 4, 'y los contadores del momento');
    } finally {
      extractor.terminar(); grafista.terminar();
      await GC.almacen.vaciar('documentos');
      await GC.almacen.vaciar('grafo');
    }
  });

  caso('navegador: grafo', 'un índice vacío se declara vacío, no se inventa un grafo', async function () {
    var grafista = GC.pool.crear({ ruta: '../js/trabajadores/grafista.js', n: 1 });
    try {
      await GC.almacen.vaciar('documentos');
      var r = await grafista.enviarA(0, { t: 'construir', opciones: { baseDeDatos: GC.bdPruebas } });
      A.igual(r.t, 'grafo-vacio');
      A.contiene(r.motivo, 'No hay documentos');
    } finally { grafista.terminar(); }
  });
})(typeof self !== 'undefined' ? self : globalThis);
