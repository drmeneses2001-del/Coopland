# sismolat — pronóstico sísmico probabilístico para América Latina

Biblioteca docente e investigativa para calcular **tasas de ocurrencia,
probabilidades condicionales y medidas formales de desempeño** sobre catálogos
sísmicos, con la región de arranque en México (subducción de Cocos/Rivera y
Faja Volcánica Transmexicana).

> **Esto no es un predictor de sismos.** La predicción determinista —lugar,
> tiempo y magnitud con precisión útil— no está científicamente demostrada.
>
> **Esto no es un sistema de alerta.** SASMEX (México), SNAM/CSN (Chile) y
> ShakeAlert (EUA) detectan ondas P de un sismo *que ya ocurrió*; eso es otra
> cosa y no tiene relación con este software.
>
> Lee [`docs/00-contrato-epistemologico.md`](docs/00-contrato-epistemologico.md)
> antes de usar cualquier resultado.

---

## Estado actual

**Fases 0–4 implementadas y validadas.** Fases 5–8 fuera del alcance acordado.

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Procedencia por tipos, esquema de catálogo, reproducibilidad, detección de fuga | ✅ |
| 1 | Ingesta: registro de fuentes, cliente FDSN, deduplicación, homogenización | ⚠️ ver abajo |
| 2 | Mc (3 métodos + espacial + temporal), valor b, decluster (3 métodos) | ✅ |
| 3 | Omori–Utsu, Båth, ETAS temporal (MLE + simulación), ETAS espacio-temporal (simulación), **sismicidad suavizada** | ✅ |
| 4 | CSEP (N/L/CL/S/M, poissoniano y basado en catálogo), ganancia de información, Molchan, ROC, Brier | ✅ |
| 5–8 | PSHA, Coulomb, hipótesis exploratorias, capa de lenguaje | ❌ no implementadas |

**143 pruebas, todas en verde** (138 rápidas + 5 lentas de recuperación y calibración).

### ⚠️ Advertencia sobre la Fase 1

**El paquete no ha procesado ni un solo dato real.** El entorno de desarrollo
tenía el egreso de red bloqueado hacia todos los servicios sismológicos
(`earthquake.usgs.gov`, `www.ssn.unam.mx`, `www.isc.ac.uk`, `www.globalcmt.org`,
`service.iris.edu`), así que **ninguna ruta de API, formato ni licencia pudo
verificarse**.

En lugar de escribir URLs de memoria —que producirían código que *parece*
verificado— `parametros/fuentes.toml` no contiene ninguna URL base, y el cliente
se niega a consultar una fuente sin verificar:

```
ErrorDeFuenteNoVerificada: La fuente 'ssn_unam' no está verificada.
  documentacion  : http://www.ssn.unam.mx/catalogo/
  licencia       : POR VERIFICAR
Abre la documentación oficial, comprueba la URL base real del servicio y
rellena url_base + verificado = true en parametros/fuentes.toml.
```

Todo lo demás se validó sobre **catálogos sintéticos con parámetros conocidos**,
que es el criterio correcto para estimadores: si el ajuste no recupera los
valores con los que se simuló, el estimador está mal.

Detalle completo en [`docs/01-fuentes-verificadas.md`](docs/01-fuentes-verificadas.md)
y [`docs/03-pendientes.md`](docs/03-pendientes.md).

---

## Instalación

```bash
pip install -e ".[dev]"
pytest -m "not lento"        # 121 pruebas, ~8 s
pytest -m lento              # recuperación de parámetros de ETAS, ~27 s
python ejemplos/canalizacion_sintetica.py
```

Requiere Python ≥ 3.11 (usa `tomllib` de la biblioteca estándar).

El extra `[psha]` instala OpenQuake, que es **AGPL-3.0**: leer
[`docs/adr/0002-openquake-y-agpl.md`](docs/adr/0002-openquake-y-agpl.md) antes.
Las fases 0–4 no lo necesitan.

---

## Lo que distingue a este paquete

### 1. Un valor sin procedencia no se puede construir

```python
>>> Cantidad(1.0, "adimensional", Procedencia.PUBLICADO)
ErrorDeProcedencia: procedencia PUBLICADO exige una fuente citable

>>> Cantidad(1.02, "adimensional", Procedencia.PUBLICADO,
...          fuente="Aki 1965", incertidumbre=0.05)
1.02 +/- 0.05 adimensional [PUBLICADO: Aki 1965]
```

La incertidumbre `None` significa *no cuantificada* y se muestra así. El número
desnudo no existe.

### 2. Los coeficientes no verificados contaminan lo que derivan

```python
>>> gardner_knopoff(catalogo)
ErrorDeParametrosNoVerificados: Los coeficientes de 'gardner_knopoff' están
marcados como NO VERIFICADOS en parametros/ventanas_decluster.toml.
  fuente declarada : Gardner y Knopoff (1974), Bull. Seismol. Soc. Am.
  qué verificar    : tabla de ventanas espacio-temporales
```

Con `permitir_no_verificado=True` funciona, y **todo lo derivado queda marcado**.

### 3. No hay método privilegiado donde no debe haberlo

Sobre un catálogo sintético con Mc verdadero = 3.5:

| Método | Mc |
|---|---|
| Máxima curvatura | 3.8 |
| Bondad de ajuste | 3.5 |
| Estabilidad de b | 4.1 |

