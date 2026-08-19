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


  // --- brechas -------------------------------------------------------------
  // Cada tarjeta trae los dos extremos, el peso, los documentos más cercanos a
  // cada lado y la pregunta. El botón «Tender el puente» la revela; la pregunta
  // ya está construida por plantilla, así que aparece sin esperar a nada.
  function chipComunidad(id) {
    return '<span class="chip" style="display:inline-block;width:10px;height:10px;border-radius:2px;background:' +
      COL.deComunidad(id) + '"></span>';
  }

  function terminosChips(lista) {
    return (lista || []).map(function (t) {
      return '<span class="concepto"><b>' + esc(t) + '</b></span>';
    }).join('');
  }

  function documentosChips(docs) {
    if (!docs || !docs.length) return '<div>sin documentos propios</div>';
    return docs.map(function (d) {
      var ruta = typeof d === 'string' ? d : d.ruta;
      var extra = (d && d.conceptos) ? ' · ' + d.conceptos : '';
      return '<div title="' + esc(ruta) + '">' + esc(ruta) + esc(extra) + '</div>';
    }).join('');
  }

  function bloquePregunta(b, indice, grupo) {
    var id = 'preg-' + grupo + '-' + indice;
    return '<div class="acciones" style="margin-top:10px">' +
        '<button class="menor" data-pregunta="' + id + '">Tender el puente</button>' +
      '</div>' +
      '<div class="pregunta" id="' + id + '" hidden>' +
        '<p>' + esc(b.pregunta ? b.pregunta.texto : '—') + '</p>' +
        '<span class="origen">pregunta por plantilla · la capa de IA de la Fase 6 podrá refinarla</span>' +
      '</div>';
  }

  function tarjetaEstructural(b, i) {
    var saltos = b.sinCamino ? 'sin camino' : (b.distancia === 1 ? '1 salto' : b.distancia + ' saltos');
    return '<div class="brecha">' +
      '<div class="extremos">' +
        '<div class="lado">' +
          '<h5>' + chipComunidad(b.comunidadA) + 'Territorio A · ' + F.numero(b.nodosA) + ' conceptos</h5>' +
          '<div class="terminos">' + terminosChips(b.terminosA) + '</div>' +
          '<div class="docs">' + documentosChips(b.documentosA) + '</div>' +
        '</div>' +
        '<div class="hueco">' +
          '<div class="traza"></div>' +
          '<span class="saltos' + (b.sinCamino ? ' roto' : '') + '">' + esc(saltos) + '</span>' +
        '</div>' +
        '<div class="lado">' +
          '<h5>' + chipComunidad(b.comunidadB) + 'Territorio B · ' + F.numero(b.nodosB) + ' conceptos</h5>' +
          '<div class="terminos">' + terminosChips(b.terminosB) + '</div>' +
          '<div class="docs">' + documentosChips(b.documentosB) + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="medidas">' +
        '<span>peso <b>' + (b.peso * 100).toFixed(1) + '%</b></span>' +
        '<span>facilidad <b>' + b.facilidad.toFixed(2) + '</b></span>' +
        '<span>puntuación <b>' + b.puntuacion.toFixed(4) + '</b></span>' +
        '<span>aristas cruzadas <b>' + F.numero(b.aristasCruzadas) + '</b></span>' +
        '<span>densidad entre <b>' + b.densidadCruzada.toFixed(4) + '</b></span>' +
      '</div>' +
      bloquePregunta(b, i, 'est') +
    '</div>';
  }

  function tarjetaAislado(b, i) {
    return '<div class="brecha">' +
      '<div class="extremos"><div class="lado">' +
        '<h5>Documento</h5>' +
        '<div class="docs"><div>' + esc(b.ruta) + '</div></div>' +
      '</div></div>' +
      '<div class="medidas">' +
        '<span>palabras <b>' + F.numero(b.palabras) + '</b></span>' +
        '<span>conceptos propios <b>' + F.numero(b.terminos) + '</b></span>' +
        '<span>dependencias <b>0</b></span>' +
        '<span>afines por vocabulario <b>' + F.numero((b.afines || []).length) + '</b></span>' +
      '</div>' +
      ((b.afines && b.afines.length)
        ? '<div class="medidas" style="border:0;padding-top:0">' + b.afines.map(function (a) {
            return '<span>' + esc(a.ruta) + ' <b>' + a.coseno.toFixed(2) + '</b></span>';
          }).join('') + '</div>'
        : '') +
      bloquePregunta(b, i, 'ais') +
    '</div>';
  }

  function tarjetaPuente(b, i) {
    return '<div class="brecha">' +
      '<div class="extremos">' +
        '<div class="lado">' +
          '<h5>' + chipComunidad(b.comunidadA) + 'Aparece junto a</h5>' +
          '<div class="terminos">' + terminosChips(b.vecinosA) + '</div>' +
          '<div class="docs">' + documentosChips(b.documentosA) + '</div>' +
        '</div>' +
        '<div class="hueco">' +
          '<span class="saltos"><b>' + esc(b.forma) + '</b></span>' +
          '<div class="traza"></div>' +
          '<span class="saltos roto">nunca juntos</span>' +
        '</div>' +
        '<div class="lado">' +
          '<h5>' + chipComunidad(b.comunidadB) + 'Y también junto a</h5>' +
          '<div class="terminos">' + terminosChips(b.vecinosB) + '</div>' +
          '<div class="docs">' + documentosChips(b.documentosB) + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="medidas">' +
        '<span>frecuencia <b>' + F.numero(b.frecuencia) + '</b></span>' +
        '<span>intermediación <b>' + b.intermediacion.toFixed(4) + '</b></span>' +
        '<span>puntuación <b>' + b.puntuacion.toFixed(4) + '</b></span>' +
      '</div>' +
      bloquePregunta(b, i, 'pue') +
    '</div>';
  }

  function brechas(b) {
    if (!b) return;
    $('cifras-brechas').innerHTML = [
      ['Estructurales', F.numero(b.totales.estructurales), b.totales.estructurales ? 'aviso' : ''],
      ['Aislados', F.numero(b.totales.aislados), b.totales.aislados ? 'aviso' : ''],
      ['Puentes ausentes', F.numero(b.totales.puentesAusentes), b.totales.puentesAusentes ? 'aviso' : '']
    ].map(function (x) {
      return '<div class="cifra ' + x[2] + '"><b>' + esc(x[1]) + '</b><span>' + esc(x[0]) + '</span></div>';
    }).join('');

    $('cuenta-estructurales').textContent = F.numero(b.estructurales.length);
    $('lista-estructurales').innerHTML = b.estructurales.length
      ? b.estructurales.map(tarjetaEstructural).join('')
      : '<div class="vacio">Ninguna. O el grafo todavía es pequeño, o tus territorios ya se hablan entre sí.</div>';

    $('cuenta-aislados-brecha').textContent = F.numero(b.totales.aislados) +
      (b.aislados.length < b.totales.aislados ? ' · se listan ' + b.aislados.length : '');
    $('lista-aislados-brecha').innerHTML = b.aislados.length
      ? b.aislados.map(tarjetaAislado).join('')
      : '<div class="vacio">Ninguno: todos los documentos densos están enlazados con algo.</div>';

    $('cuenta-puentes').textContent = F.numero(b.totales.puentesAusentes);
    $('lista-puentes').innerHTML = b.puentesAusentes.length
      ? b.puentesAusentes.map(tarjetaPuente).join('')
      : '<div class="vacio">Ninguno.</div>';

    var p = b.parametros;
    var filas = [
      ['Densidad del grafo completo', p.estructurales.densidadGlobal != null ? p.estructurales.densidadGlobal.toFixed(5) : '—'],
      ['Mínimo de densidad interna', p.estructurales.minimoDensidadInterna != null ? p.estructurales.minimoDensidadInterna.toFixed(5) : '—'],
      ['Corte de densidad entre comunidades', p.estructurales.corteDensidad != null ? p.estructurales.corteDensidad.toFixed(5) + ' (percentil ' + p.estructurales.percentil + ')' : '—'],
      ['Comunidades consideradas', p.estructurales.comunidadesConsideradas != null ? F.numero(p.estructurales.comunidadesConsideradas) : (p.estructurales.motivo || '—')],
      ['Pares evaluados', p.estructurales.paresEvaluados != null ? F.numero(p.estructurales.paresEvaluados) : '—'],
      ['Criterio de documento aislado', p.aislados.criterio || p.aislados.motivo || '—'],
      ['Conceptos revisados como puente', p.puentesAusentes.revisados != null ? F.numero(p.puentesAusentes.revisados) : (p.puentesAusentes.motivo || '—')]
    ];
    $('tabla-parametros-brechas').innerHTML = '<tbody>' + filas.map(function (f) {
      return '<tr><td>' + esc(f[0]) + '</td><td class="ruta">' + esc(f[1]) + '</td></tr>';
    }).join('') + '</tbody>';

    $('bi-brechas').textContent = F.numero(
      b.totales.estructurales + b.totales.aislados + b.totales.puentesAusentes);
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
    brechas(resumen.brechas);
    barra(resumen);
  }

  function capaVisible(nombre) {
    ['conceptos', 'documentos', 'mixta', 'brechas'].forEach(function (c) {
      $('capa-' + c).hidden = (c !== nombre);
    });
    Array.prototype.forEach.call(document.querySelectorAll('#conmutador-capas button'), function (b) {
      b.setAttribute('aria-selected', String(b.dataset.capa === nombre));
    });
  }

  return {
    progreso: progreso, pintar: pintar, afinidades: afinidades, brechas: brechas, capaVisible: capaVisible,
    ultimo: function () { return ultimo; }
  };
});
