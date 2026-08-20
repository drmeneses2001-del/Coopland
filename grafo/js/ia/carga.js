(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.ia = raiz.GC.ia || {}).carga = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Auditor de la carga que sale del dispositivo.
  //
  // La restricción del proyecto —«enviar únicamente listas de términos y
  // nombres de clúster, nunca texto crudo de documentos»— no puede quedarse en
  // una convención entre programadores. Hay material clínico en la carpeta: si
  // algún día una acción nueva mete por descuido un fragmento de documento en
  // el objeto, tiene que fallar aquí y no salir a la red.
  //
  // Por eso el auditor no confía en quién lo llama. Recorre la carga entera y
  // la rechaza si encuentra cualquier cosa que no parezca un término o un
  // nombre de tema: cadenas largas, frases con puntuación de prosa, claves no
  // declaradas, o un tamaño total que no cabe en una lista de conceptos.

  // Un término clínico largo («insuficiencia cardiaca con fracción de eyección
  // preservada») cabe de sobra en 120 caracteres. Una oración de un documento,
  // no.
  var MAX_CADENA = 120;
  var MAX_BYTES = 4096;
  var MAX_ELEMENTOS = 400;
  var MAX_PROFUNDIDAD = 4;

  // Claves permitidas. Una acción nueva que quiera enviar otra cosa tiene que
  // añadirla aquí a conciencia, que es justo el momento de pararse a pensar.
  var CLAVES = new Set([
    'tipo', 'idioma',
    'terminos', 'terminosA', 'terminosB', 'vecinosA', 'vecinosB',
    'concepto', 'nombre', 'tema', 'temas',
    'distancia', 'aristasCruzadas', 'frecuencia', 'documentos',
    'comunidad', 'comunidadA', 'comunidadB',
    'palabras', 'conceptos', 'modularidad', 'diversidad'
  ]);

  // Señales de prosa: dos o más finales de oración, o un salto de párrafo.
  // Un término no tiene puntos; una línea de documento sí.
  var PROSA = /[.!?…][\s"'»)]+[A-ZÁÉÍÓÚÑ¿¡]/;
  var SALTO = /\n/;

  function revisar(carga) {
    var motivos = [];
    var cadenas = 0, numeros = 0;

    function mirar(valor, camino, profundidad) {
      if (profundidad > MAX_PROFUNDIDAD) {
        motivos.push('estructura demasiado anidada en ' + camino);
        return;
      }
      if (valor === null || valor === undefined) return;

      if (typeof valor === 'number' || typeof valor === 'boolean') { numeros++; return; }

      if (typeof valor === 'string') {
        cadenas++;
        if (valor.length > MAX_CADENA) {
          motivos.push(camino + ': cadena de ' + valor.length + ' caracteres (máximo ' + MAX_CADENA + ')');
        }
        if (SALTO.test(valor)) motivos.push(camino + ': contiene saltos de línea, señal de texto de documento');
        else if (PROSA.test(valor)) motivos.push(camino + ': parece prosa, no un término');
        return;
      }

      if (Array.isArray(valor)) {
        if (valor.length > MAX_ELEMENTOS) motivos.push(camino + ': ' + valor.length + ' elementos (máximo ' + MAX_ELEMENTOS + ')');
        for (var i = 0; i < Math.min(valor.length, MAX_ELEMENTOS); i++) mirar(valor[i], camino + '[' + i + ']', profundidad + 1);
        return;
      }

      if (typeof valor === 'object') {
        Object.keys(valor).forEach(function (k) {
          if (!CLAVES.has(k)) {
            motivos.push(camino + '.' + k + ': clave no declarada en la lista de campos permitidos');
            return;
          }
          mirar(valor[k], camino + '.' + k, profundidad + 1);
        });
        return;
      }

      motivos.push(camino + ': tipo de dato no permitido (' + typeof valor + ')');
    }

    mirar(carga, 'carga', 0);

    var texto;
    try { texto = JSON.stringify(carga); }
    catch (e) { motivos.push('la carga no es serializable: ' + e.message); texto = ''; }
    var bytes = texto ? new TextEncoder().encode(texto).length : 0;
    if (bytes > MAX_BYTES) motivos.push('la carga ocupa ' + bytes + ' bytes (máximo ' + MAX_BYTES + ')');

    return {
      seguro: motivos.length === 0,
      motivos: motivos,
      resumen: { bytes: bytes, cadenas: cadenas, numeros: numeros },
      texto: texto
    };
  }

  // Comprobación cruzada contra el corpus: aunque la forma sea válida, si una
  // cadena aparece literalmente dentro de un documento indexado es texto del
  // usuario y no puede salir. Es la última red, y la más cara: sólo se usa
  // sobre las cadenas de la carga, que son pocas y cortas.
  function contrastarConDocumentos(carga, textos) {
    var sospechosas = [];
    var vistas = new Set();

    function recorrer(v) {
      if (typeof v === 'string') {
        // Un término suelto sí aparece en los documentos: eso es lo normal.
        // Lo que delata a un fragmento es que sean varias palabras seguidas.
        if (v.split(/\s+/).length >= 5 && !vistas.has(v)) {
          vistas.add(v);
          for (var i = 0; i < textos.length; i++) {
            if (textos[i] && textos[i].indexOf(v) !== -1) { sospechosas.push(v); break; }
          }
        }
        return;
      }
      if (Array.isArray(v)) { v.forEach(recorrer); return; }
      if (v && typeof v === 'object') { Object.keys(v).forEach(function (k) { recorrer(v[k]); }); }
    }
    recorrer(carga);
    return { seguro: sospechosas.length === 0, sospechosas: sospechosas };
  }

  return {
    revisar: revisar, contrastarConDocumentos: contrastarConDocumentos,
    CLAVES: CLAVES, MAX_CADENA: MAX_CADENA, MAX_BYTES: MAX_BYTES, MAX_ELEMENTOS: MAX_ELEMENTOS
  };
});
