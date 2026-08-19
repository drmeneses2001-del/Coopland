# Estado de verificación de las fuentes de datos

**Fecha de la verificación: 2026-08-19.**

## Resumen: qué se pudo comprobar

El entorno donde se desarrolló este código tiene el **egreso de red bloqueado
hacia todos los servicios sismológicos**. Los intentos de acceso devolvieron
`EGRESS_BLOCKED` para:

- `earthquake.usgs.gov`
- `www.ssn.unam.mx`
- `www.isc.ac.uk`
- `www.globalcmt.org`
- `service.iris.edu`

En consecuencia **no fue posible verificar ni una sola ruta de API, formato de
respuesta o licencia de uso**. Escribir esas URLs de memoria habría producido
código que *parece* verificado y no lo está, que es exactamente lo que prohíbe
la regla 3 del contrato epistemológico.

**Decisión de diseño resultante:** `parametros/fuentes.toml` no contiene
ninguna URL base. El cliente FDSN se niega a construir una consulta contra una
fuente sin verificar, con un mensaje que dice qué hay que comprobar y dónde.

## Lo que sí se verificó

| Elemento | Resultado | Cómo |
|---|---|---|
| **pyCSEP** | Licencia **BSD 3-Clause**. Requiere Python ≥ 3.9. Instalable por pip y conda. | Repositorio `SCECcode/pycsep` |
| **OpenQuake engine** | Licencia **AGPL-3.0** — texto literal: "GNU AFFERO GENERAL PUBLIC LICENSE Version 3, 19 November 2007" | Archivo `LICENSE` de `gem/oq-engine` |
| **SSN (UNAM)** | Existe catálogo en `ssn.unam.mx/catalogo/` y catálogo histórico separado en `sismoshistoricos.ssn.unam.mx`. Registros desde 1900; más de 200 000 eventos. | Búsqueda web |

La implicación de licencia de OpenQuake está analizada en
[`adr/0002-openquake-y-agpl.md`](adr/0002-openquake-y-agpl.md). No afecta a las
fases 0–4, que no lo usan.

## Qué hay que verificar antes de ingerir datos reales

Para cada fuente, y **antes** de rellenar `url_base` y poner `verificado = true`:

1. **Ruta base real del servicio** y si expone FDSN o solo formulario web.
2. **Formato de respuesta** y nombres de columna.
3. **Escalas de magnitud** reportadas y si cambian a lo largo del catálogo.
4. **Magnitud de completitud** declarada o estimable, y su variación temporal
   (cada expansión de red la baja de golpe).
5. **Licencia y requisito de citación.** Si prohíbe redistribución, dejar
   `puede_cachearse = false`: la capa de ingesta respeta esa marca.
6. **Política de revisión retroactiva** del catálogo.

### Prioridad para la región elegida (México: Cocos/Rivera + FVTM)

| Orden | Fuente | Por qué | Pendiente crítico |
|---|---|---|---|
| 1 | **SSN (UNAM)** | Fuente primaria de la región; catálogo largo y denso | ¿Hay servicio FDSN o solo descarga manual? De eso depende todo el conector |
| 2 | **USGS / ComCat** | Referencia global, contraste y deduplicación | Límite de eventos por consulta; política de tasa |
| 3 | **GCMT** | Mw de referencia para calibrar las conversiones de magnitud | Formato del archivo de soluciones |
| 4 | **ISC** | Boletín revisado, para el catálogo histórico | Límites de consulta automatizada |

### Fuentes de fases posteriores (no necesarias para 0–4)

Slab2, GEM Global Active Faults Database, MORVEL/NUVEL, GNSS (Nevada Geodetic
Laboratory, EarthScope/GAGE, IGS), ERA5 vía Copernicus, mareógrafos
(PSMSL/UHSLC/COI), boyas DART (NOAA/NDBC), mapas de Vs30 y de periodo dominante
del Valle de México, modelos de marea oceánica (TPXO, FES — **verificar
licencia con cuidado**, varios restringen el uso comercial).

## Qué NO se hizo, y por qué

- **No se descargó ningún dato real.** Todo lo que se validó se validó sobre
  catálogos sintéticos con parámetros conocidos.
- **No se ejecutó el cliente FDSN contra ningún servicio.** El parseo está
  probado contra respuestas de ejemplo con el formato del estándar, no contra
  respuestas reales. Es plausible que un servicio concreto devuelva variantes
  del formato que el parser no maneje.
- **No se verificó ninguna cita bibliográfica** contra el documento original.
  Las referencias que aparecen en los docstrings (Aki 1965, Utsu, Shi y Bolt
  1982, Wiemer y Wyss 2000, Gardner y Knopoff 1974, Reasenberg 1985, Zaliapin y
  Ben-Zion 2013, Ogata 1988) están anotadas como no verificadas. Los
  estimadores se validan por **recuperación de parámetros**, no por la cita.
