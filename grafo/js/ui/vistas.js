(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.ui = raiz.GC.ui || {}).vistas = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  var F = raiz.GC.ui.formato;
  var esc = F.escapar;
  var $ = function (id) { return document.getElementById(id); };

  function mostrar(id, visible) { var e = $(id); if (e) e.hidden = !visible; }

  // --- capacidades ---------------------------------------------------------
  function rutas(deteccion, verificaciones, elegida) {
    var IMP = raiz.GC.capacidades.IMPLICACIONES;
    var html = ['A', 'B', 'C'].map(function (k) {
      var r = deteccion.rutas[k];
      var v = verificaciones[k];
      var clase, leyenda;
      if (v === true) { clase = 'si'; leyenda = 'verificada en este dispositivo'; }
      else if (v === false) { clase = 'no'; leyenda = 'verificada: NO funciona aquí'; }
      else if (r.disponible) { clase = k === 'B' ? 'duda' : 'si'; leyenda = k === 'B' ? 'sondeo positivo, sin verificar' : 'disponible'; }
      else { clase = 'no'; leyenda = 'no disponible'; }

      return '<div class="ficha' + (k === elegida ? ' elegida' : '') + '">' +
        '<h3><span class="punto ' + clase + '"></span>' + esc(IMP[k].titulo) + (k === elegida ? ' <span class="etiqueta ok">en uso</span>' : '') + '</h3>' +
        '<p class="motivo">' + esc(leyenda) + ' · ' + esc(r.motivo) + '</p>' +
        '<p><b>Re-escaneo:</b> ' + esc(IMP[k].reescaneo) + '</p>' +
        '<p>' + esc(IMP[k].detalle) + '</p>' +
        '</div>';
    }).join('');
    $('rejilla-rutas').innerHTML = html;
    $('ruta-elegida').textContent = 'ruta activa: ' + elegida;
  }

  function entorno(deteccion) {
    var e = deteccion.entorno;
    var filas = [
      ['Web Workers', e.worker ? 'sí' : 'no'],
      ['IndexedDB', e.indexedDB ? 'sí' : 'no'],
      ['crypto.subtle (SHA-256)', e.cryptoSubtle ? 'sí' : 'no — se usa FNV-1a en JS'],
      ['Contexto seguro', e.contextoSeguro === null ? 'desconocido' : (e.contextoSeguro ? 'sí' : 'no')],
      ['Service Worker', e.serviceWorker ? 'sí' : 'no — no habrá modo avión'],
      ['Núcleos declarados', String(e.nucleos)],
      ['WebGL', e.webgl ? 'sí' : 'no — la Fase 5 caerá a canvas 2D'],
      ['OffscreenCanvas', e.offscreenCanvas ? 'sí' : 'no'],
      ['Puntero', e.puntero]
    ];
    $('tabla-entorno').innerHTML = '<tbody>' + filas.map(function (f) {
      return '<tr><td>' + esc(f[0]) + '</td><td class="ruta">' + esc(f[1]) + '</td></tr>';
    }).join('') + '</tbody>';
  }

  // --- progreso ------------------------------------------------------------
  function progreso(p) {
    if (p.fase === 'diff') {
      $('progreso-fase').textContent = 'comparando con el índice guardado';
      $('progreso-cuenta').textContent = p.candidatos + ' candidatos de ' + p.total;
      $('progreso-barra').style.width = '2%';
      return;
    }
    var pct = p.total ? (p.hechos / p.total) : 0;
    $('progreso-fase').textContent = 'analizando';
    $('progreso-cuenta').textContent = F.numero(p.hechos) + ' / ' + F.numero(p.total);
    $('progreso-barra').style.width = (pct * 100).toFixed(1) + '%';
    $('progreso-encurso').innerHTML = (p.enCurso || []).slice(0, 4).map(function (c) {
      return '<div>' + esc(c.ruta) + ' · ' + esc(c.fase) + '</div>';
    }).join('');
  }

  // --- índice --------------------------------------------------------------
  function cifras(est, duracionMs) {
    var e = est.porEstado || {};
    var noLeidos = (e.error || 0) + (e['sin-texto'] || 0) + (e['solo-metadatos'] || 0);
    $('cifras-indice').innerHTML = [
      ['Documentos', F.numero(est.documentos), ''],
      ['Con texto', F.numero(e.ok || 0), 'ok'],
      ['Sin contenido', F.numero(noLeidos), noLeidos ? 'aviso' : ''],
      ['No leídos', F.numero(e.error || 0), (e.error || 0) ? 'fallo' : ''],
      ['Conceptos', F.numero(est.conceptos), ''],
      ['Palabras', F.numero(est.palabras), ''],
      ['Tamaño', F.bytes(est.bytes), ''],
      ['Duración', F.duracion(duracionMs), '']
    ].map(function (c) {
      return '<div class="cifra ' + c[2] + '"><b>' + esc(c[1]) + '</b><span>' + esc(c[0]) + '</span></div>';
    }).join('');

    $('tabla-extensiones').innerHTML =
      '<thead><tr><th>Extensión</th><th>Documentos</th></tr></thead><tbody>' +
      est.porExtension.map(function (x) {
        return '<tr><td class="ruta">.' + esc(x.ext) + '</td><td class="num">' + F.numero(x.n) + '</td></tr>';
      }).join('') + '</tbody>';
  }

  // --- qué cambió ----------------------------------------------------------
  function listaRutas(items, limite) {
    if (!items.length) return '<div class="vacio">ninguno</div>';
    var visibles = items.slice(0, limite || 25);
    var html = '<div class="desplaza"><table class="datos"><tbody>' + visibles.map(function (i) {
      var extra = i.delta != null
        ? '<td class="num">' + (i.delta > 0 ? '+' : '') + F.numero(i.delta) + ' pal.</td>'
        : (i.palabras != null ? '<td class="num">' + F.numero(i.palabras) + ' pal.</td>' : '<td></td>');
      return '<tr><td class="ruta">' + esc(i.ruta) + '</td>' + extra +
        '<td>' + (i.estado ? F.estado(i.estado) : '') + '</td></tr>';
    }).join('') + '</tbody></table></div>';
    if (items.length > visibles.length) html += '<div class="pendiente">… y ' + F.numero(items.length - visibles.length) + ' más</div>';
    return html;
  }

  function cambios(c, fechaTs) {
    $('cambios-fecha').textContent = F.fecha(fechaTs);
    var bloques = [];

    if (c.primeraVez) {
      bloques.push('<p class="nota">Primera indexación de esta carpeta: todo es nuevo. ' +
        'A partir de la próxima apertura, esta sección muestra sólo la diferencia.</p>');
    }

    bloques.push('<div class="cambio alta"><h4>Documentos nuevos · ' + F.numero(c.nuevos.length) + '</h4>' + listaRutas(c.nuevos) + '</div>');
    bloques.push('<div class="cambio mod"><h4>Modificados · ' + F.numero(c.modificados.length) + '</h4>' + listaRutas(c.modificados) + '</div>');
    bloques.push('<div class="cambio baja"><h4>Eliminados · ' + F.numero(c.eliminados.length) + '</h4>' + listaRutas(c.eliminados) + '</div>');

    if (c.conceptosNuevos.length) {
      bloques.push('<div class="cambio alta"><h4>Conceptos que aparecen por primera vez · ' + F.numero(c.conceptosNuevos.length) + '</h4>' +
        '<div class="fichas-conceptos">' + c.conceptosNuevos.slice(0, 60).map(function (x) {
          return '<span class="concepto"><b>' + esc(x.lema) + '</b> <i>' + x.docs + '</i></span>';
        }).join('') + '</div></div>');
    }
    if (c.conceptosCrecidos.length) {
      bloques.push('<div class="cambio mod"><h4>Conceptos que se extendieron a más documentos · ' + F.numero(c.conceptosCrecidos.length) + '</h4>' +
        '<div class="fichas-conceptos">' + c.conceptosCrecidos.slice(0, 40).map(function (x) {
          return '<span class="concepto"><b>' + esc(x.lema) + '</b> <i>' + x.antes + '→' + x.despues + '</i></span>';
        }).join('') + '</div></div>');
    }
    if (c.conceptosIdos.length) {
      bloques.push('<div class="cambio baja"><h4>Conceptos que desaparecieron del corpus · ' + F.numero(c.conceptosIdos.length) + '</h4>' +
        '<div class="fichas-conceptos">' + c.conceptosIdos.slice(0, 40).map(function (x) {
          return '<span class="concepto"><b>' + esc(x.lema) + '</b></span>';
        }).join('') + '</div></div>');
    }

    bloques.push('<div class="cambio"><h4>Pendiente de fase</h4>' +
      c.pendientesDeFase.map(function (p) { return '<div class="pendiente">' + esc(p) + '</div>'; }).join('') + '</div>');

    $('contenido-cambios').innerHTML = bloques.join('');
  }

  // --- errores -------------------------------------------------------------
  function errores(docs) {
    var problematicos = docs.filter(function (d) { return d.estado !== 'ok'; })
      .sort(function (a, b) {
        var orden = { error: 0, 'sin-texto': 1, 'solo-metadatos': 2 };
        return (orden[a.estado] - orden[b.estado]) || a.ruta.localeCompare(b.ruta);
      });
    $('errores-cuenta').textContent = F.numero(problematicos.length) + ' de ' + F.numero(docs.length);
    $('tabla-errores').innerHTML =
      '<thead><tr><th>Documento</th><th>Estado</th><th>Motivo</th></tr></thead><tbody>' +
      (problematicos.length
        ? problematicos.map(function (d) {
            return '<tr><td class="ruta">' + esc(d.ruta) + '</td><td>' + F.estado(d.estado) + '</td>' +
              '<td>' + esc(d.error || d.aviso || '—') + '</td></tr>';
          }).join('')
        : '<tr><td colspan="3" class="vacio">Todos los documentos se leyeron con texto.</td></tr>') +
      '</tbody>';
    return problematicos.length;
  }

  // --- inventario ----------------------------------------------------------
  var TOPE_FILAS = 300;
  function inventario(docs, filtro) {
    var f = (filtro || '').trim().toLowerCase();
    var lista = f ? docs.filter(function (d) {
      return d.ruta.toLowerCase().indexOf(f) !== -1 || ('.' + d.ext) === f || d.ext === f.replace(/^\./, '');
    }) : docs;
    lista = lista.slice().sort(function (a, b) { return (b.modificado || 0) - (a.modificado || 0); });
    $('inventario-cuenta').textContent = F.numero(lista.length) + (f ? ' de ' + F.numero(docs.length) : '');
    var visibles = lista.slice(0, TOPE_FILAS);
    $('tabla-inventario').innerHTML =
      '<thead><tr><th>Documento</th><th>Estado</th><th>Idioma</th><th>Palabras</th><th>Términos</th><th>Modificado</th></tr></thead><tbody>' +
      (visibles.length ? visibles.map(function (d) {
        return '<tr><td class="ruta">' + esc(d.ruta) + '</td>' +
          '<td>' + F.estado(d.estado) + '</td>' +
          '<td class="ruta">' + esc(d.idioma || '—') + '</td>' +
          '<td class="num">' + F.numero(d.palabras || 0) + '</td>' +
          '<td class="num">' + F.numero(d.nTerminos || 0) + '</td>' +
          '<td class="num">' + esc(F.fecha(d.modificado)) + '</td></tr>';
      }).join('') : '<tr><td colspan="6" class="vacio">Sin coincidencias.</td></tr>') +
      '</tbody>';
    if (lista.length > visibles.length) {
      $('tabla-inventario').insertAdjacentHTML('beforeend',
        '<tfoot><tr><td colspan="6" class="pendiente">Mostrando ' + TOPE_FILAS + ' de ' + F.numero(lista.length) + '. Filtra para acotar.</td></tr></tfoot>');
    }
  }

  // --- vocabulario ---------------------------------------------------------
  function conceptos(vocabulario) {
    var top = vocabulario.slice().sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0]); }).slice(0, 200);
    $('conceptos-cuenta').textContent = F.numero(vocabulario.length) + ' lemas · 200 más extendidos';
    $('lista-conceptos').innerHTML = top.map(function (v) {
      return '<span class="concepto"><b>' + esc(v[0]) + '</b> <i>' + v[1] + '</i></span>';
    }).join('') || '<div class="vacio">Sin vocabulario todavía.</div>';
  }

  // --- barra inferior ------------------------------------------------------
  function barra(est, nErrores, arranqueMs, duracionMs) {
    document.getElementById('bi-docs').textContent = F.numero(est.documentos);
    document.getElementById('bi-conceptos').textContent = F.numero(est.conceptos);
    document.getElementById('bi-palabras').textContent = F.numero(est.palabras);
    document.getElementById('bi-errores').textContent = F.numero(nErrores);
    document.getElementById('bi-arranque').textContent = F.duracion(arranqueMs);
    document.getElementById('bi-duracion').textContent = F.duracion(duracionMs);
  }

  return {
    mostrar: mostrar, rutas: rutas, entorno: entorno, progreso: progreso, cifras: cifras,
    cambios: cambios, errores: errores, inventario: inventario, conceptos: conceptos,
    barra: barra
  };
});
