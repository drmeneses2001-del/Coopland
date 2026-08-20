(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.ui = raiz.GC.ui || {}).visor = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  var GC = raiz.GC;
  var F = GC.ui.formato;
  var esc = F.escapar;

  // Visor de documento con trazabilidad.
  //
  // Ésta es la promesa que separa este proyecto de una caja negra: cada arista
  // del grafo guardó de qué documento y de qué oración salió, así que al abrir
  // un documento desde un nodo se puede subrayar exactamente la línea que
  // produjo la conexión. Si el panel afirma que dos conceptos están unidos, se
  // puede ir a ver dónde se dijo.

  // Devuelve los índices de oración de este documento que generaron aristas
  // del concepto seleccionado.
  function oracionesDeConcepto(capas, conceptoId, ruta) {
    var indices = new Set();
    if (!capas || conceptoId == null || conceptoId < 0) return indices;
    var aristas = capas.conceptos.aristas;
    for (var i = 0; i < aristas.length; i++) {
      var e = aristas[i];
      if (e.a !== conceptoId && e.b !== conceptoId) continue;
      var muestras = e.muestras || [];
      for (var k = 0; k < muestras.length; k++) {
        if (muestras[k].ruta === ruta && muestras[k].oracion >= 0) indices.add(muestras[k].oracion);
      }
    }
    return indices;
  }

  // Y los del otro extremo, para poder decir con qué concepto conecta cada
  // línea subrayada en vez de subrayar sin explicar.
  function parejasDeConcepto(capas, conceptoId, ruta) {
    var mapa = new Map();
    if (!capas || conceptoId == null || conceptoId < 0) return mapa;
    var aristas = capas.conceptos.aristas;
    var nodos = capas.conceptos.nodos;
    for (var i = 0; i < aristas.length; i++) {
      var e = aristas[i];
      if (e.a !== conceptoId && e.b !== conceptoId) continue;
      var otro = e.a === conceptoId ? e.b : e.a;
      var muestras = e.muestras || [];
      for (var k = 0; k < muestras.length; k++) {
        if (muestras[k].ruta !== ruta || muestras[k].oracion < 0) continue;
        if (!mapa.has(muestras[k].oracion)) mapa.set(muestras[k].oracion, []);
        var lista = mapa.get(muestras[k].oracion);
        var forma = nodos[otro] ? (nodos[otro].forma || nodos[otro].lema) : '';
        if (forma && lista.indexOf(forma) === -1) lista.push(forma);
      }
    }
    return mapa;
  }

  function cabecera(doc) {
    var filas = [
      ['ruta', doc.ruta],
      ['formato', doc.parser + (doc.ext ? ' · .' + doc.ext : '')],
      ['estado', doc.estado],
      ['idioma', doc.idioma || '—'],
      ['palabras', F.numero(doc.palabras || 0)],
      ['oraciones', F.numero(doc.oraciones || 0)],
      ['modificado', F.fecha(doc.modificado)],
      ['huella', doc.hash ? doc.hash.slice(0, 24) + '…' : '—']
    ];
    return '<table class="datos"><tbody>' + filas.map(function (f) {
      return '<tr><td>' + esc(f[0]) + '</td><td class="ruta">' + esc(f[1]) + '</td></tr>';
    }).join('') + '</tbody></table>';
  }

  async function abrir(ruta, opciones) {
    opciones = opciones || {};
    var caja = document.getElementById('visor');
    var cuerpo = document.getElementById('visor-cuerpo');
    var titulo = document.getElementById('visor-titulo');
    if (!caja) return null;

    caja.hidden = false;
    titulo.textContent = ruta;
    cuerpo.innerHTML = '<div class="vacio">Leyendo el documento…</div>';

    var doc;
    try { doc = await GC.almacen.leer('documentos', ruta); }
    catch (e) { cuerpo.innerHTML = '<div class="vacio">No se pudo leer: ' + esc(e.message) + '</div>'; return null; }
    if (!doc) { cuerpo.innerHTML = '<div class="vacio">Ese documento ya no está en el índice.</div>'; return null; }

    var partes = [];
    partes.push('<details class="plegable"><summary>Ficha del documento</summary><div class="desplaza">' +
      cabecera(doc) + '</div></details>');

    if (doc.estado !== 'ok' || !doc.texto) {
      partes.push('<div class="vacio">' +
        esc(doc.error || doc.aviso || 'Este documento no tiene texto indexado.') +
        '</div>');
      cuerpo.innerHTML = partes.join('');
      return doc;
    }

    var oraciones = GC.terminos.oraciones(doc.texto);
    var resaltadas = oracionesDeConcepto(opciones.capas, opciones.conceptoId, ruta);
    var parejas = parejasDeConcepto(opciones.capas, opciones.conceptoId, ruta);

    if (opciones.conceptoId != null && opciones.conceptoId >= 0) {
      var nombre = opciones.capas && opciones.capas.conceptos.nodos[opciones.conceptoId];
      partes.push('<p class="nota">Subrayadas, las <b>' + F.numero(resaltadas.size) + '</b> ' +
        (resaltadas.size === 1 ? 'oración' : 'oraciones') + ' de este documento que generaron aristas de ' +
        '<b>' + esc(nombre ? (nombre.forma || nombre.lema) : '—') + '</b>. ' +
        (resaltadas.size ? 'Cada afirmación del panel se puede rastrear hasta aquí.'
                         : 'Ninguna: la conexión de ese concepto viene de otros documentos.') + '</p>');
    }

    var html = ['<div class="texto-documento">'];
    for (var i = 0; i < oraciones.length; i++) {
      var marcada = resaltadas.has(i);
      var conQuien = parejas.get(i);
      html.push('<span class="oracion' + (marcada ? ' resaltada' : '') + '"' +
        (conQuien && conQuien.length ? ' title="une con: ' + esc(conQuien.join(', ')) + '"' : '') +
        ' data-oracion="' + i + '">' + esc(oraciones[i].texto) + '</span> ');
    }
    html.push('</div>');
    partes.push(html.join(''));

    if (doc.textoTruncado) {
      partes.push('<p class="pendiente">El texto guardado está recortado a 2 MB: el documento original es más largo.</p>');
    }

    cuerpo.innerHTML = partes.join('');

    // Llevar la vista a la primera oración subrayada: si hay que buscarla a
    // mano, la trazabilidad deja de ser útil en un documento largo.
    var primera = cuerpo.querySelector('.oracion.resaltada');
    if (primera && primera.scrollIntoView) primera.scrollIntoView({ block: 'center' });
    return doc;
  }

  function cerrar() {
    var caja = document.getElementById('visor');
    if (caja) caja.hidden = true;
  }

  return { abrir: abrir, cerrar: cerrar, oracionesDeConcepto: oracionesDeConcepto, parejasDeConcepto: parejasDeConcepto };
});