Dispersión **0.6 unidades** — mucho mayor que el error estadístico de cada uno.
`comparar_metodos_mc` la reporta en lugar de elegir por el usuario. Igual con el
decluster, donde los tres métodos difirieron en **19 puntos porcentuales** de
eventos eliminados sobre el mismo catálogo.

### 4. Las pruebas poissonianas se niegan a correr sobre modelos autoexcitados

Sobre un catálogo generado por ETAS, con un pronóstico de sismicidad suavizada:

| Prueba | Poissoniana | Basada en catálogo |
|---|---|---|
| N-test | p = 1.0e-35 → **rechaza** | p = 0.14 → no rechaza |
| S-test | p = 0 → **rechaza** | p = 0.77 → no rechaza |
| M-test | p = 0.17 → no rechaza | p = 0.13 → no rechaza |

`var(N)/media(N) = 36.5` en las simulaciones del modelo (bajo Poisson valdría 1).

Los rechazos poissonianos son **espurios**: castigan al modelo por una
sobredispersión y un agrupamiento que el modelo predice correctamente. Nótese
que el M-test *no* rechaza en ninguna versión — el agrupamiento afecta al conteo
y al espacio, no a la distribución de magnitudes. `PronosticoRejilla` lleva la
bandera `poisson_valido`, y las pruebas lanzan `ErrorDeSupuesto` cuando no
corresponde.

### 5. Detecta destreza cuando existe, y no la inventa cuando no

El mismo análisis sobre dos catálogos que solo difieren en el fondo espacial de
la simulación:

| Escenario | Ganancia | Molchan ASS | ROC AUC | Destreza Brier |
|---|---|---|---|---|
| Fondo **heterogéneo** (hay estructura) | **+1.172** | **+0.754** | **0.911** | **+0.437** |
| Fondo **uniforme** (no hay nada que aprender) | −0.081 | −0.118 | 0.462 | −0.054 |

Un módulo que solo acertara en una de las dos mitades sería inútil: la primera
detecta ceguera, la segunda detecta invención de destreza.

La línea base usa la distribución G–R de magnitudes a propósito: una referencia
uniforme también en magnitud sería un hombre de paja e inflaría la ganancia
aparente.

### 6. La referencia no es un rival trivial

El modelo de comparación es **sismicidad suavizada** con núcleo adaptativo (el
ancho de cada evento es la distancia a su k-ésimo vecino), no un Poisson
uniforme. Es el rival exigente que se usa en la práctica: buena parte de los
modelos publicados apenas lo superan.

El ancho del núcleo se elige por verosimilitud **dentro del entrenamiento**;
`optimizar_ancho` no recibe el periodo de prueba, así que la salvaguarda contra
la fuga es estructural, no una comprobación posterior.

### 7. Se declara lo que el software no puede garantizar

`verificar_corte_temporal` detecta fuga **por marcas de tiempo** y lo dice: la
fuga por selección de modelo tras haber visto el catálogo completo es indecidible
desde el código. Para eso existe `BitacoraDeDecisiones`, que no detecta nada —
obliga a dejar constancia fechada.

---

## Validaciones realizadas

| Comprobación | Resultado |
|---|---|
| Recuperación de b (Aki–Utsu) | Insesgado; **cobertura del intervalo 1σ = 68.3 %**, nominal exacto |
| Sesgo por binning | Sin la corrección `Mc − dM/2`, b sale sesgado a 1.125 (verdadero 1.0) |
| Recuperación de Omori–Utsu (K, c, p) | Los tres dentro de ~2σ |
| Recuperación de ETAS (μ, K, α, c, p) | Recupera; degeneración K–α documentada |
| Calibración de las 5 pruebas CSEP | Tasa de rechazo ≈ α con el modelo correcto |
| Potencia del S-test | Detecta error espacial (0.26) donde el N-test correctamente no (0.035) |
| Empates en Molchan/ROC | Pronóstico constante da AUC = 0.5 y ASS = 0 **exactos** |
| Brier de la climatología | Destreza y resolución exactamente 0 |
| Calibración de S/M-test basados en catálogo | 0.033 y 0.050 con el modelo correcto |
| Potencia del S-test basado en catálogo | **1.000** frente a un fondo espacial equivocado |
| Especificidad del M-test | 0.050 ante ese mismo error espacial: no reacciona a lo que no le toca |
| Conservación de masa del suavizado | Exacta, también con núcleos que tocan el borde |

---

## Estructura

```
src/sismolat/
  procedencia.py        Cantidad con unidad, incertidumbre y procedencia obligatorias
  catalogo.py           Esquema validado + advertencias + huella reproducible
  reproducibilidad.py   Identificador de análisis, fuga temporal, registro de pruebas múltiples
  sintetico.py          Generadores con parámetros conocidos (para las pruebas)
  ingesta/              fuentes · fdsn · dedup · homogenizacion · instantanea
  estadistica/          gutenberg_richter · mc · decluster
  modelos/              omori · etas · suavizado
  evaluacion/           pronostico · csep · alarma
parametros/             Coeficientes externalizados, todos marcados verificado = false
docs/                   Contrato, fuentes, supuestos, pendientes, ADR
ejemplos/               Canalización completa fases 0-4 sobre datos sintéticos
```

Cada módulo documenta en su docstring: **la matemática** (derivación y
condiciones de validez), **los datos** (procedencia y sesgos) y **lo que ese
módulo no puede hacer**.

---

## Licencia

Sin decidir todavía: depende de si el proyecto adopta OpenQuake en la fase 5.
Ver [`docs/adr/0002-openquake-y-agpl.md`](docs/adr/0002-openquake-y-agpl.md).
