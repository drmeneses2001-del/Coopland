"""Ley de Gutenberg-Richter: estimacion de b por maxima verosimilitud.

La matematica
-------------
Sobre el umbral de completitud Mc, la distribucion de magnitudes se modela
como exponencial truncada por la izquierda:

    f(M) = beta * exp(-beta * (M - Mc)),   M >= Mc,   beta = b * ln(10)

de donde ``log10 N(>=M) = a - b*M``. El estimador de maxima verosimilitud del
parametro de una exponencial es el inverso de la media de los excesos, lo que
da el estimador de Aki-Utsu. Con magnitudes discretizadas en pasos de dM, el
umbral efectivo es ``Mc - dM/2`` (correccion por binning de Utsu).

Supuestos y condiciones de validez
----------------------------------
* Las magnitudes estan **completas** sobre Mc. Un Mc mal estimado sesga b mucho
  mas que cualquier otra fuente de error.
* Las magnitudes estan en **una sola escala**. Mezclar escalas invalida el
  estimador: cada escala satura a un nivel distinto y la mezcla curva la FMD.
* Los eventos son independientes *para el calculo del error estandar*. En un
  catalogo con replicas, sigma_b esta subestimado.
* No hay truncamiento superior. Si la region tiene un Mmax fisico cercano al
  rango observado, el estimador sin truncar sesga b hacia arriba.

Lo que este modulo NO puede hacer
---------------------------------
* No decide Mc: eso es :mod:`sismolat.estadistica.mc`.
* No distingue un cambio real de b de un artefacto por Mc variable en el
  espacio o el tiempo. Un mapa de b sobre Mc constante produce estructura
  espacial falsa (ver docs/02-supuestos.md).
* No prueba que la distribucion sea exponencial. Para eso, comparar contra el
  modelo de sismo caracteristico (fuera del alcance de esta fase).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..procedencia import Cantidad, Procedencia

__all__ = [
    "AjusteGR", "ajustar", "b_aki_utsu", "a_valor", "fmd",
    "n_acumulada_esperada", "prueba_utsu",
]

_LOG10E = math.log10(math.e)


@dataclass(frozen=True)
class AjusteGR:
    """Resultado de un ajuste de Gutenberg-Richter."""

    b: Cantidad
    a: Cantidad
    mc: float
    dm: float
    n: int
    #: Magnitud maxima observada, util para juzgar el rango de validez.
    mag_max: float

    def log_n_acumulada(self, m: np.ndarray | float) -> np.ndarray:
        """log10 N(>=M) predicho por el ajuste."""
        return self.a.valor - self.b.valor * np.asarray(m, dtype=float)

    def __str__(self) -> str:
        return (
            f"GR sobre Mc={self.mc:.2f} (dM={self.dm:g}, n={self.n}): "
            f"b = {self.b}, a = {self.a}"
        )


def fmd(magnitudes: np.ndarray, dm: float = 0.1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Distribucion frecuencia-magnitud.

    Devuelve ``(centros, incremental, acumulada)`` donde ``acumulada[i]`` es el
    numero de eventos con magnitud >= ``centros[i]``.
    """
    m = np.asarray(magnitudes, dtype=float)
    m = m[np.isfinite(m)]
    if m.size == 0:
        return np.array([]), np.array([]), np.array([])
    # Rejilla anclada en multiplos de dm para que sea estable entre subconjuntos.
    lo = math.floor(m.min() / dm) * dm
    hi = math.ceil(m.max() / dm) * dm
    centros = np.round(np.arange(lo, hi + dm / 2, dm), 10)
    bordes = np.append(centros - dm / 2, centros[-1] + dm / 2)
    incremental, _ = np.histogram(m, bins=bordes)
    acumulada = np.cumsum(incremental[::-1])[::-1]
    return centros, incremental.astype(float), acumulada.astype(float)


