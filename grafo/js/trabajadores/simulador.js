/* Simulación dirigida por fuerzas, en su propio worker.
   El hilo de la interfaz no calcula ni una posición: recibe un arreglo de
   coordenadas y lo dibuja. Por eso el lienzo sigue respondiendo al dedo
   mientras diez mil nodos se están acomodando.

   Repulsión por rejilla espacial con radio de corte, atracción por arista y
   gravedad hacia el centro. La rejilla vale igual para dos y tres dimensiones,
   que es lo que permite el conmutador 2D/3D sin duplicar el motor. */
'use strict';

var estado = {
  n: 0,
  dim: 2,
  pos: null,          // Float32Array n*dim
  vel: null,
  fijo: null,         // Uint8Array: nodos anclados por el dedo
  grado: null,
  comunidad: null,
  aristaA: null, aristaB: null, aristaPeso: null,
  visible: null,      // Uint8Array: qué nodos participan y se dibujan
  calor: 1,
  corriendo: false,
  temporizador: null,
  buffersLibres: [],
  opciones: {}
};

var POR_DEFECTO = {
  repulsion: 900,
  radioCorte: 260,        // más allá de esto la repulsión no se calcula
  atraccion: 0.010,
  longitud: 40,
  gravedad: 0.012,
  friccion: 0.86,
  calorMinimo: 0.004,
  enfriamiento: 0.994,
  pasoMaximo: 12,
  // Los nodos de la misma comunidad se atraen algo más: sin esto los colores
  // quedan salpicados y el mapa deja de leerse de un vistazo.
  cohesionComunidad: 1.5
};

function azar(semilla) {
  var s = semilla >>> 0 || 1;
  return function () {
    s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0;
    return s / 4294967296;
  };
}

// Disposición inicial en espiral: arrancar desde el azar puro hace que las
// primeras decenas de cuadros sean un hervidero ilegible.
function sembrar() {
  var r = azar(20240101);
  var d = estado.dim;
  var radio = 12 * Math.sqrt(estado.n);
  for (var i = 0; i < estado.n; i++) {
    var t = i * 2.399963;                   // ángulo áureo
    var q = radio * Math.sqrt(i / Math.max(1, estado.n));
    estado.pos[i * d] = Math.cos(t) * q + (r() - 0.5) * 4;
    estado.pos[i * d + 1] = Math.sin(t) * q + (r() - 0.5) * 4;
    if (d === 3) estado.pos[i * d + 2] = (r() - 0.5) * radio * 0.6;
  }
}

// ---------------------------------------------------------------- rejilla ---
var rejilla = { celdas: null, inicio: null, orden: null, lado: 0, minX: 0, minY: 0, minZ: 0, nx: 0, ny: 0, nz: 0 };

function construirRejilla() {
  var d = estado.dim, n = estado.n, pos = estado.pos;
  var minX = Infinity, minY = Infinity, minZ = Infinity;
  var maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  var i;
  for (i = 0; i < n; i++) {
    if (!estado.visible[i]) continue;
    var x = pos[i * d], y = pos[i * d + 1];
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
    if (d === 3) { var z = pos[i * d + 2]; if (z < minZ) minZ = z; if (z > maxZ) maxZ = z; }
  }
  if (!isFinite(minX)) { minX = minY = minZ = 0; maxX = maxY = maxZ = 1; }
  if (d === 2) { minZ = 0; maxZ = 1; }

  var lado = estado.opciones.radioCorte;
  var nx = Math.max(1, Math.min(512, Math.ceil((maxX - minX) / lado) + 1));
  var ny = Math.max(1, Math.min(512, Math.ceil((maxY - minY) / lado) + 1));
  var nz = d === 3 ? Math.max(1, Math.min(64, Math.ceil((maxZ - minZ) / lado) + 1)) : 1;
  var total = nx * ny * nz;

  var cuenta = new Int32Array(total + 1);
  var celdaDe = new Int32Array(n);
  for (i = 0; i < n; i++) {
    if (!estado.visible[i]) { celdaDe[i] = -1; continue; }
    var cx = Math.min(nx - 1, Math.max(0, Math.floor((pos[i * d] - minX) / lado)));
    var cy = Math.min(ny - 1, Math.max(0, Math.floor((pos[i * d + 1] - minY) / lado)));
    var cz = d === 3 ? Math.min(nz - 1, Math.max(0, Math.floor((pos[i * d + 2] - minZ) / lado))) : 0;
    var c = (cz * ny + cy) * nx + cx;
    celdaDe[i] = c;
    cuenta[c + 1]++;
  }
  for (i = 0; i < total; i++) cuenta[i + 1] += cuenta[i];
  var orden = new Int32Array(n);
  var cursor = cuenta.slice(0, total);
  for (i = 0; i < n; i++) {
    if (celdaDe[i] < 0) continue;
    orden[cursor[celdaDe[i]]++] = i;
  }

  rejilla.inicio = cuenta; rejilla.orden = orden; rejilla.celdaDe = celdaDe;
  rejilla.lado = lado; rejilla.minX = minX; rejilla.minY = minY; rejilla.minZ = minZ;
  rejilla.nx = nx; rejilla.ny = ny; rejilla.nz = nz;
}

