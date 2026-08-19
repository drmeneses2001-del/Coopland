"""Generadores de catalogos sinteticos con parametros conocidos.

Existen para las pruebas de **recuperacion de parametros**: si un estimador no
recupera los valores con los que se simulo el catalogo, el estimador esta mal.
Es el unico criterio de correccion disponible cuando no se puede cotejar contra
una implementacion de referencia.

Nota sobre discretizacion
-------------------------
Un catalogo real reporta magnitudes redondeadas a un paso ``dm``. Un evento se
reporta con magnitud ``Mc`` cuando su magnitud verdadera cae en
``[Mc - dm/2, Mc + dm/2)``. Por tanto, para simular un catalogo *completo sobre
Mc*, las magnitudes verdaderas deben generarse desde ``Mc - dm/2``, no desde
``Mc``. Generarlas desde ``Mc`` produce un catalogo cuyo umbral efectivo real es
``Mc + dm/2`` y hace que el estimador de Aki-Utsu parezca sesgado cuando no lo
esta. Esta sutileza es la razon de que este generador viva en el paquete y no
suelto en los tests.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .catalogo import Catalogo

__all__ = [
    "magnitudes_gr", "catalogo_poisson_gr", "redondear_a_paso", "tiempos_omori",
]


def redondear_a_paso(m: np.ndarray, dm: float) -> np.ndarray:
    """Redondeo al multiplo de ``dm`` mas cercano, como reporta una agencia."""
    return np.round(np.asarray(m, dtype=float) / dm) * dm


def magnitudes_gr(
    n: int,
    b: float,
    mc: float,
    dm: float = 0.1,
    *,
    m_max: float | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """``n`` magnitudes Gutenberg-Richter, discretizadas y completas sobre ``mc``.

    Parametros
    ----------
    m_max:
        Si se da, la distribucion se trunca por arriba (modelo G-R truncado).
        ``None`` produce G-R sin truncar.
    """
    rng = rng or np.random.default_rng()
    beta = b * math.log(10.0)
    base = mc - dm / 2.0
    if m_max is None:
        crudas = base + rng.exponential(1.0 / beta, size=n)
    else:
        # Inversa de la exponencial truncada en [base, m_max].
        u = rng.random(n)
        rango = 1.0 - math.exp(-beta * (m_max - base))
        crudas = base - np.log1p(-u * rango) / beta
    return redondear_a_paso(crudas, dm)


def catalogo_poisson_gr(
    tasa_anual: float,
    anios: float,
    b: float,
    mc: float,
    dm: float = 0.1,
    *,
    caja: tuple[float, float, float, float] = (-106.0, -94.0, 14.0, 21.0),
    prof_km: tuple[float, float] = (5.0, 60.0),
    t_inicio: str = "2000-01-01",
    agencia: str = "SINTETICO",
    escala: str = "Mw",
    m_max: float | None = None,
    rng: np.random.Generator | None = None,
) -> Catalogo:
    """Catalogo poissoniano homogeneo en tiempo y uniforme en espacio.

    Es la linea base obligatoria de comparacion (fase 3) y el insumo de las
    pruebas de la fase 4. La caja por defecto cubre aproximadamente el margen
    de subduccion de Cocos frente a Guerrero-Oaxaca; es solo un rectangulo de
    conveniencia, no una zona sismogenica definida.
    """
    rng = rng or np.random.default_rng()
    n = int(rng.poisson(tasa_anual * anios))
    t0 = pd.Timestamp(t_inicio)
    dias = np.sort(rng.random(n) * anios * 365.25)
    lon0, lon1, lat0, lat1 = caja
    df = pd.DataFrame({
        "id_evento": [f"SINT{i:07d}" for i in range(n)],
        "tiempo": t0 + pd.to_timedelta(dias, unit="D"),
        "lon": rng.uniform(lon0, lon1, n),
        "lat": rng.uniform(lat0, lat1, n),
        "prof_km": rng.uniform(prof_km[0], prof_km[1], n),
        "mag": magnitudes_gr(n, b, mc, dm, m_max=m_max, rng=rng),
        "mag_escala": escala,
        "agencia": agencia,
    })
    return Catalogo(df, origen=f"sintetico:poisson(tasa={tasa_anual},b={b},mc={mc})")


def tiempos_omori(
    K: float,
    c: float,
    p: float,
    t0: float,
    t1: float,
    *,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Tiempos de replicas de un proceso de Poisson no homogeneo de Omori-Utsu.

    Se simula por inversion de la funcion acumulada, que es exacta (no
    aproximada por adelgazamiento), de modo que la prueba de recuperacion de
    parametros mide el estimador y no el simulador.
    """
    rng = rng or np.random.default_rng()
    if abs(p - 1.0) < 1e-10:
        def Lam(t):
            return K * np.log((t + c) / (t0 + c))

        def Lam_inv(y):
            return (t0 + c) * np.exp(y / K) - c
    else:
        q = 1.0 - p

        def Lam(t):
            return K / q * ((t + c) ** q - (t0 + c) ** q)

        def Lam_inv(y):
            return ((t0 + c) ** q + y * q / K) ** (1.0 / q) - c

    total = float(Lam(t1))
    if total <= 0:
        return np.array([])
    n = int(rng.poisson(total))
    u = np.sort(rng.random(n)) * total
    return np.asarray(Lam_inv(u), dtype=float)
