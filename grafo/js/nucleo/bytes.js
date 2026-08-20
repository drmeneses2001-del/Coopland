(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else ((raiz.GC = raiz.GC || {}).bytes = api);
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Decodificación de bytes a texto sin adivinar: BOM primero,
  // luego UTF-8 estricto, y sólo si UTF-8 falla se asume Windows-1252
  // (habitual en documentos clínicos antiguos exportados desde Windows).

  var CP1252 = {
    128:'€',130:'‚',131:'ƒ',132:'„',133:'…',134:'†',135:'‡',
    136:'ˆ',137:'‰',138:'Š',139:'‹',140:'Œ',142:'Ž',145:'‘',
    146:'’',147:'“',148:'”',149:'•',150:'–',151:'—',152:'˜',
    153:'™',154:'š',155:'›',156:'œ',158:'ž',159:'Ÿ'
  };

  function deCp1252(bytes) {
    var salida = '';
    for (var i = 0; i < bytes.length; i++) {
      var b = bytes[i];
      salida += (b >= 128 && b <= 159) ? (CP1252[b] || '�') : String.fromCharCode(b);
    }
    return salida;
  }

  function aTexto(bytes) {
    if (!bytes || !bytes.length) return { texto: '', codificacion: 'vacío' };

    if (bytes.length >= 3 && bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF) {
      return { texto: new TextDecoder('utf-8').decode(bytes.subarray(3)), codificacion: 'utf-8-bom' };
    }
    if (bytes.length >= 2 && bytes[0] === 0xFF && bytes[1] === 0xFE) {
      return { texto: new TextDecoder('utf-16le').decode(bytes.subarray(2)), codificacion: 'utf-16le' };
    }
    if (bytes.length >= 2 && bytes[0] === 0xFE && bytes[1] === 0xFF) {
      return { texto: new TextDecoder('utf-16be').decode(bytes.subarray(2)), codificacion: 'utf-16be' };
    }
    try {
      return { texto: new TextDecoder('utf-8', { fatal: true }).decode(bytes), codificacion: 'utf-8' };
    } catch (e) {
      return { texto: deCp1252(bytes), codificacion: 'windows-1252' };
    }
  }

  return { aTexto: aTexto, deCp1252: deCp1252 };
});
