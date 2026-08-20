(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.ia = raiz.GC.ia || {}).acciones = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Las cuatro acciones de la capa de IA.
  //
  // Cada una declara tres cosas por separado, y esa separación es el diseño:
  //
  //   carga(datos)      lo único que saldría del dispositivo
  //   plantilla(datos)  la respuesta sin IA, que tiene que servir por sí sola
  //   mensaje(carga)    el texto que se le manda al modelo, hecho SÓLO con la carga
  //
  // `mensaje` no recibe los datos originales, sólo la carga ya auditada. Así es
  // imposible que la redacción del prompt cuele por detrás un dato que la
  // auditoría no vio pasar.

  function lista(xs, cuantos) {
    var t = (xs || []).slice(0, cuantos || 8);
    if (!t.length) return '—';
    if (t.length === 1) return t[0];
    return t.slice(0, -1).join(', ') + ' y ' + t[t.length - 1];
  }

  var SISTEMA_COMUN =
    'Eres el asistente de un médico especialista que analiza la estructura de su propio archivo ' +
    'de documentos clínicos y docentes. Recibes ÚNICAMENTE listas de términos y nombres de tema ' +
    'extraídos de un grafo de co-ocurrencia: nunca ves el texto de los documentos, así que no ' +
    'supongas su contenido ni cites nada como si lo hubieras leído. ' +
    'Responde en español, en el mismo registro técnico que los términos que recibes. ' +
    'Sé breve y concreto: sin preámbulos, sin repetir la pregunta, sin ofrecerte a seguir ayudando. ' +
    'Si los términos son demasiado heterogéneos para decir algo con fundamento, dilo en una frase ' +
    'en vez de inventar una relación.';

  var ACCIONES = [
    // ------------------------------------------------------------------ 1 ---
    {
      id: 'nombrar-tema',
      nombre: 'Nombrar el tema',
      descripcion: 'Pone nombre a una comunidad del grafo a partir de sus términos más centrales.',
      esfuerzo: 'low',
      maxTokens: 200,

      carga: function (tema) {
        return {
          tipo: 'nombrar-tema',
          terminos: (tema.terminos || []).slice(0, 12).map(function (t) { return t.forma || t.lema; }),
          conceptos: tema.nodos,
          documentos: tema.documentos
        };
      },

      plantilla: function (tema) {
        var t = (tema.terminos || []).slice(0, 3).map(function (x) { return x.forma || x.lema; });
        return t.join(' · ') || 'sin nombre';
      },

      mensaje: function (carga) {
        return 'Estos ' + carga.conceptos + ' conceptos forman una comunidad del grafo, repartida en ' +
          carga.documentos + ' documentos. Los más centrales son: ' + lista(carga.terminos, 12) + '.\n\n' +
          'Dale un nombre de tres a seis palabras que un médico reconocería como el asunto que los une. ' +
          'Responde sólo con el nombre, sin comillas ni punto final.';
      },

      interpretar: function (texto) {
        return texto.split('\n')[0].replace(/^["'«]|["'».]$/g, '').trim().slice(0, 70);
      }
    },

    // ------------------------------------------------------------------ 2 ---
    {
      id: 'resumir-tema',
      nombre: 'Resumir el tema',
      descripcion: 'Explica en un párrafo qué asunto reúne a los términos de una comunidad.',
      esfuerzo: 'medium',
      maxTokens: 500,

      carga: function (tema) {
        return {
          tipo: 'resumir-tema',
          nombre: tema.nombre,
          terminos: (tema.terminos || []).slice(0, 16).map(function (t) { return t.forma || t.lema; }),
          conceptos: tema.nodos,
          documentos: tema.documentos
        };
      },

      plantilla: function (tema) {
        var t = (tema.terminos || []).map(function (x) { return x.forma || x.lema; });
        return 'Comunidad de ' + tema.nodos + ' conceptos repartida en ' + tema.documentos +
          ' documentos. Sus términos más centrales son ' + lista(t, 6) + '. ' +
          'La centralidad la encabeza ' + (t[0] || '—') + ', que es por donde pasa la mayor parte ' +
          'de los caminos dentro de este tema.';
      },

      mensaje: function (carga) {
        return 'Tema «' + carga.nombre + '» del grafo: ' + carga.conceptos + ' conceptos en ' +
          carga.documentos + ' documentos.\n\nTérminos, de más a menos central: ' + lista(carga.terminos, 16) + '.\n\n' +
          'Escribe un solo párrafo (tres o cuatro frases) que explique qué asunto reúne a estos términos ' +
          'y qué distingue a este tema de otros del mismo archivo. No enumeres los términos: interprétalos.';
      },

      interpretar: function (texto) { return texto.trim(); }
    },

    // ------------------------------------------------------------------ 3 ---
    {
      id: 'pregunta-puente',
      nombre: 'Refinar la pregunta puente',
      descripcion: 'Reescribe la pregunta de investigación de una brecha entre dos territorios.',
      esfuerzo: 'high',
      maxTokens: 700,

      carga: function (brecha) {
        return {
          tipo: 'pregunta-puente',
          terminosA: (brecha.terminosA || []).slice(0, 8),
          terminosB: (brecha.terminosB || []).slice(0, 8),
          distancia: brecha.sinCamino ? -1 : brecha.distancia,
          aristasCruzadas: brecha.aristasCruzadas
        };
      },

      plantilla: function (brecha) {
        return brecha.pregunta ? brecha.pregunta.texto : '';
      },

      mensaje: function (carga) {
        var cercania = carga.distancia < 0
          ? 'No hay ningún camino entre los dos territorios en el grafo: están separados por completo.'
          : 'Sus conceptos más centrales están a ' + carga.distancia +
            (carga.distancia === 1 ? ' salto' : ' saltos') + ' de distancia, con ' +
            (carga.aristasCruzadas === 0 ? 'ninguna conexión directa' :
             carga.aristasCruzadas + (carga.aristasCruzadas === 1 ? ' conexión directa' : ' conexiones directas')) + '.';
        return 'En el archivo hay dos territorios densos que casi no se hablan entre sí.\n\n' +
          'Territorio A: ' + lista(carga.terminosA, 8) + '\n' +
          'Territorio B: ' + lista(carga.terminosB, 8) + '\n\n' + cercania + '\n\n' +
          'Escribe UNA pregunta de investigación que obligue a cruzar de A a B: concreta, contestable ' +
          'con trabajo clínico o con una revisión, y que nombre elementos de los dos lados. ' +
          'Añade después una sola frase explicando por qué esa pregunta es la que abre el paso. ' +
          'No propongas varias preguntas.';
      },

      interpretar: function (texto) { return texto.trim(); }
    },

    // ------------------------------------------------------------------ 4 ---
    {
      id: 'preguntas-aislado',
      nombre: 'Preguntas para un documento aislado',
      descripcion: 'Propone por dónde reconectar un documento que quedó suelto en el archivo.',
      esfuerzo: 'medium',
      maxTokens: 800,

      carga: function (doc) {
        return {
          tipo: 'preguntas-aislado',
          nombre: doc.nombreCorto,
          terminos: (doc.terminosPropios || []).slice(0, 14),
          palabras: doc.palabras,
          temas: (doc.temasCercanos || []).slice(0, 4)
        };
      },

      plantilla: function (doc) {
        return doc.pregunta ? doc.pregunta.texto : '';
      },

      mensaje: function (carga) {
        var contexto = carga.temas && carga.temas.length
          ? 'Los temas más cercanos del archivo son: ' + lista(carga.temas, 4) + '.'
          : 'No hay ningún tema cercano: el documento está completamente aislado.';
        return 'El documento «' + carga.nombre + '» (' + carga.palabras + ' palabras) no está enlazado ' +
          'con ningún otro del archivo.\n\n' +
          'Sus conceptos propios son: ' + lista(carga.terminos, 14) + '.\n' + contexto + '\n\n' +
          'Propón tres preguntas de investigación que lo reconecten con el resto del material. ' +
          'Una por línea, empezando cada una con «—». Nada más.';
      },

      interpretar: function (texto) {
        var lineas = texto.split('\n')
          .map(function (l) { return l.replace(/^\s*[—\-*•]\s*/, '').trim(); })
          .filter(function (l) { return l.length > 15; });
        return lineas.slice(0, 3);
      }
    }
  ];

  function obtener(id) {
    for (var i = 0; i < ACCIONES.length; i++) if (ACCIONES[i].id === id) return ACCIONES[i];
    return null;
  }

  return { ACCIONES: ACCIONES, obtener: obtener, SISTEMA_COMUN: SISTEMA_COMUN, lista: lista };
});
