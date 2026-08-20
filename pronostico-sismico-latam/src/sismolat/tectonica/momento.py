"""Presupuesto de momento: de tasas de deslizamiento a tasas de sismos.

El vinculo cuantitativo entre tectonica y pronostico
----------------------------------------------------
Una falla o una interfase que acumula deslizamiento a una tasa :math:`v` sobre
un area :math:`A` genera momento sismico a razon de

.. math:: \\dot{M_0} = \\mu\\, A\\, v

Si una fraccion :math:`\\chi` de ese momento se libera en sismos (el
**acoplamiento sismico**), la tasa sismica debe cumplir

.. math:: \\chi \\dot{M_0} = \\int_{m_{min}}^{m_{max}} \\nu(m)\\, M_0(m)\\, dm

Con la distribucion de Gutenberg-Richter, eso fija la tasa total de eventos
sobre :math:`m_{min}`. Es el unico vinculo cuantitativo legitimo entre la
cinematica de placas y el pronostico sismico, y usa datos geodesicos que son
independientes del catalogo.

Por que el resultado es siempre una familia de curvas
-----------------------------------------------------
Tres parametros mal restringidos dominan el resultado:

* **m_max** es el peor de todos. La integral de momento esta dominada por los
  eventos mayores, asi que subir m_max en medio grado reparte el mismo momento
  entre muchos menos sismos y baja la tasa de los pequenos.
* **El acoplamiento sismico** :math:`\\chi` varia entre segmentos y epocas, y
  no se mide directamente: se infiere.
* **b**, que controla como se reparte el momento entre magnitudes.

Por eso :func:`tasa_desde_deslizamiento` devuelve una :class:`Cantidad` y
:func:`familia_de_tasas` explora el rango. Reportar un numero unico sugiere una
precision que no existe.

Lo que este modulo NO puede hacer
---------------------------------
* No estima el acoplamiento: hay que darselo.
* No distingue deslizamiento asismico (deslizamiento lento, reptacion) del
  deficit acumulado. Esa distincion se mete por ``chi``, que es donde vive toda
  la ignorancia sobre el tema.
* No dice **cuando**. Un presupuesto de momento equilibrado es compatible con
  muchas historias temporales distintas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..procedencia import Cantidad, Procedencia

__all__ = [
    "momento_desde_magnitud", "magnitud_desde_momento", "tasa_momento_geodesico",
    "tasa_desde_deslizamiento", "familia_de_tasas", "comparar_con_catalogo",
]


def momento_desde_magnitud(mw: np.ndarray | float) -> np.ndarray:
    """``M0 = 10^(1.5 Mw + 9.1)`` en N m. Es una definicion, no una regresion."""
    return np.power(10.0, 1.5 * np.asarray(mw, dtype=float) + 9.1)


def magnitud_desde_momento(m0_nm: np.ndarray | float) -> np.ndarray:
    """Inversa de :func:`momento_desde_magnitud`."""
    m0 = np.asarray(m0_nm, dtype=float)
    if np.any(m0 <= 0):
        raise ValueError("el momento debe ser positivo")
    return (2.0 / 3.0) * (np.log10(m0) - 9.1)


def tasa_momento_geodesico(
    area_km2: Cantidad, tasa_deslizamiento_mm_ano: Cantidad,
    mu_pa: float = 3.0e10,
) -> Cantidad:
    """``M0_punto = mu * A * v``, en N m/ano.

    ``area_km2`` es el area sismogenica acoplada, no el area total de la
    estructura: incluir la parte que desliza asismicamente sobreestima el
    momento disponible.
    """
    for nombre, c in (("area_km2", area_km2),
                      ("tasa_deslizamiento_mm_ano", tasa_deslizamiento_mm_ano)):
        if not isinstance(c, Cantidad):
            raise TypeError(f"'{nombre}' debe ser una Cantidad con procedencia declarada")
    a_m2 = area_km2.valor * 1e6
    v_m = tasa_deslizamiento_mm_ano.valor * 1e-3
    valor = mu_pa * a_m2 * v_m

    # Propagacion de primer orden con errores relativos independientes.
    rel = 0.0
    for c in (area_km2, tasa_deslizamiento_mm_ano):
        if c.incertidumbre is not None and c.valor != 0:
            rel += (c.incertidumbre / c.valor) ** 2
    sigma = valor * math.sqrt(rel) if rel > 0 else None

    return Cantidad(
        valor, "N m/ano", Procedencia.DERIVADO,
        fuente=(f"mu={mu_pa:.3g} Pa, A={area_km2.valor:.4g} km2, "
                f"v={tasa_deslizamiento_mm_ano.valor:.4g} mm/ano"),
        incertidumbre=sigma,
        verificado=area_km2.verificado and tasa_deslizamiento_mm_ano.verificado,
        notas=("El area debe ser la sismogenica ACOPLADA. Incluir la porcion que desliza "
               "asismicamente sobreestima el momento disponible para sismos."),
    )


def _momento_medio_gr(b: float, m_min: float, m_max: float, dm: float = 0.01) -> float:
    """Momento sismico medio por evento bajo G-R truncada, en N m."""
    beta = b * math.log(10.0)
    bordes = np.arange(m_min, m_max + dm / 2, dm)
    bordes = bordes[bordes < m_max - 1e-12]
    bordes = np.append(bordes, m_max)
    norm = 1.0 - math.exp(-beta * (m_max - m_min))
    acum = (1.0 - np.exp(-beta * (bordes - m_min))) / norm
    masa = np.diff(acum)
    centros = 0.5 * (bordes[:-1] + bordes[1:])
    return float(np.sum(masa * momento_desde_magnitud(centros)))


def tasa_desde_deslizamiento(
    momento_geodesico: Cantidad,
    b: Cantidad,
    m_min: float,
    m_max: Cantidad,
    acoplamiento: Cantidad,
    *,
    dm: float = 0.01,
) -> Cantidad:
    """Tasa anual de eventos con :math:`m \\ge m_{min}` compatible con el momento.

    Reparte :math:`\\chi \\dot{M_0}` segun la distribucion de Gutenberg-Richter
    truncada: la tasa total es el momento disponible dividido entre el momento
    medio por evento.
    """
    for nombre, c in (("b", b), ("m_max", m_max), ("acoplamiento", acoplamiento)):
        if not isinstance(c, Cantidad):
            raise TypeError(f"'{nombre}' debe ser una Cantidad con procedencia declarada")
    if not 0 < acoplamiento.valor <= 1:
        raise ValueError("el acoplamiento sismico debe estar en (0, 1]")
    if m_max.valor <= m_min:
        raise ValueError("m_max debe superar m_min")

    m0_medio = _momento_medio_gr(b.valor, m_min, m_max.valor, dm)
    disponible = acoplamiento.valor * momento_geodesico.valor
    tasa = disponible / m0_medio

    debiles = [c.procedencia.value for c in (m_max, acoplamiento) if c.procedencia.es_debil]
    return Cantidad(
        tasa, f"eventos/ano con m>={m_min:g}", Procedencia.DERIVADO,
        fuente=(f"presupuesto de momento: chi={acoplamiento.valor:g}, b={b.valor:g}, "
                f"m_max={m_max.valor:g}, M0_medio={m0_medio:.4g} N m"),
        verificado=all(c.verificado for c in (momento_geodesico, b, m_max, acoplamiento)),
        notas=(
            "Dominada por m_max: la integral de momento la controlan los eventos mayores. "
            + (f"Procedencias debiles en la entrada: {debiles}. " if debiles else "")
            + "Usar familia_de_tasas para ver el rango, no este numero solo."
        ),
    )


def familia_de_tasas(
    momento_geodesico: Cantidad,
    b_valores: tuple[float, ...],
    m_min: float,
    m_max_valores: tuple[float, ...],
    acoplamiento_valores: tuple[float, ...],
    *,
    dm: float = 0.01,
) -> dict:
    """Explora el rango de tasas sobre las combinaciones de b, m_max y acoplamiento.

    Es la salida recomendada. Devuelve la matriz completa mas el rango, y el
    **factor de dispersion**: cuantas veces mayor es la tasa mayor que la menor.
    Un factor de 5 o 10 no es raro, y expresa una ignorancia real que un numero
    unico ocultaria.
    """
    filas = []
    for b in b_valores:
        for mm in m_max_valores:
            for chi in acoplamiento_valores:
                m0_medio = _momento_medio_gr(b, m_min, mm, dm)
                filas.append({
                    "b": b, "m_max": mm, "acoplamiento": chi,
                    "tasa_anual": chi * momento_geodesico.valor / m0_medio,
                })
    tasas = np.array([f["tasa_anual"] for f in filas])
    return {
        "combinaciones": filas,
        "tasa_min": float(tasas.min()),
        "tasa_max": float(tasas.max()),
        "tasa_mediana": float(np.median(tasas)),
        "factor_dispersion": float(tasas.max() / tasas.min()),
        "advertencia": (
            f"La tasa varia en un factor {tasas.max() / tasas.min():.1f} sobre las "
            f"{len(filas)} combinaciones exploradas. El parametro dominante es m_max. "
            "Reportar un valor unico sugiere una precision que no existe."
        ),
    }


def comparar_con_catalogo(
    tasa_geodesica: Cantidad, tasa_catalogo: Cantidad,
) -> dict:
    """Contrasta la tasa deducida del momento con la observada en el catalogo.

    Es una de las comprobaciones mas informativas disponibles, porque las dos
    estimaciones son **independientes**: una viene de la geodesia, la otra del
    catalogo sismico.

    Un desajuste grande admite varias lecturas, y el software no puede decidir
    entre ellas: deficit de momento aun no liberado, deslizamiento asismico mayor
    del supuesto, m_max mal puesto, catalogo demasiado corto para contener los
    eventos grandes, o area acoplada mal estimada.
    """
    razon = tasa_geodesica.valor / tasa_catalogo.valor if tasa_catalogo.valor else float("inf")
    if 0.5 <= razon <= 2.0:
        lectura = "Compatibles dentro de un factor 2, que es lo mas que suele poder pedirse."
    elif razon > 2.0:
        lectura = (
            f"La geodesia implica {razon:.1f} veces mas sismos de los observados. Puede ser "
            "deficit de momento sin liberar, deslizamiento asismico mayor del supuesto, "
            "area acoplada sobreestimada, o un catalogo demasiado corto para contener los "
            "eventos grandes. El software no puede distinguirlas."
        )
    else:
        lectura = (
            f"El catalogo tiene {1 / razon:.1f} veces mas sismos de los que el momento "
            "geodesico permite. Revisa el area acoplada, la tasa de deslizamiento, o si el "
            "catalogo incluye eventos de otras fuentes."
        )
    return {"razon_geodesica_catalogo": razon, "interpretacion": lectura,
            "tasa_geodesica": tasa_geodesica.valor,
            "tasa_catalogo": tasa_catalogo.valor}
