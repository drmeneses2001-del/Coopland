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

## Evaluación

| Supuesto | Dónde | Efecto si es falso |
|---|---|---|
| Poisson por celda | `n_test`, `l_test`, `brier` | **Rechazos espurios** con modelos autoexcitados. Bloqueado por `poisson_valido=False` |
| Definición fija del evento objetivo | `EventoObjetivo` | Brier y Molchan cambian de valor; debe fijarse antes de mirar datos |
| Medida de referencia declarada | `molchan` | El eje τ deja de ser interpretable. **Exigida en la firma** |
| Suavizado en `l_test_catalogo` | `suavizado=0.1` | `SUPUESTO`; repetir con otro valor |

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
