(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.ui = raiz.GC.ui || {}).vistasGrafo = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  var F = raiz.GC.ui.formato;
  var COL = raiz.GC.ui.colores;
  var esc = F.escapar;
  var $ = function (id) { return document.getElementById(id); };

  // Guardamos el último resumen para poder repintar la tabla de afinidad
  // cuando el usuario mueve el deslizador, sin recalcular el grafo.
  var ultimo = null;

  function progreso(p) {
    $('grafo-fase').textContent = p.fase || 'trabajando';
    $('grafo-cuenta').textContent = p.total > 1 ? F.numero(p.hechos) + ' / ' + F.numero(p.total) : '';
    var pct = p.total > 1 ? (p.hechos / p.total) : 0.5;
    $('grafo-barra').style.width = (pct * 100).toFixed(1) + '%';
  }

  // --- cifras generales ----------------------------------------------------
  function cifras(r) {
    var c = r.conceptos;
    $('cifras-grafo').innerHTML = [
      ['Conceptos', F.numero(c.nodos), ''],
      ['Aristas', F.numero(c.aristas), ''],
      ['Comunidades', F.numero(c.comunidades), ''],
      ['Modularidad', c.modularidad.toFixed(3), ''],
      ['Componentes', F.numero(c.componentes.cuantas), c.componentes.cuantas > 1 ? 'aviso' : ''],
      ['Documentos', F.numero(r.documentos.totales.documentos), ''],
      ['Dependencias', F.numero(r.documentos.totales.dependencias), ''],
      ['Duración', F.duracion(r.duracionMs), '']
    ].map(function (x) {
      return '<div class="cifra ' + x[2] + '"><b>' + esc(x[1]) + '</b><span>' + esc(x[0]) + '</span></div>';
    }).join('');

    var avisos = [];
    var t = c.totales;
    if (t.nodosDescartados) {
      avisos.push('Se dejaron fuera ' + F.numero(t.nodosDescartados) + ' conceptos de ' + F.numero(t.conceptosVistos) +
        ' (aparecen menos de ' + c.corte.minFrecuencia + ' veces, o no entran en el tope de ' + F.numero(c.corte.maxNodos) + ').');
    }
    if (t.aristasDescartadas) {
      avisos.push(F.numero(t.aristasDescartadas) + ' aristas por debajo del peso mínimo (' + c.corte.minPeso + ').');
    }
    if (!c.intermediacion.exacta) {
      avisos.push('Intermediación aproximada por muestreo de ' + F.numero(c.intermediacion.fuentes) +
        ' pivotes: el grafo supera el umbral del cálculo exacto.');
    }
    if (c.componentes.cuantas > 1) {
      avisos.push('El grafo tiene ' + F.numero(c.componentes.cuantas) + ' componentes; el mayor reúne ' +
        F.numero(c.componentes.mayor) + ' conceptos. Los caminos mínimos sólo existen dentro de cada componente.');
    }
    $('grafo-corte').innerHTML = avisos.map(esc).join('<br>');
  }

  // --- diversidad temática -------------------------------------------------
  var TRAMOS = [
    { hasta: 0.20, nombre: 'Enfocada' },
    { hasta: 0.40, nombre: 'Media' },
    { hasta: 0.60, nombre: 'Diversa' },
    { hasta: 1.00, nombre: 'Dispersa' }
  ];

  function diversidad(d) {
    var q = Math.max(0, Math.min(1, d.q));
    var tramos = TRAMOS.map(function (t) {
      return '<i class="' + (d.etiqueta === t.nombre ? 'activo' : '') + '"></i>';
    }).join('');
    var rotulos = TRAMOS.map(function (t) { return '<span>' + esc(t.nombre) + '</span>'; }).join('');
    $('medidor-diversidad').innerHTML =
      '<div class="cabeza">' +
        '<span class="etiqueta-grande">' + esc(d.etiqueta) + '</span>' +
        '<span class="q">modularidad Q = ' + q.toFixed(4) + '</span>' +
      '</div>' +
      '<div class="escala">' +
        '<div class="tramos">' + tramos + '</div>' +
        '<div class="aguja" style="left:' + (q * 100).toFixed(1) + '%"></div>' +
        '<div class="rotulos">' + rotulos + '</div>' +
      '</div>' +
      '<p>' + esc(d.explicacion) + '</p>';
  }

  // --- comunidades ---------------------------------------------------------
  function comunidades(lista) {
    $('temas-cuenta').textContent = F.numero(lista.length) + ' comunidades';
    $('reparto-comunidades').innerHTML = lista.map(function (c) {
      return '<i style="background:' + COL.deComunidad(c.id) + ';flex:' + Math.max(1, c.nodos) + '" ' +
        'title="' + esc(c.nombre) + '"></i>';
    }).join('');

    $('lista-comunidades').innerHTML = lista.map(function (c) {
      var color = COL.deComunidad(c.id);
      return '<div class="comunidad" style="border-left-color:' + color + '">' +
        '<div class="cabeza">' +
          '<span class="chip" style="background:' + color + '"></span>' +
          '<span class="nombre">' + esc(c.nombre || 'sin nombre') + '</span>' +
          '<span class="cifra-com">' + c.porcentaje.toFixed(1) + '% · ' + F.numero(c.nodos) + ' conceptos · ' +
            F.numero(c.documentos) + ' docs</span>' +
        '</div>' +
        '<div class="terminos">' + c.terminos.map(function (t) {
          return '<span class="concepto"><b>' + esc(t.forma) + '</b> <i>' + F.numero(t.frecuencia) + '</i></span>';
        }).join('') + '</div>' +
      '</div>';
    }).join('') || '<div class="vacio">Sin comunidades.</div>';
  }

  // --- tablas de conceptos -------------------------------------------------
  function influyentes(lista, comunidadDe) {
    $('tabla-influyentes').innerHTML =
      '<thead><tr><th>Concepto</th><th>Tema</th><th>Intermediación</th><th>Grado</th><th>Frecuencia</th><th>Docs</th></tr></thead><tbody>' +
      (lista.length ? lista.map(function (x) {
        var c = comunidadDe ? comunidadDe(x.id) : null;
        return '<tr>' +
          '<td class="ruta">' + esc(x.forma) + '</td>' +
          '<td>' + (c == null ? '—' : '<span class="chip" style="display:inline-block;width:10px;height:10px;border-radius:2px;background:' + COL.deComunidad(c) + '"></span>') + '</td>' +
          '<td class="num">' + x.intermediacion.toFixed(4) + '</td>' +
          '<td class="num">' + F.numero(x.grado) + '</td>' +
          '<td class="num">' + F.numero(x.frecuencia) + '</td>' +
          '<td class="num">' + F.numero(x.docs) + '</td></tr>';
      }).join('') : '<tr><td colspan="6" class="vacio">Sin datos.</td></tr>') + '</tbody>';
  }

  function conectores(lista) {
    $('tabla-conectores').innerHTML =
      '<thead><tr><th>Concepto</th><th>Razón</th><th>Intermediación</th><th>Frecuencia</th><th>Docs</th></tr></thead><tbody>' +
      (lista.length ? lista.map(function (x) {
        return '<tr><td class="ruta">' + esc(x.forma) + '</td>' +
          '<td class="num">' + x.razon.toFixed(2) + '</td>' +
          '<td class="num">' + x.intermediacion.toFixed(4) + '</td>' +
          '<td class="num">' + F.numero(x.frecuencia) + '</td>' +
          '<td class="num">' + F.numero(x.docs) + '</td></tr>';
      }).join('') : '<tr><td colspan="5" class="vacio">Sin puntos conectores: el grafo no tiene todavía caminos que atravesar.</td></tr>') +
      '</tbody>';
  }

  // --- capa de documentos --------------------------------------------------
  function documentos(d) {
    var t = d.totales;
    $('cifras-documentos').innerHTML = [
      ['Documentos', F.numero(t.documentos), ''],
      ['Dependencias', F.numero(t.dependencias), ''],
      ['Afinidades', F.numero(t.afinidades), ''],
      ['Sin destino', F.numero(t.enlacesSinResolver), t.enlacesSinResolver ? 'aviso' : ''],
      ['Aislados', F.numero(d.aislados.cuantos), d.aislados.cuantos ? 'aviso' : '']
    ].map(function (x) {
      return '<div class="cifra ' + x[2] + '"><b>' + esc(x[1]) + '</b><span>' + esc(x[0]) + '</span></div>';
    }).join('');

    $('dependencias-cuenta').textContent = F.numero(t.dependencias) +
      (d.dependencias.length < t.dependencias ? ' · se listan ' + d.dependencias.length : '');
    $('tabla-dependencias').innerHTML =
      '<thead><tr><th>Desde</th><th>Hacia</th><th>Tipo</th><th>Peso</th></tr></thead><tbody>' +
      (d.dependencias.length ? d.dependencias.map(function (e) {
        return '<tr><td class="ruta">' + esc(e.desde) + '</td><td class="ruta">' + esc(e.hasta) + '</td>' +
          '<td><span class="arista-tipo ' + esc(e.tipo) + '">' + esc(e.tipo) + '</span><br>' +
          '<span class="pendiente">' + esc(e.detalle || '') + '</span></td>' +
          '<td class="num">' + F.numero(e.peso) + '</td></tr>';
      }).join('') : '<tr><td colspan="4" class="vacio">Ninguna. Nada en esta carpeta enlaza con nada: todo lo que veas en el grafo será afinidad estadística, no estructura escrita.</td></tr>') +
      '</tbody>';

    $('tabla-aislados').innerHTML =
      '<thead><tr><th>Documento</th><th>Palabras</th><th>Términos</th></tr></thead><tbody>' +
      (d.aislados.muestra.length ? d.aislados.muestra.map(function (x) {
        return '<tr><td class="ruta">' + esc(x.ruta) + '</td><td class="num">' + F.numero(x.palabras) +
          '</td><td class="num">' + F.numero(x.terminos) + '</td></tr>';
      }).join('') : '<tr><td colspan="3" class="vacio">Ninguno.</td></tr>') + '</tbody>';
    $('aislados-cuenta').textContent = F.numero(d.aislados.cuantos) +
      (d.aislados.criterio ? ' · ' + d.aislados.criterio : '');

    $('sinresolver-cuenta').textContent = F.numero(t.enlacesSinResolver);
    $('tabla-sinresolver').innerHTML =
      '<thead><tr><th>Desde</th><th>Destino escrito</th><th>Motivo</th></tr></thead><tbody>' +
      (d.sinResolver.length ? d.sinResolver.map(function (x) {
        return '<tr><td class="ruta">' + esc(x.desde) + '</td><td class="ruta">' + esc(x.destino) + '</td>' +
          '<td>' + esc(x.motivo) + '</td></tr>';
      }).join('') : '<tr><td colspan="3" class="vacio">Todos los enlaces escritos apuntan a algo del índice.</td></tr>') + '</tbody>';
  }

  // La tabla de afinidad se filtra en vivo: el deslizador sube el umbral sobre
  // los pares ya calculados, sin volver a construir nada.
  function afinidades(lista, umbral) {
    var visibles = lista.filter(function (e) { return e.coseno >= umbral; });
    $('afinidades-cuenta').textContent = F.numero(visibles.length) + ' pares sobre ' + umbral.toFixed(2);
    $('umbral-valor').textContent = umbral.toFixed(2);
    $('tabla-afinidades').innerHTML =
      '<thead><tr><th>Documento</th><th>Documento</th><th>Coseno</th></tr></thead><tbody>' +
      (visibles.length ? visibles.slice(0, 200).map(function (e) {
        return '<tr><td class="ruta">' + esc(e.desde) + '</td><td class="ruta">' + esc(e.hasta) + '</td>' +
          '<td class="num">' + e.coseno.toFixed(3) + '</td></tr>';
      }).join('') : '<tr><td colspan="3" class="vacio">Ningún par por encima de este umbral.</td></tr>') + '</tbody>';
  }

  // --- capa mixta ----------------------------------------------------------
  function mixta(m, huerfanos, nodosDoc) {
    $('cifras-mixta').innerHTML = [
      ['Pertenencias', F.numero(m.pertenencias), ''],
      ['Conceptos con doc.', F.numero(m.conceptosConDocumento), ''],
      ['Docs con concepto', F.numero(m.documentosConConcepto), ''],
      ['Docs sin concepto', F.numero(m.documentosSinConcepto), m.documentosSinConcepto ? 'aviso' : '']
    ].map(function (x) {
      return '<div class="cifra ' + x[2] + '"><b>' + esc(x[1]) + '</b><span>' + esc(x[0]) + '</span></div>';
    }).join('');

    $('huerfanos-cuenta').textContent = F.numero((huerfanos || []).length);
    $('tabla-huerfanos').innerHTML =
      '<thead><tr><th>Documento</th></tr></thead><tbody>' +
      ((huerfanos || []).length
        ? huerfanos.slice(0, 60).map(function (r) { return '<tr><td class="ruta">' + esc(r) + '</td></tr>'; }).join('')
        : '<tr><td class="vacio">Todos los documentos tocan al menos un concepto del grafo.</td></tr>') +
      '</tbody>';
  }

  function barra(r) {
    $('bi-grafo-nodos').textContent = F.numero(r.conceptos.nodos);
    $('bi-comunidades').textContent = F.numero(r.conceptos.comunidades);
    $('bi-modularidad').textContent = r.conceptos.modularidad.toFixed(3);
  }

  function pintar(resumen, opciones) {
    ultimo = resumen;
    opciones = opciones || {};
    $('grafo-fecha').textContent = F.fecha(resumen.fecha);
    cifras(resumen);
    diversidad(resumen.conceptos.diversidad);
    comunidades(resumen.comunidades);
    influyentes(resumen.influyentes, opciones.comunidadDe);
    conectores(resumen.conectores);
    documentos(resumen.documentos);
    afinidades(resumen.documentos.afinidades, opciones.umbral != null ? opciones.umbral : resumen.documentos.totales.sueloAfinidad);
    mixta(resumen.mixta, opciones.huerfanos, resumen.documentos.totales.documentos);
    barra(resumen);
  }

  function capaVisible(nombre) {
    ['conceptos', 'documentos', 'mixta'].forEach(function (c) {
      $('capa-' + c).hidden = (c !== nombre);
    });
    Array.prototype.forEach.call(document.querySelectorAll('#conmutador-capas button'), function (b) {
      b.setAttribute('aria-selected', String(b.dataset.capa === nombre));
    });
  }

  return {
    progreso: progreso, pintar: pintar, afinidades: afinidades, capaVisible: capaVisible,
    ultimo: function () { return ultimo; }
  };
});
