(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.ia = raiz.GC.ia || {}).proveedor = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  // Interfaz de proveedor conectable.
  //
  // Un proveedor sólo tiene que saber hacer una cosa: recibir un sistema y un
  // mensaje de texto y devolver texto. Todo lo que decide QUÉ se envía —y la
  // auditoría de que no sale nada que no deba— vive fuera, en `ia/carga.js` y
  // `ia/acciones.js`, precisamente para que añadir un proveedor no pueda
  // ampliar por descuido lo que se transmite.

  var registro = new Map();

  function registrar(definicion) {
    if (!definicion || !definicion.id || typeof definicion.completar !== 'function') {
      throw new Error('Un proveedor necesita id y una función completar().');
    }
    registro.set(definicion.id, definicion);
    return definicion;
  }

  function lista() { return Array.from(registro.values()); }
  function obtener(id) { return registro.get(id) || null; }

  // ------------------------------------------------------------- Anthropic ---
  // El SDK oficial, empaquetado para el navegador y servido desde vendor/. Se
  // carga sólo cuando el usuario activa la capa: mientras la IA está apagada
  // —que es como viene— no se descarga ni un byte de él.
  var sdkCargado = null;

  async function cargarSdk() {
    if (sdkCargado) return sdkCargado;
    var modulo = await import('../../vendor/anthropic.browser.min.mjs');
    var Anthropic = raiz.Anthropic || modulo.default;
    if (!Anthropic) throw new Error('El SDK de Anthropic no expuso su constructor.');
    sdkCargado = Anthropic;
    return Anthropic;
  }

  registrar({
    id: 'anthropic',
    nombre: 'Claude · Anthropic',
    enlaceClave: 'https://console.anthropic.com/settings/keys',
    prefijoClave: 'sk-ant-',
    modeloPorDefecto: 'claude-opus-5',
    modelos: [
      { id: 'claude-opus-5', nombre: 'Claude Opus 5', nota: 'el más capaz de uso general' },
      { id: 'claude-sonnet-5', nombre: 'Claude Sonnet 5', nota: 'más barato y rápido' },
      { id: 'claude-haiku-4-5', nombre: 'Claude Haiku 4.5', nota: 'el más económico' }
    ],

    async completar(peticion) {
      var Anthropic = await cargarSdk();
      var cliente = new Anthropic({
        apiKey: peticion.clave,
        // La clave vive en este dispositivo y la petición sale desde el
        // navegador: es exactamente el modelo de esta aplicación, sin servidor
        // intermedio. El SDK exige declararlo a conciencia.
        dangerouslyAllowBrowser: true,
        maxRetries: 1
      });

      var cuerpo = {
        model: peticion.modelo || 'claude-opus-5',
        max_tokens: peticion.maxTokens || 1500,
        system: peticion.sistema,
        messages: [{ role: 'user', content: peticion.mensaje }],
        thinking: { type: 'adaptive' },
        output_config: { effort: peticion.esfuerzo || 'medium' },
        // Si un clasificador declina la petición —y con material clínico puede
        // pasar—, el servidor la reintenta en otro modelo dentro de la misma
        // llamada en vez de dejar al usuario sin respuesta.
        betas: ['server-side-fallback-2026-07-01'],
        fallbacks: 'default'
      };

      var respuesta = await cliente.beta.messages.create(cuerpo, { signal: peticion.senal });

      // Siempre se mira stop_reason antes que el contenido: una negativa llega
      // con HTTP 200 y contenido vacío, no como error.
      if (respuesta.stop_reason === 'refusal') {
        var detalle = respuesta.stop_details || {};
        return {
          rechazado: true,
          motivo: 'El modelo declinó esta petición' + (detalle.category ? ' (' + detalle.category + ')' : '') + '.',
          texto: '', modelo: respuesta.model, uso: respuesta.usage || null
        };
      }

      var texto = (respuesta.content || [])
        .filter(function (b) { return b.type === 'text'; })
        .map(function (b) { return b.text; })
        .join('\n')
        .trim();

      var cambioDeModelo = (respuesta.content || []).some(function (b) { return b.type === 'fallback'; });

      return {
        rechazado: false,
        texto: texto,
        modelo: respuesta.model,
        cambioDeModelo: cambioDeModelo,
        uso: respuesta.usage ? {
          entrada: respuesta.usage.input_tokens,
          salida: respuesta.usage.output_tokens
        } : null
      };
    }
  });

  // ------------------------------------------------- proveedor compatible ---
  // Cualquier servicio que hable el formato de la API de mensajes de Anthropic
  // en otra dirección. Existe para que «conectable» no sea una promesa: se
  // rellena la dirección y funciona, sin tocar el resto de la aplicación.
  registrar({
    id: 'compatible',
    nombre: 'Otro servicio compatible',
    enlaceClave: '',
    prefijoClave: '',
    requiereDireccion: true,
    modeloPorDefecto: '',
    modelos: [],

    async completar(peticion) {
      if (!peticion.direccion) throw new Error('Falta la dirección del servicio.');
      var r = await fetch(peticion.direccion.replace(/\/+$/, '') + '/v1/messages', {
        method: 'POST',
        signal: peticion.senal,
        headers: {
          'content-type': 'application/json',
          'x-api-key': peticion.clave,
          'anthropic-version': '2023-06-01'
        },
        body: JSON.stringify({
          model: peticion.modelo,
          max_tokens: peticion.maxTokens || 1500,
          system: peticion.sistema,
          messages: [{ role: 'user', content: peticion.mensaje }]
        })
      });
      if (!r.ok) throw new Error('El servicio respondió ' + r.status + ' ' + r.statusText);
      var datos = await r.json();
      if (datos.stop_reason === 'refusal') {
        return { rechazado: true, motivo: 'El servicio declinó la petición.', texto: '', modelo: datos.model };
      }
      return {
        rechazado: false,
        texto: (datos.content || []).filter(function (b) { return b.type === 'text'; })
          .map(function (b) { return b.text; }).join('\n').trim(),
        modelo: datos.model,
        uso: datos.usage ? { entrada: datos.usage.input_tokens, salida: datos.usage.output_tokens } : null
      };
    }
  });

  return { registrar: registrar, lista: lista, obtener: obtener };
});
