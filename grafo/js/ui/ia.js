(function (raiz, fabrica) {
  var api = fabrica(raiz);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; (raiz.GC.ui = raiz.GC.ui || {}).ia = api; }
})(typeof self !== 'undefined' ? self : globalThis, function (raiz) {
  'use strict';

  var GC = raiz.GC;
  var F = GC.ui.formato;
  var esc = F.escapar;
  var $ = function (id) { return document.getElementById(id); };

  // Capa de IA: apagada por defecto, y con dos cerrojos distintos.
  //
  //   la clave      vive en localStorage y persiste entre sesiones
  //   la activación vive en sessionStorage y muere al cerrar la pestaña
  //
  // Son dos cosas separadas a propósito: tener la clave guardada no autoriza a
  // enviar nada. Cada sesión hay que decir que sí otra vez, que es lo que pide
  // la especificación y lo que corresponde cuando en la carpeta hay material
  // clínico. Y aun activada, ninguna acción sale sin que el usuario haya visto
  // antes, literalmente, lo que se va a transmitir.

  var CLAVE_ALMACEN = 'grafo-ia-clave';
  var CLAVE_PROVEEDOR = 'grafo-ia-proveedor';
  var CLAVE_MODELO = 'grafo-ia-modelo';
  var CLAVE_DIRECCION = 'grafo-ia-direccion';
  var CLAVE_SESION = 'grafo-ia-activa';

  var oyentes = [];
  function alCambiar(cb) { oyentes.push(cb); }
  function avisar() { oyentes.forEach(function (cb) { try { cb(); } catch (e) { /* nada */ } }); }

  function leer(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } }
  function escribir(k, v) { try { if (v) localStorage.setItem(k, v); else localStorage.removeItem(k); } catch (e) { /* nada */ } }

  function hayClave() { return !!leer(CLAVE_ALMACEN); }
  function activaEstaSesion() {
    try { return sessionStorage.getItem(CLAVE_SESION) === 'si'; } catch (e) { return false; }
  }
  function activa() { return hayClave() && activaEstaSesion(); }

  function proveedorActual() {
    return GC.ia.proveedor.obtener(leer(CLAVE_PROVEEDOR) || 'anthropic') || GC.ia.proveedor.obtener('anthropic');
  }
  function modeloActual() {
    var p = proveedorActual();
    return leer(CLAVE_MODELO) || (p && p.modeloPorDefecto) || '';
  }

  // ------------------------------------------------------------- ejecución ---
  // Devuelve siempre algo utilizable: si la IA está apagada, si el usuario
  // cancela la vista previa, si el modelo declina o si la red falla, sale la
  // versión por plantilla. La aplicación nunca depende de que esto funcione.
  async function ejecutar(accionId, datos) {
    var accion = GC.ia.acciones.obtener(accionId);
    if (!accion) throw new Error('Acción de IA desconocida: ' + accionId);

    var porPlantilla = { texto: accion.plantilla(datos), origen: 'plantilla' };
    if (!activa()) return porPlantilla;

    var carga = accion.carga(datos);

    // 1) Auditoría de forma. Si falla, es un fallo de este programa, no del
    //    usuario: se dice con todas las letras y no se envía nada.
    var revision = GC.ia.carga.revisar(carga);
    if (!revision.seguro) {
      alert('La aplicación ha bloqueado este envío.\n\n' +
        'La carga no cumple las reglas de privacidad:\n· ' + revision.motivos.join('\n· ') +
        '\n\nEsto es un error del programa. No se ha enviado nada.');
      return porPlantilla;
    }

    // 2) Contraste con el corpus. Sólo mira cadenas de cinco palabras o más:
    //    si no hay ninguna —y en una lista de términos no la hay—, ni siquiera
    //    se abre la base de datos.
    var fuga = await contrastarSiHaceFalta(carga);
    if (fuga && !fuga.seguro) {
      alert('La aplicación ha bloqueado este envío.\n\n' +
        'Estas cadenas aparecen literalmente en tus documentos:\n· ' + fuga.sospechosas.join('\n· ') +
        '\n\nEsto es un error del programa. No se ha enviado nada.');
      return porPlantilla;
    }

    var sistema = GC.ia.acciones.SISTEMA_COMUN;
    var mensaje = accion.mensaje(carga);

    // 3) Vista previa. Lo que se enseña es lo que se manda, carácter a carácter.
    var confirmado = await vistaPrevia({
      accion: accion, carga: carga, revision: revision,
      sistema: sistema, mensaje: mensaje
    });
    if (!confirmado) return porPlantilla;

    // 4) Envío.
    try {
      var proveedor = proveedorActual();
      var r = await proveedor.completar({
        clave: leer(CLAVE_ALMACEN),
        modelo: modeloActual(),
        direccion: leer(CLAVE_DIRECCION),
        sistema: sistema,
        mensaje: mensaje,
        maxTokens: accion.maxTokens,
        esfuerzo: accion.esfuerzo
      });
      if (r.rechazado) {
        anunciarIA(r.motivo + ' Se mantiene la versión por plantilla.');
        return porPlantilla;
      }
      if (!r.texto) {
        anunciarIA('El modelo devolvió una respuesta vacía. Se mantiene la versión por plantilla.');
        return porPlantilla;
      }
      anunciarIA('Respondió ' + (r.modelo || 'el modelo') +
        (r.cambioDeModelo ? ' (tras declinar el primero)' : '') +
        (r.uso ? ' · ' + F.numero(r.uso.entrada) + ' + ' + F.numero(r.uso.salida) + ' tokens' : ''));
      return { texto: accion.interpretar(r.texto), origen: 'ia', modelo: r.modelo, uso: r.uso, crudo: r.texto };
    } catch (e) {
      anunciarIA('Falló la llamada: ' + (e && e.message || e) + '. Se mantiene la versión por plantilla.');
      return porPlantilla;
    }
  }

  async function contrastarSiHaceFalta(carga) {
    var largas = [];
    (function recorrer(v) {
      if (typeof v === 'string') { if (v.split(/\s+/).length >= 5) largas.push(v); return; }
      if (Array.isArray(v)) { v.forEach(recorrer); return; }
      if (v && typeof v === 'object') Object.keys(v).forEach(function (k) { recorrer(v[k]); });
    })(carga);
    if (!largas.length) return { seguro: true, sospechosas: [], omitido: true };

    var textos = [];
    try {
      await GC.almacen.recorrer('documentos', function (d) { if (d.texto) textos.push(d.texto); });
    } catch (e) { /* sin índice que contrastar */ }
    return GC.ia.carga.contrastarConDocumentos(carga, textos);
  }

  function anunciarIA(texto) {
    var e = $('ia-estado');
    if (e) e.textContent = texto;
  }

  // ----------------------------------------------------------- vista previa ---
  function vistaPrevia(datos) {
    return new Promise(function (resolver) {
      var caja = $('dialogo-ia');
      var p = proveedorActual();
      $('ia-previa-titulo').textContent = datos.accion.nombre;
      $('ia-previa-cuerpo').innerHTML =
        '<p class="nota">Esto es <b>exactamente</b> lo que saldría de este dispositivo. Nada más. ' +
        'Se envía a <b>' + esc(p ? p.nombre : '—') + '</b>, modelo <code>' + esc(modeloActual() || '—') + '</code>.</p>' +

        '<label class="campo">Datos del grafo que se transmiten · ' +
          F.numero(datos.revision.resumen.bytes) + ' bytes</label>' +
        '<pre class="carga-ia">' + esc(JSON.stringify(datos.carga, null, 2)) + '</pre>' +

        '<label class="campo">Instrucción del sistema</label>' +
        '<pre class="carga-ia tenue">' + esc(datos.sistema) + '</pre>' +

        '<label class="campo">Mensaje</label>' +
        '<pre class="carga-ia">' + esc(datos.mensaje) + '</pre>' +

        '<p class="nota"><b>No</b> se envía: el texto de ningún documento, sus rutas, sus nombres de ' +
        'archivo, ni ningún dato de paciente. La auditoría de esta carga pasó ' +
        F.numero(datos.revision.resumen.cadenas) + ' cadenas y ' +
        F.numero(datos.revision.resumen.numeros) + ' cifras por la lista de campos permitidos.</p>';

      caja.hidden = false;

      function cerrar(valor) {
        caja.hidden = true;
        $('btn-ia-enviar').removeEventListener('click', alEnviar);
        $('btn-ia-cancelar').removeEventListener('click', alCancelar);
        resolver(valor);
      }
      function alEnviar() { cerrar(true); }
      function alCancelar() { cerrar(false); }
      $('btn-ia-enviar').addEventListener('click', alEnviar);
      $('btn-ia-cancelar').addEventListener('click', alCancelar);
    });
  }

  // --------------------------------------------------------------- ajustes ---
  function pintarAjustes() {
    var p = proveedorActual();
    var sel = $('ia-proveedor');
    if (sel && !sel.dataset.listo) {
      sel.innerHTML = GC.ia.proveedor.lista().map(function (x) {
        return '<option value="' + esc(x.id) + '">' + esc(x.nombre) + '</option>';
      }).join('');
      sel.dataset.listo = '1';
    }
    if (sel) sel.value = p ? p.id : 'anthropic';

    var selModelo = $('ia-modelo');
    if (selModelo) {
      if (p && p.modelos.length) {
        selModelo.innerHTML = p.modelos.map(function (m) {
          return '<option value="' + esc(m.id) + '">' + esc(m.nombre) + (m.nota ? ' · ' + esc(m.nota) : '') + '</option>';
        }).join('');
        selModelo.value = modeloActual();
        selModelo.disabled = false;
      } else {
        selModelo.innerHTML = '<option value="">escríbelo en la dirección del servicio</option>';
        selModelo.disabled = true;
      }
    }

    $('ia-direccion-campo').hidden = !(p && p.requiereDireccion);
    $('ia-direccion').value = leer(CLAVE_DIRECCION);
    $('ia-clave').value = hayClave() ? '' : '';
    $('ia-clave').placeholder = hayClave() ? 'hay una clave guardada en este dispositivo' : (p && p.prefijoClave ? p.prefijoClave + '…' : 'clave del servicio');

    $('ia-activa').checked = activaEstaSesion();
    $('ia-activa').disabled = !hayClave();

    var estado;
    if (!hayClave()) estado = 'apagada · no hay clave guardada';
    else if (!activaEstaSesion()) estado = 'apagada · hay clave, falta activarla en esta sesión';
    else estado = 'activa en esta sesión · caduca al cerrar la pestaña';
    $('ia-resumen').textContent = estado;
    $('ia-borrar').disabled = !hayClave();
  }

  function montar() {
    if (!$('ia-proveedor')) return;
    pintarAjustes();

    $('ia-proveedor').addEventListener('change', function () {
      escribir(CLAVE_PROVEEDOR, this.value);
      escribir(CLAVE_MODELO, '');
      pintarAjustes();
    });
    $('ia-modelo').addEventListener('change', function () { escribir(CLAVE_MODELO, this.value); });
    $('ia-direccion').addEventListener('change', function () { escribir(CLAVE_DIRECCION, this.value.trim()); });

    $('btn-ia-guardar').addEventListener('click', function () {
      var v = $('ia-clave').value.trim();
      if (!v) { anunciarIA('Escribe la clave antes de guardarla.'); return; }
      var p = proveedorActual();
      if (p && p.prefijoClave && v.indexOf(p.prefijoClave) !== 0) {
        if (!confirm('Esa clave no empieza por «' + p.prefijoClave + '», que es lo habitual en ' +
                     p.nombre + '.\n\n¿Guardarla de todos modos?')) return;
      }
      escribir(CLAVE_ALMACEN, v);
      $('ia-clave').value = '';
      anunciarIA('Clave guardada en este dispositivo. Actívala abajo para usarla en esta sesión.');
      pintarAjustes();
      avisar();
    });

    $('ia-borrar').addEventListener('click', function () {
      if (!confirm('Se borra la clave de este dispositivo. ¿Continuar?')) return;
      escribir(CLAVE_ALMACEN, '');
      try { sessionStorage.removeItem(CLAVE_SESION); } catch (e) { /* nada */ }
      anunciarIA('Clave borrada.');
      pintarAjustes();
      avisar();
    });

    $('ia-activa').addEventListener('change', function () {
      try {
        if (this.checked) sessionStorage.setItem(CLAVE_SESION, 'si');
        else sessionStorage.removeItem(CLAVE_SESION);
      } catch (e) { /* nada */ }
      anunciarIA(this.checked
        ? 'Capa de IA activa hasta que cierres la pestaña. Cada envío seguirá pidiendo confirmación.'
        : 'Capa de IA apagada.');
      pintarAjustes();
      avisar();
    });

    $('btn-ia-cerrar-previa').addEventListener('click', function () { $('btn-ia-cancelar').click(); });
  }

  return {
    montar: montar, ejecutar: ejecutar, activa: activa, hayClave: hayClave,
    alCambiar: alCambiar, pintarAjustes: pintarAjustes, proveedorActual: proveedorActual,
    modeloActual: modeloActual
  };
});
