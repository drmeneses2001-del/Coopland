"""Ley de Omori-Utsu y ley de Bath.

La matematica
-------------
La tasa de replicas tras un evento principal decae como

.. math::
    n(t) = \\frac{K}{(t + c)^{p}}

Se ajusta por maxima verosimilitud tratando la secuencia como un proceso de
Poisson no homogeneo con esa intensidad. Para una ventana de observacion
``[T0, T1]``, la log-verosimilitud es

.. math::
    \\ell = n \\ln K - p \\sum_i \\ln(t_i + c) - K \\int_{T_0}^{T_1} (t+c)^{-p} dt

``K`` se elimina analiticamente (``K = n / I``), y la optimizacion numerica queda
en dos parametros, ``(c, p)``, que es un problema bien condicionado.

Supuestos y condiciones de validez
----------------------------------
* La secuencia es **una sola**: si dentro de la ventana ocurre una replica
  suficientemente grande con su propia secuencia, el ajuste de un solo Omori la
  mezcla y sesga ``p`` hacia abajo. Para eso esta ETAS.
* El catalogo esta **completo desde T0**. En las primeras horas tras un sismo
  grande la completitud se degrada mucho (saturacion de registros); empezar la
  ventana en T0 = 0 sesga ``c`` hacia arriba de forma sistematica. Elegir T0 es
  una decision que hay que declarar.
* ``c`` no tiene interpretacion fisica limpia: absorbe la incompletitud
  temprana. Un ``c`` "estimado" es en buena medida una medida de cuan mal se
  registro el principio de la secuencia.

Lo que este modulo NO puede hacer
---------------------------------
* No predice cuando ocurrira la proxima replica, ni su magnitud.
* No separa replicas de sismicidad de fondo. Supone que todo lo que hay en la
  ventana pertenece a la secuencia.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import optimize, stats

from ..procedencia import Cantidad, Procedencia

__all__ = ["AjusteOmori", "ajustar_omori", "integral_omori", "tasa_omori", "bath"]


def integral_omori(c: float, p: float, t0: float, t1: float) -> float:
    """:math:`\\int_{t_0}^{t_1} (t+c)^{-p} dt`, con el caso p=1 tratado aparte."""
    if abs(p - 1.0) < 1e-10:
        return math.log((t1 + c) / (t0 + c))
    return ((t1 + c) ** (1.0 - p) - (t0 + c) ** (1.0 - p)) / (1.0 - p)


def tasa_omori(t: np.ndarray, K: float, c: float, p: float) -> np.ndarray:
    """Tasa instantanea ``n(t) = K/(t+c)^p`` (eventos por unidad de tiempo)."""
    return K / np.power(np.asarray(t, dtype=float) + c, p)


@dataclass(frozen=True)
class AjusteOmori:
    """Parametros de Omori-Utsu ajustados por MLE, con incertidumbre."""

    K: Cantidad
    c: Cantidad
    p: Cantidad
    n: int
    t0: float
    t1: float
    log_verosimilitud: float
    convergio: bool
    #: Matriz de covarianza de (c, p) por inversa del hessiano observado.
    covarianza_cp: np.ndarray
    advertencias: list[str]

    def tasa(self, t: np.ndarray) -> np.ndarray:
        return tasa_omori(t, self.K.valor, self.c.valor, self.p.valor)

    def esperados(self, t_desde: float, t_hasta: float) -> float:
        """Numero esperado de eventos en ``[t_desde, t_hasta]``."""
        return self.K.valor * integral_omori(self.c.valor, self.p.valor, t_desde, t_hasta)

    def __str__(self) -> str:
        estado = "" if self.convergio else "  [NO CONVERGIO]"
        return (f"Omori-Utsu (n={self.n}, ventana [{self.t0:g}, {self.t1:g}] d): "
                f"p = {self.p}, c = {self.c}, K = {self.K}{estado}")


def ajustar_omori(
    tiempos_dias: np.ndarray,
    *,
    t0: float | None = None,
    t1: float | None = None,
    p_inicial: float = 1.1,
    c_inicial: float = 0.01,
) -> AjusteOmori:
    """Ajusta ``n(t) = K/(t+c)^p`` por maxima verosimilitud.

    Parametros
    ----------
    tiempos_dias:
        Tiempos de las replicas en dias **desde el evento principal**, todos
        estrictamente positivos.
    t0, t1:
        Ventana de observacion. Por defecto ``t0`` es el primer evento y ``t1``
        el ultimo. Elegir ``t0`` mayor que cero para saltarse la incompletitud
        temprana es legitimo y frecuente, pero **debe declararse**: cambia ``c``
        sustancialmente.
    """
    t = np.asarray(tiempos_dias, dtype=float)
    t = np.sort(t[np.isfinite(t) & (t > 0)])
    if t.size < 10:
        raise ValueError(
            f"solo {t.size} replicas con t>0; se requieren al menos 10 para un ajuste "
            "con incertidumbre interpretable"
        )
    t0 = float(t[0]) if t0 is None else float(t0)
    t1 = float(t[-1]) if t1 is None else float(t1)
    t = t[(t >= t0) & (t <= t1)]
    n = int(t.size)
    if n < 10:
        raise ValueError(f"solo {n} replicas dentro de la ventana [{t0:g}, {t1:g}]")

    def menos_log_verosimilitud(theta: np.ndarray) -> float:
        log_c, p = theta
        c = math.exp(log_c)  # c > 0 por parametrizacion
        if not (0.1 < p < 5.0):
            return 1e12
        I = integral_omori(c, p, t0, t1)
        if I <= 0 or not math.isfinite(I):
            return 1e12
        K = n / I
        ll = n * math.log(K) - p * float(np.sum(np.log(t + c))) - K * I
        return -ll if math.isfinite(ll) else 1e12

    res = optimize.minimize(
        menos_log_verosimilitud,
        x0=np.array([math.log(c_inicial), p_inicial]),
        method="Nelder-Mead",
        options={"xatol": 1e-8, "fatol": 1e-10, "maxiter": 5000},
    )
    log_c, p = res.x
    c = math.exp(log_c)
    I = integral_omori(c, p, t0, t1)
    K = n / I
    ll = -res.fun

    # Covarianza por hessiano numerico en (c, p), no en (log c, p).
    def mll_cp(v: np.ndarray) -> float:
        cc, pp = v
        if cc <= 0:
            return 1e12
        return menos_log_verosimilitud(np.array([math.log(cc), pp]))

    cov = _covarianza_numerica(mll_cp, np.array([c, p]))
    sigma_c = math.sqrt(cov[0, 0]) if cov[0, 0] > 0 else float("nan")
    sigma_p = math.sqrt(cov[1, 1]) if cov[1, 1] > 0 else float("nan")
    # sigma_K por propagacion de primer orden a traves de K = n/I(c,p).
    sigma_K = _sigma_K(n, c, p, t0, t1, cov)

    avisos: list[str] = []
    if not res.success:
        avisos.append(f"El optimizador no reporto convergencia: {res.message}")
    if p < 0.8 or p > 1.6:
        avisos.append(
            f"p = {p:.2f} queda fuera del rango habitualmente observado (aprox. 0.8-1.5). "
            "Revisa si la ventana mezcla dos secuencias o si el catalogo esta incompleto."
        )
    if t0 <= 0 or (t.size and t0 < 0.01):
        avisos.append(
            "La ventana empieza practicamente en el instante del principal. La incompletitud "
            "de las primeras horas sesga c hacia arriba: c estara midiendo, en buena parte, "
            "cuantos eventos se perdieron, no una propiedad fisica de la secuencia."
        )
    if not math.isfinite(sigma_p):
        avisos.append("El hessiano no es definido positivo: la incertidumbre de p no es fiable.")

    fuente = f"MLE Omori-Utsu sobre n={n} replicas, ventana [{t0:g}, {t1:g}] d"
    return AjusteOmori(
        K=Cantidad(K, "eventos/dia^(1-p)", Procedencia.DERIVADO, fuente=fuente,
                   incertidumbre=sigma_K,
                   notas="K depende de Mc de la secuencia; no es comparable entre catalogos "
                         "con completitud distinta"),
        c=Cantidad(c, "dias", Procedencia.DERIVADO, fuente=fuente, incertidumbre=sigma_c,
                   notas="c absorbe la incompletitud temprana; no interpretar como fisico"),
        p=Cantidad(p, "adimensional", Procedencia.DERIVADO, fuente=fuente, incertidumbre=sigma_p),
        n=n, t0=t0, t1=t1, log_verosimilitud=ll, convergio=bool(res.success),
        covarianza_cp=cov, advertencias=avisos,
    )


def _covarianza_numerica(f, x0: np.ndarray, paso_rel: float = 1e-4) -> np.ndarray:
    """Inversa del hessiano numerico de la menos-log-verosimilitud."""
    k = x0.size
    h = np.maximum(np.abs(x0) * paso_rel, 1e-8)
    H = np.zeros((k, k))
    f0 = f(x0)
    for i in range(k):
        for j in range(i, k):
            xpp, xpm, xmp, xmm = x0.copy(), x0.copy(), x0.copy(), x0.copy()
            xpp[i] += h[i]; xpp[j] += h[j]
            xpm[i] += h[i]; xpm[j] -= h[j]
            xmp[i] -= h[i]; xmp[j] += h[j]
            xmm[i] -= h[i]; xmm[j] -= h[j]
            if i == j:
                xp, xm = x0.copy(), x0.copy()
                xp[i] += h[i]; xm[i] -= h[i]
                H[i, i] = (f(xp) - 2 * f0 + f(xm)) / (h[i] ** 2)
            else:
                H[i, j] = H[j, i] = (f(xpp) - f(xpm) - f(xmp) + f(xmm)) / (4 * h[i] * h[j])
    try:
        return np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return np.full((k, k), np.nan)


def _sigma_K(n: int, c: float, p: float, t0: float, t1: float, cov: np.ndarray) -> float:
    """Propaga la incertidumbre de (c, p) a K = n/I(c, p), mas el termino de conteo."""
    if not np.all(np.isfinite(cov)):
        return float("nan")
    eps = 1e-6
    I = integral_omori(c, p, t0, t1)
    dI_dc = (integral_omori(c + eps, p, t0, t1) - integral_omori(c - eps, p, t0, t1)) / (2 * eps)
    dI_dp = (integral_omori(c, p + eps, t0, t1) - integral_omori(c, p - eps, t0, t1)) / (2 * eps)
    g = np.array([-n / I**2 * dI_dc, -n / I**2 * dI_dp])
    var_param = float(g @ cov @ g)
    var_conteo = n / I**2  # var(n) ~ n bajo Poisson
    v = var_param + var_conteo
    return math.sqrt(v) if v > 0 else float("nan")


def bath(
    mag_principal: float,
    magnitudes_replicas: np.ndarray,
    *,
    mc: float | None = None,
) -> dict:
    """Diferencia de Bath: ``dM = M_principal - M_mayor_replica``.

    **Advertencia de estatus.** La "ley" de Bath es una regularidad empirica con
    dispersion grande (del orden de +/- 0.5 unidades), no una ley al nivel de
    Gutenberg-Richter u Omori. Ademas esta sesgada: si la mayor replica cae por
    debajo de Mc no se observa, lo que **infla** dM de forma sistematica en
    secuencias pequenas o mal registradas.

    Esta funcion devuelve el valor observado junto con el diagnostico de sesgo.
    No devuelve una prediccion de la magnitud de la proxima replica, porque la
    dispersion hace que tal prediccion no sea util.
    """
    m = np.asarray(magnitudes_replicas, dtype=float)
    m = m[np.isfinite(m)]
    if m.size == 0:
        raise ValueError("no hay replicas con magnitud")
    m_max = float(m.max())
    dm = float(mag_principal) - m_max
    avisos = [
        "La diferencia de Bath tiene dispersion de aproximadamente +/- 0.5 unidades entre "
        "secuencias. Un valor unico no es informativo sobre la proxima secuencia.",
    ]
    if mc is not None and m_max <= mc + 0.3:
        avisos.append(
            f"La mayor replica observada ({m_max:.2f}) esta muy cerca de Mc ({mc:.2f}). "
            "Es probable que la verdadera mayor replica no se haya registrado, lo que sesga "
            "dM hacia arriba. Este valor no debe usarse."
        )
    if m.size < 20:
        avisos.append(
            f"Solo {m.size} replicas. Con secuencias cortas, el maximo observado subestima "
            "sistematicamente el maximo real y dM sale inflado."
        )
    return {
        "delta_m": dm,
        "mag_principal": float(mag_principal),
        "mag_mayor_replica": m_max,
        "n_replicas": int(m.size),
        "advertencias": avisos,
    }