function paso() {
  var d = estado.dim, n = estado.n, pos = estado.pos, vel = estado.vel;
  var o = estado.opciones;
  var i, j, k;

  construirRejilla();

  // --- repulsión, sólo entre celdas vecinas -------------------------------
  var corte2 = o.radioCorte * o.radioCorte;
  var nx = rejilla.nx, ny = rejilla.ny, nz = rejilla.nz;
  for (i = 0; i < n; i++) {
    if (!estado.visible[i] || estado.fijo[i]) continue;
    var c = rejilla.celdaDe[i];
    if (c < 0) continue;
    var cx = c % nx, cy = Math.floor(c / nx) % ny, cz = Math.floor(c / (nx * ny));
    var xi = pos[i * d], yi = pos[i * d + 1], zi = d === 3 ? pos[i * d + 2] : 0;
    var fx = 0, fy = 0, fz = 0;
    var cargaI = 1 + (estado.grado[i] || 0) * 0.12;

    var dzMin = d === 3 ? -1 : 0, dzMax = d === 3 ? 1 : 0;
    for (var dz = dzMin; dz <= dzMax; dz++) {
      var pz = cz + dz;
      if (pz < 0 || pz >= nz) continue;
      for (var dy = -1; dy <= 1; dy++) {
        var py = cy + dy;
        if (py < 0 || py >= ny) continue;
        for (var dx = -1; dx <= 1; dx++) {
          var px = cx + dx;
          if (px < 0 || px >= nx) continue;
          var celda = (pz * ny + py) * nx + px;
          var desde = rejilla.inicio[celda], hasta = rejilla.inicio[celda + 1];
          for (k = desde; k < hasta; k++) {
            j = rejilla.orden[k];
            if (j === i) continue;
            var ex = xi - pos[j * d], ey = yi - pos[j * d + 1];
            var ez = d === 3 ? zi - pos[j * d + 2] : 0;
            var dist2 = ex * ex + ey * ey + ez * ez;
            if (dist2 > corte2) continue;
            if (dist2 < 0.01) { ex = (i - j) * 0.01 + 0.05; ey = 0.05; dist2 = 0.01; }
            var carga = o.repulsion * cargaI * (1 + (estado.grado[j] || 0) * 0.12);
            var f = carga / dist2;
            var dist = Math.sqrt(dist2);
            fx += (ex / dist) * f; fy += (ey / dist) * f;
            if (d === 3) fz += (ez / dist) * f;
          }
        }
      }
    }
    vel[i * d] += fx * estado.calor;
    vel[i * d + 1] += fy * estado.calor;
    if (d === 3) vel[i * d + 2] += fz * estado.calor;
  }

  // --- atracción por arista ------------------------------------------------
  var m = estado.aristaA.length;
  for (k = 0; k < m; k++) {
    var a = estado.aristaA[k], b = estado.aristaB[k];
    if (!estado.visible[a] || !estado.visible[b]) continue;
    var ax = pos[a * d], ay = pos[a * d + 1], az = d === 3 ? pos[a * d + 2] : 0;
    var bx = pos[b * d], by = pos[b * d + 1], bz = d === 3 ? pos[b * d + 2] : 0;
    var vx = bx - ax, vy = by - ay, vz = bz - az;
    var len = Math.sqrt(vx * vx + vy * vy + vz * vz) || 0.01;
    var cohesion = estado.comunidad && estado.comunidad[a] === estado.comunidad[b] ? o.cohesionComunidad : 1;
    var fuerza = (len - o.longitud) * o.atraccion * estado.aristaPeso[k] * cohesion * estado.calor;
    var ux = (vx / len) * fuerza, uy = (vy / len) * fuerza, uz = (vz / len) * fuerza;
    if (!estado.fijo[a]) { vel[a * d] += ux; vel[a * d + 1] += uy; if (d === 3) vel[a * d + 2] += uz; }
    if (!estado.fijo[b]) { vel[b * d] -= ux; vel[b * d + 1] -= uy; if (d === 3) vel[b * d + 2] -= uz; }
  }

  // --- gravedad, fricción e integración -----------------------------------
  var maxPaso = o.pasoMaximo;
  for (i = 0; i < n; i++) {
    if (!estado.visible[i] || estado.fijo[i]) continue;
    for (var c2 = 0; c2 < d; c2++) {
      var idx = i * d + c2;
      vel[idx] -= pos[idx] * o.gravedad * estado.calor;
      vel[idx] *= o.friccion;
      if (vel[idx] > maxPaso) vel[idx] = maxPaso;
      else if (vel[idx] < -maxPaso) vel[idx] = -maxPaso;
      pos[idx] += vel[idx];
    }
  }

  estado.calor *= o.enfriamiento;
}

