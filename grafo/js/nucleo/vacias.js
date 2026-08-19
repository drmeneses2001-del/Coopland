(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else ((raiz.GC = raiz.GC || {}).vacias = api);
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Lista propia de palabras vacías (stop words), bilingüe.
  // Las claves están sin acentos y en minúscula, igual que las claves de término.
  // El usuario puede ampliarla desde la interfaz; ver almacen.config('vaciasPropias').

  var ES = ('a al algo algun alguna algunas alguno algunos ante antes aquel aquella aquellas aquello aquellos aqui asi aun aunque ' +
    'bajo bien cada casi como con contra cual cuales cuando cuanto cuyo de del demas desde donde dos e el ella ellas ello ellos ' +
    'en entre era eran eres es esa esas ese eso esos esta estaba estan estar estas este esto estos estoy fue fueron fui ha habia ' +
    'haber habia han has hasta hay he hemos hizo hoy incluso ir junto la las le les lo los luego mas me mediante mi mia mientras ' +
    'mio mis misma mismo mucho muy nada ni no nos nosotros nuestra nuestro o os otra otras otro otros para pero pese poco por ' +
    'porque pues que quien quienes se sea segun ser si sido sin sobre solo son su sus tal tambien tan tanto te tenemos tener ' +
    'tengo ti tiene tienen todo todos tras tu tus un una unas uno unos usted ustedes va van varias varios ver vez y ya yo ' +
    'cuanta cuantas cuantos donde dicha dicho durante ejemplo etc fin forma general modo parte pueden puede ademas asimismo ' +
    'cabe cierta cierto debe deben decir dice dijo estara estaria hacer hace hacia mismas mismos nunca otra siempre siendo ' +
    'siguiente sino sola solas solos tener tenia toda todas ultimo unico vease').split(/\s+/);

  var EN = ('a about above after again against all am an and any are as at be because been before being below between both but ' +
    'by can cannot could did do does doing down during each few for from further had has have having he her here hers herself ' +
    'him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other ' +
    'ought our ours ourselves out over own same she should so some such than that the their theirs them themselves then there ' +
    'these they this those through to too under until up very was we were what when where which while who whom why will with ' +
    'would you your yours yourself yourselves also may might must shall upon within without however therefore thus among ' +
    'per via versus et al etc figure table using used use results result study studies patient patients').split(/\s+/);

  // Ruido de formato y unidades sueltas que aparecen en PDF y DOCX clínicos.
  var RUIDO = ('http https www com org html pdf docx doc txt md rtf csv json png jpg jpeg fig tab pag pp vol num nro ref ' +
    'copyright reservados derechos all rights reserved page').split(/\s+/);


  // Verbos de discurso: el andamio con el que se escribe cualquier texto
  // académico o clínico. No son conceptos, pero se comportan como si lo fueran
  // —aparecen en todas partes y conectan todo con todo—, así que sin esta lista
  // acaban encabezando la intermediación y tapando lo que de verdad une el
  // corpus. Se enumeran las formas reales, no un patrón: una regla morfológica
  // se llevaría por delante sustantivos legítimos.
  //
  // Quedan FUERA a propósito las formas que también son sustantivos comunes en
  // medicina: «muestra», «resultado», «estado», «mejora», «cuenta», «control».
  var VERBOS_ES = (
    'exige exigen exigir exigido depende dependen depender dependiendo ' +
    'produce producen producir producido produjo produjeron ' +
    'responde responden responder respondido eleva elevan elevar elevado ' +
    'permite permiten permitir permitido incluye incluyen incluir incluido ' +
    'presenta presentan presentar presentado presentaba muestran mostrar mostrado ' +
    'indica indican indicar indicado senala senalan senalar senalado ' +
    'considera consideran considerar considerado realiza realizan realizar realizado ' +
    'obtiene obtienen obtener obtenido observa observan observar observado ' +
    'encuentra encuentran encontrar encontrado describe describen describir descrito ' +
    'define definen definir definido requiere requieren requerir requerido ' +
    'existe existen existir ocurre ocurren ocurrir ocurrido ' +
    'aparece aparecen aparecer aparecido resulta resultan resultar ' +
    'supone suponen suponer lleva llevan llevar implica implican implicar ' +
    'determina determinan determinar genera generan generar ' +
    'utiliza utilizan utilizar utilizado emplea emplean emplear empleado ' +
    'consiste consisten consistir corresponde corresponden corresponder ' +
    'constituye constituyen constituir representa representan representar ' +
    'mejoran mejorar mejorado aumenta aumentan aumentar ' +
    'disminuye disminuyen disminuir mantiene mantienen mantener ' +
    'recibe reciben recibir recibido evalua evaluan evaluar evaluado ' +
    'compara comparan comparar analiza analizan analizar ' +
    'discute discuten discutir discutido concluye concluyen concluir ' +
    'sugiere sugieren sugerir propone proponen proponer ' +
    'plantea plantean plantear destaca destacan destacar ' +
    'sigue siguen seguir seguido puede pueden poder podria podrian pudo pudieron ' +
    'debe deben deber deberia deberian tiene tienen tener tenia tenido ' +
    'hace hacen hacer dice dicen decir dicho van ' +
    'permite conlleva conllevan implicar acompana acompanan acompanar'
  ).split(/\s+/);

  // En inglés el lematizador ya reduce a la forma base, así que basta con ella.
  var VERBOS_EN = (
    'require show present indicate suggest describe define include provide ' +
    'obtain observe find occur appear involve determine generate use employ ' +
    'consist correspond constitute represent improve increase decrease ' +
    'maintain receive evaluate compare analyze analyse discuss conclude ' +
    'propose highlight follow need make take give get become remain allow ' +
    'enable report note consider assess examine investigate demonstrate support'
  ).split(/\s+/);

  function conjuntoBase() {
    var s = new Set();
    ES.forEach(function (w) { s.add(w); });
    EN.forEach(function (w) { s.add(w); });
    RUIDO.forEach(function (w) { s.add(w); });
    VERBOS_ES.forEach(function (w) { s.add(w); });
    VERBOS_EN.forEach(function (w) { s.add(w); });
    return s;
  }

  return { ES: ES, EN: EN, RUIDO: RUIDO, VERBOS_ES: VERBOS_ES, VERBOS_EN: VERBOS_EN, conjuntoBase: conjuntoBase };
});
