# Supuestos declarados

Todo supuesto que afecta a un resultado numérico, con su efecto y cómo
comprobarlo.

## Estadística de catálogos

| Supuesto | Dónde | Efecto si es falso | Cómo comprobarlo |
|---|---|---|---|
| Magnitudes completas sobre Mc | `gutenberg_richter`, `etas` | b sesgado; ETAS sesgado en μ y K | `comparar_metodos_mc`, `mc_por_ventanas` |
| Una sola escala de magnitud | todo el paquete | La FMD se curva; b pierde sentido físico | `Catalogo.advertencias()` lo detecta |
| Mc constante en el espacio | mapas de b | **Estructura espacial falsa con aspecto tectónico** | `mc_espacial` |
| Mc constante en el tiempo | series de tasa | Saltos artificiales confundidos con cambios reales | `mc_por_ventanas` |
| Eventos independientes (σ de Shi-Bolt) | `b_aki_utsu` | σ_b **subestimado** con réplicas presentes | Comparar σ con catálogo declusterizado |
| Sin truncamiento superior de magnitud | `b_aki_utsu` | b sesgado hacia arriba si hay Mmax cercano | `magnitudes_gr(m_max=...)` |
| Corrección MAXC = +0.2 | `mc.CORRECCION_MAXC_POR_DEFECTO` | Mc desplazado; b cambia | Es `CONVENCION`; **no calibrada para esta región** |

## Modelos de proceso puntual

| Supuesto | Dónde | Efecto si es falso |
|---|---|---|
| La ventana contiene **una sola** secuencia | `ajustar_omori` | p sesgado hacia abajo; usar ETAS |
| Completitud desde t₀ | `ajustar_omori` | c sesgado hacia arriba: **c mide en buena parte la incompletitud temprana**, no física |
| Magnitudes independientes del historial | `etas` | Supuesto fuerte y contestado |
| p > 1 | `simular_etas` | Con p ≤ 1 la productividad diverge; el código lo rechaza |
| Fondo uniforme en la caja | `simular_espacio_temporal` | **No es realista**; sirve para pruebas, no para uso |

### Degeneración conocida de ETAS

En las pruebas de recuperación, `K` y `α` se desvían de forma **correlacionada**
(una baja cuando la otra sube). Es un comportamiento real del modelo, no un fallo
del optimizador: la verosimilitud es plana a lo largo de esa dirección. Las σ que
salen del hessiano son **optimistas** en esa combinación. Si se necesita `α` bien
determinada, conviene fijarla o usar un prior informativo.

## Sismicidad suavizada

| Supuesto | Dónde | Efecto si es falso |
|---|---|---|
| **La sismicidad futura ocurre donde la pasada** | `pronostico_suavizado` | Es la hipótesis que el modelo encarna. **Falsa justo donde más importa**: un sismo grande en una brecha sísmica ocurre, por definición, donde no ha habido sismicidad reciente |
| Estacionariedad de la tasa | escalado de `dias_entrenamiento` a `dias_pronostico` | El total pronosticado se desvía; comprobable a posteriori con el N-test |
| Piso uniforme del 1 % | `PISO_RELATIVO_POR_DEFECTO` | `SUPUESTO`. Sin él, una celda sin sismicidad histórica da log-verosimilitud −∞ ante un solo evento. Subirlo acerca el modelo al uniforme y reduce a la vez su ganancia potencial y su riesgo de catástrofe |
| Catálogo declusterizado | uso previsto | Suavizar el catálogo completo mete las réplicas pasadas en el mapa de fondo y concentra el pronóstico donde hubo secuencias — que es donde menos probable es que se repitan a medio plazo |

### El ancho del núcleo no es un parámetro libre

Elegirlo mirando el periodo de prueba es fuga de información y es una de las
formas más comunes de inflar el desempeño aparente. `optimizar_ancho` parte el
entrenamiento internamente por un corte temporal y **no recibe el periodo de
prueba**: la salvaguarda es estructural, no una comprobación posterior.

Cuando el óptimo cae en un extremo del rango probado, o cuando la verosimilitud
apenas varía entre candidatos, la función lo advierte: en ese caso el ancho está
mal determinado y reportar el óptimo como si estuviera restringido es engañoso.

## Evaluación

| Supuesto | Dónde | Efecto si es falso |
|---|---|---|
| Poisson por celda | `n_test`, `l_test`, `brier` | **Rechazos espurios** con modelos autoexcitados. Bloqueado por `poisson_valido=False` |
| Definición fija del evento objetivo | `EventoObjetivo` | Brier y Molchan cambian de valor; debe fijarse antes de mirar datos |
| Medida de referencia declarada | `molchan` | El eje τ deja de ser interpretable. **Exigida en la firma** |
| Suavizado en las pruebas basadas en catálogo | `suavizado=0.1` | `SUPUESTO`; repetir con otro valor |
| Estadístico independiente de *N* | `s_test_catalogo`, `m_test_catalogo` | Necesario: con ETAS, la mayoría de las simulaciones tiene menos eventos que el observado |

### Por qué las pruebas marginales basadas en catálogo no remuestrean a *N* fijo

El diseño obvio —extraer *N* observado eventos de cada catálogo simulado— falla
de dos maneras, y ambas se comprobaron empíricamente:

- **Sin reemplazo**: con ETAS, casi todas las simulaciones tienen menos eventos
  que el observado (en una prueba, 391 de 400) y hay que descartarlas, lo que
  sesga la referencia hacia las realizaciones más productivas del modelo.
- **Con reemplazo**: aparecen localizaciones repetidas que agrupan
  artificialmente los catálogos de referencia, hunden su verosimilitud y dejan
  al observado siempre por encima. El cuantil sale 1.0000 y **la prueba pierde
  toda su potencia**.

El estadístico usado es la log-verosimilitud media **por evento**, que es
independiente de *N* y aprovecha todas las simulaciones.

### Empates en Molchan y ROC

Las celdas con la misma tasa pronosticada **no pueden ordenarse entre sí**. Si se
desempatan por índice de arreglo, un pronóstico uniforme llega a dar AUC ≠ 0.5 y
ASS ≠ 0 — destreza aparente que el modelo no tiene. El código agrupa los empates
y las pruebas verifican que el pronóstico constante da exactamente 0.5 y 0.

## Ingesta

| Supuesto | Dónde | Efecto |
|---|---|---|
| Umbrales de duplicado (16 s, 100 km, 1.0 mag) | `CriterioDuplicado` | `CONVENCION`, no calibrada. Los casos dudosos se reportan sin resolver |
| Escalas Mw/Mww/Mwc equivalentes | `homogenizar` | Difieren en centésimas por venir de inversiones distintas |
| Hanks-Kanamori con constante 9.1 | `momento_a_mw` | **Depende del convenio de unidades** (N m frente a dyn cm). Verificar el del catálogo de origen |

## Geometría

La rejilla regular en grados **no es equiárea**. `Rejilla.areas_km2` corrige por
el coseno de la latitud; para las latitudes de México (14–33 N) el error de área
sin corregir es del orden del 3–15 %. La vecindad circular en grados de
`mc_espacial` tiene la misma distorsión: es aceptable para diagnóstico, no para
calcular tasas por unidad de área.
