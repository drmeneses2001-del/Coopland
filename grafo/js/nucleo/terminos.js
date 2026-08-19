(function (raiz, fabrica) {
  var vacias = (typeof module === 'object' && module.exports)
    ? require('./vacias.js')
    : (raiz.GC && raiz.GC.vacias);
  var api = fabrica(vacias);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else ((raiz.GC = raiz.GC || {}).terminos = api);
})(typeof self !== 'undefined' ? self : globalThis, function (vacias) {
  'use strict';

  // ---------------------------------------------------------------------
  // Normalización, segmentación y lematización ligera bilingüe (ES/EN).
  // La clave de un término va sin acentos y en minúscula; la forma mostrada
  // conserva la grafía más frecuente en el corpus del documento.
  // ---------------------------------------------------------------------

  // La eñe se protege antes de descomponer: en español «año» y «ano» son
  // conceptos distintos, y NFD las fundiría en el mismo lema.
  function clave(palabra) {
    return palabra
      .toLowerCase()
      .replace(/ñ/g, '\u0001')
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')   // quita el resto de diacríticos
      .replace(/\u0001/g, 'ñ')
      .replace(/[^a-z0-9ñ]/g, '');
  }

  // Segmentación en oraciones. Protege abreviaturas frecuentes en texto
  // clínico y académico para no partir donde no hay final de oración.
  var ABREVIATURAS = /(?:\b(?:dr|dra|sr|sra|lic|mtro|etc|vs|fig|tab|no|núm|nro|pág|aprox|ej|p\.?\s?ej|et al|e\.?g|i\.?e|mg|ml|kg|cm|mm|hrs?)\.)$/i;

  function oraciones(texto) {
    var resultado = [];
    if (!texto) return resultado;
    var inicio = 0;
    var re = /([.!?…]+|\n{2,})(\s+|$)/g;
    var m;
    while ((m = re.exec(texto)) !== null) {
      var corte = m.index + m[1].length;
      var fragmento = texto.slice(inicio, corte);
      if (ABREVIATURAS.test(fragmento.trimEnd())) continue; // falso final
      var limpio = fragmento.trim();
      if (limpio) resultado.push({ texto: limpio, desde: inicio, hasta: corte });
      inicio = corte + m[2].length;
    }
    var cola = texto.slice(inicio).trim();
    if (cola) resultado.push({ texto: cola, desde: inicio, hasta: texto.length });
    return resultado;
  }

  // Detección de idioma por proporción de palabras vacías reconocidas.
  var SET_ES = new Set(vacias.ES);
  var SET_EN = new Set(vacias.EN);

  function detectarIdioma(texto) {
    var muestra = texto.slice(0, 20000).toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '');
    var palabras = muestra.match(/[a-zñ]{2,}/g);
    if (!palabras || palabras.length < 20) return { idioma: 'indeterminado', es: 0, en: 0 };
    var es = 0, en = 0;
    for (var i = 0; i < palabras.length; i++) {
      if (SET_ES.has(palabras[i])) es++;
      if (SET_EN.has(palabras[i])) en++;
    }
    var idioma;
    if (es === 0 && en === 0) idioma = 'indeterminado';
    else if (es >= en * 1.3) idioma = 'es';
    else if (en >= es * 1.3) idioma = 'en';
    else idioma = 'mixto';
    return { idioma: idioma, es: es / palabras.length, en: en / palabras.length };
  }

  // Lematización ligera. Conservadora a propósito: normaliza plurales y unos
  // pocos sufijos productivos. No es un stemmer agresivo — preferimos dos
  // nodos separados antes que fusionar dos conceptos distintos.
  var VOCALES = /[aeiou]/;

  // Terminaciones invariables en singular y plural. Sin esta guarda, la regla
  // de plural destroza medio vocabulario clínico: dosis, crisis, diagnosis,
  // fibrosis, amiloidosis, hepatitis, artritis, virus, tórax…
  var INVARIABLES = /(?:sis|tis|xis|isis|us|is|ax|ex|ix|ox)$/;

  function lematizarEs(p) {
    if (INVARIABLES.test(p)) return p;
    if (p.length > 7 && /mente$/.test(p)) return p.slice(0, -5);
    if (p.length > 7 && /ciones$/.test(p)) return p.slice(0, -6) + 'cion';
    if (p.length > 7 && /idades$/.test(p)) return p.slice(0, -6) + 'idad';
    if (p.length > 4 && /ces$/.test(p)) return p.slice(0, -3) + 'z';   // luces->luz, raices->raiz
    if (p.length > 4 && /es$/.test(p)) {
      // ¿El singular termina en consonante (hospitales->hospital) o en -e
      // (pacientes->paciente)? Lo decide la consonante final del candidato.
      // La -s queda fuera a propósito: los singulares en -s son raros (mes,
      // gas) y los nombres en -se son constantes (fase, base, clase, frase);
      // incluirla arruinaba más palabras de las que arreglaba.
      var base = p.slice(0, -2);
      if (/[lrndzjxy]$/.test(base)) return base;
      return p.slice(0, -1);
    }
    if (p.length > 4 && /s$/.test(p) && VOCALES.test(p.slice(-2, -1))) return p.slice(0, -1);
    return p;
  }

  function lematizarEn(p) {
    if (INVARIABLES.test(p)) return p;   // analysis, diagnosis, virus, index…
    if (p.length > 4 && /ies$/.test(p)) return p.slice(0, -3) + 'y';
    if (p.length > 4 && /(?:sses|shes|ches|xes|zes)$/.test(p)) return p.slice(0, -2);
    if (p.length > 5 && /ing$/.test(p)) {
      var base = p.slice(0, -3);
      if (base.length > 3 && base[base.length - 1] === base[base.length - 2]) base = base.slice(0, -1);
      return base;
    }
    if (p.length > 4 && /ed$/.test(p) && !/eed$/.test(p)) return p.slice(0, -2);
    if (p.length > 3 && /s$/.test(p) && !/ss$/.test(p)) return p.slice(0, -1);
    return p;
  }

  function lematizar(p, idioma) {
    if (idioma === 'es') return lematizarEs(p);
    if (idioma === 'en') return lematizarEn(p);
    // Mixto o indeterminado: sólo normalización de plural común a ambos.
    if (INVARIABLES.test(p)) return p;
    if (p.length > 4 && /s$/.test(p) && !/ss$/.test(p) && VOCALES.test(p.slice(-2, -1))) return p.slice(0, -1);
    return p;
  }

  // Tokenización con posición. La posición permite, más adelante, resaltar en
  // el visor la oración exacta que generó cada arista.
  function tokenizar(texto, opciones) {
    opciones = opciones || {};
    var idioma = opciones.idioma || detectarIdioma(texto).idioma;
    var vaciasSet = opciones.vacias || vacias.conjuntoBase();
    var minimo = opciones.minimo || 3;
    var segmentos = oraciones(texto);
    var tokens = [];
    var re = /[\p{L}\p{N}][\p{L}\p{N}\-·']*/gu;

    for (var s = 0; s < segmentos.length; s++) {
      var seg = segmentos[s], m;
      re.lastIndex = 0;
      while ((m = re.exec(seg.texto)) !== null) {
        var bruto = m[0];
        var k = clave(bruto);
        if (k.length < minimo) continue;
        if (/^\d+$/.test(k)) continue;                 // cifras sueltas, no
        if (vaciasSet.has(k)) continue;
        var lema = lematizar(k, idioma);
        if (lema.length < minimo || vaciasSet.has(lema)) continue;
        tokens.push({
          lema: lema,
          forma: bruto,
          oracion: s,
          desde: seg.desde + m.index,
          hasta: seg.desde + m.index + bruto.length
        });
      }
    }
    return { tokens: tokens, oraciones: segmentos, idioma: idioma };
  }

  // Frecuencias por lema, conservando la grafía superficial más usada.
  function frecuencias(tokens) {
    var mapa = new Map();
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      var e = mapa.get(t.lema);
      if (!e) { e = { lema: t.lema, n: 0, formas: new Map(), oraciones: new Set() }; mapa.set(t.lema, e); }
      e.n++;
      e.formas.set(t.forma, (e.formas.get(t.forma) || 0) + 1);
      e.oraciones.add(t.oracion);
    }
    var salida = [];
    mapa.forEach(function (e) {
      var mejor = '', mejorN = -1;
      e.formas.forEach(function (n, forma) { if (n > mejorN) { mejorN = n; mejor = forma; } });
      salida.push({ lema: e.lema, forma: mejor, n: e.n, oraciones: Array.from(e.oraciones) });
    });
    salida.sort(function (a, b) { return b.n - a.n || a.lema.localeCompare(b.lema); });
    return salida;
  }

  // Términos derivados de la ruta y el nombre del archivo. Es lo único que
  // tienen los archivos de los que no podemos extraer texto (imágenes, etc.),
  // y es lo que les permite existir como nodos huérfanos visibles.
  function terminosDeRuta(ruta, vaciasSet) {
    vaciasSet = vaciasSet || vacias.conjuntoBase();
    var partes = String(ruta || '').split(/[\/\\]/);
    var texto = partes.join(' ')
      .replace(/\.[A-Za-z0-9]{1,5}$/, ' ')
      .replace(/[_\-.]+/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2');
    var vistos = new Map();
    var m, re = /[\p{L}\p{N}]{3,}/gu;
    while ((m = re.exec(texto)) !== null) {
      var k = clave(m[0]);
      if (k.length < 3 || /^\d+$/.test(k) || vaciasSet.has(k)) continue;
      if (!vistos.has(k)) vistos.set(k, { lema: k, forma: m[0], n: 0 });
      vistos.get(k).n++;
    }
    return Array.from(vistos.values());
  }

  return {
    clave: clave,
    oraciones: oraciones,
    detectarIdioma: detectarIdioma,
    lematizar: lematizar,
    tokenizar: tokenizar,
    frecuencias: frecuencias,
    terminosDeRuta: terminosDeRuta
  };
});
