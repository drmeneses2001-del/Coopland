(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.lienzo = raiz.GC.lienzo || {}).lienzo = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  var CAM = raiz.GC.lienzo.camara;
  var COL = raiz.GC.ui.colores;

  // Renderizador en canvas 2D. No es SVG a propósito: con miles de nodos, cada
  // elemento del DOM cuesta memoria y recálculo de estilo, y el iPad se rinde
  // mucho antes de los mil. Aquí todo es un solo elemento y un bucle de dibujo.
  //
  // Lo que sostiene los cuadros por segundo no es el trazado en sí, son tres
  // cosas: recortar por la ventana visible, agrupar por color en un solo
  // camino, y bajar el detalle cuando se ve el grafo entero —a esa escala
  // nadie distingue una arista de peso 1, así que no se dibuja—.

  function crear(canvas, opciones) {
    opciones = opciones || {};
    var ctx = canvas.getContext('2d', { alpha: false });
    var camara = CAM.crear({ ancho: canvas.clientWidth || 800, alto: canvas.clientHeight || 600 });

    var g = {
      n: 0, dim: 2,
      pos: new Float32Array(0),
      nodos: [], aristas: [],
      comunidad: null, intermediacion: null, grado: null,
      visible: null,
      tipoNodo: 'concepto'      // 'concepto' | 'documento' | 'mixto'
    };

    var vista = {
      seleccion: -1,
      resaltados: null,         // Set de ids a iluminar
      ruta: null,               // arreglo ordenado de ids
      etiquetasMax: 60,
      mostrarEtiquetas: true,
      umbralAfinidad: 0.12,
      alfaNodo: null,           // Map id -> opacidad, durante las transiciones
      dpr: 1,
      ultimoDibujoMs: 0,
      cuadros: 0, fps: 0, ultimoFps: 0,
      dibujados: { nodos: 0, aristas: 0 }
    };

    var estilo = {
      fondo: '#16181b', linea: '#33373d', texto: '#e7e9ec', tenue: '#7f858e',
      activo: '#6db6e8', ok: '#5fd39b', aviso: '#e0b451'
    };

    // Los colores se leen del CSS: el lienzo no puede tener su propia paleta o
    // dejaría de pertenecer al mismo instrumento que el resto de la interfaz.
    function leerEstilo() {
      if (typeof getComputedStyle === 'undefined') return;
      var cs = getComputedStyle(document.documentElement);
      function v(nombre, respaldo) {
        var x = cs.getPropertyValue(nombre);
        return x && x.trim() ? x.trim() : respaldo;
      }
      estilo.fondo = v('--fondo', estilo.fondo);
      estilo.linea = v('--linea', estilo.linea);
      estilo.texto = v('--texto', estilo.texto);
      estilo.tenue = v('--texto-tenue', estilo.tenue);
      estilo.activo = v('--activo', estilo.activo);
      estilo.ok = v('--ok', estilo.ok);
      estilo.aviso = v('--aviso', estilo.aviso);
    }

    function redimensionar() {
      var dpr = Math.min(2, (raiz.devicePixelRatio || 1));   // más de 2 no se ve y cuesta el doble
      var ancho = canvas.clientWidth || canvas.parentNode.clientWidth || 800;
      var alto = canvas.clientHeight || 420;
      vista.dpr = dpr;
      canvas.width = Math.round(ancho * dpr);
      canvas.height = Math.round(alto * dpr);
      camara.tamano(ancho, alto);
    }

    // --------------------------------------------------------------- datos ---
    function cargar(datos) {
      g.n = datos.nodos.length;
      g.dim = datos.dim === 3 ? 3 : 2;
      g.nodos = datos.nodos;
      g.aristas = datos.aristas || [];
      g.comunidad = datos.comunidad || null;
      g.intermediacion = datos.intermediacion || null;
      g.grado = datos.grado || null;
      g.tipoNodo = datos.tipoNodo || 'concepto';
      g.visible = datos.visible || new Uint8Array(g.n).fill(1);
      if (!g.pos || g.pos.length !== g.n * g.dim) g.pos = new Float32Array(g.n * g.dim);
      camara.dimension(g.dim);
      calcularMaximos();
      construirIndiceEspacial();
    }

    function actualizarPosiciones(pos) {
      if (!pos || !pos.length) return;
      if (pos.length !== g.pos.length) g.pos = new Float32Array(pos.length);
      g.pos.set(pos);
      construirIndiceEspacial();
    }

    // --------------------------------------------- índice para el dedo ------
    // Rejilla en coordenadas del mundo. Sin ella, cada toque recorrería los
    // diez mil nodos y el arrastre se sentiría pegajoso.
    var indice = { celdas: null, lado: 1, minX: 0, minY: 0, nx: 1, ny: 1 };

    function construirIndiceEspacial() {
      if (!g.n) { indice.celdas = null; return; }
      var caja = CAM.cajaDe(g.pos, g.n, g.dim, g.visible);
      var lado = Math.max(8, (caja.maxX - caja.minX + caja.maxY - caja.minY) / Math.max(8, Math.sqrt(g.n) * 2));
      var nx = Math.max(1, Math.min(400, Math.ceil((caja.maxX - caja.minX) / lado) + 1));
      var ny = Math.max(1, Math.min(400, Math.ceil((caja.maxY - caja.minY) / lado) + 1));
      var celdas = new Array(nx * ny);
      for (var i = 0; i < g.n; i++) {
        if (!g.visible[i]) continue;
        var cx = Math.min(nx - 1, Math.max(0, Math.floor((g.pos[i * g.dim] - caja.minX) / lado)));
        var cy = Math.min(ny - 1, Math.max(0, Math.floor((g.pos[i * g.dim + 1] - caja.minY) / lado)));
        var c = cy * nx + cx;
        if (!celdas[c]) celdas[c] = [];
        celdas[c].push(i);
      }
      indice = { celdas: celdas, lado: lado, minX: caja.minX, minY: caja.minY, nx: nx, ny: ny };
    }

    // --------------------------------------------------------------- estilo ---
    // El tamaño del nodo es la intermediación: responde a «¿por dónde pasa el
    // discurso?», que es la pregunta que hace útil al grafo.
    //
    // La escala es RELATIVA al máximo de este grafo, no absoluta. La
    // intermediación normalizada divide por el número de pares posibles, así
    // que en un grafo de treinta nodos vale cien veces más que en uno de tres
    // mil: con una fórmula absoluta, el mismo código dibujaba puntos invisibles
    // en un corpus grande y globos que se comían la pantalla en uno pequeño.
    var RADIO_MIN = 2.6, RADIO_MAX = 13;
    var maximos = { inter: 0, frecuencia: 1, palabras: 1 };

    function calcularMaximos() {
      maximos = { inter: 0, frecuencia: 1, palabras: 1 };
      for (var i = 0; i < g.n; i++) {
        if (g.intermediacion && g.intermediacion[i] > maximos.inter) maximos.inter = g.intermediacion[i];
        var f = g.nodos[i].frecuencia || 0;
        if (f > maximos.frecuencia) maximos.frecuencia = f;
        var p = g.nodos[i].palabras || 0;
        if (p > maximos.palabras) maximos.palabras = p;
      }
    }

    function radioDe(i) {
      if (g.tipoNodo === 'documento') {
        var pal = (g.nodos[i].palabras || 0) / maximos.palabras;
        return RADIO_MIN + (RADIO_MAX - RADIO_MIN) * Math.sqrt(Math.max(0, Math.min(1, pal)));
      }
      var frac = 0;
      if (maximos.inter > 0 && g.intermediacion) frac = g.intermediacion[i] / maximos.inter;
      // Raíz cuadrada: el área del círculo crece con el cuadrado del radio, así
      // que sin ella el nodo más central se ve muchísimo más grande de lo que
      // dice su cifra.
      var r = RADIO_MIN + (RADIO_MAX - RADIO_MIN) * Math.sqrt(Math.max(0, Math.min(1, frac)));
      // Suelo por frecuencia: un concepto muy repetido nunca es un punto perdido
      // aunque no intermedie nada.
      var suelo = RADIO_MIN + 2.4 * Math.sqrt((g.nodos[i].frecuencia || 0) / maximos.frecuencia);
      return Math.max(r, suelo);
    }

    function colorDe(i) {
      if (g.tipoNodo === 'documento') {
        var estadoDoc = g.nodos[i].estado;
        if (estadoDoc === 'error') return estilo.tenue;
        if (estadoDoc !== 'ok') return estilo.aviso;
        return estilo.activo;
      }
      return COL.deComunidad(g.comunidad ? g.comunidad[i] : 0);
    }

    // Los nodos no crecen linealmente con el zoom: si lo hicieran, al acercarse
    // se convertirían en manchas que tapan sus propias aristas. Crecen a la
    // raíz, y con techo.
    function escalaRadio() {
      return Math.max(0.55, Math.min(1.9, Math.sqrt(camara.estado.escala)));
    }

    // Nivel de detalle: cuánto se puede callar sin mentir. A poca escala, las
    // aristas flojas son ruido gris; a mucha escala se dibujan todas.
    function nivelDetalle() {
      var e = camara.estado.escala;
      var visibles = 0;
      for (var i = 0; i < g.n; i++) if (g.visible[i]) visibles++;
      var pesoMin = 0;
      if (visibles > 400) pesoMin = e < 0.35 ? 3 : (e < 0.8 ? 2 : (e < 1.6 ? 1.2 : 0));
      else if (visibles > 120) pesoMin = e < 0.5 ? 1.5 : 0;
      return {
        pesoMinArista: pesoMin,
        etiquetas: vista.mostrarEtiquetas && e > 0.45,
        radioMinEtiqueta: e > 1.6 ? 0 : (e > 0.9 ? 3.4 : 5)
      };
    }

    // --------------------------------------------------------------- dibujo ---
    function dibujar() {
      var t0 = (typeof performance !== 'undefined' ? performance.now() : Date.now());
      var dpr = vista.dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = estilo.fondo;
      ctx.fillRect(0, 0, camara.estado.ancho, camara.estado.alto);
      if (!g.n) { vista.ultimoDibujoMs = 0; return; }

      var lod = nivelDetalle();
      var ventana = camara.ventana(120);
      var proyectado = new Float32Array(g.n * 3);   // x, y, k
      var dentro = new Uint8Array(g.n);
      var i;

      for (i = 0; i < g.n; i++) {
        if (!g.visible[i]) continue;
        var mx = g.pos[i * g.dim], my = g.pos[i * g.dim + 1];
        var mz = g.dim === 3 ? g.pos[i * g.dim + 2] : 0;
        if (mx < ventana.minX || mx > ventana.maxX || my < ventana.minY || my > ventana.maxY) continue;
        var p = camara.proyectar(mx, my, mz);
        proyectado[i * 3] = p.x; proyectado[i * 3 + 1] = p.y; proyectado[i * 3 + 2] = p.k;
        dentro[i] = 1;
      }

      var cuentaAristas = dibujarAristas(lod, proyectado, dentro);
      var cuentaNodos = dibujarNodos(proyectado, dentro);
      if (vista.ruta && vista.ruta.length > 1) dibujarRuta(proyectado, dentro);
      if (lod.etiquetas) dibujarEtiquetas(lod, proyectado, dentro);
      if (vista.seleccion >= 0 && dentro[vista.seleccion]) dibujarSeleccion(proyectado);

      vista.dibujados = { nodos: cuentaNodos, aristas: cuentaAristas };
      vista.ultimoDibujoMs = (typeof performance !== 'undefined' ? performance.now() : Date.now()) - t0;
      contarCuadro();
    }

    function contarCuadro() {
      var ahora = (typeof performance !== 'undefined' ? performance.now() : Date.now());
      vista.cuadros++;
      if (ahora - vista.ultimoFps >= 1000) {
        vista.fps = Math.round(vista.cuadros * 1000 / (ahora - vista.ultimoFps));
        vista.cuadros = 0; vista.ultimoFps = ahora;
      }
    }

    function dibujarAristas(lod, proyectado, dentro) {
      var dibujadas = 0;
      var resaltadas = vista.resaltados;

      // Dos pasadas por estilo de trazo: sólida para lo que alguien escribió,
      // punteada para lo que sólo se parece. Mezclarlas fue el error que este
      // proyecto no quiere repetir.
      var grupos = { solida: [], punteada: [] };
      for (var e = 0; e < g.aristas.length; e++) {
        var ar = g.aristas[e];
        var a = ar.a, b = ar.b;
        if (!dentro[a] && !dentro[b]) continue;
        if (!g.visible[a] || !g.visible[b]) continue;
        if (ar.tipo === 'afinidad') {
          if ((ar.coseno || 0) < vista.umbralAfinidad) continue;
          grupos.punteada.push(e);
        } else {
          if ((ar.peso || 1) < lod.pesoMinArista && !(resaltadas && (resaltadas.has(a) || resaltadas.has(b)))) continue;
          grupos.solida.push(e);
        }
      }

      ctx.lineCap = 'round';
      ['solida', 'punteada'].forEach(function (clase) {
        var ids = grupos[clase];
        if (!ids.length) return;
        ctx.setLineDash(clase === 'punteada' ? [2, 4] : []);

        // Agrupar por color en un solo camino: cambiar de estilo es lo caro,
        // no trazar la línea.
        var porColor = new Map();
        for (var k = 0; k < ids.length; k++) {
          var ar2 = g.aristas[ids[k]];
          var mismaComunidad = g.comunidad && g.comunidad[ar2.a] === g.comunidad[ar2.b];
          var iluminada = resaltadas && (resaltadas.has(ar2.a) || resaltadas.has(ar2.b));
          var color = iluminada ? estilo.activo
            : (g.tipoNodo === 'concepto' && mismaComunidad ? COL.deComunidad(g.comunidad[ar2.a]) : estilo.linea);
          var alfa = iluminada ? 0.75 : (clase === 'punteada' ? 0.30 : 0.22);
          var clave = color + '|' + alfa;
          if (!porColor.has(clave)) porColor.set(clave, { color: color, alfa: alfa, ids: [] });
          porColor.get(clave).ids.push(ids[k]);
        }

        porColor.forEach(function (grupo) {
          ctx.globalAlpha = grupo.alfa;
          ctx.strokeStyle = grupo.color;
          ctx.lineWidth = 1;
          ctx.beginPath();
          for (var j = 0; j < grupo.ids.length; j++) {
            var ar3 = g.aristas[grupo.ids[j]];
            ctx.moveTo(proyectado[ar3.a * 3], proyectado[ar3.a * 3 + 1]);
            ctx.lineTo(proyectado[ar3.b * 3], proyectado[ar3.b * 3 + 1]);
            dibujadas++;
          }
          ctx.stroke();
        });
      });

      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      return dibujadas;
    }

    function dibujarNodos(proyectado, dentro) {
      var porColor = new Map();
      var cuenta = 0;
      for (var i = 0; i < g.n; i++) {
        if (!dentro[i]) continue;
        var color = colorDe(i);
        var apagado = vista.resaltados && vista.resaltados.size && !vista.resaltados.has(i);
        // La opacidad se agrupa en cinco escalones. Es lo que permite que un
        // nodo entre con animación sin romper el agrupado por color, que es de
        // donde salen los cuadros por segundo.
        var alfa = apagado ? 0.20 : 1;
        if (vista.alfaNodo && vista.alfaNodo.has(i)) alfa *= vista.alfaNodo.get(i);
        var escalon = Math.max(1, Math.round(alfa * 5));
        var clave = color + '|' + escalon;
        if (!porColor.has(clave)) porColor.set(clave, { color: color, alfa: escalon / 5, ids: [] });
        porColor.get(clave).ids.push(i);
        cuenta++;
      }

      porColor.forEach(function (grupo) {
        ctx.globalAlpha = grupo.alfa;
        ctx.fillStyle = grupo.color;
        ctx.beginPath();
        for (var j = 0; j < grupo.ids.length; j++) {
          var i2 = grupo.ids[j];
          var r = radioDe(i2) * escalaRadio() * proyectado[i2 * 3 + 2];
          if (r < 0.6) r = 0.6;
          var x = proyectado[i2 * 3], y = proyectado[i2 * 3 + 1];
          ctx.moveTo(x + r, y);
          ctx.arc(x, y, r, 0, Math.PI * 2);
        }
        ctx.fill();
      });
      ctx.globalAlpha = 1;
      return cuenta;
    }

    function dibujarEtiquetas(lod, proyectado, dentro) {
      var candidatos = [];
      for (var i = 0; i < g.n; i++) {
        if (!dentro[i]) continue;
        var r = radioDe(i) * escalaRadio();
        if (r < lod.radioMinEtiqueta) continue;
        if (vista.resaltados && vista.resaltados.size && !vista.resaltados.has(i)) continue;
        candidatos.push([i, r]);
      }
      candidatos.sort(function (a, b) { return b[1] - a[1]; });
      candidatos = candidatos.slice(0, vista.etiquetasMax);

      ctx.font = '500 11px ui-monospace, SFMono-Regular, Menlo, monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      // Las etiquetas van con un contorno del color del fondo, no con una caja:
      // una caja por etiqueta sería otra capa de ruido sobre el grafo.
      ctx.lineJoin = 'round';
      ctx.lineWidth = 3;
      ctx.strokeStyle = estilo.fondo;
      for (var k = 0; k < candidatos.length; k++) {
        var id = candidatos[k][0];
        var texto = etiquetaDe(id);
        var x = proyectado[id * 3], y = proyectado[id * 3 + 1] - candidatos[k][1] - 7;
        ctx.strokeText(texto, x, y);
      }
      ctx.fillStyle = estilo.texto;
      for (k = 0; k < candidatos.length; k++) {
        var id2 = candidatos[k][0];
        ctx.fillText(etiquetaDe(id2), proyectado[id2 * 3], proyectado[id2 * 3 + 1] - candidatos[k][1] - 7);
      }
    }

    function etiquetaDe(i) {
      var nodo = g.nodos[i];
      if (g.tipoNodo === 'documento') {
        var partes = String(nodo.ruta || nodo.nombre || '').split('/');
        return partes[partes.length - 1].replace(/\.[A-Za-z0-9]{1,10}$/, '');
      }
      return nodo.forma || nodo.lema || '';
    }

    function dibujarSeleccion(proyectado) {
      var i = vista.seleccion;
      var r = radioDe(i) * escalaRadio() * proyectado[i * 3 + 2];
      ctx.strokeStyle = estilo.texto;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(proyectado[i * 3], proyectado[i * 3 + 1], r + 5, 0, Math.PI * 2);
      ctx.stroke();
    }

    // La ruta de lectura se dibuja por encima de todo: es una respuesta, no
    // parte del paisaje.
    function dibujarRuta(proyectado, dentro) {
      ctx.setLineDash([]);
      ctx.globalAlpha = 0.95;
      ctx.strokeStyle = estilo.ok;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      var empezado = false;
      for (var k = 0; k < vista.ruta.length; k++) {
        var id = vista.ruta[k];
        if (!dentro[id]) { empezado = false; continue; }
        var x = proyectado[id * 3], y = proyectado[id * 3 + 1];
        if (!empezado) { ctx.moveTo(x, y); empezado = true; } else ctx.lineTo(x, y);
      }
      ctx.stroke();

      ctx.fillStyle = estilo.ok;
      for (k = 0; k < vista.ruta.length; k++) {
        var id2 = vista.ruta[k];
        if (!dentro[id2]) continue;
        ctx.beginPath();
        ctx.arc(proyectado[id2 * 3], proyectado[id2 * 3 + 1], 4, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    // ------------------------------------------------------------- el dedo ---
    // Radio de acierto generoso: en un iPad el objetivo real es la yema, no el
    // píxel. Se busca en las celdas vecinas y gana el nodo más cercano.
    function nodoEn(px, py, radioPantalla) {
      if (!indice.celdas) return -1;
      radioPantalla = radioPantalla || 22;
      var mundo = camara.aMundo(px, py);
      var radioMundo = radioPantalla / camara.estado.escala;
      var cx = Math.floor((mundo.x - indice.minX) / indice.lado);
      var cy = Math.floor((mundo.y - indice.minY) / indice.lado);
      var alcance = Math.max(1, Math.ceil(radioMundo / indice.lado));
      var mejor = -1, mejorDist = Infinity;

      for (var dy = -alcance; dy <= alcance; dy++) {
        for (var dx = -alcance; dx <= alcance; dx++) {
          var x = cx + dx, y = cy + dy;
          if (x < 0 || y < 0 || x >= indice.nx || y >= indice.ny) continue;
          var celda = indice.celdas[y * indice.nx + x];
          if (!celda) continue;
          for (var k = 0; k < celda.length; k++) {
            var i = celda[k];
            if (!g.visible[i]) continue;
            var p = camara.proyectar(g.pos[i * g.dim], g.pos[i * g.dim + 1], g.dim === 3 ? g.pos[i * g.dim + 2] : 0);
            var ex = p.x - px, ey = p.y - py;
            var d2 = ex * ex + ey * ey;
            var r = Math.max(12, radioDe(i) * escalaRadio() + 10);   // el objetivo es la yema, no el píxel
            if (d2 < r * r && d2 < mejorDist) { mejorDist = d2; mejor = i; }
          }
        }
      }
      return mejor;
    }

    function posicionDe(i) {
      return {
        x: g.pos[i * g.dim], y: g.pos[i * g.dim + 1],
        z: g.dim === 3 ? g.pos[i * g.dim + 2] : 0
      };
    }

    function encuadrar() {
      camara.ajustarA(CAM.cajaDe(g.pos, g.n, g.dim, g.visible), 70);
    }

    leerEstilo();
    redimensionar();

    return {
      canvas: canvas, camara: camara, vista: vista, grafo: g,
      cargar: cargar, actualizarPosiciones: actualizarPosiciones,
      dibujar: dibujar, redimensionar: redimensionar, leerEstilo: leerEstilo,
      nodoEn: nodoEn, posicionDe: posicionDe, encuadrar: encuadrar,
      radioDe: radioDe, colorDe: colorDe, etiquetaDe: etiquetaDe,
      nivelDetalle: nivelDetalle
    };
  }

  return { crear: crear };
});
