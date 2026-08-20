(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.ui = raiz.GC.ui || {}).mapa = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  var GC = raiz.GC;
  var F = GC.ui.formato;
  var COL = GC.ui.colores;
  var esc = F.escapar;
  var $ = function (id) { return document.getElementById(id); };

  // Controlador del lienzo: arma los datos de la capa activa, arranca el
  // simulador en su worker, conecta los gestos y mantiene el bucle de dibujo.
  //
  // El bucle no dibuja siempre: sólo cuando algo cambió. Un iPad que redibuja
  // diez mil nodos sesenta veces por segundo sin que nada se mueva se calienta
  // y gasta batería para no enseñar nada nuevo.

  var TOPE_INICIAL = 320;        // nodos visibles al abrir, por centralidad
  var MS_TRANSICION = 650;       // duración del cambio entre instantáneas

  var M = {
    capas: null, resumen: null,
    capa: 'conceptos', dim: 2,
    datos: null, visible: null,
    lienzo: null, sim: null, gestos: null,
    seleccion: -1, rutaOrigen: -1,
    montado: false, dibujarPendiente: true, bucle: null,
    filtros: { umbral: 0.12, tipo: '', desdeFecha: 0, busqueda: '' },
    instantaneas: [], indiceTiempo: -1,
    transicion: null
  };

  // ---------------------------------------------------------------- datos ---
  // Cada capa produce el mismo trío: nodos, aristas y los vectores que dan
  // color y tamaño. El resto del lienzo no sabe qué capa está dibujando.
  function armarConceptos(capas) {
    var c = capas.conceptos;
    return {
      tipoNodo: 'concepto',
      nodos: c.nodos,
      aristas: c.aristas,
      comunidad: c.comunidad,
      intermediacion: c.intermediacion,
      grado: c.grado
    };
  }

  function armarDocumentos(capas) {
    var d = capas.documentos;
    var aristas = d.dependencias.map(function (e) {
      return { a: e.a, b: e.b, peso: e.peso || 1, tipo: e.tipo, detalle: e.detalle };
    }).concat(d.afinidades.map(function (e) {
      return { a: e.a, b: e.b, peso: e.coseno, tipo: 'afinidad', coseno: e.coseno };
    }));
    // Sin comunidades propias, los documentos se colorean por carpeta: es la
    // agrupación que el usuario ya conoce porque la creó él.
    var carpetas = new Map();
    var comunidad = new Int32Array(d.nodos.length);
    d.nodos.forEach(function (n, i) {
      var carpeta = n.ruta.indexOf('/') === -1 ? '' : n.ruta.slice(0, n.ruta.lastIndexOf('/'));
      if (!carpetas.has(carpeta)) carpetas.set(carpeta, carpetas.size);
      comunidad[i] = carpetas.get(carpeta);
    });
    var grado = new Float32Array(d.nodos.length);
    aristas.forEach(function (e) { grado[e.a]++; grado[e.b]++; });
    return {
      tipoNodo: 'documento', nodos: d.nodos, aristas: aristas,
      comunidad: comunidad, intermediacion: null, grado: grado, carpetas: carpetas
    };
  }

  function armarMixta(capas) {
    var c = capas.conceptos, d = capas.documentos;
    var desplazamiento = c.nodos.length;
    var nodos = c.nodos.concat(d.nodos.map(function (n) {
      return { id: n.id + desplazamiento, ruta: n.ruta, nombre: n.nombre, estado: n.estado,
               palabras: n.palabras, esDocumento: true };
    }));
    var aristas = c.aristas.map(function (e) { return { a: e.a, b: e.b, peso: e.peso }; });
    d.dependencias.forEach(function (e) {
      aristas.push({ a: e.a + desplazamiento, b: e.b + desplazamiento, peso: e.peso || 1, tipo: e.tipo });
    });
    (capas.mixta.pertenencias || []).forEach(function (p) {
      aristas.push({ a: p.concepto, b: p.documento + desplazamiento, peso: 0.6, tipo: 'pertenencia' });
    });
    var comunidad = new Int32Array(nodos.length);
    var intermediacion = new Float64Array(nodos.length);
    for (var i = 0; i < c.nodos.length; i++) {
      comunidad[i] = c.comunidad[i];
      intermediacion[i] = c.intermediacion[i];
    }
    for (var j = 0; j < d.nodos.length; j++) comunidad[j + desplazamiento] = -1;
    var grado = new Float32Array(nodos.length);
    aristas.forEach(function (e) { grado[e.a]++; grado[e.b]++; });
    return {
      tipoNodo: 'mixto', nodos: nodos, aristas: aristas, comunidad: comunidad,
      intermediacion: intermediacion, grado: grado, desplazamiento: desplazamiento
    };
  }

  function armarCapa(capa) {
    if (capa === 'documentos') return armarDocumentos(M.capas);
    if (capa === 'mixta') return armarMixta(M.capas);
    return armarConceptos(M.capas);
  }

  // Visibilidad inicial: sólo lo más central. El resto existe y se despliega
  // con doble toque; cargar diez mil nodos de golpe no es un mapa, es niebla.
  function visibilidadInicial(datos) {
    var n = datos.nodos.length;
    var v = new Uint8Array(n);
    if (n <= TOPE_INICIAL) { v.fill(1); return v; }
    var orden = [];
    for (var i = 0; i < n; i++) {
      var puntuacion = datos.intermediacion ? datos.intermediacion[i] : 0;
      orden.push([i, puntuacion, datos.nodos[i].frecuencia || datos.nodos[i].palabras || 0]);
    }
    orden.sort(function (a, b) { return b[1] - a[1] || b[2] - a[2]; });
    for (var k = 0; k < TOPE_INICIAL; k++) v[orden[k][0]] = 1;
    return v;
  }

  // --------------------------------------------------------------- filtros ---
  function aplicarFiltros() {
    var datos = M.datos;
    var n = datos.nodos.length;
    var busqueda = M.filtros.busqueda.trim().toLowerCase();
    var resaltados = busqueda ? new Set() : null;

    for (var i = 0; i < n; i++) {
      var nodo = datos.nodos[i];
      var pasa = true;
      if (M.filtros.tipo && (nodo.ext || '') !== M.filtros.tipo && nodo.ruta) pasa = false;
      if (M.filtros.desdeFecha && nodo.modificado && nodo.modificado < M.filtros.desdeFecha) pasa = false;
      if (!pasa) M.visible[i] = 0;
      if (busqueda && M.visible[i]) {
        var texto = (nodo.forma || nodo.lema || nodo.ruta || '').toLowerCase();
        if (texto.indexOf(busqueda) !== -1) resaltados.add(i);
      }
    }
    M.lienzo.vista.resaltados = resaltados && resaltados.size ? resaltados : null;
    M.lienzo.vista.umbralAfinidad = M.filtros.umbral;
    enviarVisibles(0.25);
    pedirDibujo();
  }

  function enviarVisibles(calor) {
    if (!M.sim) return;
    M.sim.postMessage({ t: 'visibles', visible: M.visible, calor: calor });
  }

  // ------------------------------------------------------------- simulador ---
  function arrancarSimulador(posicionesPrevias) {
    if (M.sim) M.sim.terminate();
    M.sim = new Worker('js/trabajadores/simulador.js');
    var datos = M.datos;
    var m = datos.aristas.length;
    var a = new Int32Array(m), b = new Int32Array(m), peso = new Float32Array(m);
    for (var i = 0; i < m; i++) {
      a[i] = datos.aristas[i].a; b[i] = datos.aristas[i].b;
      peso[i] = Math.min(4, datos.aristas[i].peso || 1);
    }
    M.sim.onmessage = function (ev) {
      var msg = ev.data;
      if (msg.t === 'posiciones') {
        M.lienzo.actualizarPosiciones(msg.pos);
        M.sim.postMessage({ t: 'devolver', pos: msg.pos }, [msg.pos.buffer]);
        pedirDibujo();
      } else if (msg.t === 'reposo') {
        actualizarHud();
      }
    };
    M.sim.postMessage({
      t: 'iniciar', n: datos.nodos.length, dim: M.dim,
      aristaA: a, aristaB: b, aristaPeso: peso,
      comunidad: datos.comunidad ? Int32Array.from(datos.comunidad) : null,
      grado: datos.grado ? Float32Array.from(datos.grado) : null,
      visible: M.visible,
      posiciones: posicionesPrevias || null
    });
  }

  // ---------------------------------------------------------------- dibujo ---
  function pedirDibujo() { M.dibujarPendiente = true; }

  function bucleDibujo() {
    M.bucle = requestAnimationFrame(bucleDibujo);
    if (M.transicion) avanzarTransicion();
    if (!M.dibujarPendiente) return;
    M.dibujarPendiente = false;
    M.lienzo.dibujar();
    actualizarHud();
  }

  function actualizarHud() {
    var v = M.lienzo.vista;
    var visibles = 0;
    for (var i = 0; i < M.visible.length; i++) if (M.visible[i]) visibles++;
    $('hud').textContent =
      v.fps + ' fps · ' + v.ultimoDibujoMs.toFixed(1) + ' ms\n' +
      F.numero(v.dibujados.nodos) + ' nodos · ' + F.numero(v.dibujados.aristas) + ' aristas\n' +
      F.numero(visibles) + ' de ' + F.numero(M.datos.nodos.length) + ' visibles · ×' +
      M.lienzo.camara.estado.escala.toFixed(2);

    var ocultos = M.datos.nodos.length - visibles;
    $('aviso-lienzo').hidden = ocultos <= 0;
    if (ocultos > 0) {
      $('aviso-lienzo').textContent = F.numero(ocultos) +
        ' nodos ocultos por centralidad o por filtro · doble toque en un nodo para desplegar sus vecinos';
    }
  }

  // ------------------------------------------------------------- selección ---
  function seleccionar(id) {
    M.seleccion = id;
    M.lienzo.vista.seleccion = id;
    if (id < 0) { $('ficha-nodo').hidden = true; pedirDibujo(); return; }
    pintarFicha(id);
    pedirDibujo();
  }

  function pintarFicha(id) {
    var nodo = M.datos.nodos[id];
    var caja = $('ficha-nodo');
    var esDoc = M.datos.tipoNodo === 'documento' || nodo.esDocumento;
    var filas = [];
    var titulo, color;

    if (esDoc) {
      titulo = M.lienzo.etiquetaDe(id);
      color = M.lienzo.colorDe(id);
      filas.push(['ruta', nodo.ruta]);
      filas.push(['estado', nodo.estado || '—']);
      filas.push(['palabras', F.numero(nodo.palabras || 0)]);
      if (nodo.idioma) filas.push(['idioma', nodo.idioma]);
    } else {
      titulo = nodo.forma || nodo.lema;
      color = M.lienzo.colorDe(id);
      filas.push(['frecuencia', F.numero(nodo.frecuencia || 0)]);
      filas.push(['documentos', F.numero(nodo.docs || 0)]);
      if (M.datos.intermediacion) filas.push(['intermediación', M.datos.intermediacion[id].toFixed(4)]);
      if (M.datos.grado) filas.push(['grado', F.numero(M.datos.grado[id])]);
      if (M.datos.comunidad && M.datos.comunidad[id] >= 0) filas.push(['tema', '#' + M.datos.comunidad[id]]);
    }

    var acciones = ['<button class="menor" data-accion="vecindario">Aislar vecindario</button>'];
    if (esDoc) acciones.push('<button class="menor" data-accion="abrir">Abrir documento</button>');
    else acciones.push('<button class="menor" data-accion="documentos">Ver documentos</button>');
    acciones.push('<button class="menor" data-accion="ruta">' +
      (M.rutaOrigen === id ? 'Origen fijado' : 'Origen de ruta') + '</button>');

    caja.innerHTML =
      '<h4><span class="chip" style="background:' + color + '"></span>' + esc(titulo) + '</h4>' +
      '<dl>' + filas.map(function (f) {
        return '<dt>' + esc(f[0]) + '</dt><dd>' + esc(f[1]) + '</dd>';
      }).join('') + '</dl>' +
      '<div class="acciones">' + acciones.join('') + '</div>';
    caja.hidden = false;
    caja.dataset.nodo = String(id);
  }

  // Vecinos ocultos de un nodo: lo que el doble toque despliega.
  function vecinosDe(id) {
    var lista = [];
    for (var i = 0; i < M.datos.aristas.length; i++) {
      var e = M.datos.aristas[i];
      if (e.a === id) lista.push(e.b);
      else if (e.b === id) lista.push(e.a);
    }
    return lista;
  }

  function expandir(id) {
    if (id < 0) return;
    var vecinos = vecinosDe(id);
    var nuevos = 0;
    for (var i = 0; i < vecinos.length; i++) {
      if (!M.visible[vecinos[i]]) { M.visible[vecinos[i]] = 1; nuevos++; }
    }
    if (!nuevos) { anunciar('Ese nodo no tiene vecinos ocultos.'); return; }
    // Los recién aparecidos entran con una animación corta: sin ella, seis
    // nodos nuevos surgen de golpe y el ojo pierde de vista dónde estaba.
    entrarConTransicion(vecinos);
    enviarVisibles(0.5);
    anunciar(F.plural(nuevos, 'vecino') + ' desplegado' + (nuevos === 1 ? '' : 's') + '.');
  }

  function aislarVecindario(id) {
    var conjunto = new Set(vecinosDe(id));
    conjunto.add(id);
    for (var i = 0; i < M.visible.length; i++) M.visible[i] = conjunto.has(i) ? 1 : 0;
    enviarVisibles(0.7);
    setTimeout(function () { M.lienzo.encuadrar(); pedirDibujo(); }, 260);
    anunciar('Vecindario aislado: ' + F.plural(conjunto.size, 'nodo') + '.');
  }

  function ocultarRama(id) {
    var vecinos = vecinosDe(id);
    var ocultados = 0;
    for (var i = 0; i < vecinos.length; i++) {
      // Sólo se oculta lo que cuelga de este nodo: si un vecino tiene otras
      // conexiones visibles, se queda. Ocultar una rama no es podar el árbol.
      var otros = vecinosDe(vecinos[i]).filter(function (v) { return v !== id && M.visible[v]; });
      if (!otros.length && M.visible[vecinos[i]]) { M.visible[vecinos[i]] = 0; ocultados++; }
    }
    enviarVisibles(0.3);
    anunciar(ocultados ? F.plural(ocultados, 'nodo') + ' ocultado' + (ocultados === 1 ? '' : 's') + '.'
                       : 'Todos sus vecinos cuelgan también de otros nodos.');
  }

  function anunciar(texto) {
    var a = $('grafo-estado');
    if (a) a.textContent = texto;
  }

  // ------------------------------------------------------- menú contextual ---
  function abrirMenu(id, punto) {
    if (id < 0) { cerrarMenu(); return; }
    var menu = $('menu-contextual');
    var esDoc = M.datos.tipoNodo === 'documento' || M.datos.nodos[id].esDocumento;
    var opciones = [];
    if (esDoc) opciones.push(['abrir', 'Abrir documento']);
    else opciones.push(['documentos', 'Ver sus documentos']);
    opciones.push(['vecindario', 'Aislar vecindario']);
    opciones.push(['fijar', 'Fijar posición']);
    opciones.push(['rama', 'Ocultar rama']);
    opciones.push(['ruta', 'Definir como origen de ruta']);

    menu.innerHTML = opciones.map(function (o) {
      return '<button data-accion="' + o[0] + '" data-nodo="' + id + '">' + esc(o[1]) + '</button>';
    }).join('');
    menu.hidden = false;
    var caja = $('mapa').getBoundingClientRect();
    var lienzoCaja = M.lienzo.canvas.getBoundingClientRect();
    var x = Math.min(punto.x, lienzoCaja.width - 220);
    var y = Math.min(punto.y, lienzoCaja.height - opciones.length * 44 - 10);
    menu.style.left = Math.max(6, x) + 'px';
    menu.style.top = Math.max(6, y) + 'px';
  }

  function cerrarMenu() { $('menu-contextual').hidden = true; }

  async function ejecutarAccion(accion, id) {
    cerrarMenu();
    if (id < 0 || id == null) return;
    var nodo = M.datos.nodos[id];
    var esDoc = M.datos.tipoNodo === 'documento' || nodo.esDocumento;

    if (accion === 'abrir' && esDoc) {
      await GC.ui.visor.abrir(nodo.ruta, { capas: M.capas, conceptoId: -1 });
      return;
    }
    if (accion === 'documentos' && !esDoc) {
      var rutas = nodo.rutas || [];
      if (!rutas.length) { anunciar('Ese concepto no tiene documentos registrados.'); return; }
      // Se abre el primero y se subrayan las oraciones que produjeron sus
      // aristas: ésta es la trazabilidad completa, del panel a la línea.
      await GC.ui.visor.abrir(rutas[0], { capas: M.capas, conceptoId: id });
      return;
    }
    if (accion === 'vecindario') { aislarVecindario(id); return; }
    if (accion === 'rama') { ocultarRama(id); return; }
    if (accion === 'fijar') {
      var p = M.lienzo.posicionDe(id);
      M.sim.postMessage({ t: 'fijar', id: id, x: p.x, y: p.y, z: p.z });
      anunciar('Posición fijada. Arrástralo para moverlo.');
      return;
    }
    if (accion === 'ruta') { definirOrigenRuta(id); return; }
  }

  // -------------------------------------------------------- ruta de lectura ---
  function definirOrigenRuta(id) {
    if (M.rutaOrigen < 0) {
      M.rutaOrigen = id;
      anunciar('Origen: ' + M.lienzo.etiquetaDe(id) + '. Ahora elige el destino.');
      if (M.seleccion === id) pintarFicha(id);
      return;
    }
    if (M.rutaOrigen === id) { M.rutaOrigen = -1; anunciar('Origen anulado.'); return; }
    calcularRuta(M.rutaOrigen, id);
    M.rutaOrigen = -1;
  }

  function calcularRuta(origen, destino) {
    var r = GC.grafo.ruta.calcular(M.datos.nodos.length, M.datos.aristas, origen, destino, {
      umbralAfinidad: M.filtros.umbral
    });
    if (!r.existe) { M.lienzo.vista.ruta = null; anunciar(r.motivo); pedirDibujo(); return; }

    // Todo el camino se hace visible: una ruta con tramos ocultos no es un plan.
    for (var i = 0; i < r.camino.length; i++) M.visible[r.camino[i]] = 1;
    enviarVisibles(0.3);
    M.lienzo.vista.ruta = r.camino;
    pedirDibujo();

    var etiquetas = r.camino.map(function (id) { return M.lienzo.etiquetaDe(id); });
    var plan = '';
    if (M.datos.tipoNodo === 'concepto') {
      var docs = [];
      var usados = new Set();
      r.camino.forEach(function (id) {
        (M.datos.nodos[id].rutas || []).some(function (ruta) {
          if (usados.has(ruta)) return false;
          usados.add(ruta); docs.push(ruta); return true;
        });
      });
      plan = docs.length ? ' · plan de lectura: ' + docs.join(' → ') : '';
    }
    anunciar('Ruta de ' + F.plural(r.camino.length, 'paso') + ': ' + etiquetas.join(' → ') +
      ' (coste ' + r.coste.toFixed(2) + ')' + plan);
  }

  // ------------------------------------------------------------ transición ---
  // Entrada suave de nodos nuevos, que es lo que hace legible tanto el
  // despliegue de vecinos como el salto entre instantáneas.
  function entrarConTransicion(ids) {
    var mapa = new Map();
    ids.forEach(function (id) { mapa.set(id, 0); });
    M.transicion = { desde: Date.now(), nodos: mapa };
    M.lienzo.vista.alfaNodo = mapa;
    pedirDibujo();
  }

  function avanzarTransicion() {
    var t = (Date.now() - M.transicion.desde) / MS_TRANSICION;
    if (t >= 1) {
      M.transicion = null;
      M.lienzo.vista.alfaNodo = null;
      pedirDibujo();
      return;
    }
    var alfa = t * t * (3 - 2 * t);   // suavizado
    M.transicion.nodos.forEach(function (_, id) { M.transicion.nodos.set(id, alfa); });
    pedirDibujo();
  }

  // -------------------------------------------------------------- controles ---
  function conectarControles() {
    var lienzoEl = M.lienzo.canvas;

    M.gestos = GC.lienzo.gestos.conectar(lienzoEl, {
      alToque: function (id) { cerrarMenu(); seleccionar(id); },
      alDobleToque: function (id) { cerrarMenu(); if (id >= 0) { seleccionar(id); expandir(id); } },
      alSostener: function (id, p) { if (id >= 0) { seleccionar(id); abrirMenu(id, p); } },
      alTomarNodo: function (id) {
        var p = M.lienzo.posicionDe(id);
        M.sim.postMessage({ t: 'fijar', id: id, x: p.x, y: p.y, z: p.z });
      },
      alArrastrarNodo: function (id, p) {
        var mundo = M.lienzo.camara.aMundo(p.x, p.y);
        M.sim.postMessage({ t: 'fijar', id: id, x: mundo.x, y: mundo.y, z: mundo.z });
        M.sim.postMessage({ t: 'calentar', valor: 0.25 });
      },
      alSoltarNodo: function (id, anclar) { M.sim.postMessage({ t: 'soltar', id: id, anclar: anclar }); },
      alCambiarVista: function () { cerrarMenu(); pedirDibujo(); }
    }, {
      nodoEn: function (x, y) { return M.lienzo.nodoEn(x, y); },
      zoom: function (f, x, y) { M.lienzo.camara.zoom(f, x, y); },
      desplazar: function (dx, dy) { M.lienzo.camara.desplazar(dx, dy); }
    });

    $('ficha-nodo').addEventListener('click', function (ev) {
      var b = ev.target.closest('button[data-accion]');
      if (!b) return;
      ejecutarAccion(b.dataset.accion, parseInt(this.dataset.nodo, 10));
    });
    $('menu-contextual').addEventListener('click', function (ev) {
      var b = ev.target.closest('button[data-accion]');
      if (!b) return;
      ejecutarAccion(b.dataset.accion, parseInt(b.dataset.nodo, 10));
    });

    $('conmutador-capas').addEventListener('click', function (ev) {
      var b = ev.target.closest('button[data-capa]');
      if (!b) return;
      cambiarCapa(b.dataset.capa);
    });

    $('panel-pestanas').addEventListener('click', function (ev) {
      var b = ev.target.closest('button[data-pestana]');
      if (!b) return;
      Array.prototype.forEach.call(this.querySelectorAll('button'), function (x) {
        x.setAttribute('aria-selected', String(x === b));
      });
      Array.prototype.forEach.call(document.querySelectorAll('.pestana'), function (x) {
        x.hidden = x.dataset.pestana !== b.dataset.pestana;
      });
    });

    $('btn-dimension').addEventListener('click', function () {
      M.dim = M.dim === 2 ? 3 : 2;
      this.textContent = M.dim === 2 ? '2D' : '3D';
      this.setAttribute('aria-pressed', String(M.dim === 3));
      M.lienzo.grafo.dim = M.dim;
      M.lienzo.camara.dimension(M.dim);
      M.lienzo.cargar(Object.assign({}, M.datos, { dim: M.dim, visible: M.visible }));
      arrancarSimulador(null);
      anunciar(M.dim === 3 ? 'Tres dimensiones: arrastra el fondo para mirar alrededor.' : 'Dos dimensiones.');
    });

    $('umbral-afinidad').addEventListener('input', function () {
      M.filtros.umbral = parseFloat(this.value);
      $('umbral-valor').textContent = M.filtros.umbral.toFixed(2);
      M.lienzo.vista.umbralAfinidad = M.filtros.umbral;
      if (GC.ui.vistasGrafo && M.resumen) {
        GC.ui.vistasGrafo.afinidades(M.resumen.documentos.afinidades, M.filtros.umbral);
      }
      pedirDibujo();
    });

    $('busqueda').addEventListener('input', function () {
      M.filtros.busqueda = this.value;
      aplicarFiltros();
      if (this.value.trim() && M.lienzo.vista.resaltados) {
        anunciar(F.plural(M.lienzo.vista.resaltados.size, 'coincidencia') + '.');
      }
    });

    $('filtro-tipo').addEventListener('change', function () {
      M.filtros.tipo = this.value;
      reconstruirVisibilidad();
    });

    $('filtro-fecha').addEventListener('input', function () {
      var rango = M.rangoFechas;
      if (!rango) return;
      var f = parseInt(this.value, 10) / 100;
      M.filtros.desdeFecha = f <= 0 ? 0 : rango.min + (rango.max - rango.min) * f;
      $('fecha-valor').textContent = M.filtros.desdeFecha ? F.fecha(M.filtros.desdeFecha) : 'todo';
      reconstruirVisibilidad();
    });

    $('btn-encuadrar').addEventListener('click', function () { M.lienzo.encuadrar(); pedirDibujo(); });

    $('btn-plegar-panel').addEventListener('click', function () {
      var plegado = $('mapa').classList.toggle('panel-plegado');
      this.setAttribute('aria-expanded', String(!plegado));
      this.title = plegado ? 'Desplegar el panel' : 'Plegar el panel';
      // El lienzo cambia de ancho: hay que rehacer el búfer o se ve estirado.
      setTimeout(function () { M.lienzo.redimensionar(); pedirDibujo(); }, 30);
    });

    $('btn-ruta').addEventListener('click', function () {
      if (M.seleccion < 0) { anunciar('Selecciona primero un nodo, y luego el destino.'); return; }
      definirOrigenRuta(M.seleccion);
    });

    $('btn-cerrar-visor').addEventListener('click', function () { GC.ui.visor.cerrar(); });

    $('deslizador-tiempo').addEventListener('input', function () {
      irAInstantanea(parseInt(this.value, 10));
    });
    $('btn-tiempo-actual').addEventListener('click', function () {
      $('deslizador-tiempo').value = String(M.instantaneas.length);
      irAInstantanea(M.instantaneas.length);
    });

    raiz.addEventListener('resize', function () {
      M.lienzo.redimensionar();
      pedirDibujo();
    });
  }

  function reconstruirVisibilidad() {
    var base = visibilidadInicial(M.datos);
    M.visible.set(base);
    aplicarFiltros();
  }

  function cambiarCapa(capa) {
    if (capa === M.capa) return;
    M.capa = capa;
    Array.prototype.forEach.call($('conmutador-capas').querySelectorAll('button'), function (b) {
      b.setAttribute('aria-selected', String(b.dataset.capa === capa));
    });
    M.datos = armarCapa(capa);
    M.visible = visibilidadInicial(M.datos);
    M.seleccion = -1; M.rutaOrigen = -1;
    $('ficha-nodo').hidden = true;
    M.lienzo.vista.ruta = null;
    M.lienzo.vista.seleccion = -1;
    M.lienzo.cargar(Object.assign({}, M.datos, { dim: M.dim, visible: M.visible }));
    arrancarSimulador(null);
    prepararFiltroTipo();
    setTimeout(function () { M.lienzo.encuadrar(); pedirDibujo(); }, 400);
    anunciar('Capa de ' + capa + ' · ' + F.plural(M.datos.nodos.length, 'nodo') + '.');
  }

  function prepararFiltroTipo() {
    var sel = $('filtro-tipo');
    var extensiones = new Map();
    var fechas = [];
    M.datos.nodos.forEach(function (n) {
      if (n.ext) extensiones.set(n.ext, (extensiones.get(n.ext) || 0) + 1);
      if (n.modificado) fechas.push(n.modificado);
    });
    sel.innerHTML = '<option value="">todos</option>' +
      Array.from(extensiones.entries()).sort(function (a, b) { return b[1] - a[1]; })
        .map(function (e) { return '<option value="' + esc(e[0]) + '">.' + esc(e[0]) + ' (' + e[1] + ')</option>'; }).join('');
    sel.disabled = extensiones.size === 0;
    M.rangoFechas = fechas.length ? { min: Math.min.apply(null, fechas), max: Math.max.apply(null, fechas) } : null;
    $('filtro-fecha').disabled = !M.rangoFechas;
  }

  // ------------------------------------------------------------- el tiempo ---
  async function cargarInstantaneas() {
    M.instantaneas = (await GC.almacen.listarInstantaneas()).filter(function (i) { return i.grafo; });
    var deslizador = $('deslizador-tiempo');
    var hayTiempo = M.instantaneas.length >= 1;
    $('tiempo').hidden = !hayTiempo;
    // La ficha del nodo tiene que subir para no quedar debajo de la línea.
    document.querySelector('.mapa-lienzo').classList.toggle('con-tiempo', hayTiempo);
    deslizador.max = String(M.instantaneas.length);
    deslizador.value = String(M.instantaneas.length);
    M.indiceTiempo = M.instantaneas.length;
    $('tiempo-etiqueta').textContent = 'estado actual';
    $('tiempo-marca-inicio').textContent = M.instantaneas.length ? F.fecha(M.instantaneas[0].fecha) : '';
    pintarEvolucion();
  }

  function pintarEvolucion() {
    var lista = M.instantaneas;
    if (!lista.length) {
      $('cifras-evolucion').innerHTML = '<div class="cifra"><b>0</b><span>instantáneas</span></div>';
      $('tabla-historial').innerHTML = '<tbody><tr><td class="vacio">Todavía no hay historia que recorrer.</td></tr></tbody>';
      return;
    }
    var primera = lista[0], ultima = lista[lista.length - 1];
    $('cifras-evolucion').innerHTML = [
      ['Instantáneas', F.numero(lista.length)],
      ['Conceptos', F.numero(ultima.conceptos) + (lista.length > 1 ? ' (' + (ultima.conceptos - primera.conceptos >= 0 ? '+' : '') + F.numero(ultima.conceptos - primera.conceptos) + ')' : '')],
      ['Documentos', F.numero(ultima.documentos)],
      ['Modularidad', ultima.grafo && ultima.grafo.modularidad != null ? ultima.grafo.modularidad.toFixed(3) : '—']
    ].map(function (c) {
      return '<div class="cifra"><b>' + esc(c[1]) + '</b><span>' + esc(c[0]) + '</span></div>';
    }).join('');

    $('tabla-historial').innerHTML =
      '<thead><tr><th>Fecha</th><th>Docs</th><th>Conceptos</th><th>Q</th></tr></thead><tbody>' +
      lista.slice().reverse().slice(0, 40).map(function (i) {
        return '<tr><td class="ruta">' + esc(F.fecha(i.fecha)) + '</td>' +
          '<td class="num">' + F.numero(i.documentos) + '</td>' +
          '<td class="num">' + F.numero(i.conceptos) + '</td>' +
          '<td class="num">' + (i.grafo && i.grafo.modularidad != null ? i.grafo.modularidad.toFixed(3) : '—') + '</td></tr>';
      }).join('') + '</tbody>';
  }

  // Viajar a una instantánea: se rearma el grafo de aquel día y se conservan
  // las posiciones de los conceptos que ya existían, para que el cambio se lea
  // como un movimiento y no como otro dibujo.
  function irAInstantanea(indice) {
    M.indiceTiempo = indice;
    if (indice >= M.instantaneas.length) {
      $('tiempo-etiqueta').textContent = 'estado actual';
      M.capa = null;
      cambiarCapa('conceptos');
      return;
    }
    var inst = M.instantaneas[indice];
    if (!inst || !inst.grafo) return;

    var posicionesPrevias = null;
    var previos = new Map();
    if (M.datos && M.datos.tipoNodo === 'concepto') {
      for (var i = 0; i < M.datos.nodos.length; i++) {
        previos.set(M.datos.nodos[i].lema, M.lienzo.posicionDe(i));
      }
    }

    var g = inst.grafo;
    var nodos = g.nodos.map(function (n, i) {
      return { id: i, lema: n.lema, forma: n.forma, frecuencia: n.frecuencia, docs: 0, rutas: [] };
    });
    var aristas = g.aristas.map(function (a) { return { a: a[0], b: a[1], peso: a[2] }; });
    var comunidad = new Int32Array(nodos.length);
    var intermediacion = new Float64Array(nodos.length);
    g.nodos.forEach(function (n, i) { comunidad[i] = n.comunidad; intermediacion[i] = n.intermediacion; });
    var grado = new Float32Array(nodos.length);
    aristas.forEach(function (e) { grado[e.a]++; grado[e.b]++; });

    M.datos = { tipoNodo: 'concepto', nodos: nodos, aristas: aristas,
                comunidad: comunidad, intermediacion: intermediacion, grado: grado };
    M.visible = new Uint8Array(nodos.length).fill(1);

    // Semilla de posiciones: los que ya estaban, donde estaban.
    posicionesPrevias = new Float32Array(nodos.length * M.dim);
    var nuevos = [];
    nodos.forEach(function (n, i) {
      var p = previos.get(n.lema);
      if (p) {
        posicionesPrevias[i * M.dim] = p.x;
        posicionesPrevias[i * M.dim + 1] = p.y;
        if (M.dim === 3) posicionesPrevias[i * M.dim + 2] = p.z;
      } else nuevos.push(i);
    });
    if (!previos.size) posicionesPrevias = null;

    M.seleccion = -1;
    M.lienzo.vista.seleccion = -1;
    M.lienzo.vista.ruta = null;
    $('ficha-nodo').hidden = true;
    M.lienzo.cargar(Object.assign({}, M.datos, { dim: M.dim, visible: M.visible }));
    arrancarSimulador(posicionesPrevias);
    if (nuevos.length && previos.size) entrarConTransicion(nuevos);

    $('tiempo-etiqueta').textContent = F.fecha(inst.fecha) + ' · ' +
      F.numero(inst.conceptos) + ' conceptos · ' + F.numero(inst.documentos) + ' documentos' +
      (g.modularidad != null ? ' · Q = ' + g.modularidad.toFixed(3) : '');
    anunciar('Viajando al ' + F.fecha(inst.fecha) + '. ' +
      (nuevos.length && previos.size ? F.plural(nuevos.length, 'concepto') + ' que no existían ahora.' : ''));
  }

  // ---------------------------------------------------------------- montaje ---
  async function montar(capas, resumen) {
    M.capas = capas;
    M.resumen = resumen;
    M.datos = armarCapa(M.capa);
    M.visible = visibilidadInicial(M.datos);

    if (!M.montado) {
      M.lienzo = GC.lienzo.lienzo.crear($('lienzo'));
      conectarControles();
      M.montado = true;
    } else {
      M.lienzo.redimensionar();
    }

    M.lienzo.vista.umbralAfinidad = M.filtros.umbral;
    M.lienzo.cargar(Object.assign({}, M.datos, { dim: M.dim, visible: M.visible }));
    prepararFiltroTipo();
    arrancarSimulador(null);
    await cargarInstantaneas();

    if (M.bucle) cancelAnimationFrame(M.bucle);
    bucleDibujo();
    setTimeout(function () { M.lienzo.encuadrar(); pedirDibujo(); }, 500);
    anunciar('Lienzo listo · ' + F.plural(M.datos.nodos.length, 'nodo') + ' en la capa de conceptos.');
  }

  function desmontar() {
    if (M.bucle) cancelAnimationFrame(M.bucle);
    if (M.sim) { M.sim.terminate(); M.sim = null; }
    M.bucle = null;
  }

  return {
    montar: montar, desmontar: desmontar, estado: M,
    irAInstantanea: irAInstantanea, recargarInstantaneas: cargarInstantaneas,
    TOPE_INICIAL: TOPE_INICIAL
  };
});
