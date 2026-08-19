"""Pruebas de modulacion por una covariable continua (presion, temperatura, nivel del mar).

Como se plantea la prueba correctamente
---------------------------------------
La pregunta no es "¿estan correlacionadas la sismicidad y la presion?" —dos
series temporales cualesquiera con tendencia o estacionalidad salen
correlacionadas— sino:

    ¿Los valores de la covariable **en los instantes en que ocurren sismos**
    difieren de los valores que la covariable toma **en general**?

Eso convierte el problema en comparar dos distribuciones: la de la covariable
muestreada en los tiempos de los eventos, frente a su distribucion marginal en
todo el periodo. Es una prueba bien planteada, no una correlacion espuria entre
series.

Que se reporta, y por que en ese orden
--------------------------------------
1. **Tamano de efecto** primero: la diferencia de medias en unidades de la
   desviacion tipica de la covariable. Es lo que dice si el efecto importa.
2. **Potencia**: sin ella, un resultado no significativo no distingue "no hay
   efecto" de "no habia datos".
3. **p-valor** al final, y siempre junto al numero de pruebas realizadas en el
   proyecto.

Advertencias estructurales
--------------------------
* La **estacionalidad compartida** es la trampa principal: si tanto la
  covariable como la completitud del catalogo varian con la estacion, aparece
  correlacion sin relacion causal. :func:`prueba_de_covariable` avisa cuando la
  covariable tiene estructura anual marcada.
* La **autocorrelacion** de ambas series reduce el numero efectivo de datos
  independientes muy por debajo de N. El p-valor nominal es entonces
  demasiado optimista, y por eso se ofrece el p por permutacion en bloques.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

__all__ = ["ResultadoCovariable", "prueba_de_covariable", "potencia_covariable"]


@dataclass(frozen=True)
class ResultadoCovariable:
    """Comparacion entre la covariable en los eventos y su distribucion general."""

    n_eventos: int
    media_en_eventos: float
    media_general: float
    desviacion_general: float
    #: Diferencia de medias en unidades de la desviacion tipica (d de Cohen).
    tamano_efecto: float
    p_valor: float
    p_por_bloques: float | None
    potencia: float | None
    advertencias: tuple[str, ...] = ()

    @property
    def significativo(self) -> bool:
        return self.p_valor < 0.05

    def __str__(self) -> str:
        pot = f", potencia={self.potencia:.2f}" if self.potencia is not None else ""
        return (f"Covariable (n={self.n_eventos}): efecto d={self.tamano_efecto:+.4f}, "
                f"p={self.p_valor:.4g}{pot}")


def _interpolar(tiempos_eventos, tiempos_serie, valores_serie):
    t = np.asarray(tiempos_eventos, dtype=float)
    ts = np.asarray(tiempos_serie, dtype=float)
    vs = np.asarray(valores_serie, dtype=float)
    orden = np.argsort(ts)
    ts, vs = ts[orden], vs[orden]
    dentro = (t >= ts[0]) & (t <= ts[-1])
    if not dentro.any():
        raise ValueError(
            "ningun evento cae dentro del periodo cubierto por la serie de la covariable"
        )
    return np.interp(t[dentro], ts, vs), int((~dentro).sum()), ts, vs


def prueba_de_covariable(
    tiempos_eventos_dias: np.ndarray,
    tiempos_serie_dias: np.ndarray,
    valores_serie: np.ndarray,
    *,
    n_permutaciones: int = 2000,
    bloque_dias: float = 30.0,
    semilla: int = 0,
    detectar_estacionalidad: bool = True,
) -> ResultadoCovariable:
    """Compara la covariable en los tiempos de los eventos con su distribucion general.

    El p-valor principal sale de una prueba de Mann-Whitney (no supone
    normalidad). El ``p_por_bloques`` sale de permutar bloques temporales
    completos, lo que **preserva la autocorrelacion** de la covariable y da un
    p-valor mucho mas honesto cuando ambas series son suaves.
    """
    en_eventos, fuera, ts, vs = _interpolar(
        tiempos_eventos_dias, tiempos_serie_dias, valores_serie)
    n = en_eventos.size
    if n < 20:
        raise ValueError(f"solo {n} eventos dentro del periodo de la serie; se requieren 20")

    media_ev = float(en_eventos.mean())
    media_gen = float(vs.mean())
    sd = float(vs.std(ddof=1))
    if sd == 0:
        raise ValueError("la covariable es constante: no hay nada que probar")
    d = (media_ev - media_gen) / sd

    p = float(stats.mannwhitneyu(en_eventos, vs, alternative="two-sided").pvalue)

    # p por permutacion en bloques: desplaza circularmente la serie por bloques,
    # conservando su autocorrelacion.
    rng = np.random.default_rng(semilla)
    nulos = np.empty(n_permutaciones)
    span = ts[-1] - ts[0]
    t_ev = np.asarray(tiempos_eventos_dias, dtype=float)
    t_ev = t_ev[(t_ev >= ts[0]) & (t_ev <= ts[-1])]
    for k in range(n_permutaciones):
        corrimiento = rng.random() * span
        t_desplazado = ts[0] + (t_ev - ts[0] + corrimiento) % span
        nulos[k] = np.interp(t_desplazado, ts, vs).mean()
    p_bloques = float((np.sum(np.abs(nulos - media_gen) >= abs(media_ev - media_gen)) + 1)
                      / (n_permutaciones + 1))

    avisos: list[str] = []
    if fuera:
        avisos.append(
            f"{fuera} eventos quedaron fuera del periodo cubierto por la serie y se "
            "excluyeron."
        )
    if abs(d) < 0.05 and p < 0.05:
        avisos.append(
            f"Efecto significativo pero diminuto (d={d:+.4f}). Con N grande cualquier "
            "desviacion minuscula sale significativa: el tamano de efecto es lo que importa."
        )
    if p_bloques > 0.05 >= p:
        avisos.append(
            f"El p nominal ({p:.4g}) es significativo pero el p por permutacion en bloques "
            f"({p_bloques:.4g}) NO lo es. La autocorrelacion de la covariable estaba "
            "inflando la significancia: el resultado honesto es el de bloques."
        )
    if detectar_estacionalidad and span > 730:
        fase_anual = 2 * math.pi * (ts % 365.25) / 365.25
        r = math.hypot(float(np.mean(np.cos(fase_anual) * (vs - media_gen))),
                       float(np.mean(np.sin(fase_anual) * (vs - media_gen)))) / sd
        if r > 0.15:
            avisos.append(
                f"La covariable tiene estructura anual marcada (amplitud relativa {r:.2f}). "
                "Si la completitud del catalogo tambien varia con la estacion, aparecera "
                "correlacion sin relacion causal. Comprueba Mc por ventanas antes de "
                "interpretar."
            )

    return ResultadoCovariable(
        n_eventos=n, media_en_eventos=media_ev, media_general=media_gen,
        desviacion_general=sd, tamano_efecto=d, p_valor=p, p_por_bloques=p_bloques,
        potencia=None, advertencias=tuple(avisos),
    )


def potencia_covariable(
    n: int, tamano_efecto: float, *, alfa: float = 0.05, n_simulaciones: int = 2000,
    semilla: int = 0,
) -> float:
    """Potencia para detectar un efecto de tamano ``d`` con ``n`` eventos.

    Obligatoria para interpretar un resultado no significativo.
    """
    if n < 3:
        raise ValueError("se requieren al menos 3 eventos")
    rng = np.random.default_rng(semilla)
    referencia = rng.standard_normal((n_simulaciones, max(n * 5, 200)))
    muestra = rng.standard_normal((n_simulaciones, n)) + tamano_efecto
    rechazos = 0
    for k in range(n_simulaciones):
        if stats.mannwhitneyu(muestra[k], referencia[k],
                              alternative="two-sided").pvalue < alfa:
            rechazos += 1
    return rechazos / n_simulaciones
