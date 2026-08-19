(function () {
  'use strict';

  var GC = self.GC;
  var V = GC.ui.vistas, F = GC.ui.formato;
  var $ = function (id) { return document.getElementById(id); };

  var estado = {
    deteccion: null,
    verificaciones: {},
    rutaElegida: 'C',
    indice: GC.indice.vacio(),
    pool: null,
    handleCarpeta: null,
    arranqueMs: null,
    ultimaDuracion: null,
    trabajando: false
  };

  function decir(texto) { $('estado-global').textContent = texto; }

  // ------------------------------------------------------------------ pool
  function pool() {
    if (!estado.pool) {
      var n = Math.max(2, Math.min(4, (navigator.hardwareConcurrency || 2) - 1));
      estado.pool = GC.pool.crear({ ruta: 'js/trabajadores/extractor.js', n: n });
    }
    return estado.pool;
  }

  async function aplicarVacias() {
    var texto = (await GC.almacen.config('vaciasPropias')) || '';
    var lista = texto.split(/[\n,;]+/).map(function (s) { return s.trim(); }).filter(Boolean);
    $('vacias-propias').value = texto;
    var r = await pool().difundir({ t: 'vacias', lista: lista });
    $('vacias-cuenta').textContent = (r[0] && r[0].n ? r[0].n : 0) + ' palabras vacías activas';
    return lista;
  }

  // ------------------------------------------------- pintado del estado actual
  function repintar(cambios, duracionMs) {
    var est = GC.indice.estadisticas(estado.indice);
    V.mostrar('bloque-resumen', true);
    V.cifras(est, duracionMs != null ? duracionMs : estado.ultimaDuracion);

    var nProblemas = V.errores(estado.indice.docs);
    V.mostrar('bloque-errores', estado.indice.docs.length > 0);

    V.mostrar('bloque-inventario', estado.indice.docs.length > 0);
    V.inventario(estado.indice.docs, $('filtro-inventario').value);

    V.mostrar('bloque-conceptos', estado.indice.vocabulario.length > 0);
    V.conceptos(estado.indice.vocabulario);

    if (cambios) { V.mostrar('bloque-cambios', true); V.cambios(cambios, estado.indice.fecha); }

    V.barra(est, (est.porEstado.error || 0), estado.arranqueMs, duracionMs != null ? duracionMs : estado.ultimaDuracion);
    refrescarHistorial();
    refrescarEspacio();
  }

  async function refrescarHistorial() {
    var lista = await GC.almacen.listarInstantaneas();
    V.mostrar('bloque-historial', lista.length > 0);
    if (lista.length) V.historial(lista);
  }

  async function refrescarEspacio() {
    var e = await GC.almacen.espacio();
    var persistente = (navigator.storage && navigator.storage.persisted) ? await navigator.storage.persisted() : false;
    $('nota-espacio').textContent = e
      ? 'Usado ' + F.bytes(e.usage) + ' de ' + F.bytes(e.quota) + ' disponibles. ' +
        'Almacenamiento ' + (persistente ? 'persistente (el sistema no lo borrará por espacio).' : 'no persistente: iPadOS puede vaciarlo si falta espacio.')
      : 'El navegador no informa del espacio disponible.';
  }

  // ------------------------------------------------------------- capacidades
  async function detectarYPintar() {
    estado.deteccion = GC.capacidades.detectar();
    estado.verificaciones = (await GC.almacen.config('verificaciones')) || {};
    estado.rutaElegida = GC.capacidades.elegirRuta(estado.deteccion, estado.verificaciones);
    V.rutas(estado.deteccion, estado.verificaciones, estado.rutaElegida);
    V.entorno(estado.deteccion);
    pintarAccionesIngesta();
  }

  // La verificación empírica de la ruta B: se abre el selector y se comprueba
  // si los archivos traen webkitRelativePath. Es la única forma de saberlo.
  async function verificarB() {
    if (!estado.deteccion.rutas.B.disponible) {
      alert('El sondeo ya descartó la ruta B en este navegador: la propiedad webkitdirectory no existe.');
      return;
    }
    decir('esperando selección de carpeta…');
    var archivos = await GC.ingesta.pedirArchivos({ directorio: true });
    if (!archivos.length) { decir('verificación cancelada'); return; }
    var conRuta = archivos.filter(function (f) { return f.webkitRelativePath && f.webkitRelativePath.indexOf('/') !== -1; }).length;
    var funciona = conRuta > 0;
    estado.verificaciones.B = funciona;
    await GC.almacen.config('verificaciones', estado.verificaciones);
    estado.rutaElegida = GC.capacidades.elegirRuta(estado.deteccion, estado.verificaciones);
    V.rutas(estado.deteccion, estado.verificaciones, estado.rutaElegida);
    pintarAccionesIngesta();
    decir(funciona
      ? 'ruta B verificada: ' + archivos.length + ' archivos con jerarquía de carpetas'
      : 'ruta B NO funciona aquí: llegaron ' + archivos.length + ' archivos sin ruta relativa');

    if (funciona && confirm('La ruta B funciona: llegaron ' + archivos.length + ' archivos.\n\n¿Indexar ahora esta carpeta?')) {
      await indexarInventario(GC.ingesta.inventarioDesdeArchivos(archivos, 'B'), 'carpeta (ruta B)');
    }
  }

  // ------------------------------------------------------------------ ingesta
  function pintarAccionesIngesta() {
    var acciones = [];
    var d = estado.deteccion, v = estado.verificaciones;

    if (d.rutas.A.disponible && v.A !== false) acciones.push('<button class="primario" id="btn-a">Elegir carpeta (ruta A)</button>');
    if (d.rutas.B.disponible && v.B !== false) acciones.push('<button' + (estado.rutaElegida === 'B' ? ' class="primario"' : '') + ' id="btn-b">Elegir carpeta (ruta B)</button>');
    acciones.push('<button' + (estado.rutaElegida === 'C' ? ' class="primario"' : '') + ' id="btn-c">Elegir archivos sueltos</button>');
    acciones.push('<button id="btn-zip">Cargar un ZIP</button>');
    if (estado.indice.docs.length) acciones.push('<button id="btn-reindexar">Volver a comparar la carpeta</button>');

    $('acciones-ingesta').innerHTML = acciones.join('');

    var nota = estado.indice.origen
      ? 'Última fuente indexada: <b>' + F.escapar(estado.indice.origen) + '</b>, el ' + F.fecha(estado.indice.fecha) + '. ' +
        'Se compara por ruta, tamaño, fecha y huella de contenido: sólo se vuelve a leer lo que cambió.'
      : 'Elige la carpeta que quieres convertir en grafo. Ninguna app de iPadOS puede leer «todo el iPad»: ' +
        'el alcance máximo es la carpeta que otorgues aquí (iCloud Drive, «En mi iPad», una bóveda de Obsidian…).';
    $('nota-ingesta').innerHTML = nota;

    if ($('btn-a')) $('btn-a').onclick = ingestaA;
    if ($('btn-b')) $('btn-b').onclick = ingestaB;
    if ($('btn-c')) $('btn-c').onclick = ingestaC;
    if ($('btn-zip')) $('btn-zip').onclick = ingestaZip;
    if ($('btn-reindexar')) $('btn-reindexar').onclick = reindexar;
  }

  async function ingestaA() {
    try {
      var handle = await GC.ingesta.elegirCarpetaA();
      estado.handleCarpeta = handle;
      await GC.almacen.config('carpetaA', handle);
      await recorrerYIndexarA(handle);
    } catch (e) {
      if (e && e.name === 'AbortError') { decir('selección cancelada'); return; }
      decir('error al elegir carpeta: ' + e.message);
    }
  }

  async function recorrerYIndexarA(handle) {
    decir('recorriendo la carpeta…');
    V.mostrar('bloque-progreso', true);
    var inventario = await GC.ingesta.inventarioA(handle, function (n) { decir('recorriendo… ' + n + ' archivos'); });
    await indexarInventario(inventario, (handle.name || 'carpeta') + ' (ruta A)');
  }

  async function ingestaB() {
    decir('esperando selección de carpeta…');
    var archivos = await GC.ingesta.pedirArchivos({ directorio: true });
    if (!archivos.length) { decir('selección cancelada'); return; }
    var conRuta = archivos.some(function (f) { return f.webkitRelativePath; });
    estado.verificaciones.B = conRuta;
    await GC.almacen.config('verificaciones', estado.verificaciones);
    if (!conRuta) {
      V.rutas(estado.deteccion, estado.verificaciones, GC.capacidades.elegirRuta(estado.deteccion, estado.verificaciones));
      decir('la ruta B no devolvió rutas de carpeta: se indexan como archivos sueltos');
    }
    await indexarInventario(GC.ingesta.inventarioDesdeArchivos(archivos, conRuta ? 'B' : 'C'), conRuta ? 'carpeta (ruta B)' : 'archivos sueltos');
  }

  async function ingestaC() {
    decir('esperando selección de archivos…');
    var archivos = await GC.ingesta.pedirArchivos({ multiple: true });
    if (!archivos.length) { decir('selección cancelada'); return; }
    await indexarInventario(GC.ingesta.inventarioDesdeArchivos(archivos, 'C'), 'archivos sueltos (ruta C)');
  }

  async function ingestaZip() {
    decir('esperando el archivo ZIP…');
    var archivos = await GC.ingesta.pedirArchivos({ multiple: false, aceptar: '.zip,application/zip' });
    if (!archivos.length) { decir('selección cancelada'); return; }
    var zip = archivos[0];
    if (!GC.ingesta.esZip(zip)) { decir('el archivo elegido no es un ZIP'); return; }

    V.mostrar('bloque-progreso', true);
    decir('descomprimiendo ' + F.bytes(zip.size) + '…');
    var buffer = await zip.arrayBuffer();
    var r = await pool().enviarAlZip({ t: 'zip-cargar', buffer: buffer }, null, [buffer]);
    if (r.t === 'zip-error') { decir(r.error); V.mostrar('bloque-progreso', false); return; }

    var inventario = r.entradas.map(function (e) { return Object.assign({}, e, { origen: 'C-zip' }); });
    await indexarInventario(inventario, zip.name + ' (ZIP)', r.id);
    await pool().enviarAlZip({ t: 'zip-liberar', zipId: r.id });
  }

  async function reindexar() {
    if (estado.handleCarpeta) {
      var permiso = await GC.ingesta.permisoA(estado.handleCarpeta, true);
      if (permiso !== 'granted') { decir('permiso denegado sobre la carpeta guardada'); return; }
      await recorrerYIndexarA(estado.handleCarpeta);
      return;
    }
    // Sin handle persistente hay que volver a elegir: es el coste de la ruta B/C.
    if (estado.deteccion.rutas.B.disponible && estado.verificaciones.B !== false) await ingestaB();
    else await ingestaC();
  }

  // --------------------------------------------------------------- indexación
  async function indexarInventario(inventario, origen, zipId) {
    if (estado.trabajando) return;
    if (!inventario.length) { decir('no llegó ningún archivo indexable'); return; }
    estado.trabajando = true;
    V.mostrar('bloque-progreso', true);

    var resumenIngesta = GC.ingesta.resumirInventario(inventario);
    decir('indexando ' + F.numero(resumenIngesta.total) + ' archivos · ' + F.bytes(resumenIngesta.bytes));

    try {
      var r = await GC.indexador.indexar({
        inventario: inventario,
        pool: pool(),
        indicePrevio: estado.indice,
        origen: origen,
        zipId: zipId,
        alProgresar: V.progreso
      });
      estado.indice = r.indice;
      estado.ultimaDuracion = r.duracionMs;
      await GC.indexador.guardarInstantanea(r.indice);
      repintar(r.cambios, r.duracionMs);
      decir('índice al día · ' + F.numero(r.analizados) + ' analizados, ' +
            F.numero(r.sinCambios) + ' sin cambios, ' + F.duracion(r.duracionMs));
      if (resumenIngesta.noDescargados) {
        decir('índice al día · atención: ' + resumenIngesta.noDescargados + ' archivos no están descargados de iCloud');
      }
    } catch (e) {
      decir('fallo en la indexación: ' + (e && e.message || e));
      console.error(e);
    } finally {
      estado.trabajando = false;
      V.mostrar('bloque-progreso', false);
      pintarAccionesIngesta();
    }
  }

  // -------------------------------------------------------------------- inicio
  async function iniciar() {
    var t0 = performance.now();
    decir('leyendo el índice guardado…');

    try {
      var guardado = await GC.almacen.leer('grafo', GC.indice.CLAVE);
      if (guardado) estado.indice = guardado;
    } catch (e) {
      decir('no se pudo abrir el índice: ' + e.message);
    }

    estado.arranqueMs = performance.now() - t0;
    repintar(null, null);
    decir(estado.indice.docs.length
      ? 'índice reconstruido en ' + F.duracion(estado.arranqueMs)
      : 'sin índice todavía');

    await detectarYPintar();
    await aplicarVacias();

    // Ruta A: si el permiso sobre la carpeta sigue vigente, el re-escaneo es
    // automático. Si caducó, se pide con un solo toque — no se hace en silencio.
    try {
      var handle = await GC.almacen.config('carpetaA');
      if (handle) {
        estado.handleCarpeta = handle;
        var permiso = await GC.ingesta.permisoA(handle, false);
        if (permiso === 'granted') {
          decir('carpeta autorizada: re-escaneando…');
          await recorrerYIndexarA(handle);
        } else {
          decir('la carpeta guardada necesita reconfirmación');
          $('acciones-ingesta').insertAdjacentHTML('afterbegin',
            '<button class="primario" id="btn-reconfirmar">Reconfirmar «' + F.escapar(handle.name || 'carpeta') + '»</button>');
          $('btn-reconfirmar').onclick = async function () {
            var p = await GC.ingesta.permisoA(handle, true);
            if (p === 'granted') await recorrerYIndexarA(handle);
            else decir('permiso denegado');
          };
        }
      }
    } catch (e) { /* la carpeta guardada ya no es válida */ }

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('sw.js').catch(function () { /* sin modo avión */ });
    }
  }

  // ------------------------------------------------------------------ eventos
  $('filtro-inventario').addEventListener('input', function () {
    V.inventario(estado.indice.docs, this.value);
  });
  $('btn-verificar-b').addEventListener('click', verificarB);
  $('btn-reset-verif').addEventListener('click', async function () {
    estado.verificaciones = {};
    await GC.almacen.config('verificaciones', {});
    await detectarYPintar();
    decir('verificaciones olvidadas');
  });
  $('btn-guardar-vacias').addEventListener('click', async function () {
    await GC.almacen.config('vaciasPropias', $('vacias-propias').value);
    await aplicarVacias();
    decir('palabras vacías guardadas · reindexa para aplicarlas al texto ya leído');
  });
  $('btn-persistir').addEventListener('click', async function () {
    if (!navigator.storage || !navigator.storage.persist) { decir('este navegador no ofrece almacenamiento persistente'); return; }
    var ok = await navigator.storage.persist();
    decir(ok ? 'almacenamiento persistente concedido' : 'almacenamiento persistente denegado');
    refrescarEspacio();
  });
  $('btn-borrar').addEventListener('click', async function () {
    if (!confirm('Se borra el índice completo: documentos, grafo e instantáneas.\nTus archivos originales no se tocan.\n\n¿Continuar?')) return;
    await GC.almacen.borrarTodo();
    estado.indice = GC.indice.vacio();
    estado.handleCarpeta = null;
    location.reload();
  });

  iniciar();
})();
