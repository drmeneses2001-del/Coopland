(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.ui = raiz.GC.ui || {}).formato = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  var NUM = new Intl.NumberFormat('es-MX');

  function numero(n) { return NUM.format(Math.round(n || 0)); }

  function bytes(n) {
    if (!n) return '0 B';
    var u = ['B', 'kB', 'MB', 'GB', 'TB'], i = 0, v = n;
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return (i === 0 ? Math.round(v) : v.toFixed(v < 10 ? 1 : 0)) + ' ' + u[i];
  }

  function duracion(ms) {
    if (ms == null) return '—';
    if (ms < 1000) return Math.round(ms) + ' ms';
    if (ms < 60000) return (ms / 1000).toFixed(ms < 10000 ? 2 : 1) + ' s';
    return Math.floor(ms / 60000) + ' min ' + Math.round((ms % 60000) / 1000) + ' s';
  }

  function fecha(ts) {
    if (!ts) return '—';
    var d = new Date(ts);
    return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' }) +
      ' ' + d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
  }

  function escapar(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  var ETIQUETAS_ESTADO = {
    'ok': { texto: 'leído', clase: 'ok' },
    'sin-texto': { texto: 'sin capa de texto', clase: 'aviso' },
    'solo-metadatos': { texto: 'sólo metadatos', clase: 'aviso' },
    'error': { texto: 'no leído', clase: 'fallo' }
  };

  function estado(e) {
    var x = ETIQUETAS_ESTADO[e] || { texto: e || '—', clase: '' };
    return '<span class="etiqueta ' + x.clase + '">' + escapar(x.texto) + '</span>';
  }

  return { numero: numero, bytes: bytes, duracion: duracion, fecha: fecha, escapar: escapar, estado: estado, ETIQUETAS_ESTADO: ETIQUETAS_ESTADO };
});
