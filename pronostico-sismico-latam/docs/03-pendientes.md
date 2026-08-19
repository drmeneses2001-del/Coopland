# Lo que quedó sin verificar o sin hacer

Lista explícita, exigida por el plan de entrega ("al terminar cada fase, entrega
… una lista explícita de lo que quedó sin verificar").

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
| **ETAS espacio-temporal** | Simulación sí (`simular_espacio_temporal`). **MLE espacial (d, q, γ) no.** El MLE temporal (μ, K, α, c, p) está completo y validado |
| **Modelos de recurrencia** (BPT, lognormal, Weibull) | No implementados. Ver la advertencia de dominancia del prior en la revisión metodológica: con 2–3 intervalos observados la posterior es esencialmente el prior |
| **Sismicidad suavizada** como línea base espacial | No implementada. La línea base actual es Poisson homogéneo |
| **Ley de Båth** | Implementada con su diagnóstico de sesgo, no como predictor |
| **Frontend** | No existe. El paquete es una biblioteca de Python |
| **Almacenamiento PostgreSQL/PostGIS** | No. Se usa Parquet para instantáneas |

## Deuda técnica conocida

1. **Coste computacional del MLE de ETAS**: la verosimilitud es O(n²) sin
   truncar. Con ~2 500 eventos tarda ~15 s por ajuste. Para catálogos de 10⁵
   eventos hará falta truncar la influencia temporal o vectorizar.
2. **`mc_espacial` es O(celdas × eventos)**: aceptable para diagnóstico, lento
   para rejillas finas sobre catálogos grandes.
3. **Licencia del repositorio sin decidir.** Ver
   [`adr/0002-openquake-y-agpl.md`](adr/0002-openquake-y-agpl.md).
