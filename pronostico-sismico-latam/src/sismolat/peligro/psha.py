"""Peligro sismico probabilistico: integracion de Cornell-McGuire.

La matematica
-------------
La tasa anual de excedencia de un nivel de intensidad ``z`` es

.. math::
    \\lambda(IM > z) = \\sum_{s} \\nu_s
        \\int\\!\\!\\int P(IM > z \\mid m, r)\\, f_s(m)\\, f_s(r)\\, dm\\, dr

donde :math:`\\nu_s` es la tasa de la fuente, :math:`f(m)` la distribucion de
magnitudes (Gutenberg-Richter truncada) y :math:`f(r)` la de distancias, que
aqui sale de discretizar la fuente de area en fuentes puntuales.

La probabilidad de excedencia condicional usa la dispersion **aleatoria** del
GMM, que es lognormal:

.. math::
    P(IM > z \\mid m, r) = 1 - \\Phi\\!\\left(
        \\frac{\\ln z - \\mu(m, r)}{\\sigma(m, r)} \\right)

Aleatoria frente a epistemica
-----------------------------
La sigma del GMM que entra en esta integral es variabilidad **aleatoria**: la
dispersion real de los registros alrededor de la mediana, que no se reduce con
mas conocimiento. La incertidumbre **epistemica** —que GMM usar, que b, que
m_max— **no** entra aqui: se representa con las ramas del arbol logico
(:mod:`sismolat.peligro.arbol`), que produce una distribucion de curvas de
peligro en lugar de una sola.

Confundirlas es uno de los errores mas frecuentes en PSHA. Meter incertidumbre
epistemica dentro de sigma ensancha la curva de forma que parece conservadora y
no lo es: destruye la separacion que permite decir cuanto del resultado es
ignorancia y cuanto es azar irreducible.

Truncamiento de epsilon
-----------------------
La cola lognormal sin truncar predice aceleraciones fisicamente imposibles a
periodos de retorno largos. La practica habitual es truncar en 3-4 sigma. El
valor es una **CONVENCION** declarada y afecta al resultado en los periodos de
retorno largos, que son justamente los que interesan.

Lo que este modulo NO puede hacer
---------------------------------
* No modela rupturas finitas (ver :mod:`sismolat.peligro.fuentes`).
* No incluye efectos de sitio mas alla del parametro del GMM. Para el Valle de
  Mexico eso es insuficiente: ver :mod:`sismolat.peligro.sitio`.
* No produce mapas oficiales de peligro ni sustituye a la normativa vigente.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from scipy import stats

from ..procedencia import Cantidad, Procedencia, convencion
from .fuentes import FuenteArea
from .gmm import ModeloMovimiento

__all__ = [
    "Sitio", "CurvaDePeligro", "Desagregacion",
    "curva_de_peligro", "desagregar", "EPSILON_MAXIMO_POR_DEFECTO",
    "probabilidad_en_periodo", "periodo_de_retorno",
]

#: Truncamiento de la cola lognormal del GMM, en numero de sigmas.
EPSILON_MAXIMO_POR_DEFECTO = convencion(
    3.0, "sigmas",
    motivo=(
        "sin truncar, la cola lognormal predice aceleraciones fisicamente imposibles a "
        "periodos de retorno largos. Truncar entre 3 y 4 sigma es practica establecida; "
        "el valor concreto afecta al resultado en 2475 anios y debe reportarse."
    ),
)


@dataclass(frozen=True)
class Sitio:
    """Punto donde se evalua el peligro."""

    nombre: str
    lon: float
    lat: float
    vs30: Cantidad

    def __post_init__(self) -> None:
        if not isinstance(self.vs30, Cantidad):
            raise TypeError("vs30 debe ser una Cantidad con procedencia declarada")
        if self.vs30.valor <= 0:
            raise ValueError("vs30 debe ser positiva")


@dataclass(frozen=True)
class CurvaDePeligro:
    """Tasa anual de excedencia frente a nivel de intensidad."""

    niveles: np.ndarray            # niveles de intensidad (g para PGA/SA)
    tasas: np.ndarray              # tasa anual de excedencia
    sitio: Sitio
    medida: str
    #: Contribucion de cada fuente, por nombre.
    por_fuente: dict[str, np.ndarray] = field(default_factory=dict)
    modelos: tuple[str, ...] = ()
    epsilon_max: float = 3.0
    advertencias: tuple[str, ...] = ()

    def nivel_para_periodo(self, periodo_retorno_anios: float) -> float:
        """Nivel de intensidad excedido con el periodo de retorno dado.

        Se interpola en escala log-log, que es donde la curva de peligro es
        aproximadamente recta. Si el periodo pedido cae fuera del rango
        calculado, se lanza un error en lugar de extrapolar: extrapolar una
        curva de peligro mas alla de los niveles evaluados es una de las formas
        mas faciles de producir un numero sin sustento.
        """
        objetivo = 1.0 / periodo_retorno_anios
        val = self.tasas > 0
        t, n = self.tasas[val], self.niveles[val]
        if objetivo > t.max() or objetivo < t.min():
            raise ValueError(
                f"un periodo de retorno de {periodo_retorno_anios:g} anios (tasa "
                f"{objetivo:.3g}) cae fuera del rango calculado "
                f"[{1/t.max():.1f}, {1/t.min():.1f}] anios. Amplia los niveles de "
                "intensidad en lugar de extrapolar."
            )
        orden = np.argsort(t)
        return float(np.exp(np.interp(math.log(objetivo), np.log(t[orden]), np.log(n[orden]))))

    def probabilidad_en(self, anios: float) -> np.ndarray:
        """Probabilidad de excedencia en una ventana de ``anios``, bajo Poisson."""
        return 1.0 - np.exp(-self.tasas * anios)

    def __str__(self) -> str:
        return (f"Curva de peligro {self.medida} en {self.sitio.nombre} "
                f"({len(self.niveles)} niveles, modelos: {', '.join(self.modelos)})")


def probabilidad_en_periodo(tasa_anual: np.ndarray | float, anios: float) -> np.ndarray:
    """``P = 1 - exp(-lambda T)``: probabilidad de al menos una excedencia."""
    return 1.0 - np.exp(-np.asarray(tasa_anual, dtype=float) * anios)


def periodo_de_retorno(probabilidad: float, anios: float) -> float:
    """Periodo de retorno equivalente a una probabilidad en una ventana.

    Por ejemplo, 10 % en 50 anios equivale a 475 anios; 2 % en 50 anios, a 2475.
    """
    if not 0 < probabilidad < 1:
        raise ValueError("la probabilidad debe estar en (0, 1)")
    return -anios / math.log(1.0 - probabilidad)


def _prob_excedencia(
    ln_z: np.ndarray, mu: np.ndarray, sigma: np.ndarray, eps_max: float,
) -> np.ndarray:
    """P(IM > z | m, r) con la normal truncada en +/- eps_max sigmas."""
    eps = (ln_z - mu) / sigma
    if not math.isfinite(eps_max) or eps_max <= 0:
        return stats.norm.sf(eps)
    norm = stats.norm.cdf(eps_max) - stats.norm.cdf(-eps_max)
    p = (stats.norm.cdf(eps_max) - stats.norm.cdf(np.clip(eps, -eps_max, eps_max))) / norm
    return np.where(eps > eps_max, 0.0, np.where(eps < -eps_max, 1.0, p))


def curva_de_peligro(
    sitio: Sitio,
    fuentes: Sequence[tuple[FuenteArea, ModeloMovimiento]],
    niveles: np.ndarray,
    *,
    medida: str = "PGA",
    dm: float = 0.1,
    epsilon_max: Cantidad | None = None,
    parametros_extra: dict | None = None,
) -> CurvaDePeligro:
    """Curva de peligro por integracion de Cornell-McGuire.

    ``fuentes`` es una lista de pares ``(FuenteArea, ModeloMovimiento)``: cada
    fuente lleva **su propio** GMM, porque el modelo apropiado depende del
    regimen tectonico y mezclarlos seria un error.
    """
    epsilon_max = epsilon_max or EPSILON_MAXIMO_POR_DEFECTO
    niveles = np.asarray(niveles, dtype=float)
    if np.any(niveles <= 0):
        raise ValueError("los niveles de intensidad deben ser positivos")
    ln_z = np.log(niveles)

    total = np.zeros_like(niveles)
    por_fuente: dict[str, np.ndarray] = {}
    avisos: list[str] = []
    modelos: list[str] = []

    for fuente, modelo in fuentes:
        if fuente.regimen is not modelo.regimen:
            raise ValueError(
                f"la fuente '{fuente.nombre}' es de regimen {fuente.regimen.value} pero "
                f"el modelo '{modelo.nombre}' es de {modelo.regimen.value}"
            )
        puntos = fuente.discretizar()
        dist = puntos.distancias_km(sitio.lon, sitio.lat)
        centros, tasas_m = fuente.magnitudes.tasas_por_bin(dm)

        aporte = np.zeros_like(niveles)
        for m, nu_m in zip(centros, tasas_m):
            if nu_m <= 0:
                continue
            mu, sig = modelo.media_y_sigma(
                float(m), dist, medida=medida, vs30=sitio.vs30.valor,
                parametros_extra=parametros_extra,
            )
            # P de excedencia para cada nivel y cada punto -> (n_niveles, n_puntos)
            p = _prob_excedencia(ln_z[:, None], mu[None, :], sig[None, :],
                                 epsilon_max.valor)
            aporte += nu_m * (p * puntos.peso[None, :]).sum(axis=1)

        por_fuente[fuente.nombre] = aporte
        total += aporte
        modelos.append(modelo.nombre)
        avisos.extend(fuente.advertencias())
        sin_declarar = modelo.parametros_sin_declarar(parametros_extra)
        if sin_declarar:
            avisos.append(
                f"'{modelo.nombre}' usa los parametros {sin_declarar} y no se le dieron: "
                "OpenQuake les asigna valores por defecto que AFECTAN al resultado."
            )

    avisos.append(
        f"Cola lognormal truncada en {epsilon_max.valor:g} sigmas "
        f"[{epsilon_max.procedencia.value}]. El valor influye sobre todo en periodos de "
        "retorno largos, que son los de interes para diseno."
    )
    avisos.append(
        "La sigma usada es variabilidad ALEATORIA del GMM. La incertidumbre EPISTEMICA "
        "(que GMM, que b, que m_max) no esta en esta curva: requiere arbol logico."
    )
    return CurvaDePeligro(
        niveles=niveles, tasas=total, sitio=sitio, medida=medida,
        por_fuente=por_fuente, modelos=tuple(modelos),
        epsilon_max=float(epsilon_max.valor),
        advertencias=tuple(dict.fromkeys(avisos)),
    )


@dataclass(frozen=True)
class Desagregacion:
    """Contribucion al peligro por magnitud, distancia y epsilon."""

    nivel_objetivo: float
    tasa_total: float
    bordes_m: np.ndarray
    bordes_r: np.ndarray
    bordes_eps: np.ndarray
    #: Matriz (m, r, eps) con la contribucion a la tasa de excedencia.
    contribucion: np.ndarray
    sitio: Sitio
    medida: str

    @property
    def fraccion(self) -> np.ndarray:
        """Contribucion normalizada: suma 1."""
        s = self.contribucion.sum()
        return self.contribucion / s if s > 0 else self.contribucion

    def modal(self) -> dict[str, float]:
        """Escenario modal: el bin (m, r, eps) que mas contribuye.

        **Advertencia de interpretacion**: el escenario modal no es "el sismo que
        va a producir esa aceleracion". Es el bin que mas aporta a una suma sobre
        muchos escenarios, y con distribuciones anchas o multimodales puede no
        ser representativo de nada. Mirar tambien la media y la forma completa.
        """
        i, j, k = np.unravel_index(int(np.argmax(self.contribucion)),
                                   self.contribucion.shape)
        cm = 0.5 * (self.bordes_m[:-1] + self.bordes_m[1:])
        cr = 0.5 * (self.bordes_r[:-1] + self.bordes_r[1:])
        ce = 0.5 * (self.bordes_eps[:-1] + self.bordes_eps[1:])
        return {"magnitud": float(cm[i]), "distancia_km": float(cr[j]),
                "epsilon": float(ce[k]),
                "fraccion": float(self.fraccion[i, j, k])}

    def media(self) -> dict[str, float]:
        """Magnitud, distancia y epsilon medios ponderados por contribucion."""
        f = self.fraccion
        cm = 0.5 * (self.bordes_m[:-1] + self.bordes_m[1:])
        cr = 0.5 * (self.bordes_r[:-1] + self.bordes_r[1:])
        ce = 0.5 * (self.bordes_eps[:-1] + self.bordes_eps[1:])
        return {"magnitud": float((f.sum(axis=(1, 2)) * cm).sum()),
                "distancia_km": float((f.sum(axis=(0, 2)) * cr).sum()),
                "epsilon": float((f.sum(axis=(0, 1)) * ce).sum())}


def desagregar(
    sitio: Sitio,
    fuentes: Sequence[tuple[FuenteArea, ModeloMovimiento]],
    nivel_objetivo: float,
    *,
    medida: str = "PGA",
    dm: float = 0.2,
    bordes_r: np.ndarray | None = None,
    bordes_eps: np.ndarray | None = None,
    epsilon_max: Cantidad | None = None,
    parametros_extra: dict | None = None,
) -> Desagregacion:
    """Desagregacion magnitud-distancia-epsilon de la tasa de excedencia.

    Responde "que combinacion de sismo, distancia y desviacion respecto a la
    mediana del GMM produce el peligro a este nivel". Es lo que permite elegir
    escenarios de diseno coherentes con la curva.

    La suma de todas las contribuciones reproduce exactamente la tasa de
    excedencia total en ese nivel; hay una prueba que lo comprueba.
    """
    epsilon_max = epsilon_max or EPSILON_MAXIMO_POR_DEFECTO
    e_max = epsilon_max.valor
    ln_z = math.log(nivel_objetivo)
    bordes_eps = np.linspace(-e_max, e_max, 13) if bordes_eps is None else np.asarray(bordes_eps)
    bordes_r = np.arange(0.0, 501.0, 25.0) if bordes_r is None else np.asarray(bordes_r)

    m_min = min(f.magnitudes.m_min for f, _ in fuentes)
    m_max = max(f.magnitudes.m_max.valor for f, _ in fuentes)
    bordes_m = np.arange(m_min, m_max + dm / 2, dm)
    if bordes_m[-1] < m_max - 1e-9:
        bordes_m = np.append(bordes_m, m_max)

    contrib = np.zeros((bordes_m.size - 1, bordes_r.size - 1, bordes_eps.size - 1))
    norm_eps = stats.norm.cdf(e_max) - stats.norm.cdf(-e_max)

    for fuente, modelo in fuentes:
        puntos = fuente.discretizar()
        dist = puntos.distancias_km(sitio.lon, sitio.lat)
        idx_r = np.clip(np.digitize(dist, bordes_r) - 1, 0, bordes_r.size - 2)
        centros_m, tasas_m = fuente.magnitudes.tasas_por_bin(dm)
        idx_m = np.clip(np.digitize(centros_m, bordes_m) - 1, 0, bordes_m.size - 2)

        for im, (m, nu_m) in enumerate(zip(centros_m, tasas_m)):
            if nu_m <= 0:
                continue
            mu, sig = modelo.media_y_sigma(
                float(m), dist, medida=medida, vs30=sitio.vs30.valor,
                parametros_extra=parametros_extra,
            )
            eps_umbral = (ln_z - mu) / sig            # epsilon minimo para exceder
            for k in range(bordes_eps.size - 1):
                a, b = bordes_eps[k], bordes_eps[k + 1]
                lo = np.maximum(a, eps_umbral)
                masa = np.where(
                    b > lo,
                    (stats.norm.cdf(np.minimum(b, e_max)) -
                     stats.norm.cdf(np.clip(lo, -e_max, e_max))) / norm_eps,
                    0.0,
                )
                aporte = nu_m * puntos.peso * np.maximum(masa, 0.0)
                np.add.at(contrib[idx_m[im], :, k], idx_r, aporte)

    return Desagregacion(
        nivel_objetivo=float(nivel_objetivo), tasa_total=float(contrib.sum()),
        bordes_m=bordes_m, bordes_r=bordes_r, bordes_eps=bordes_eps,
        contribucion=contrib, sitio=sitio, medida=medida,
    )
