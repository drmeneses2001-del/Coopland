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
      registro: raiz.GC.registro, parsers: raiz.GC.parsers
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

  return { casos: casos, afirmar: afirmar, igual: igual, contiene: contiene, noContiene: noContiene };
});
