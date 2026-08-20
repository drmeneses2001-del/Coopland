(function (raiz, fabrica) {
  var bytesMod = (typeof module === 'object' && module.exports) ? require('../nucleo/bytes.js') : (raiz.GC && raiz.GC.bytes);
  var api = fabrica(bytesMod);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.parsers = raiz.GC.parsers || {}).datos = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (bytesMod) {
  'use strict';

  // CSV y JSON son fuentes ESTRUCTURALES, no de contenido: se indexan sus
  // encabezados y sus claves, nunca los valores. Un CSV de pacientes aporta
  // así sus dimensiones al grafo sin que ningún dato de fila entre al índice.

  function detectarSeparador(linea) {
    var candidatos = [',', ';', '\t', '|'];
    var mejor = ',', mejorN = -1;
    candidatos.forEach(function (c) {
      var n = linea.split(c).length;
      if (n > mejorN) { mejorN = n; mejor = c; }
    });
    return mejor;
  }

  function partirFilaCsv(linea, sep) {
    var campos = [], actual = '', entreComillas = false;
    for (var i = 0; i < linea.length; i++) {
      var c = linea[i];
      if (entreComillas) {
        if (c === '"') {
          if (linea[i + 1] === '"') { actual += '"'; i++; }
          else entreComillas = false;
        } else actual += c;
      } else if (c === '"') entreComillas = true;
      else if (c === sep) { campos.push(actual); actual = ''; }
      else actual += c;
    }
    campos.push(actual);
    return campos.map(function (s) { return s.trim(); });
  }

  function analizarCsv(texto) {
    var lineas = texto.split(/\r?\n/).filter(function (l) { return l.trim() !== ''; });
    if (!lineas.length) return { encabezados: [], filas: 0 };
    var sep = detectarSeparador(lineas[0]);
    var encabezados = partirFilaCsv(lineas[0], sep).filter(function (h) { return h !== ''; });
    return { encabezados: encabezados, filas: Math.max(0, lineas.length - 1), separador: sep };
  }

  function clavesDe(valor, profundidad, acumulado, limite) {
    if (profundidad > 8 || acumulado.size >= limite) return acumulado;
    if (Array.isArray(valor)) {
      for (var i = 0; i < valor.length && i < 500; i++) clavesDe(valor[i], profundidad + 1, acumulado, limite);
    } else if (valor && typeof valor === 'object') {
      var claves = Object.keys(valor);
      for (var j = 0; j < claves.length; j++) {
        acumulado.set(claves[j], (acumulado.get(claves[j]) || 0) + 1);
        if (acumulado.size >= limite) break;
        clavesDe(valor[claves[j]], profundidad + 1, acumulado, limite);
      }
    }
    return acumulado;
  }

  async function analizar(entrada) {
    var d = bytesMod.aTexto(entrada.bytes);
    if (entrada.ext === 'json') {
      var datos;
      try { datos = JSON.parse(d.texto); }
      catch (e) { return { estado: 'error', texto: '', error: 'JSON inválido: ' + e.message }; }
      var mapa = clavesDe(datos, 0, new Map(), 5000);
      if (!mapa.size) return { estado: 'sin-texto', texto: '', aviso: 'JSON sin claves indexables (valor escalar o arreglo plano).' };
      var claves = Array.from(mapa.keys());
      // Cada clave se repite según su frecuencia: así pesa lo que aparece más.
      var texto = [];
      mapa.forEach(function (n, k) { for (var i = 0; i < Math.min(n, 20); i++) texto.push(k.replace(/[_\-.]+/g, ' ')); });
      return {
        estado: 'ok', texto: texto.join(' '),
        meta: { formato: 'json', clavesUnicas: claves.length, soloEstructura: true, claves: claves.slice(0, 200) }
      };
    }

    var r = analizarCsv(d.texto);
    if (!r.encabezados.length) return { estado: 'sin-texto', texto: '', aviso: 'CSV sin fila de encabezados legible.' };
    return {
      estado: 'ok',
      texto: r.encabezados.map(function (h) { return h.replace(/[_\-.]+/g, ' '); }).join(' \n'),
      meta: { formato: 'csv', filas: r.filas, columnas: r.encabezados.length, separador: r.separador, soloEstructura: true, encabezados: r.encabezados }
    };
  }

  return { nombre: 'datos', extensiones: ['csv', 'tsv', 'json'], analizar: analizar, analizarCsv: analizarCsv, partirFilaCsv: partirFilaCsv };
});
