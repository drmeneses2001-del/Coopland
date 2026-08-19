(function (raiz, fabrica) {
  var mods;
  if (typeof module === 'object' && module.exports) {
    mods = {
      hash: require('../js/nucleo/hash.js'),
      bytes: require('../js/nucleo/bytes.js'),
      vacias: require('../js/nucleo/vacias.js'),
      terminos: require('../js/nucleo/terminos.js'),
      diff: require('../js/nucleo/diff.js'),
      indice: require('../js/nucleo/indice.js'),
      registro: require('../js/parsers/registro.js'),
      grafo: {
        coocurrencia: require('../js/grafo/coocurrencia.js'),
        louvain: require('../js/grafo/louvain.js'),
        metricas: require('../js/grafo/metricas.js'),
        documentos: require('../js/grafo/documentos.js'),
        mixta: require('../js/grafo/mixta.js'),
        brechas: require('../js/grafo/brechas.js'),
        preguntas: require('../js/grafo/preguntas.js')
      },
      colores: require('../js/ui/colores.js'),
      parsers: {
        texto: require('../js/parsers/texto.js'),
        rtf: require('../js/parsers/rtf.js'),
        html: require('../js/parsers/html.js'),
        datos: require('../js/parsers/datos.js'),
        pdf: require('../js/parsers/pdf.js'),
        docx: require('../js/parsers/docx.js'),
        binario: require('../js/parsers/binario.js')
      }
    };
  } else {
    mods = {
      hash: raiz.GC.hash, bytes: raiz.GC.bytes, vacias: raiz.GC.vacias,
      terminos: raiz.GC.terminos, diff: raiz.GC.diff, indice: raiz.GC.indice,
      registro: raiz.GC.registro, parsers: raiz.GC.parsers,
      grafo: raiz.GC.grafo, colores: raiz.GC.ui.colores
    };
  }
  var api = fabrica(mods);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; raiz.GC.casos = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (M) {
  'use strict';

  function afirmar(condicion, mensaje) {
    if (!condicion) throw new Error(mensaje || 'afirmación fallida');
  }
  function igual(a, b, mensaje) {
    if (a !== b) throw new Error((mensaje || 'valores distintos') + ': se esperaba ' + JSON.stringify(b) + ' y llegó ' + JSON.stringify(a));
  }
  function contiene(texto, aguja, mensaje) {
    if (String(texto).toLowerCase().indexOf(String(aguja).toLowerCase()) === -1) {
      throw new Error((mensaje || 'falta el fragmento') + ': «' + aguja + '»');
    }
  }
  function noContiene(texto, aguja, mensaje) {
    if (String(texto).toLowerCase().indexOf(String(aguja).toLowerCase()) !== -1) {
      throw new Error((mensaje || 'no debía aparecer') + ': «' + aguja + '»');
    }
  }

  function codificar(s) {
    if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(s);
    return new Uint8Array(Buffer.from(s, 'utf8'));
  }

  var casos = [];
  function caso(grupo, nombre, fn, requiere) { casos.push({ grupo: grupo, nombre: nombre, fn: fn, requiere: requiere || null }); }

  // ---------------------------------------------------------------- hash ---
  caso('hash', 'la huella es estable y distingue contenidos', async function () {
    var a = await M.hash.huella(codificar('insuficiencia cardiaca'));
    var b = await M.hash.huella(codificar('insuficiencia cardiaca'));
    var c = await M.hash.huella(codificar('insuficiencia cardíaca'));
    igual(a, b, 'la misma entrada debe dar la misma huella');
    afirmar(a !== c, 'un acento distinto debe cambiar la huella');
    afirmar(/^(sha256|fnv64):/.test(a), 'la huella debe declarar su algoritmo');
  });

  caso('hash', 'el respaldo FNV-1a funciona sin crypto.subtle', function () {
    var x = M.hash.fnv1a64(codificar('hola'));
    var y = M.hash.fnv1a64(codificar('hola'));
    var z = M.hash.fnv1a64(codificar('holb'));
    igual(x, y, 'determinista');
    afirmar(x !== z, 'sensible a un byte');
    igual(x.length, 16, 'debe ser de 64 bits en hexadecimal');
  });

  // --------------------------------------------------------------- bytes ---
  caso('bytes', 'decodifica UTF-8, BOM y respalda en Windows-1252', function () {
    igual(M.bytes.aTexto(codificar('cardiología')).texto, 'cardiología');
    var conBom = new Uint8Array([0xEF, 0xBB, 0xBF].concat(Array.from(codificar('nota'))));
    var r = M.bytes.aTexto(conBom);
    igual(r.texto, 'nota', 'el BOM debe descartarse');
    igual(r.codificacion, 'utf-8-bom');
    var latin = new Uint8Array([0x63, 0x61, 0x72, 0x64, 0xED, 0x61, 0x63, 0x6F]); // "cardíaco" en cp1252
    var l = M.bytes.aTexto(latin);
    igual(l.codificacion, 'windows-1252', 'UTF-8 inválido debe caer a cp1252');
    contiene(l.texto, 'cardíaco');
  });

  // ------------------------------------------------------------ terminos ---
  caso('terminos', 'la clave normaliza acentos y mayúsculas', function () {
    igual(M.terminos.clave('Cardiología'), 'cardiologia');
    igual(M.terminos.clave('NIÑO'), 'niño');
    igual(M.terminos.clave('post-operatorio'), 'postoperatorio');
  });

  caso('terminos', 'las abreviaturas no parten la oración', function () {
    var o = M.terminos.oraciones('El Dr. Pérez evaluó al paciente. La evolución fue buena.');
    igual(o.length, 2, 'deben salir dos oraciones');
    contiene(o[0].texto, 'Dr. Pérez');
  });

  caso('terminos', 'detecta español e inglés', function () {
    igual(M.terminos.detectarIdioma('El paciente presenta una insuficiencia cardiaca con disnea de esfuerzo y edema en las piernas. La evolución fue favorable tras el tratamiento con diuréticos y el control de la presión arterial.').idioma, 'es');
    igual(M.terminos.detectarIdioma('The patient presented with heart failure and shortness of breath. The evolution was favourable after treatment with diuretics and the control of the arterial pressure in this case.').idioma, 'en');
  });

  caso('terminos', 'la lematización es conservadora', function () {
    igual(M.terminos.lematizar('insuficiencias', 'es'), 'insuficiencia');
    igual(M.terminos.lematizar('hospitales', 'es'), 'hospital');
    igual(M.terminos.lematizar('evaluaciones', 'es'), 'evaluacion');
    igual(M.terminos.lematizar('studies', 'en'), 'study');
    igual(M.terminos.lematizar('reading', 'en'), 'read');
    igual(M.terminos.lematizar('mes', 'es'), 'mes', 'no debe destrozar palabras cortas');
  });

  caso('terminos', 'las terminaciones invariables del léxico clínico se respetan', function () {
    ['dosis', 'crisis', 'diagnosis', 'fibrosis', 'amiloidosis', 'estenosis',
     'hepatitis', 'artritis', 'analisis', 'virus', 'torax'].forEach(function (p) {
      igual(M.terminos.lematizar(p, 'es'), p, 'no debe amputarse «' + p + '»');
      igual(M.terminos.lematizar(p, 'mixto'), p, 'tampoco en modo mixto');
    });
    ['analysis', 'diagnosis', 'virus', 'index'].forEach(function (p) {
      igual(M.terminos.lematizar(p, 'en'), p, 'no debe amputarse «' + p + '»');
    });
    igual(M.terminos.lematizar('dosis', 'es'), 'dosis');
    igual(M.terminos.lematizar('pacientes', 'es'), 'paciente', 'el plural normal sí se normaliza');
  });

  caso('terminos', 'tokeniza sin vacías y cuenta frecuencias', function () {
    var r = M.terminos.tokenizar('La insuficiencia cardiaca y la insuficiencia renal son frecuentes en el paciente anciano.');
    var lemas = r.tokens.map(function (t) { return t.lema; });
    noContiene(lemas.join(' '), ' la ', 'las vacías no deben pasar');
    var f = M.terminos.frecuencias(r.tokens);
    igual(f[0].lema, 'insuficiencia', 'el lema más frecuente debe encabezar');
    igual(f[0].n, 2);
    afirmar(r.tokens[0].desde >= 0 && r.tokens[0].hasta > r.tokens[0].desde, 'cada token debe traer su posición');
  });

  caso('terminos', 'la ruta aporta términos a los archivos sin texto', function () {
    var t = M.terminos.terminosDeRuta('clinica/2024/insuficiencia-cardiaca_notas.pdf').map(function (x) { return x.lema; });
    afirmar(t.indexOf('clinica') !== -1 && t.indexOf('insuficiencia') !== -1, 'faltan términos de la ruta');
    afirmar(t.indexOf('pdf') === -1, 'la extensión no es un concepto');
  });

  // --------------------------------------------------------- parser texto ---
  caso('parser: texto', 'markdown — limpia sintaxis y recoge enlaces', async function (E) {
    var bytes = await E.muestra('notas-clinicas.md');
    var r = await M.parsers.texto.analizar({ nombre: 'notas-clinicas.md', ruta: 'clinica/notas-clinicas.md', ext: 'md', bytes: bytes });
    igual(r.estado, 'ok');
    contiene(r.texto, 'fracción de eyección preservada');
    contiene(r.texto, 'espironolactona');
    noContiene(r.texto, '[[', 'los corchetes de wikilink deben desaparecer');
    noContiene(r.texto, '##', 'las almohadillas de título deben desaparecer');
    var destinos = r.meta.enlaces.map(function (e) { return e.destino; });
    afirmar(destinos.indexOf('fisiopatología') !== -1, 'falta el wikilink');
    afirmar(destinos.indexOf('ensayos/diureticos.md') !== -1, 'falta el enlace markdown relativo');
    afirmar(destinos.indexOf('docencia/sesion-cardiologia.md') !== -1, 'falta la ruta citada en el texto');
  });

  caso('parser: texto', 'texto plano — se conserva íntegro', async function (E) {
    var bytes = await E.muestra('lecture-notes.txt');
    var r = await M.parsers.texto.analizar({ nombre: 'lecture-notes.txt', ruta: 'lecture-notes.txt', ext: 'txt', bytes: bytes });
    igual(r.estado, 'ok');
    contiene(r.texto, 'premature closure');
    igual(M.terminos.detectarIdioma(r.texto).idioma, 'en');
  });

  // ----------------------------------------------------------- parser rtf ---
  caso('parser: rtf', 'decodifica acentos y descarta tablas de control', async function (E) {
    var bytes = await E.muestra('sesion.rtf');
    var r = await M.parsers.rtf.analizar({ nombre: 'sesion.rtf', ruta: 'sesion.rtf', ext: 'rtf', bytes: bytes });
    igual(r.estado, 'ok');
    contiene(r.texto, 'Sesión docente de cardiología');
    contiene(r.texto, 'insuficiencia');
    contiene(r.texto, '72 años');
    noContiene(r.texto, 'fonttbl', 'la tabla de fuentes no es contenido');
    noContiene(r.texto, 'Helvetica', 'los nombres de fuente no son contenido');
    noContiene(r.texto, 'Muestra de prueba', 'los destinos opcionales deben ignorarse');
  });

  caso('parser: rtf', 'un archivo que no es RTF se reporta como error', async function () {
    var r = await M.parsers.rtf.analizar({ nombre: 'x.rtf', ruta: 'x.rtf', ext: 'rtf', bytes: codificar('esto no es rtf') });
    igual(r.estado, 'error');
    contiene(r.error, 'RTF');
  });

  // ---------------------------------------------------------- parser html ---
  caso('parser: html', 'extrae texto visible, título y enlaces locales', async function (E) {
    var bytes = await E.muestra('pagina-guardada.html');
    var r = await M.parsers.html.analizar({ nombre: 'pagina-guardada.html', ruta: 'pagina-guardada.html', ext: 'html', bytes: bytes });
    igual(r.estado, 'ok');
    igual(r.meta.titulo, 'Guía de hipertensión arterial');
    contiene(r.texto, 'presión arterial', 'las entidades deben decodificarse');
    contiene(r.texto, 'Adherencia terapéutica');
    noContiene(r.texto, 'esto no debe indexarse', 'el script no es contenido');
    noContiene(r.texto, 'color:#000', 'el estilo no es contenido');
    var destinos = r.meta.enlaces.map(function (e) { return e.destino; });
    igual(destinos.length, 1, 'sólo el enlace local cuenta como dependencia');
    igual(destinos[0], 'anexos/tablas.html');
  });

  // --------------------------------------------------------- parser datos ---
  caso('parser: datos', 'CSV — encabezados como términos, sin valores de fila', async function (E) {
    var bytes = await E.muestra('pacientes.csv');
    var r = await M.parsers.datos.analizar({ nombre: 'pacientes.csv', ruta: 'pacientes.csv', ext: 'csv', bytes: bytes });
    igual(r.estado, 'ok');
    igual(r.meta.filas, 3);
    igual(r.meta.columnas, 6);
    contiene(r.texto, 'diagnostico principal');
    noContiene(r.texto, 'espironolactona', 'ningún valor de fila puede entrar al índice');
    noContiene(r.texto, '1001', 'ningún folio puede entrar al índice');
    afirmar(r.meta.soloEstructura === true, 'debe declararse como fuente estructural');
  });

  caso('parser: datos', 'CSV — respeta comillas y detecta el separador', function () {
    igual(M.parsers.datos.partirFilaCsv('a;"b;c";d', ';').length, 3);
    igual(M.parsers.datos.analizarCsv('x;y;z\n1;2;3').separador, ';');
  });

  caso('parser: datos', 'JSON — claves como términos, valores fuera', async function (E) {
    var bytes = await E.muestra('protocolo.json');
    var r = await M.parsers.datos.analizar({ nombre: 'protocolo.json', ruta: 'protocolo.json', ext: 'json', bytes: bytes });
    igual(r.estado, 'ok');
    contiene(r.texto, 'presion arterial', 'las claves con guion bajo se separan');
    contiene(r.texto, 'criterios');
    noContiene(r.texto, 'embarazo', 'ningún valor puede entrar al índice');
    noContiene(r.texto, 'manejo de insuficiencia', 'ningún valor puede entrar al índice');
  });

  caso('parser: datos', 'JSON inválido se reporta, no se adivina', async function () {
    var r = await M.parsers.datos.analizar({ nombre: 'x.json', ruta: 'x.json', ext: 'json', bytes: codificar('{roto') });
    igual(r.estado, 'error');
    contiene(r.error, 'JSON inválido');
  });

  // ------------------------------------------------------- parser binario ---
  caso('parser: binario', 'una imagen entra como nodo huérfano, no como error', async function (E) {
    var bytes = await E.muestra('ecocardiograma.png');
    var r = await M.parsers.binario.analizar({ nombre: 'ecocardiograma.png', ruta: 'estudios/ecocardiograma.png', ext: 'png', bytes: bytes });
    igual(r.estado, 'solo-metadatos');
    igual(r.meta.formato, 'imagen');
    igual(r.texto, '', 'no se inventa contenido');
    var t = M.terminos.terminosDeRuta('estudios/ecocardiograma.png').map(function (x) { return x.lema; });
    afirmar(t.indexOf('ecocardiograma') !== -1, 'el huérfano conserva los términos de su nombre');
  });

  // ---------------------------------------------------------- parser pdf ---
  caso('parser: pdf', 'extrae la capa de texto', async function (E) {
    var bytes = await E.muestra('revision.pdf');
    var r = await M.parsers.pdf.analizar({ nombre: 'revision.pdf', ruta: 'revision.pdf', ext: 'pdf', bytes: bytes }, { pdfjsLib: E.pdfjsLib });
    igual(r.estado, 'ok', r.error || '');
    contiene(r.texto, 'hipertension arterial resistente');
    contiene(r.texto, 'adherencia terapeutica');
    igual(r.meta.paginas, 1);
  }, 'pdf');

  caso('parser: pdf', 'un PDF sin capa de texto se marca escaneado, no se inventa', async function (E) {
    var bytes = await E.muestra('escaneado.pdf');
    var r = await M.parsers.pdf.analizar({ nombre: 'escaneado.pdf', ruta: 'escaneado.pdf', ext: 'pdf', bytes: bytes }, { pdfjsLib: E.pdfjsLib });
    igual(r.estado, 'sin-texto');
    igual(r.texto, '');
    contiene(r.aviso, 'Escaneado');
  }, 'pdf');

  // --------------------------------------------------------- parser docx ---
  caso('parser: docx', 'extrae el texto de los párrafos', async function (E) {
    var bytes = await E.muestra('ensayo.docx');
    var r = await M.parsers.docx.analizar({ nombre: 'ensayo.docx', ruta: 'docencia/ensayo.docx', ext: 'docx', bytes: bytes }, { mammoth: E.mammoth });
    igual(r.estado, 'ok', r.error || '');
    contiene(r.texto, 'formacion medica continua');
    contiene(r.texto, 'simulacion de alta fidelidad');
  }, 'docx');

  caso('parser: docx', 'un archivo que no es DOCX se reporta como error', async function (E) {
    var r = await M.parsers.docx.analizar({ nombre: 'x.docx', ruta: 'x.docx', ext: 'docx', bytes: codificar('no soy un zip') }, { mammoth: E.mammoth });
    igual(r.estado, 'error');
    contiene(r.error, 'DOCX');
  }, 'docx');

  // ------------------------------------------------------------- registro ---
  caso('registro', 'enruta por extensión y nunca omite un archivo', function () {
    igual(M.registro.extensionDe('nota.final.MD'), 'md');
    igual(M.registro.parserPara('md').nombre, 'texto');
    igual(M.registro.parserPara('pdf').nombre, 'pdf');
    igual(M.registro.parserPara('csv').nombre, 'datos');
    igual(M.registro.parserPara('sketch').nombre, 'binario', 'lo desconocido cae en binario, no se descarta');
  });

  caso('registro', 'rechaza por tamaño en lugar de colgar el iPad', async function () {
    var enorme = { nombre: 'grande.txt', ruta: 'grande.txt', ext: 'txt', bytes: { length: M.registro.LIMITE_BYTES + 1 } };
    var r = await M.registro.analizar(enorme);
    igual(r.estado, 'error');
    contiene(r.error, 'límite');
  });

  // ----------------------------------------------------------------- diff ---
  caso('diff', 'separa nuevos, candidatos, sin cambios y eliminados', function () {
    var guardados = [
      { ruta: 'a.md', tamano: 100, modificado: 1000, hash: 'h1' },
      { ruta: 'b.md', tamano: 200, modificado: 2000, hash: 'h2' },
      { ruta: 'c.md', tamano: 300, modificado: 3000, hash: 'h3' }
    ];
    var inventario = [
      { ruta: 'a.md', tamano: 100, modificado: 1000 },          // idéntico
      { ruta: 'b.md', tamano: 250, modificado: 2000 },          // cambió de tamaño
      { ruta: 'd.md', tamano: 400, modificado: 4000 }           // nuevo
    ];
    var r = M.diff.comparar(inventario, guardados);
    igual(r.sinCambios.length, 1);
    igual(r.candidatos.length, 2);
    igual(r.nuevos.length, 1);
    igual(r.eliminados.length, 1);
    igual(r.eliminados[0].ruta, 'c.md');
  });

  caso('diff', 'tolera el ruido de fecha de iCloud', function () {
    var r = M.diff.comparar(
      [{ ruta: 'a.md', tamano: 100, modificado: 1000 + M.diff.TOLERANCIA_FECHA_MS - 1 }],
      [{ ruta: 'a.md', tamano: 100, modificado: 1000, hash: 'h1' }]
    );
    igual(r.sinCambios.length, 1, 'una diferencia por debajo de la tolerancia no es un cambio');
  });

  caso('diff', 'el hash es la última palabra', function () {
    afirmar(M.diff.cambioReal({ hash: 'h1' }, 'h2') === true);
    afirmar(M.diff.cambioReal({ hash: 'h1' }, 'h1') === false, 'mismo hash, mismo contenido');
    afirmar(M.diff.cambioReal(null, 'h1') === true);
  });

  // ---------------------------------------------------------------- indice ---
  caso('indice', 'mantiene el vocabulario exacto entre aperturas', function () {
    var doc = function (ruta, lemas) {
      return {
        ruta: ruta, nombre: ruta, ext: 'md', tamano: 10, modificado: 1, hash: 'h-' + ruta,
        estado: 'ok', parser: 'texto', idioma: 'es', palabras: 10, oraciones: 2,
        terminos: lemas.map(function (l) { return { lema: l, forma: l, n: 1 }; }), terminosRuta: []
      };
    };
    var i0 = M.indice.vacio();
    var i1 = M.indice.aplicar(i0, { actualizados: [{ doc: doc('a.md', ['edema', 'disnea']), lemasPrevios: null }] });
    igual(i1.docs.length, 1);
    igual(i1.vocabulario.length, 2);

    var i2 = M.indice.aplicar(i1, { actualizados: [{ doc: doc('b.md', ['edema', 'sincope']), lemasPrevios: null }] });
    igual(i2.vocabulario.length, 3);
    igual(M.indice.mapaVocabulario(i2).get('edema'), 2, 'edema está en dos documentos');

    // a.md se reescribe y pierde «disnea»
    var i3 = M.indice.aplicar(i2, {
      actualizados: [{ doc: doc('a.md', ['edema', 'ortopnea']), lemasPrevios: new Set(['edema', 'disnea']) }]
    });
    afirmar(!M.indice.mapaVocabulario(i3).has('disnea'), 'un lema sin documentos sale del vocabulario');
    igual(M.indice.mapaVocabulario(i3).get('edema'), 2, 'edema sigue en dos documentos');

    // se borra b.md
    var i4 = M.indice.aplicar(i3, { eliminados: [{ ruta: 'b.md', lemas: new Set(['edema', 'sincope']) }] });
    igual(i4.docs.length, 1);
    igual(M.indice.mapaVocabulario(i4).get('edema'), 1);
    afirmar(!M.indice.mapaVocabulario(i4).has('sincope'));

    var est = M.indice.estadisticas(i4);
    igual(est.documentos, 1);
    igual(est.conceptos, 2);
  });

  caso('indice', 'la proyección ligera no arrastra el texto', function () {
    var p = M.indice.proyectar({
      ruta: 'a.md', nombre: 'a.md', ext: 'md', tamano: 1, modificado: 1, hash: 'h',
      estado: 'ok', parser: 'texto', idioma: 'es', palabras: 3, oraciones: 1,
      texto: 'un texto larguísimo que no debe viajar', terminos: [{ lema: 'x' }]
    });
    afirmar(p.texto === undefined, 'el índice ligero no puede llevar texto');
    igual(p.nTerminos, 1);
  });


  // ============================ Fase 3: el grafo ============================

  var KARATE = ('0 1,0 2,0 3,0 4,0 5,0 6,0 7,0 8,0 10,0 11,0 12,0 13,0 17,0 19,0 21,0 31,1 2,1 3,1 7,1 13,' +
    '1 17,1 19,1 21,1 30,2 3,2 7,2 8,2 9,2 13,2 27,2 28,2 32,3 7,3 12,3 13,4 6,4 10,5 6,5 10,5 16,6 16,' +
    '8 30,8 32,8 33,9 33,13 33,14 32,14 33,15 32,15 33,18 32,18 33,19 33,20 32,20 33,22 32,22 33,23 25,' +
    '23 27,23 29,23 32,23 33,24 25,24 27,24 31,25 31,26 29,26 33,27 33,28 31,28 33,29 32,29 33,30 32,' +
    '30 33,31 32,31 33,32 33').split(',').map(function (par) {
      var p = par.trim().split(' ');
      return { a: +p[0], b: +p[1], peso: 1 };
    });

  // ------------------------------------------------------- co-ocurrencia ---
  caso('grafo: co-ocurrencia', 'la ventana de 4 conecta lo que está cerca y nada más', function () {
    var a = M.grafo.coocurrencia.crear();
    // Seis lemas seguidos en una sola oración.
    var tokens = ['uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis'].map(function (l, i) {
      return { lema: l, forma: l, oracion: 0, desde: i, hasta: i + 1 };
    });
    a.agregar('x.md', tokens);
    var g = a.construir({ minFrecuencia: 1, minPeso: 0.1 });
    var indice = {}; g.nodos.forEach(function (n) { indice[n.lema] = n.id; });
    function hay(x, y) {
      return g.aristas.some(function (e) {
        return (e.a === indice[x] && e.b === indice[y]) || (e.a === indice[y] && e.b === indice[x]);
      });
    }
    afirmar(hay('uno', 'dos'), 'vecinos inmediatos');
    afirmar(hay('uno', 'tres'), 'dentro de la ventana');
    afirmar(hay('uno', 'cuatro'), 'la ventana de 4 abarca las posiciones i..i+3');
    afirmar(hay('uno', 'cinco') === false, 'la quinta posición ya cae fuera de la ventana');
    afirmar(hay('dos', 'cinco'), 'la ventana se desliza: desde «dos» sí se alcanza «cinco»');
  });

  caso('grafo: co-ocurrencia', 'la misma oración pesa más que cruzar un punto', function () {
    var dentro = M.grafo.coocurrencia.crear();
    dentro.agregar('a.md', [
      { lema: 'alfa', forma: 'alfa', oracion: 0 }, { lema: 'beta', forma: 'beta', oracion: 0 }
    ]);
    var fuera = M.grafo.coocurrencia.crear();
    fuera.agregar('b.md', [
      { lema: 'alfa', forma: 'alfa', oracion: 0 }, { lema: 'beta', forma: 'beta', oracion: 1 }
    ]);
    var pesoDentro = dentro.construir({ minFrecuencia: 1, minPeso: 0 }).aristas[0].peso;
    var pesoFuera = fuera.construir({ minFrecuencia: 1, minPeso: 0 }).aristas[0].peso;
    afirmar(pesoDentro > pesoFuera, 'la arista intraoración debe pesar más: ' + pesoDentro + ' vs ' + pesoFuera);
    igual(pesoDentro, M.grafo.coocurrencia.PESO_MISMA_ORACION);
  });

  caso('grafo: co-ocurrencia', 'cada arista guarda de dónde salió', function () {
    var a = M.grafo.coocurrencia.crear();
    a.agregar('clinica/notas.md', M.terminos.tokenizar('La disnea acompaña al edema pulmonar.').tokens);
    var g = a.construir({ minFrecuencia: 1, minPeso: 0 });
    afirmar(g.aristas.length > 0, 'debe haber aristas');
    var m = g.aristas[0].muestras[0];
    igual(m.ruta, 'clinica/notas.md', 'la muestra debe apuntar al documento de origen');
    afirmar(typeof m.oracion === 'number', 'y al índice de oración, que es lo que permite subrayarla');
  });

  caso('grafo: co-ocurrencia', 'el corte informa de lo que deja fuera', function () {
    var a = M.grafo.coocurrencia.crear();
    a.agregar('a.md', M.terminos.tokenizar('alfa beta gamma delta epsilon zeta eta theta iota kappa').tokens);
    var g = a.construir({ maxNodos: 3, minFrecuencia: 1, minPeso: 0 });
    igual(g.nodos.length, 3, 'el tope de nodos debe respetarse');
    afirmar(g.totales.nodosDescartados > 0, 'y lo descartado debe contarse');
    afirmar(g.totales.aristasDescartadas > 0, 'igual que las aristas que se quedan sin extremo');
  });

  caso('grafo: co-ocurrencia', 'un archivo sin texto entra por sus términos de ruta', function () {
    var a = M.grafo.coocurrencia.crear();
    a.agregarRuta('estudios/ecocardiograma-basal.png', M.terminos.terminosDeRuta('estudios/ecocardiograma-basal.png'));
    var g = a.construir({ minFrecuencia: 1, minPeso: 0 });
    var lemas = g.nodos.map(function (n) { return n.lema; });
    afirmar(lemas.indexOf('ecocardiograma') !== -1, 'el huérfano aporta sus conceptos de nombre');
    afirmar(g.aristas.length > 0, 'y quedan conectados entre sí, no como polvo suelto');
    igual(g.aristas[0].peso, M.grafo.coocurrencia.PESO_ENTRE_ORACIONES,
      'sin oraciones, la ruta conecta con el peso débil');
  });

  caso('grafo: co-ocurrencia', 'un umbral de cero significa cero, no el valor por defecto', function () {
    var a = M.grafo.coocurrencia.crear();
    a.agregar('x.md', [
      { lema: 'alfa', forma: 'alfa', oracion: 0 }, { lema: 'beta', forma: 'beta', oracion: 1 }
    ]);
    var g = a.construir({ minFrecuencia: 0, minPeso: 0, minDocs: 0 });
    igual(g.corte.minPeso, 0, 'el corte debe reflejar lo pedido, no lo supuesto');
    igual(g.corte.minFrecuencia, 0);
    igual(g.aristas.length, 1, 'con umbral cero no se descarta la arista débil');
  });

  // ------------------------------------------------------------- Louvain ---
  caso('grafo: Louvain', 'reproduce la partición conocida del club de kárate', function () {
    var r = M.grafo.louvain.detectar(34, KARATE);
    igual(r.comunidades, 4, 'la partición canónica tiene cuatro comunidades');
    afirmar(r.modularidad > 0.41 && r.modularidad < 0.43,
      'la modularidad publicada ronda 0.4188, y salió ' + r.modularidad.toFixed(4));
    afirmar(r.comunidad[0] !== r.comunidad[33],
      'los dos líderes del club deben quedar en comunidades distintas');
  });

  caso('grafo: Louvain', 'la comunidad 0 es siempre la mayor', function () {
    var r = M.grafo.louvain.detectar(34, KARATE);
    var cuenta = {};
    for (var i = 0; i < 34; i++) cuenta[r.comunidad[i]] = (cuenta[r.comunidad[i]] || 0) + 1;
    var tamanos = Object.keys(cuenta).map(function (k) { return cuenta[k]; });
    igual(cuenta[0], Math.max.apply(null, tamanos), 'la renumeración por tamaño debe ser estable');
  });

  caso('grafo: Louvain', 'las camarillas inconexas alcanzan el máximo teórico de Q', function () {
    // Para k camarillas separadas, la modularidad máxima es 1 - 1/k.
    function cliques(k) {
      var aristas = [];
      for (var c = 0; c < k; c++) {
        var base = c * 3;
        [[0, 1], [0, 2], [1, 2]].forEach(function (p) {
          aristas.push({ a: base + p[0], b: base + p[1], peso: 1 });
        });
      }
      return M.grafo.louvain.detectar(k * 3, aristas);
    }
    var dos = cliques(2);
    igual(dos.comunidades, 2);
    afirmar(Math.abs(dos.modularidad - 0.5) < 0.001, 'con dos camarillas Q = 0.5, y salió ' + dos.modularidad);
    igual(M.grafo.louvain.diversidad(dos.modularidad).etiqueta, 'Diversa');

    var tres = cliques(3);
    igual(tres.comunidades, 3);
    afirmar(Math.abs(tres.modularidad - 2 / 3) < 0.001, 'con tres camarillas Q = 0.667, y salió ' + tres.modularidad);
    igual(M.grafo.louvain.diversidad(tres.modularidad).etiqueta, 'Dispersa',
      'sólo a partir de tres islas separadas el corpus está de verdad disperso');
  });

  caso('grafo: Louvain', 'un grafo sin aristas no revienta', function () {
    var r = M.grafo.louvain.detectar(5, []);
    igual(r.modularidad, 0);
    igual(r.comunidades, 5);
  });

  caso('grafo: Louvain', 'la diversidad temática cubre los cuatro tramos', function () {
    igual(M.grafo.louvain.diversidad(0.10).etiqueta, 'Enfocada');
    igual(M.grafo.louvain.diversidad(0.30).etiqueta, 'Media');
    igual(M.grafo.louvain.diversidad(0.50).etiqueta, 'Diversa');
    igual(M.grafo.louvain.diversidad(0.75).etiqueta, 'Dispersa');
    afirmar(M.grafo.louvain.diversidad(0.5).q === 0.5, 'la cifra viaja siempre con la etiqueta');
  });

  // ------------------------------------------------------------ métricas ---
  caso('grafo: métricas', 'la intermediación coincide con los valores conocidos', function () {
    // Camino de cinco nodos: 0, 3, 4, 3, 0.
    var camino = [{ a: 0, b: 1 }, { a: 1, b: 2 }, { a: 2, b: 3 }, { a: 3, b: 4 }].map(function (e) {
      return { a: e.a, b: e.b, peso: 1 };
    });
    var r = M.grafo.metricas.intermediacion(5, camino);
    igual(Math.round(r.valor[0]), 0);
    igual(Math.round(r.valor[1]), 3);
    igual(Math.round(r.valor[2]), 4);
    igual(Math.round(r.valor[4]), 0);
    afirmar(r.exacta, 'con cinco nodos el cálculo debe ser exacto');

    // Kárate: valores publicados 231.07 para el nodo 0 y 160.55 para el 33.
    var k = M.grafo.metricas.intermediacion(34, KARATE);
    afirmar(Math.abs(k.valor[0] - 231.07) < 0.5, 'nodo 0: ' + k.valor[0].toFixed(2));
    afirmar(Math.abs(k.valor[33] - 160.55) < 0.5, 'nodo 33: ' + k.valor[33].toFixed(2));
  });

  caso('grafo: métricas', 'el centro de una estrella se lleva toda la intermediación', function () {
    var aristas = [];
    for (var i = 1; i <= 5; i++) aristas.push({ a: 0, b: i, peso: 1 });
    var r = M.grafo.metricas.intermediacion(6, aristas);
    igual(r.valor[0], 10, 'los diez pares de hojas pasan por el centro');
    igual(r.valor[3], 0, 'ninguna hoja intermedia nada');
  });

  caso('grafo: métricas', 'el muestreo aproxima sin mentir sobre lo que hace', function () {
    var r = M.grafo.metricas.intermediacion(34, KARATE, { umbralExacto: 10, pivotes: 20 });
    afirmar(r.exacta === false, 'debe declararse aproximada');
    igual(r.fuentes, 20, 'y decir con cuántos pivotes');
    afirmar(r.valor[0] > 100, 'el nodo más central debe seguir destacando: ' + r.valor[0].toFixed(1));
    // Reproducible: la misma entrada, el mismo resultado.
    var otra = M.grafo.metricas.intermediacion(34, KARATE, { umbralExacto: 10, pivotes: 20 });
    igual(r.valor[0], otra.valor[0], 'el muestreo usa azar fijo: dos aperturas dan lo mismo');
  });

  caso('grafo: métricas', 'cuenta las componentes conexas', function () {
    var r = M.grafo.metricas.componentes(5, [{ a: 0, b: 1, peso: 1 }, { a: 2, b: 3, peso: 1 }]);
    igual(r.cuantas, 3, 'dos parejas y un nodo suelto');
    igual(r.mayor, 2);
  });

  caso('grafo: métricas', 'los puntos conectores prefieren el puente al protagonista', function () {
    // Dos camarillas unidas por un solo nodo poco frecuente.
    var aristas = [];
    [[0, 1], [0, 2], [1, 2], [4, 5], [4, 6], [5, 6], [2, 3], [3, 4]].forEach(function (p) {
      aristas.push({ a: p[0], b: p[1], peso: 1 });
    });
    var nodos = [];
    for (var i = 0; i < 7; i++) {
      nodos.push({ id: i, lema: 'n' + i, forma: 'n' + i, frecuencia: i === 3 ? 2 : 40, docs: 1, rutas: [] });
    }
    var inter = M.grafo.metricas.intermediacion(7, aristas);
    var conectores = M.grafo.metricas.puntosConectores(nodos, inter.normal, 5);
    igual(conectores[0].lema, 'n3', 'el puente raro debe encabezar, no los nodos repetidos');
  });

  caso('grafo: métricas', 'el resumen de comunidad trae porcentaje y nombre por plantilla', function () {
    var nodos = [
      { id: 0, lema: 'edema', forma: 'edema', frecuencia: 9, docs: 2, rutas: ['a.md'] },
      { id: 1, lema: 'disnea', forma: 'disnea', frecuencia: 7, docs: 2, rutas: ['a.md'] },
      { id: 2, lema: 'docencia', forma: 'docencia', frecuencia: 5, docs: 1, rutas: ['b.md'] }
    ];
    var inter = new Float64Array([0.5, 0.3, 0.1]);
    var r = M.grafo.metricas.resumirComunidades(nodos, [0, 0, 1], inter, 8);
    igual(r.length, 2);
    igual(r[0].nodos, 2);
    afirmar(Math.abs(r[0].porcentaje - 66.67) < 0.1, 'porcentaje: ' + r[0].porcentaje);
    contiene(r[0].nombre, 'edema', 'el nombre por plantilla usa los términos más centrales');
  });

  // --------------------------------------------------- capa de documentos ---
  caso('grafo: documentos', 'resuelve enlaces relativos, wikilinks y declara los ambiguos', function () {
    var rutas = ['clinica/notas.md', 'clinica/fisiopatologia.md', 'docencia/sesion.md', 'archivo/sesion.md'];
    var idx = M.grafo.documentos.indiceDeRutas(rutas);
    igual(M.grafo.documentos.resolver('fisiopatologia', 'clinica/notas.md', idx).indice, 1, 'wikilink por nombre');
    igual(M.grafo.documentos.resolver('../docencia/sesion.md', 'clinica/notas.md', idx).indice, 2, 'ruta relativa');
    igual(M.grafo.documentos.resolver('clinica/fisiopatologia.md', 'x.md', idx).indice, 1, 'ruta desde la raíz');
    igual(M.grafo.documentos.resolver('sesion', 'clinica/notas.md', idx).motivo, 'ambiguo',
      'dos documentos con el mismo nombre no producen una dependencia inventada');
    igual(M.grafo.documentos.resolver('no-existe.md', 'clinica/notas.md', idx).motivo, 'sin destino');
  });

  caso('grafo: documentos', 'detecta secuencias de versión por el nombre', function () {
    var aristas = M.grafo.documentos.secuenciasDeVersion([
      'ensayo v1.md', 'ensayo v2.md', 'ensayo v3.md', 'otro.md'
    ]);
    igual(aristas.length, 2, 'tres versiones encadenan dos aristas');
    igual(aristas[0].tipo, 'version');
    var conCopia = M.grafo.documentos.secuenciasDeVersion(['informe borrador.md', 'informe final.md']);
    igual(conCopia.length, 1, 'borrador y final son la misma secuencia');
    afirmar(M.grafo.documentos.analizarVersion('sin marcas.md') === null, 'un nombre normal no es una versión');
  });

  caso('grafo: documentos', 'las referencias compartidas exigen más de una coincidencia', function () {
    var claves = [
      new Set(['cita:perez:2019', 'cita:lopez:2020', 'doi:10.1001/x']),
      new Set(['cita:perez:2019', 'cita:lopez:2020']),
      new Set(['cita:perez:2019'])
    ];
    var aristas = M.grafo.documentos.aristasPorReferencia(claves, 2);
    igual(aristas.length, 1, 'sólo el par que comparte dos referencias');
    igual(aristas[0].peso, 2);
  });

  caso('grafo: documentos', 'extrae DOI y citas de autor y año', function () {
    var c = M.grafo.documentos.clavesBibliograficas(
      'Como señala Perez, 2019 y confirma Lopez et al., 2020 (doi 10.1001/jama.2019.1234).');
    var lista = Array.from(c);
    afirmar(lista.indexOf('cita:perez:2019') !== -1, 'falta la cita simple: ' + lista.join(', '));
    afirmar(lista.indexOf('cita:lopez:2020') !== -1, 'falta la cita con et al.');
    afirmar(lista.some(function (x) { return x.indexOf('doi:10.1001/jama.2019.1234') === 0; }), 'falta el DOI');
  });

  caso('grafo: documentos', 'la afinidad ignora el vocabulario que está en todas partes', function () {
    var docs = [];
    for (var i = 0; i < 6; i++) {
      docs.push({ ruta: 'd' + i + '.md', terminos: [{ lema: 'comun', n: 10 }, { lema: 'propio' + i, n: 5 }] });
    }
    var r = M.grafo.documentos.afinidad(docs, { suelo: 0.01 });
    igual(r.pares.length, 0, 'un término presente en todos los documentos no puede emparejarlos');
    afirmar(r.terminosIgnorados >= 1, 'y debe contarse como ignorado');
  });

  caso('grafo: documentos', 'la afinidad separa dependencia de estadística', function () {
    var docs = [
      { ruta: 'a.md', nombre: 'a.md', ext: 'md', estado: 'ok', palabras: 300, meta: { enlaces: [{ tipo: 'wikilink', destino: 'b' }] },
        texto: '', terminos: [{ lema: 'insuficiencia', n: 5 }, { lema: 'cardiaca', n: 4 }] },
      { ruta: 'b.md', nombre: 'b.md', ext: 'md', estado: 'ok', palabras: 300, meta: { enlaces: [] },
        texto: '', terminos: [{ lema: 'insuficiencia', n: 3 }, { lema: 'cardiaca', n: 3 }] },
      { ruta: 'c.md', nombre: 'c.md', ext: 'md', estado: 'ok', palabras: 300, meta: { enlaces: [] },
        texto: '', terminos: [{ lema: 'docencia', n: 6 }] }
    ];
    var g = M.grafo.documentos.construir(docs, { suelo: 0.05 });
    igual(g.dependencias.length, 1, 'una sola dependencia escrita');
    igual(g.dependencias[0].tipo, 'enlace');
    afirmar(g.afinidades.some(function (e) { return (e.a === 0 && e.b === 1) || (e.a === 1 && e.b === 0); }),
      'a.md y b.md comparten vocabulario');
    afirmar(!g.afinidades.some(function (e) { return e.a === 2 || e.b === 2; }),
      'c.md no comparte nada con nadie');
  });

  // ----------------------------------------------------------- capa mixta ---
  caso('grafo: capa mixta', 'une conceptos y documentos, y señala a los que no tocan nada', function () {
    var conceptos = { nodos: [
      { id: 0, lema: 'edema', forma: 'edema' },
      { id: 1, lema: 'disnea', forma: 'disnea' }
    ] };
    var capaDocs = { nodos: [
      { id: 0, ruta: 'a.md' }, { id: 1, ruta: 'b.md' }, { id: 2, ruta: 'foto.png' }
    ] };
    var docs = [
      { ruta: 'a.md', terminos: [{ lema: 'edema', n: 3 }, { lema: 'disnea', n: 2 }] },
      { ruta: 'b.md', terminos: [{ lema: 'edema', n: 1 }] },
      { ruta: 'foto.png', terminos: [], terminosRuta: [{ lema: 'radiografia', n: 1 }] }
    ];
    var m = M.grafo.mixta.construir(conceptos, capaDocs, docs, {});
    igual(m.totales.pertenencias, 3);
    igual(m.totales.documentosSinConcepto, 1, 'la imagen no toca ningún concepto del grafo');
    igual(m.huerfanos[0], 2);
  });

  // -------------------------------------------------------------- colores ---
  caso('grafo: colores', 'doce comunidades siguen siendo distinguibles', function () {
    var tonos = [];
    for (var i = 0; i < 12; i++) tonos.push(M.colores.tono(i));
    for (var a = 0; a < 12; a++) {
      for (var b = a + 1; b < 12; b++) {
        var d = Math.abs(tonos[a] - tonos[b]);
        var separacion = Math.min(d, 360 - d);
        afirmar(separacion > 10, 'los tonos ' + a + ' y ' + b + ' están a ' + separacion.toFixed(1) + ' grados');
      }
    }
  });

  caso('grafo: colores', 'el respaldo sin oklch produce sRGB válido', function () {
    for (var i = 0; i < 15; i++) {
      var c = M.colores.aRgb(i);
      afirmar(/^rgb\(\d{1,3},\d{1,3},\d{1,3}\)$/.test(c), 'color inválido en ' + i + ': ' + c);
    }
  });


  // ============================ Fase 4: brechas =============================

  // Dos territorios densos por dentro, casi sin contacto, unidos por un solo
  // concepto poco frecuente. Es el caso que las tres definiciones deben cazar.
  function corpusConBrecha() {
    var aristas = [];
    function camarilla(ids, peso) {
      for (var i = 0; i < ids.length; i++) {
        for (var j = i + 1; j < ids.length; j++) aristas.push({ a: ids[i], b: ids[j], peso: peso || 3 });
      }
    }
    camarilla([0, 1, 2, 3]);            // clínica
    camarilla([4, 5, 6, 7]);            // docencia
    aristas.push({ a: 3, b: 8, peso: 1 }, { a: 8, b: 4, peso: 1 });   // puente por el 8

    var formas = ['edema', 'disnea', 'ortopnea', 'congestion',
                  'docencia', 'simulacion', 'evaluacion', 'curriculum', 'residente'];
    var nodos = formas.map(function (l, i) {
      return { id: i, lema: l, forma: l, frecuencia: i < 8 ? 20 : 3, docs: 2, rutas: [] };
    });
    var comunidad = [0, 0, 0, 0, 1, 1, 1, 1, 0];
    var intermediacion = new Float64Array([0.05, 0.05, 0.05, 0.40, 0.40, 0.05, 0.05, 0.05, 0.90]);

    // «residente» aparece en los dos documentos, pero nunca con ambos lados.
    var docsPorLema = new Map();
    formas.forEach(function (l, i) {
      docsPorLema.set(l, new Set(i < 4 ? ['clinica/a.md'] : (i < 8 ? ['docencia/b.md'] : ['clinica/a.md', 'docencia/b.md'])));
    });

    var capaDocumentos = {
      nodos: [
        { id: 0, ruta: 'clinica/a.md', nombre: 'a.md', estado: 'ok', palabras: 400, terminos: 30 },
        { id: 1, ruta: 'docencia/b.md', nombre: 'b.md', estado: 'ok', palabras: 380, terminos: 28 },
        { id: 2, ruta: 'notas/suelto.md', nombre: 'suelto.md', estado: 'ok', palabras: 600, terminos: 45 }
      ],
      dependencias: [],
      afinidades: [{ a: 0, b: 1, coseno: 0.21 }]
    };

    return { nodos: nodos, aristas: aristas, comunidad: comunidad,
             intermediacion: intermediacion, docsPorLema: docsPorLema, capaDocumentos: capaDocumentos };
  }

  caso('brechas: estructural', 'encuentra el par de territorios que no se hablan', function () {
    var r = M.grafo.brechas.estructurales(corpusConBrecha(), {});
    igual(r.lista.length, 1, 'debe salir exactamente la brecha entre clínica y docencia');
    var b = r.lista[0];
    igual(b.aristasCruzadas, 1,
      'el único contacto entre los dos territorios es la arista del concepto puente');
    afirmar(b.terminosA.indexOf('edema') !== -1 || b.terminosB.indexOf('edema') !== -1, 'falta el lado clínico');
    afirmar(b.terminosA.indexOf('docencia') !== -1 || b.terminosB.indexOf('docencia') !== -1, 'falta el lado docente');
  });

  caso('brechas: estructural', 'la densidad interna se compara con el grafo, no con la mediana', function () {
    // Con dos comunidades, comparar contra la mediana descarta una por
    // definición. Éste es el caso que lo demostró.
    var e = corpusConBrecha();
    var r = M.grafo.brechas.estructurales(e, {});
    afirmar(r.lista.length > 0, 'la comparación con la mediana dejaba esto en cero');
    afirmar(r.parametros.densidadGlobal < r.parametros.minimoDensidadInterna + 1e-9,
      'el mínimo interno parte de la densidad global');
  });

  caso('brechas: estructural', 'cerca y grande vale más que lejos y marginal', function () {
    // Tres camarillas: A y B grandes a dos saltos, C marginal a seis.
    var aristas = [];
    function camarilla(ids) {
      for (var i = 0; i < ids.length; i++) for (var j = i + 1; j < ids.length; j++) aristas.push({ a: ids[i], b: ids[j], peso: 3 });
    }
    camarilla([0, 1, 2, 3, 4]);          // A, grande
    camarilla([5, 6, 7, 8, 9]);          // B, grande
    camarilla([10, 11, 12]);             // C, marginal
    aristas.push({ a: 4, b: 20, peso: 1 }, { a: 20, b: 5, peso: 1 });               // A—B: dos saltos
    [21, 22, 23, 24].forEach(function (v, k) {                                       // A—C: cadena larga
      aristas.push({ a: k === 0 ? 0 : 20 + k, b: v, peso: 1 });
    });
    aristas.push({ a: 24, b: 10, peso: 1 });

    var n = 25;
    var nodos = [], comunidad = [], intermediacion = new Float64Array(n);
    for (var i = 0; i < n; i++) {
      nodos.push({ id: i, lema: 'n' + i, forma: 'n' + i, frecuencia: i < 10 ? 30 : (i < 13 ? 4 : 2), docs: 1, rutas: [] });
      comunidad.push(i < 5 ? 0 : (i < 10 ? 1 : (i < 13 ? 2 : 3)));
      intermediacion[i] = i === 20 ? 0.9 : 0.1;
    }
    var r = M.grafo.brechas.estructurales({
      nodos: nodos, aristas: aristas, comunidad: comunidad, intermediacion: intermediacion
    }, { minTamanoComunidad: 3, percentilDensidad: 90 });

    afirmar(r.lista.length >= 2, 'deben evaluarse varios pares, salieron ' + r.lista.length);
    var ab = r.lista.filter(function (b) {
      return (b.comunidadA === 0 && b.comunidadB === 1) || (b.comunidadA === 1 && b.comunidadB === 0);
    })[0];
    afirmar(ab, 'falta el par de los dos territorios grandes');
    igual(r.lista[0], ab, 'el par grande y cercano debe encabezar el ranking');
  });

  caso('brechas: estructural', 'una brecha sin camino se declara, no se puntúa como cercana', function () {
    var aristas = [];
    [[0, 1], [0, 2], [1, 2], [3, 4], [3, 5], [4, 5]].forEach(function (p) {
      aristas.push({ a: p[0], b: p[1], peso: 2 });
    });
    var nodos = [], comunidad = [0, 0, 0, 1, 1, 1];
    for (var i = 0; i < 6; i++) nodos.push({ id: i, lema: 'x' + i, forma: 'x' + i, frecuencia: 10, docs: 1, rutas: [] });
    var r = M.grafo.brechas.estructurales({
      nodos: nodos, aristas: aristas, comunidad: comunidad, intermediacion: new Float64Array(6)
    }, {});
    igual(r.lista.length, 1);
    afirmar(r.lista[0].sinCamino === true, 'dos componentes separadas no tienen camino');
    igual(r.lista[0].distancia, null);
    afirmar(r.lista[0].facilidad < 0.2, 'sin camino la facilidad debe quedar por debajo de cualquier distancia real');
  });

  caso('brechas: aislado', 'el umbral de riqueza es relativo al corpus', function () {
    var capa = {
      nodos: [
        { id: 0, ruta: 'a.md', nombre: 'a.md', estado: 'ok', palabras: 100, terminos: 10 },
        { id: 1, ruta: 'b.md', nombre: 'b.md', estado: 'ok', palabras: 200, terminos: 20 },
        { id: 2, ruta: 'c.md', nombre: 'c.md', estado: 'ok', palabras: 900, terminos: 90 }
      ],
      dependencias: [], afinidades: []
    };
    var r = M.grafo.brechas.aislados(capa, {});
    igual(r.parametros.umbralTerminos, 20, 'la mediana de 10, 20 y 90 es 20');
    afirmar(r.lista.some(function (d) { return d.ruta === 'c.md'; }), 'el documento denso debe salir');
    afirmar(!r.lista.some(function (d) { return d.ruta === 'a.md'; }), 'el más pobre del corpus no es un aislado interesante');
  });

  caso('brechas: aislado', 'un documento enlazado no es un aislado', function () {
    var capa = {
      nodos: [
        { id: 0, ruta: 'a.md', nombre: 'a.md', estado: 'ok', palabras: 500, terminos: 50 },
        { id: 1, ruta: 'b.md', nombre: 'b.md', estado: 'ok', palabras: 500, terminos: 50 }
      ],
      dependencias: [{ a: 0, b: 1, tipo: 'enlace', peso: 1 }], afinidades: []
    };
    igual(M.grafo.brechas.aislados(capa, {}).lista.length, 0);
  });

  caso('brechas: aislado', 'la isla completa pesa más que la que tiene vecinos evidentes', function () {
    var capa = {
      nodos: [
        { id: 0, ruta: 'isla.md', nombre: 'isla.md', estado: 'ok', palabras: 500, terminos: 50 },
        { id: 1, ruta: 'parecido-a.md', nombre: 'parecido-a.md', estado: 'ok', palabras: 500, terminos: 50 },
        { id: 2, ruta: 'parecido-b.md', nombre: 'parecido-b.md', estado: 'ok', palabras: 500, terminos: 50 }
      ],
      dependencias: [], afinidades: [{ a: 1, b: 2, coseno: 0.6 }]
    };
    var r = M.grafo.brechas.aislados(capa, {});
    igual(r.lista[0].ruta, 'isla.md', 'sin ningún parecido, el aislamiento es más profundo');
  });

  caso('brechas: puente ausente', 'caza el concepto que toca dos mundos sin juntarlos nunca', function () {
    var r = M.grafo.brechas.puentesAusentes(corpusConBrecha(), {});
    igual(r.lista.length, 1);
    igual(r.lista[0].forma, 'residente');
    afirmar(r.lista[0].documentosA.length > 0 && r.lista[0].documentosB.length > 0,
      'debe citar dónde aparece con cada lado');
  });

  caso('brechas: puente ausente', 'si algún documento sí junta los dos lados, no hay brecha', function () {
    var e = corpusConBrecha();
    // Ahora existe un texto donde el puente y ambos lados conviven.
    e.docsPorLema.get('congestion').add('mixto.md');
    e.docsPorLema.get('docencia').add('mixto.md');
    e.docsPorLema.get('residente').add('mixto.md');
    igual(M.grafo.brechas.puentesAusentes(e, {}).lista.length, 0,
      'el puente ya está escrito: deja de ser una ausencia');
  });

  caso('brechas: puente ausente', 'un concepto de un solo documento no puede unir nada', function () {
    var e = corpusConBrecha();
    e.docsPorLema.set('residente', new Set(['clinica/a.md']));
    igual(M.grafo.brechas.puentesAusentes(e, {}).lista.length, 0);
  });

  caso('brechas', 'el cálculo completo devuelve los tres tipos y sus parámetros', function () {
    var r = M.grafo.brechas.calcular(corpusConBrecha(), {});
    igual(r.estructurales.length, 1);
    afirmar(r.aislados.length >= 1);
    igual(r.puentesAusentes.length, 1);
    afirmar(r.estructurales[0].documentosA.length > 0, 'cada lado debe traer sus documentos más cercanos');
    afirmar(r.parametros.estructurales.corteDensidad != null, 'los parámetros del cálculo deben viajar con el resultado');
  });

  // -------------------------------------------------------------- preguntas ---
  caso('preguntas', 'cada brecha produce una pregunta utilizable sin IA', function () {
    var r = M.grafo.preguntas.poblar(M.grafo.brechas.calcular(corpusConBrecha(), {}));
    ['estructurales', 'aislados', 'puentesAusentes'].forEach(function (grupo) {
      r[grupo].forEach(function (b) {
        afirmar(b.pregunta && b.pregunta.texto.length > 40, 'pregunta demasiado corta en ' + grupo);
        afirmar(b.pregunta.texto.indexOf('?') !== -1, 'debe ser una pregunta, no un enunciado');
        afirmar(b.pregunta.texto.indexOf('undefined') === -1, 'plantilla con hueco sin rellenar: ' + b.pregunta.texto);
        igual(b.pregunta.origen, 'plantilla');
      });
    });
  });

  caso('preguntas', 'la misma brecha da siempre la misma pregunta', function () {
    var b = {
      tipo: 'estructural', comunidadA: 0, comunidadB: 1,
      terminosA: ['edema', 'disnea'], terminosB: ['docencia'],
      centralA: { forma: 'edema' }, centralB: { forma: 'docencia' },
      documentosA: [{ ruta: 'a.md' }], documentosB: [{ ruta: 'b.md' }],
      distancia: 2, sinCamino: false, aristasCruzadas: 1, peso: 0.4
    };
    igual(M.grafo.preguntas.para(b).texto, M.grafo.preguntas.para(b).texto,
      'el deslizador temporal compara instantáneas: la redacción no puede bailar');
  });

  caso('preguntas', 'una brecha sin camino no presume de cercanía', function () {
    for (var c = 0; c < 40; c++) {
      var b = {
        tipo: 'estructural', comunidadA: c, comunidadB: c + 1,
        terminosA: ['a' + c], terminosB: ['b' + c],
        centralA: { forma: 'a' + c }, centralB: { forma: 'b' + c },
        documentosA: [{ ruta: 'x.md' }], documentosB: [{ ruta: 'y.md' }],
        distancia: null, sinCamino: true, aristasCruzadas: 0, peso: 0.3
      };
      var t = M.grafo.preguntas.para(b).texto;
      afirmar(t.indexOf('el puente es corto') === -1, 'plantilla incoherente para una brecha sin camino: ' + t);
    }
  });

  caso('preguntas', 'la carga para la IA no lleva texto de los documentos', function () {
    var r = M.grafo.preguntas.poblar(M.grafo.brechas.calcular(corpusConBrecha(), {}));
    ['estructurales', 'aislados', 'puentesAusentes'].forEach(function (grupo) {
      r[grupo].forEach(function (b) {
        var carga = JSON.stringify(b.pregunta.cargaParaIA || {});
        afirmar(carga.indexOf('texto') === -1, 'la carga no puede incluir texto crudo: ' + carga);
        afirmar(carga.length < 600, 'la carga debe ser una lista de términos, no un documento');
      });
    });
  });

  return { casos: casos, afirmar: afirmar, igual: igual, contiene: contiene, noContiene: noContiene };
});
