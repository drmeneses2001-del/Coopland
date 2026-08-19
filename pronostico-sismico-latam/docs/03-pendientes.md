# Lo que quedó sin verificar o sin hacer

Lista explícita, exigida por el plan de entrega ("al terminar cada fase, entrega
… una lista explícita de lo que quedó sin verificar").

## Revisión disciplinar: pendiente

**Ningún sismólogo ha revisado este código.** El proyecto es de uso exclusivo y
personal hasta que exista esa revisión.

Las pruebas de recuperación de parámetros comprueban que el código implementa
correctamente las fórmulas. **No comprueban** que las fórmulas sean las
adecuadas para un problema concreto, ni que las decisiones metodológicas sean
defendibles. Esa es una clase de error distinta y el software no puede
detectarla.

Qué convendría que revisara un especialista, por orden de riesgo:

1. **Las decisiones metodológicas por defecto**: corrección de MAXC, umbrales de
   deduplicación, ventana de estabilidad de b, piso del suavizado. Todas están
   marcadas como `CONVENCION` o `SUPUESTO`, pero ninguna está calibrada para
   catálogos latinoamericanos.
2. **La aplicabilidad de Gardner-Knopoff a subducción mexicana**: sus ventanas
   se calibraron sobre California en los años 70 y las secuencias interfase
   tienen extensión espacial mucho mayor.
3. **La formulación de las pruebas basadas en catálogo**, que se apartan
   deliberadamente del diseño clásico de CSEP por las razones documentadas en
   `02-supuestos.md`.
4. **Los coeficientes de `parametros/`**, contra las publicaciones originales.

## Sin verificar

### Fuentes de datos — ninguna
Ningún endpoint, formato ni licencia pudo comprobarse: el egreso de red del
entorno de desarrollo bloquea todos los hosts sismológicos. Detalle en
[`01-fuentes-verificadas.md`](01-fuentes-verificadas.md).

**Consecuencia:** el paquete no ha procesado ni un solo dato real. Todo lo
validado se validó sobre catálogos sintéticos.

### Coeficientes de la literatura — ninguno
Marcados `verificado = false` en `parametros/`:

- **`ventanas_decluster.toml`**: coeficientes de Gardner-Knopoff, dimensión
  fractal de Zaliapin-Ben-Zion, parámetros de Reasenberg.
- **El radio de interacción de Reasenberg** usa una relación de escala
  longitud-magnitud genérica marcada como `SUPUESTO` en el código, no una
  relación publicada.
- **`conversiones_magnitud.toml`**: no hay ninguna conversión activa. El bloque
  `ejemplo_estructura` tiene coeficientes de marcador de posición y está
  desactivado; una prueba verifica que sigue desactivado.

### Citas bibliográficas — ninguna
Las referencias de los docstrings no se cotejaron contra los originales. Los
estimadores se validan por recuperación de parámetros, que es un criterio
independiente de la cita.

### El cliente FDSN nunca se ejecutó contra un servicio real
El parseo se probó contra respuestas de ejemplo con el formato del estándar. Es
plausible que un servicio concreto devuelva variantes que el parser no maneje.

## Fuera del alcance acordado (fases 0–4)

No implementado, por acuerdo explícito:

- **Fase 5 — PSHA**: Cornell-McGuire, árboles lógicos, GMM, desagregación,
  efecto de sitio.
- **Fase 6 — Coulomb** (Okada) y presupuesto geodésico de momento.
- **Fase 7 — hipótesis exploratorias** (mareas, clima, embalses). La
  infraestructura de preregistro y corrección por multiplicidad
  (`RegistroDePruebas`) **sí está construida y probada**, porque la necesitaba
  la fase 4.
- **Fase 8 — capa de lenguaje natural y didáctica.**

## Implementado parcialmente

| Elemento | Estado |
|---|---|
| **ETAS espacio-temporal** | Completo: simulación (con fondo heterogéneo opcional y truncamiento obligatorio) y **MLE de los ocho parámetros** (μ, K, α, c, p, d, q, γ), validado por recuperación. Limitación abierta: el fondo se supone **uniforme**; falta estimarlo conjuntamente por adelgazamiento estocástico o admitirlo como mapa |
| **Modelos de recurrencia** (BPT, lognormal, Weibull) | No implementados. Ver la advertencia de dominancia del prior en la revisión metodológica: con 2–3 intervalos observados la posterior es esencialmente el prior |
| **Sismicidad suavizada** | Implementada (núcleo fijo y adaptativo, selección de ancho sin fuga). Es la referencia espacial seria del módulo de evaluación |
| **Ley de Båth** | Implementada con su diagnóstico de sesgo, no como predictor |
| **Frontend** | No existe. El paquete es una biblioteca de Python |
| **Almacenamiento PostgreSQL/PostGIS** | No. Se usa Parquet para instantáneas |

## Deuda técnica conocida

1. **Coste computacional del MLE de ETAS**: la verosimilitud es O(n²) sin
   truncar. Con ~2 500 eventos tarda ~15 s por ajuste. Para catálogos de 10⁵
   eventos hará falta truncar la influencia temporal o vectorizar.
2. **`campo_suavizado` es O(celdas × eventos)** por trozos. Suficiente para
   rejillas de diagnóstico; para rejillas finas sobre catálogos grandes
   convendría convolución por FFT.
3. **`mc_espacial` es O(celdas × eventos)**: aceptable para diagnóstico, lento
   para rejillas finas sobre catálogos grandes.
4. **Licencia del repositorio sin decidir.** Ver
   [`adr/0002-openquake-y-agpl.md`](adr/0002-openquake-y-agpl.md).
