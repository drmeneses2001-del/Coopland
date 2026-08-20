# Primeros pasos con datos reales

Este documento es la lista concreta de lo que hay que hacer **en una máquina con
salida de red** para que el paquete deje de trabajar con catálogos sintéticos.

Nada de esto pudo hacerse durante el desarrollo: el entorno tenía bloqueado el
egreso hacia todos los servicios sismológicos. Por eso el paquete se niega a
consultar fuentes sin verificar en lugar de traer URLs escritas de memoria.

---

## Paso 1 — Verificar la fuente primaria (SSN)

**Es el paso que bloquea todo lo demás.** La pregunta concreta a resolver:

> ¿El SSN ofrece un servicio FDSN, o solo formulario web y descarga manual?

De la respuesta depende todo el diseño del conector. Comprueba en
<http://www.ssn.unam.mx/catalogo/>:

1. La URL base real del servicio de eventos.
2. El formato de respuesta y los nombres de columna.
3. Las escalas de magnitud reportadas, y si cambian a lo largo del catálogo.
4. La política de revisión retroactiva.
5. **La licencia y el requisito de citación.** Es habitual que se exija
   reconocimiento explícito al SSN en toda publicación que use sus datos.

Después, edita `parametros/fuentes.toml`:

```toml
[ssn_unam]
url_base = "<la URL que comprobaste>"
verificado = true
verificado_el = "2026-08-20"
verificado_por = "<tus iniciales>"
licencia = "<lo que digan los términos de uso>"
puede_cachearse = true   # solo si la licencia permite redistribución
```

Comprueba que quedó bien:

```python
from sismolat.ingesta.fuentes import resumen_estado
print(resumen_estado())
```

Repite para `usgs`, `gcmt` e `isc`.

> **Sobre `puede_cachearse`**: déjalo en `false` si la licencia prohíbe
> redistribución. La capa de ingesta respeta esa marca y no persistirá los
> datos. Es una decisión legal, no técnica.

---

## Paso 2 — Primera ingesta y su instantánea

```python
from sismolat.ingesta.fdsn import ConsultaEventos, ingerir
from sismolat.ingesta.instantanea import guardar

respuesta = ingerir("ssn_unam", ConsultaEventos(
    t_inicio="1990-01-01", t_fin="2026-01-01",
    lat_min=14.0, lat_max=21.0, lon_min=-106.0, lon_max=-94.0,
    mag_min=3.0,
))
if not respuesta.exito:
    print(respuesta)          # dice qué falló; no rellena con nada
```

**Guarda una instantánea antes de analizar nada.** Los catálogos se revisan
retroactivamente, y un análisis que no declare con qué estado del catálogo corrió
no es reproducible:

```python
guardar(catalogo, "instantaneas/", fuente="ssn_unam", consulta={...})
```

El cliente FDSN **nunca se ha ejecutado contra un servicio real**. Su parseo está
probado contra respuestas de ejemplo con el formato del estándar, así que es
plausible que un servicio concreto devuelva variantes que no maneje. Si falla,
el error dirá dónde.

---

## Paso 3 — Antes de creerte ningún resultado

En este orden:

```python
print(catalogo.advertencias())        # escalas mezcladas, agencias sin deduplicar
mc = comparar_metodos_mc(catalogo.magnitudes())
print(mc["advertencia"])              # la dispersión entre métodos es la Mc honesta
print(mc_por_ventanas(catalogo.df))   # saltos = expansiones de red, no sismicidad
print(mc_espacial(catalogo.df))       # Mc(x,y) antes de cualquier mapa de b
```

**Mc espacial no es opcional si vas a hacer un mapa de b.** Un Mc escalar sobre
completitud heterogénea genera estructura espacial falsa con aspecto tectónico, y
la cobertura de la red mexicana es muy desigual.

---

## Paso 4 — Verificar los coeficientes de la literatura

Todos están marcados `verificado = false` y contaminan lo que derivan.

| Archivo | Qué verificar |
|---|---|
| `parametros/ventanas_decluster.toml` | Coeficientes de Gardner-Knopoff, `d_fractal` de Zaliapin-Ben-Zion, parámetros de Reasenberg |
| `parametros/conversiones_magnitud.toml` | **Vacío a propósito.** Añade una regresión publicada y calibrada para México (idealmente SSN contra Mw de GCMT) |

Sin conversiones de magnitud verificadas, los eventos en escalas distintas de Mw
quedan con `mag_homog = NaN`. Eso es lo correcto: usarlos como si ya estuvieran
en Mw introduce un sesgo silencioso.

---

## Paso 5 — Lo que necesita revisión disciplinar antes de usarse

Por orden de riesgo, y ninguno lo puede decidir el software:

1. **Las decisiones por defecto**: corrección de MAXC (+0.2), umbrales de
   deduplicación (16 s / 100 km / 1.0 mag), piso del suavizado (1%). Ninguna
   está calibrada para catálogos latinoamericanos.
2. **Gardner-Knopoff en subducción mexicana.** Sus ventanas se calibraron sobre
   California en los años 70; las secuencias interfase tienen extensión espacial
   mucho mayor.
3. **La elección de GMM.** El código exige justificación escrita y comprueba el
   régimen tectónico, pero no puede juzgar si `ArroyoEtAl2010SInter` es adecuado
   para tu caso.
4. **El diseño de las pruebas basadas en catálogo**, que se aparta a propósito
   del CSEP clásico por las razones de `02-supuestos.md`.

---

## Lo que sigue sin poder hacerse aquí

| Elemento | Por qué | Qué haría falta |
|---|---|---|
| Citas bibliográficas verificadas | La capa de lenguaje puede alucinar referencias | Recuperar primero y resolver cada DOI contra Crossref |
| Superficie libre en el cálculo elástico | Ver abajo | Implementar la solución de semiespacio contra una referencia cotejable |
| Rupturas finitas en PSHA | Toda fuente se discretiza en puntos | Modelo de fallas con geometría |
| Estimación conjunta del fondo en ETAS espacial | El fondo se supone uniforme | Adelgazamiento estocástico |

### Sobre el error de superficie libre

Medido con `error_de_superficie_libre`, comparando magnitudes homólogas:

| Profundidad de la fuente | Razón mediana | Lectura |
|---|---|---|
| 4 km | 0.27 | apreciable — uso cualitativo |
| 8 km | 0.36 | apreciable — uso cualitativo |
| 15 km | 0.47 | apreciable — uso cualitativo |
| 30 km | 0.26 | apreciable — uso cualitativo |
| 60 km | 0.05 | pequeño — utilizable |

**Para fallas corticales típicas los resultados de Coulomb son cualitativos**
(dónde sube y dónde baja), no cuantitativos. Solo para fuentes profundas —
sismicidad intraplaca — la aproximación de medio infinito es buena.

---

## Recordatorio permanente

El proyecto es de **uso exclusivo y personal** hasta que exista revisión por un
especialista: sin docencia, sin publicar resultados, sin distribuir. Ver el
encabezado del README y `03-pendientes.md`.
