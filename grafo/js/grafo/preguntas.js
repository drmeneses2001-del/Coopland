(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.grafo = raiz.GC.grafo || {}).preguntas = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // «Tender el puente»: convertir una brecha en una pregunta de investigación.
  //
  // Sin capa de IA la pregunta se arma por plantilla, y tiene que ser útil por
  // sí sola —no un hueco a la espera de un modelo—. Por eso cada plantilla
  // nombra los dos extremos, cita el material propio del usuario y termina en
  // una pregunta que se puede llevar a una sesión clínica tal cual.
  //
  // La plantilla se elige de forma determinista a partir de la propia brecha:
  // la misma brecha da siempre la misma pregunta, y dos brechas distintas de la
  // misma sesión no salen redactadas igual.

  function semilla(texto) {
    var h = 2166136261;
    for (var i = 0; i < texto.length; i++) {
      h ^= texto.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return Math.abs(h);
  }

  function lista(terminos, cuantos) {
    var t = (terminos || []).slice(0, cuantos || 3);
    if (!t.length) return '—';
    if (t.length === 1) return t[0];
    return t.slice(0, -1).join(', ') + ' y ' + t[t.length - 1];
  }

  function nombreCorto(ruta) {
    if (!ruta) return 'un documento';
    var partes = String(ruta).split('/');
    return partes[partes.length - 1].replace(/\.[A-Za-z0-9]{1,10}$/, '');
  }

  // ------------------------------------------------------------ estructural ---
  var PLANTILLAS_ESTRUCTURAL = [
    // Las plantillas se redactan de modo que funcionen con una lista de uno o de
    // varios términos: nada de verbos que tengan que concordar con la lista.
    function (d) {
      return '¿Qué relación hay entre ' + d.a + ', por un lado, y ' + d.b + ', por otro? ' +
        'En tu material los dos territorios existen por separado —' + d.docA + ' desarrolla el primero y ' +
        d.docB + ' el segundo— pero ningún texto los pone en la misma página.';
    },
    function (d) {
      return 'Tomando ' + d.centralA + ' como punto de partida y ' + d.centralB + ' como destino: ' +
        '¿qué mecanismo explicaría el paso de uno al otro? Estás a ' + d.saltos + ' de distancia en tu propio grafo, ' +
        'así que el puente es corto y nadie lo ha escrito todavía.';
    },
    function (d) {
      return '¿En qué condiciones se cruzan ' + d.a + ' con ' + d.b + '? ' +
        'Son dos bloques densos de tu archivo (' + d.pesoTexto + ' del vocabulario entre los dos) ' +
        'unidos por apenas ' + d.aristas + '.';
    },
    function (d) {
      return 'Si tuvieras que escribir una sola nota que justificara por qué ' + d.centralA +
        ' y ' + d.centralB + ' pertenecen al mismo problema clínico, ¿cuál sería el argumento? ' +
        'Ese texto no existe en tu carpeta.';
    }
  ];

  function deEstructural(brecha) {
    var datos = {
      a: lista(brecha.terminosA, 3),
      b: lista(brecha.terminosB, 3),
      centralA: brecha.centralA ? brecha.centralA.forma : lista(brecha.terminosA, 1),
      centralB: brecha.centralB ? brecha.centralB.forma : lista(brecha.terminosB, 1),
      docA: nombreCorto(brecha.documentosA && brecha.documentosA[0] && brecha.documentosA[0].ruta),
      docB: nombreCorto(brecha.documentosB && brecha.documentosB[0] && brecha.documentosB[0].ruta),
      saltos: brecha.sinCamino ? 'sin ningún camino' : (brecha.distancia === 1 ? 'un salto' : brecha.distancia + ' saltos'),
      aristas: brecha.aristasCruzadas === 0 ? 'ninguna conexión'
        : (brecha.aristasCruzadas === 1 ? 'una conexión' : brecha.aristasCruzadas + ' conexiones'),
      pesoTexto: (brecha.peso * 100).toFixed(0) + '%'
    };
    var clave = 'e:' + brecha.comunidadA + ':' + brecha.comunidadB + ':' + datos.centralA + datos.centralB;
    var i = semilla(clave) % PLANTILLAS_ESTRUCTURAL.length;
    // Una brecha sin camino no admite la plantilla que presume de cercanía.
    if (brecha.sinCamino && i === 1) i = 3;
    return {
      texto: PLANTILLAS_ESTRUCTURAL[i](datos),
      origen: 'plantilla',
      plantilla: i,
      // Lo que se enviaría a la capa de IA de la Fase 6 si el usuario la activa:
      // términos y nombres de clúster, nunca texto de los documentos.
      cargaParaIA: {
        tipo: 'brecha-estructural',
        terminosA: brecha.terminosA, terminosB: brecha.terminosB,
        distancia: brecha.distancia, aristasCruzadas: brecha.aristasCruzadas
      }
    };
  }

  // --------------------------------------------------------------- aislado ---
  var PLANTILLAS_AISLADO = [
    function (d) {
      return '¿Con qué se conecta ' + d.nombre + '? Tiene ' + d.terminos + ' conceptos propios y ' +
        'ni un solo enlace escrito hacia el resto del archivo. ' + d.pista;
    },
    function (d) {
      return 'Escribiste ' + d.nombre + ' (' + d.palabras + ' palabras) y nunca volviste a él. ' +
        '¿Qué pregunta te llevó a escribirlo, y sigue abierta? ' + d.pista;
    },
    function (d) {
      return '¿Qué parte de ' + d.nombre + ' pertenece en realidad a otro documento tuyo? ' + d.pista;
    }
  ];

  function deAislado(doc) {
    var pista = doc.afines && doc.afines.length
      ? 'Por vocabulario se parece a ' + lista(doc.afines.map(function (a) { return nombreCorto(a.ruta); }), 2) +
        ', pero no hay ningún enlace entre ellos.'
      : 'Tampoco se parece a ningún otro documento por vocabulario: es una isla completa.';
    var datos = {
      nombre: nombreCorto(doc.ruta),
      terminos: doc.terminos,
      palabras: doc.palabras,
      pista: pista
    };
    var i = semilla('a:' + doc.ruta) % PLANTILLAS_AISLADO.length;
    return {
      texto: PLANTILLAS_AISLADO[i](datos),
      origen: 'plantilla',
      plantilla: i,
      cargaParaIA: { tipo: 'documento-aislado', nombre: datos.nombre, terminos: doc.terminos }
    };
  }

  // -------------------------------------------------------- puente ausente ---
  var PLANTILLAS_PUENTE = [
    function (d) {
      return '¿Es ' + d.forma + ' el mismo fenómeno en ' + d.a + ' que en ' + d.b + '? ' +
        'Aparece con los dos grupos por separado —en ' + d.docA + ' y en ' + d.docB + '— ' +
        'pero nunca con ambos en el mismo texto.';
    },
    function (d) {
      return 'Usas ' + d.forma + ' junto a ' + d.a + ', y también junto a ' + d.b + ', ' +
        'nunca en la misma página. ¿Es un puente real o una palabra que significa dos cosas distintas ' +
        'en dos contextos distintos?';
    },
    function (d) {
      return 'Si ' + d.forma + ' conecta ' + d.a + ' con ' + d.b + ', ¿cuál sería el caso clínico ' +
        'que lo demostrara? Ese caso no está escrito en tu archivo.';
    }
  ];

  function dePuenteAusente(p) {
    var datos = {
      forma: p.forma,
      a: lista(p.vecinosA, 2),
      b: lista(p.vecinosB, 2),
      docA: nombreCorto(p.documentosA && p.documentosA[0]),
      docB: nombreCorto(p.documentosB && p.documentosB[0])
    };
    var i = semilla('p:' + p.lema + p.comunidadA + p.comunidadB) % PLANTILLAS_PUENTE.length;
    return {
      texto: PLANTILLAS_PUENTE[i](datos),
      origen: 'plantilla',
      plantilla: i,
      cargaParaIA: { tipo: 'puente-ausente', concepto: p.forma, vecinosA: p.vecinosA, vecinosB: p.vecinosB }
    };
  }

  function para(brecha) {
    if (brecha.tipo === 'estructural') return deEstructural(brecha);
    if (brecha.tipo === 'aislado') return deAislado(brecha);
    if (brecha.tipo === 'puente-ausente') return dePuenteAusente(brecha);
    return { texto: '', origen: 'ninguno' };
  }

  // Rellena todas las brechas de un cálculo con su pregunta.
  function poblar(brechas) {
    ['estructurales', 'aislados', 'puentesAusentes'].forEach(function (grupo) {
      (brechas[grupo] || []).forEach(function (b) { b.pregunta = para(b); });
    });
    return brechas;
  }

  return {
    para: para, poblar: poblar, deEstructural: deEstructural, deAislado: deAislado,
    dePuenteAusente: dePuenteAusente, lista: lista, nombreCorto: nombreCorto, semilla: semilla
  };
});
