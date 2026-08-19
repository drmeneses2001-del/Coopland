(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.parsers = raiz.GC.parsers || {}).binario = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Todo lo que no sabemos leer. No se inventa contenido: el documento entra al
  // grafo como nodo huérfano visible, con los términos de su nombre y su ruta
  // como única materia. Un huérfano visible dice algo; un archivo omitido, no.

  var FAMILIAS = {
    imagen: ['png', 'jpg', 'jpeg', 'gif', 'heic', 'heif', 'webp', 'tiff', 'tif', 'bmp', 'svg', 'avif'],
    audio: ['m4a', 'mp3', 'wav', 'aac', 'aiff', 'caf'],
    video: ['mp4', 'mov', 'm4v', 'avi', 'mkv'],
    oficina: ['doc', 'xls', 'xlsx', 'ppt', 'pptx', 'pages', 'numbers', 'key'],
    comprimido: ['zip', 'rar', '7z', 'gz', 'tar'],
    apple: ['icloud', 'ds_store', 'plist'],
    otro: []
  };

  function familia(ext) {
    var e = String(ext || '').toLowerCase();
    for (var f in FAMILIAS) if (FAMILIAS[f].indexOf(e) !== -1) return f;
    return 'otro';
  }

  async function analizar(entrada) {
    var f = familia(entrada.ext);
    var motivos = {
      imagen: 'Imagen: sólo metadatos (no hay OCR en el dispositivo).',
      audio: 'Audio: sólo metadatos (no hay transcripción).',
      video: 'Vídeo: sólo metadatos.',
      oficina: 'Formato de Office no soportado (.docx sí lo está; .doc, .xlsx, .pptx y los de iWork no).',
      comprimido: 'Archivo comprimido: cárgalo por la ruta ZIP para indexar su contenido.',
      apple: 'Archivo de sistema de Apple: sin contenido indexable.',
      otro: 'Extensión no reconocida: sólo metadatos.'
    };
    return { estado: 'solo-metadatos', texto: '', aviso: motivos[f], meta: { formato: f, tamano: entrada.bytes ? entrada.bytes.length : entrada.tamano || 0 } };
  }

  return { nombre: 'binario', extensiones: [], analizar: analizar, familia: familia, FAMILIAS: FAMILIAS };
});