def b_aki_utsu(
    magnitudes: np.ndarray,
    mc: float,
    dm: float = 0.1,
    *,
    n_minimo: int = 50,
) -> Cantidad:
    """Estimador de maxima verosimilitud de b (Aki-Utsu) con error de Shi-Bolt.

    .. math::
        \\hat b = \\frac{\\log_{10} e}{\\bar M - (M_c - \\Delta M/2)}

    El error estandar sigue Shi y Bolt (1982), que propaga la varianza muestral
    de las magnitudes. **Advertencia**: ese error asume eventos independientes;
    en un catalogo con secuencias de replicas subestima la incertidumbre real.

    Parametros
    ----------
    n_minimo:
        Numero minimo de eventos sobre Mc. Por debajo, el estimador es
        inestable y la funcion lanza ``ValueError`` en lugar de devolver un
        numero que parezca informativo.

    Referencias (no verificadas contra el original en esta sesion; ver
    docs/01-fuentes-verificadas.md): Aki (1965); Utsu (1965); Shi y Bolt (1982).
    El estimador se valida aqui por **recuperacion de parametros** sobre
    catalogos sinteticos, no por la cita.
    """
    m = np.asarray(magnitudes, dtype=float)
    m = m[np.isfinite(m)]
    # Tolerancia para no perder eventos exactamente en Mc por error de redondeo.
    sel = m >= (mc - dm / 100.0)
    m = m[sel]
    n = m.size
    if n < n_minimo:
        raise ValueError(
            f"solo {n} eventos sobre Mc={mc:g}; se requieren al menos {n_minimo}. "
            "Baja Mc, amplia la region o el periodo, o acepta que no hay datos "
            "suficientes para estimar b aqui."
        )
    media = float(m.mean())
    denom = media - (mc - dm / 2.0)
    if denom <= 0:
        raise ValueError(
            f"la magnitud media ({media:.3f}) no supera el umbral efectivo "
            f"({mc - dm / 2.0:.3f}); revisa Mc y dM"
        )
    b = _LOG10E / denom
    # Shi y Bolt (1982): sigma_b = 2.30 * b^2 * sqrt( sum((Mi - Mbar)^2) / (n(n-1)) )
    varianza = float(np.sum((m - media) ** 2)) / (n * (n - 1))
    sigma = 2.30 * b * b * math.sqrt(varianza)
    return Cantidad(
        valor=b,
        unidad="adimensional",
        procedencia=Procedencia.DERIVADO,
        fuente=f"MLE Aki-Utsu sobre n={n} eventos con M>=Mc={mc:g}, dM={dm:g}",
        incertidumbre=sigma,
        notas=(
            "sigma por Shi-Bolt (1982) asume eventos independientes; con replicas "
            "en el catalogo esta subestimado"
        ),
    )


def a_valor(magnitudes: np.ndarray, b: Cantidad, mc: float, dm: float = 0.1) -> Cantidad:
    """Valor a de G-R anclado en Mc: ``a = log10(N(>=Mc)) + b*Mc``."""
    m = np.asarray(magnitudes, dtype=float)
    n = int(np.sum(m >= (mc - dm / 100.0)))
    if n == 0:
        raise ValueError(f"no hay eventos sobre Mc={mc:g}")
    a = math.log10(n) + b.valor * mc
    # Propagacion: var(a) = (1/(N ln10))^2 var(N) + Mc^2 var(b), con var(N) ~ N (Poisson).
    var_n = (1.0 / (n * math.log(10))) ** 2 * n
    var_b = (mc * (b.incertidumbre or 0.0)) ** 2
    return b.derivar(
        a,
        unidad="log10(eventos por periodo del catalogo)",
        fuente=f"anclado en N(>=Mc)={n}, Mc={mc:g}",
        incertidumbre=math.sqrt(var_n + var_b),
        notas=(
            "a depende de la duracion del catalogo; para tasas anuales, resta "
            "log10(duracion en anios)"
        ),
    )


def ajustar(magnitudes: np.ndarray, mc: float, dm: float = 0.1, **kw) -> AjusteGR:
    """Ajuste completo de G-R sobre un umbral Mc dado."""
    m = np.asarray(magnitudes, dtype=float)
    m = m[np.isfinite(m)]
    b = b_aki_utsu(m, mc, dm, **kw)
    a = a_valor(m, b, mc, dm)
    sobre = m[m >= (mc - dm / 100.0)]
    return AjusteGR(b=b, a=a, mc=mc, dm=dm, n=int(sobre.size), mag_max=float(sobre.max()))


def n_acumulada_esperada(a: float, b: float, magnitudes: np.ndarray) -> np.ndarray:
    """N(>=M) esperado bajo G-R con parametros (a, b)."""
    return np.power(10.0, a - b * np.asarray(magnitudes, dtype=float))


def prueba_utsu(a1: AjusteGR, a2: AjusteGR) -> dict[str, float]:
    """Compara dos valores de b mediante el estadistico de Utsu.

    Devuelve la probabilidad aproximada de que ambas muestras provengan de la
    misma poblacion. **Es una prueba aproximada**: usarla repetidamente sobre
    muchas particiones sin corregir por multiplicidad produce diferencias
    "significativas" por azar (ver :class:`RegistroDePruebas`).

    Referencia: Utsu (1966), no verificada en esta sesion.
    """
    n1, n2 = a1.n, a2.n
    b1, b2 = a1.b.valor, a2.b.valor
    # dA = -2 ln L + 2 ln(...) segun Utsu; forma practica ampliamente usada:
    dA = -2.0 * (n1 + n2) * math.log(n1 + n2)
    dA += 2.0 * n1 * math.log(n1 + n2 * b1 / b2)
    dA += 2.0 * n2 * math.log(n1 * b2 / b1 + n2)
    dA -= 2.0
    p = math.exp(-dA / 2.0 - 2.0)
    return {"dA": dA, "p_aproximada": min(max(p, 0.0), 1.0), "b1": b1, "b2": b2}
