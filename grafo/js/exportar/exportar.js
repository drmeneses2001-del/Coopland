(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { raiz.GC = raiz.GC || {}; raiz.GC.exportar = api; }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Exportables. Los tres formatos de texto se construyen con funciones puras
  // —se pueden probar en consola— y el navegador sólo se encarga de la descarga.
  //
  // El informe es el que importa de verdad: está escrito en Markdown con
  // enlaces relativos a los documentos que menciona, de modo que si se guarda
  // en la misma carpeta, la próxima indexación lo lee como un documento más y
  // sus enlaces se convierten en dependencias explícitas del grafo. El sistema
  // se alimenta de sí mismo: el informe de hoy es estructura mañana.

  function fecha(ts) {
    var d = new Date(ts || Date.now());
    function dos(n) { return String(n).padStart(2, '0'); }
    return d.getFullYear() + '-' + dos(d.getMonth() + 1) + '-' + dos(d.getDate());
  }

  function marcaDeTiempo(ts) {
    var d = new Date(ts || Date.now());
    function dos(n) { return String(n).padStart(2, '0'); }
    return fecha(ts) + ' ' + dos(d.getHours()) + ':' + dos(d.getMinutes());
  }

  // ---------------------------------------------------------- grafo.json ---
  function grafoJson(capas, resumen) {
    var c = capas.conceptos;
    return {
      generadoPor: 'Grafo de conocimiento',
      fecha: new Date(capas.fecha || Date.now()).toISOString(),
      metricas: {
        conceptos: c.nodos.length,
        aristas: c.aristas.length,
        comunidades: resumen ? resumen.conceptos.comunidades : null,
        modularidad: resumen ? resumen.conceptos.modularidad : null,
        diversidad: resumen ? resumen.conceptos.diversidad.etiqueta : null,
        componentes: resumen ? resumen.conceptos.componentes : null,
        intermediacion: resumen ? resumen.conceptos.intermediacion : null,
        corte: c.corte,
        descartados: c.totales
      },
      comunidades: (resumen ? resumen.comunidades : []).map(function (x) {
        return {
          id: x.id, nombre: x.nombre, nodos: x.nodos,
          porcentaje: Math.round(x.porcentaje * 10) / 10,
          documentos: x.documentos,
          terminos: x.terminos.map(function (t) { return t.forma; })
        };
      }),
      conceptos: {
        nodos: c.nodos.map(function (n, i) {
          return {
            id: n.id, lema: n.lema, forma: n.forma,
            frecuencia: n.frecuencia, documentos: n.docs,
            comunidad: c.comunidad[i],
            intermediacion: Math.round(c.intermediacion[i] * 1e6) / 1e6,
            grado: c.grado[i]
          };
        }),
        aristas: c.aristas.map(function (e) {
          return { a: e.a, b: e.b, peso: e.peso, documentos: e.docs };
        })
      },
      documentos: {
        nodos: capas.documentos.nodos.map(function (n) {
          return {
            id: n.id, ruta: n.ruta, extension: n.ext, estado: n.estado,
            palabras: n.palabras, terminos: n.terminos, idioma: n.idioma
          };
        }),
        dependencias: capas.documentos.dependencias.map(function (e) {
          return { a: e.a, b: e.b, tipo: e.tipo, peso: e.peso };
        }),
        afinidades: capas.documentos.afinidades.map(function (e) {
          return { a: e.a, b: e.b, coseno: e.coseno };
        })
      },
      brechas: capas.brechas || null
    };
  }

  // -------------------------------------------------------- conceptos.csv ---
  function campoCsv(v) {
    var s = String(v == null ? '' : v);
    return /[",;\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function conceptosCsv(capas, resumen) {
    var c = capas.conceptos;
    var nombreComunidad = new Map();
    (resumen ? resumen.comunidades : []).forEach(function (x) { nombreComunidad.set(x.id, x.nombre); });

    var filas = [[
      'lema', 'forma', 'frecuencia', 'documentos', 'comunidad', 'nombre_comunidad',
      'intermediacion', 'grado', 'fuerza'
    ]];
    c.nodos.forEach(function (n, i) {
      filas.push([
        n.lema, n.forma, n.frecuencia, n.docs,
        c.comunidad[i], nombreComunidad.get(c.comunidad[i]) || '',
        (c.intermediacion[i]).toFixed(6), c.grado[i],
        c.fuerza ? c.fuerza[i].toFixed(2) : ''
      ]);
    });
    // BOM al principio: sin él, Numbers y Excel abren los acentos rotos.
    return '﻿' + filas.map(function (f) { return f.map(campoCsv).join(','); }).join('\r\n') + '\r\n';
  }

  // ---------------------------------------------------------- informe.md ---
  function enlace(ruta) {
    // Enlace relativo, no absoluto: así sigue resolviendo cuando el informe se
    // guarda dentro de la misma carpeta que indexa la aplicación.
    return '[' + ruta + '](' + encodeURI(ruta) + ')';
  }

  function informeMd(capas, resumen, opciones) {
    opciones = opciones || {};
    var L = [];
    var r = resumen;

    L.push('# Estructura del archivo · ' + fecha(capas.fecha));
    L.push('');
    L.push('Informe generado por el grafo de conocimiento el ' + marcaDeTiempo(capas.fecha) +
      '. Todos los cálculos se hicieron en el dispositivo.');
    L.push('');

    // --- resumen ---
    L.push('## De un vistazo');
    L.push('');
    L.push('| | |');
    L.push('|---|---|');
    L.push('| Documentos | ' + capas.documentos.nodos.length + ' |');
    L.push('| Conceptos en el grafo | ' + capas.conceptos.nodos.length + ' |');
    L.push('| Aristas de co-ocurrencia | ' + capas.conceptos.aristas.length + ' |');
    if (r) {
      L.push('| Comunidades | ' + r.conceptos.comunidades + ' |');
      L.push('| Modularidad (Q) | ' + r.conceptos.modularidad.toFixed(4) + ' |');
      L.push('| Diversidad temática | ' + r.conceptos.diversidad.etiqueta + ' |');
      L.push('| Dependencias explícitas | ' + r.documentos.totales.dependencias + ' |');
      L.push('| Pares por afinidad | ' + r.documentos.totales.afinidades + ' |');
    }
    L.push('');
    if (r) {
      L.push('> ' + r.conceptos.diversidad.explicacion);
      L.push('');
      if (!r.conceptos.intermediacion.exacta) {
        L.push('*La intermediación de este informe es aproximada, por muestreo de ' +
          r.conceptos.intermediacion.fuentes + ' pivotes.*');
        L.push('');
      }
    }

    // --- temas ---
    if (r && r.comunidades.length) {
      L.push('## Temas');
      L.push('');
      r.comunidades.forEach(function (c) {
        L.push('### ' + (c.nombre || 'Tema ' + c.id));
        L.push('');
        L.push(c.nodos + ' conceptos · ' + c.porcentaje.toFixed(1) + '% del grafo · ' +
          c.documentos + ' documentos.');
        L.push('');
        L.push('Términos más centrales: ' + c.terminos.map(function (t) { return '**' + t.forma + '**'; }).join(', ') + '.');
        L.push('');
      });
    }

    // --- conceptos influyentes y conectores ---
    if (r && r.influyentes.length) {
      L.push('## Conceptos más influyentes');
      L.push('');
      L.push('Por intermediación: en cuántos caminos mínimos entre otros dos conceptos aparece cada uno.');
      L.push('');
      L.push('| Concepto | Intermediación | Frecuencia | Documentos |');
      L.push('|---|---:|---:|---:|');
      r.influyentes.slice(0, 15).forEach(function (x) {
        L.push('| ' + x.forma + ' | ' + x.intermediacion.toFixed(4) + ' | ' + x.frecuencia + ' | ' + x.docs + ' |');
      });
      L.push('');
    }

    if (r && r.conectores.length) {
      L.push('## Puntos conectores del discurso');
      L.push('');
      L.push('Conceptos con intermediación alta en relación con lo poco que se repiten: unen ' +
        'territorios sin ser protagonistas, y son invisibles para cualquier recuento de frecuencia.');
      L.push('');
      r.conectores.slice(0, 10).forEach(function (x) {
        L.push('- **' + x.forma + '** · razón ' + x.razon.toFixed(2) +
          ' · aparece ' + x.frecuencia + (x.frecuencia === 1 ? ' vez' : ' veces') + ' en ' + x.docs + ' documentos');
      });
      L.push('');
    }

    // --- brechas ---
    var b = capas.brechas || (r && r.brechas);
    if (b) {
      L.push('## Brechas');
      L.push('');
      L.push('Ausencias estructuralmente improbables, ordenadas por lo que valdría cerrarlas.');
      L.push('');

      if (b.estructurales.length) {
        L.push('### Entre territorios');
        L.push('');
        b.estructurales.forEach(function (x, i) {
          L.push('#### ' + (i + 1) + '. ' + x.terminosA.slice(0, 3).join(' · ') +
            '  ⟷  ' + x.terminosB.slice(0, 3).join(' · '));
          L.push('');
          L.push('- Peso: ' + (x.peso * 100).toFixed(1) + '% del vocabulario · facilidad de puente: ' +
            x.facilidad.toFixed(2) + ' · puntuación: ' + x.puntuacion.toFixed(4));
          L.push('- Separación: ' + (x.sinCamino ? '**sin ningún camino en el grafo**' :
            x.distancia + (x.distancia === 1 ? ' salto' : ' saltos')) +
            ' · aristas cruzadas: ' + x.aristasCruzadas);
          if (x.documentosA && x.documentosA.length) {
            L.push('- Lado A: ' + x.documentosA.map(function (d) { return enlace(d.ruta); }).join(', '));
          }
          if (x.documentosB && x.documentosB.length) {
            L.push('- Lado B: ' + x.documentosB.map(function (d) { return enlace(d.ruta); }).join(', '));
          }
          L.push('');
          if (x.pregunta) {
            L.push('> ' + x.pregunta.texto);
            L.push('');
            L.push('*(pregunta ' + (x.pregunta.origen === 'ia' ? 'refinada por un modelo' : 'generada por plantilla') + ')*');
            L.push('');
          }
        });
      }

      if (b.aislados.length) {
        L.push('### Documentos aislados');
        L.push('');
        L.push(b.parametros.aislados.criterio + '.');
        L.push('');
        b.aislados.forEach(function (x) {
          L.push('#### ' + enlace(x.ruta));
          L.push('');
          L.push('- ' + x.palabras + ' palabras · ' + x.terminos + ' conceptos propios · sin dependencias');
          if (x.afines && x.afines.length) {
            L.push('- Se parece por vocabulario a: ' + x.afines.map(function (a) {
              return enlace(a.ruta) + ' (' + a.coseno.toFixed(2) + ')';
            }).join(', '));
          }
          L.push('');
          if (x.pregunta) { L.push('> ' + x.pregunta.texto); L.push(''); }
        });
      }

      if (b.puentesAusentes.length) {
        L.push('### Conceptos puente ausentes');
        L.push('');
        b.puentesAusentes.forEach(function (x) {
          L.push('#### ' + x.forma);
          L.push('');
          L.push('- Con ' + x.vecinosA.join(', ') + ' en ' + (x.documentosA || []).map(enlace).join(', '));
          L.push('- Con ' + x.vecinosB.join(', ') + ' en ' + (x.documentosB || []).map(enlace).join(', '));
          L.push('- Nunca con ambos lados en el mismo texto.');
          L.push('');
          if (x.pregunta) { L.push('> ' + x.pregunta.texto); L.push(''); }
        });
      }
    }

    // --- documentos no leídos ---
    if (r && r.documentos.sinResolver && r.documentos.sinResolver.length) {
      L.push('## Enlaces sin destino');
      L.push('');
      L.push('Enlaces escritos que no apuntan a ningún documento del índice.');
      L.push('');
      r.documentos.sinResolver.forEach(function (x) {
        L.push('- ' + enlace(x.desde) + ' → `' + x.destino + '` (' + x.motivo + ')');
      });
      L.push('');
    }

    L.push('---');
    L.push('');
    L.push('*Este informe está pensado para volver a la carpeta que indexas. La próxima vez que ' +
      'abras la aplicación entrará como un documento más, y sus enlaces se convertirán en ' +
      'dependencias explícitas del grafo.*');
    L.push('');

    return L.join('\n');
  }

  // ------------------------------------------------------------ descargas ---
  function descargar(nombre, contenido, tipo) {
    var blob = contenido instanceof Blob ? contenido : new Blob([contenido], { type: tipo || 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = nombre;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 1000);
    return nombre;
  }

  function lienzoAPng(canvas, nombre) {
    return new Promise(function (resolver, rechazar) {
      if (!canvas) { rechazar(new Error('No hay lienzo que exportar.')); return; }
      canvas.toBlob(function (blob) {
        if (!blob) { rechazar(new Error('El navegador no pudo convertir el lienzo a PNG.')); return; }
        resolver(descargar(nombre || 'grafo.png', blob, 'image/png'));
      }, 'image/png');
    });
  }

  return {
    grafoJson: grafoJson, conceptosCsv: conceptosCsv, informeMd: informeMd,
    descargar: descargar, lienzoAPng: lienzoAPng,
    fecha: fecha, marcaDeTiempo: marcaDeTiempo, campoCsv: campoCsv, enlace: enlace
  };
});
