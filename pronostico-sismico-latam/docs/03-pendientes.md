# Lo que quedó sin verificar o sin hacer

Lista explícita, exigida por el plan de entrega ("al terminar cada fase, entrega
… una lista explícita de lo que quedó sin verificar").

## Sobre la revisión disciplinar

El proyecto es de **uso personal y de aprendizaje**, y para ese alcance no
requiere revisión externa. La distinción que importa mantener:

- Las pruebas verifican que **el código implementa correctamente las fórmulas**.
- No verifican que **las fórmulas sean las adecuadas** para un problema
  concreto, ni que las decisiones por defecto sean defendibles en una región
  determinada. Esa es una clase de error distinta y ningún test la detecta.

La segunda categoría no bloquea el uso personal: el programa la señala
continuamente en lugar de ocultarla. Sí volvería a ser un requisito para
docencia, publicación o distribución.

Lo que un especialista miraría primero, si alguna vez hay ocasión, por orden de
riesgo:

1. **Las decisiones por defecto**: corrección de MAXC (+0.2), umbrales de
   deduplicación (16 s / 100 km / 1.0 mag), ventana de estabilidad de b, piso
   del suavizado (1 %). Todas están marcadas como `CONVENCION` o `SUPUESTO`,
   pero ninguna está calibrada para catálogos latinoamericanos.
2. **La aplicabilidad de Gardner-Knopoff a la subducción mexicana**: sus
   ventanas se calibraron sobre California en los años 70, y las secuencias
   interfase tienen extensión espacial mucho mayor.
3. **La elección de GMM**: el código exige justificación escrita y comprueba el
   régimen tectónico, pero no puede juzgar la adecuación regional.
4. **El diseño de las pruebas basadas en catálogo**, que se aparta a propósito
   del CSEP clásico por las razones de `02-supuestos.md`.
5. **Los coeficientes de `parametros/`**, contra las publicaciones originales.

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

## Las ocho fases están implementadas

Lo que queda pendiente dentro de cada una está en la tabla de la sección
siguiente. Dos limitaciones estructurales merecen destacarse aquí:

- **Fase 6 — no se usa la solución de semiespacio de Okada.** Se parte de la
  solución de Kelvin en medio infinito, que puede derivarse y verificarse
  numéricamente, en lugar de reproducir de memoria fórmulas que no se pueden
  cotejar. El coste es que **no hay superficie libre**, lo cual es de primer
  orden para fuentes someras. El módulo cuantifica ese error en lugar de
  ocultarlo (`error_de_superficie_libre`).
- **Fase 8 — la capa de lenguaje no puede citar literatura verificable.** Hacerlo
  requiere recuperar primero y resolver cada DOI, y el egreso de red hacia los
  repositorios bibliográficos está bloqueado. La función que redacta
  interpretaciones sí está completa y con verificación mecánica de cifras.

## Implementado parcialmente

| Elemento | Estado |
|---|---|
| **ETAS espacio-temporal** | Completo: simulación (con fondo heterogéneo opcional y truncamiento obligatorio) y **MLE de los ocho parámetros** (μ, K, α, c, p, d, q, γ), validado por recuperación. Limitación abierta: el fondo se supone **uniforme**; falta estimarlo conjuntamente por adelgazamiento estocástico o admitirlo como mapa |
| **Modelos de recurrencia** (BPT, lognormal, Weibull) | No implementados. Ver la advertencia de dominancia del prior en la revisión metodológica: con 2–3 intervalos observados la posterior es esencialmente el prior |
| **Sismicidad suavizada** | Implementada (núcleo fijo y adaptativo, selección de ancho sin fuga). Es la referencia espacial seria del módulo de evaluación |
| **Ley de Båth** | Implementada con su diagnóstico de sesgo, no como predictor |
| **Frontend** | No existe. El paquete es una biblioteca de Python |
| **Almacenamiento PostgreSQL/PostGIS** | No. Se usa Parquet para instantáneas |
| **Rupturas finitas en PSHA** | No. Toda fuente se discretiza en puntos; para M grandes eso distorsiona las distancias |
| **Superficie libre en el cálculo elástico** | No. Ver arriba; el error se cuantifica pero no se corrige |
| **Resumen de literatura con citas verificadas** | No. Requiere resolución de DOI contra red |

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