function tomarBuffer() {
  var necesario = estado.n * estado.dim;
  while (estado.buffersLibres.length) {
    var b = estado.buffersLibres.pop();
    if (b.length === necesario) return b;
  }
  return new Float32Array(necesario);
}

function emitir(final) {
  var salida = tomarBuffer();
  salida.set(estado.pos);
  self.postMessage({ t: 'posiciones', pos: salida, calor: estado.calor, final: !!final }, [salida.buffer]);
}

function bucle() {
  if (!estado.corriendo) return;
  // Varios pasos por cuadro mientras hace calor: acomoda antes y el usuario ve
  // menos hervidero. Al enfriarse, un paso basta y se gasta menos batería.
  var pasos = estado.calor > 0.3 ? 3 : (estado.calor > 0.08 ? 2 : 1);
  for (var i = 0; i < pasos; i++) paso();
  emitir(false);

  if (estado.calor < estado.opciones.calorMinimo) {
    estado.corriendo = false;
    emitir(true);
    self.postMessage({ t: 'reposo' });
    return;
  }
  estado.temporizador = setTimeout(bucle, 16);
}

function iniciar(m) {
  estado.n = m.n;
  estado.dim = m.dim === 3 ? 3 : 2;
  estado.opciones = Object.assign({}, POR_DEFECTO, m.opciones || {});
  estado.pos = new Float32Array(estado.n * estado.dim);
  estado.vel = new Float32Array(estado.n * estado.dim);
  estado.fijo = new Uint8Array(estado.n);
  estado.visible = m.visible ? new Uint8Array(m.visible) : new Uint8Array(estado.n).fill(1);
  estado.comunidad = m.comunidad ? new Int32Array(m.comunidad) : null;
  estado.grado = m.grado ? new Float32Array(m.grado) : new Float32Array(estado.n);
  estado.aristaA = new Int32Array(m.aristaA || []);
  estado.aristaB = new Int32Array(m.aristaB || []);
  estado.aristaPeso = new Float32Array(m.aristaPeso || []);
  estado.buffersLibres = [];
  sembrar();
  if (m.posiciones && m.posiciones.length === estado.pos.length) estado.pos.set(m.posiciones);
  estado.calor = 1;
  estado.corriendo = true;
  self.postMessage({ t: 'iniciado', n: estado.n, dim: estado.dim, aristas: estado.aristaA.length });
  bucle();
}

self.onmessage = function (ev) {
  var m = ev.data;
  switch (m.t) {
    case 'iniciar':
      if (estado.temporizador) clearTimeout(estado.temporizador);
      iniciar(m);
      break;
    case 'devolver':
      if (m.pos) estado.buffersLibres.push(new Float32Array(m.pos));
      break;
    case 'fijar':
      if (estado.fijo) {
        estado.fijo[m.id] = 1;
        var d = estado.dim;
        estado.pos[m.id * d] = m.x;
        estado.pos[m.id * d + 1] = m.y;
        if (d === 3 && m.z != null) estado.pos[m.id * d + 2] = m.z;
        estado.vel[m.id * d] = 0; estado.vel[m.id * d + 1] = 0;
        if (d === 3) estado.vel[m.id * d + 2] = 0;
      }
      break;
    case 'soltar':
      if (estado.fijo) estado.fijo[m.id] = m.anclar ? 1 : 0;
      break;
    case 'visibles':
      if (m.visible) estado.visible = new Uint8Array(m.visible);
      estado.calor = Math.max(estado.calor, m.calor != null ? m.calor : 0.45);
      if (!estado.corriendo) { estado.corriendo = true; bucle(); }
      break;
    case 'calentar':
      estado.calor = Math.max(estado.calor, m.valor != null ? m.valor : 0.6);
      if (!estado.corriendo) { estado.corriendo = true; bucle(); }
      break;
    case 'parar':
      estado.corriendo = false;
      if (estado.temporizador) clearTimeout(estado.temporizador);
      break;
    case 'ping':
      self.postMessage({ t: 'pong', id: m.id, n: estado.n, corriendo: estado.corriendo });
      break;
    default:
      self.postMessage({ t: 'error', id: m.id, error: 'Mensaje desconocido: ' + m.t });
  }
};
