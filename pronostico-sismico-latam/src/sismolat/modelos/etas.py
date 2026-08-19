"""ETAS temporal: proceso de Hawkes autoexcitado (Ogata).

La matematica
-------------
La intensidad condicional al historial es

.. math::
    \\lambda(t \\mid H_t) = \\mu + \\sum_{t_i < t}
        \\frac{K\\, e^{\\alpha (m_i - m_0)}}{(t - t_i + c)^{p}}

El primer termino es la sismicidad de fondo (tasa constante); el segundo suma
la contribucion de cada evento anterior, con una productividad que crece
exponencialmente con la magnitud y un decaimiento de Omori-Utsu.

El **numero medio de hijos directos** de un evento de magnitud ``m`` es

.. math::
    n(m) = K e^{\\alpha(m-m_0)} \\int_0^{\\infty} (s+c)^{-p} ds
         = \\frac{K e^{\\alpha(m-m_0)} c^{1-p}}{p-1}, \\quad p > 1

y el **parametro de ramificacion** ``n`` (media sobre la distribucion de
magnitudes G-R) determina la estabilidad: con ``n >= 1`` el proceso es
supercritico y explota. El ajuste debe reportarlo siempre.

Supuestos y condiciones de validez
----------------------------------
* Catalogo **completo desde m0** en toda la ventana. ETAS es especialmente
  sensible a esto: la incompletitud tras eventos grandes hace que el modelo
  "vea" menos replicas de las que hubo y sesga ``K``, ``alpha`` y ``p``.
* Las magnitudes se suponen independientes del historial y distribuidas G-R.
  Es un supuesto fuerte y contestado.
* **No declusterizar antes de ajustar ETAS**: el modelo estima justamente la
  estructura que el decluster elimina.
* Los eventos anteriores al inicio de la ventana ejercen influencia que el
  modelo no ve (efecto de borde). Se mitiga descartando una parte inicial de la
  ventana del termino de verosimilitud (``t_inicio_ajuste``).

Lo que este modulo NO puede hacer
---------------------------------
* No es un predictor determinista: produce una **tasa** condicionada al
  historial, no un pronostico de un sismo concreto.
* Esta version es **temporal**. La version espacio-temporal se simula
  (:func:`simular_espacio_temporal`) pero su MLE espacial (parametros d, q,
  gamma) no esta implementada en esta fase; ver docs/03-pendientes.md.
* No extrapola fuera del rango de magnitudes del ajuste.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy import optimize

from ..procedencia import Cantidad, Procedencia
from .omori import integral_omori

__all__ = [
    "ParametrosETAS", "AjusteETAS", "intensidad_etas",
    "ajustar_etas", "simular_etas", "simular_espacio_temporal", "fondo_de_mezcla",
]


def fondo_de_mezcla(
    focos: "list[tuple[float, float, float, float]]",
) -> "Callable[[int, np.random.Generator], tuple[np.ndarray, np.ndarray]]":
    """Construye un muestreador de fondo como mezcla de focos gaussianos.

    Cada foco es ``(lon, lat, sigma_grados, peso)``. Sirve para simular una
    sismicidad de fondo heterogenea con la que comprobar que un modelo espacial
    encuentra la estructura que realmente existe.

    No pretende representar la tectonica de ninguna region: es un generador de
    prueba con estructura conocida, y asi debe citarse en cualquier resultado.
    """
    if not focos:
        raise ValueError("se requiere al menos un foco")
    lons = np.array([f[0] for f in focos], dtype=float)
    lats = np.array([f[1] for f in focos], dtype=float)
    sig = np.array([f[2] for f in focos], dtype=float)
    pesos = np.array([f[3] for f in focos], dtype=float)
    if np.any(sig <= 0) or np.any(pesos <= 0):
        raise ValueError("sigma y peso de cada foco deben ser positivos")
    pesos = pesos / pesos.sum()

    def muestrear(n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        k = rng.choice(len(pesos), size=n, p=pesos)
        return (rng.normal(lons[k], sig[k]), rng.normal(lats[k], sig[k]))

    return muestrear


@dataclass(frozen=True)
class ParametrosETAS:
    """Parametros del ETAS temporal. ``m0`` es la magnitud de referencia (= Mc)."""

    mu: float     # eventos/dia de fondo
    K: float      # productividad
    alpha: float  # crecimiento de productividad con la magnitud
    c: float      # dias
    p: float      # exponente de Omori
    m0: float     # magnitud de referencia

    def n_hijos(self, m: float | np.ndarray) -> np.ndarray:
        """Numero medio de hijos directos de un evento de magnitud ``m`` (t -> inf)."""
        if self.p <= 1.0:
            return np.full(np.shape(m), np.inf)
        return (self.K * np.exp(self.alpha * (np.asarray(m, float) - self.m0))
                * self.c ** (1.0 - self.p) / (self.p - 1.0))

    def ramificacion(self, b: float, m_max: float | None = None) -> float:
        """Parametro de ramificacion n: hijos esperados promediando sobre G-R.

        Con magnitudes G-R de parametro ``beta = b ln10`` sobre ``m0``:
        ``n = K c^(1-p)/(p-1) * beta/(beta-alpha)`` cuando ``alpha < beta``.
        Si ``alpha >= beta`` la integral diverge sin truncamiento y se exige
        ``m_max``. Un ``n >= 1`` significa proceso supercritico: el ajuste no es
        utilizable para pronostico.
        """
        if self.p <= 1.0:
            return float("inf")
        beta = b * math.log(10.0)
        base = self.K * self.c ** (1.0 - self.p) / (self.p - 1.0)
        if self.alpha < beta:
            if m_max is None:
                return float(base * beta / (beta - self.alpha))
            d = m_max - self.m0
            num = beta * (1.0 - math.exp(-(beta - self.alpha) * d))
            den = (beta - self.alpha) * (1.0 - math.exp(-beta * d))
            return float(base * num / den)
        if m_max is None:
            return float("inf")
        d = m_max - self.m0
        num = beta * (math.exp((self.alpha - beta) * d) - 1.0) / (self.alpha - beta)
        den = 1.0 - math.exp(-beta * d)
        return float(base * num / den)

    def a_tupla(self) -> tuple[float, ...]:
        return (self.mu, self.K, self.alpha, self.c, self.p)


def intensidad_etas(
    t_eval: np.ndarray, tiempos: np.ndarray, magnitudes: np.ndarray, par: ParametrosETAS
) -> np.ndarray:
    """Intensidad condicional evaluada en ``t_eval`` dado el historial."""
    t_eval = np.atleast_1d(np.asarray(t_eval, dtype=float))
    tiempos = np.asarray(tiempos, dtype=float)
    magnitudes = np.asarray(magnitudes, dtype=float)
    prod = par.K * np.exp(par.alpha * (magnitudes - par.m0))
    salida = np.full(t_eval.shape, par.mu, dtype=float)
    for k, t in enumerate(t_eval):
        ant = tiempos < t
        if ant.any():
            dt = t - tiempos[ant]
            salida[k] += float(np.sum(prod[ant] / np.power(dt + par.c, par.p)))
    return salida


@dataclass(frozen=True)
class AjusteETAS:
    """Resultado del ajuste de ETAS temporal por maxima verosimilitud."""

    parametros: ParametrosETAS
    cantidades: dict[str, Cantidad]
    log_verosimilitud: float
    n: int
    ventana: tuple[float, float]
    t_inicio_ajuste: float
    convergio: bool
    covarianza: np.ndarray
    advertencias: list[str] = field(default_factory=list)

    def ganancia_sobre_poisson(self, tiempos: np.ndarray, magnitudes: np.ndarray) -> float:
        """Ganancia de log-verosimilitud por evento frente a Poisson homogeneo.

        Es la comparacion obligatoria: un ETAS que no supera a Poisson
        homogeneo no aporta nada, por bien que ajuste sus propios parametros.
        """
        t0, t1 = self.ventana
        t = np.asarray(tiempos, float)
        sel = (t >= self.t_inicio_ajuste) & (t <= t1)
        n_ev = int(sel.sum())
        if n_ev == 0:
            return float("nan")
        tasa = n_ev / (t1 - self.t_inicio_ajuste)
        ll_poisson = n_ev * math.log(tasa) - tasa * (t1 - self.t_inicio_ajuste)
        return (self.log_verosimilitud - ll_poisson) / n_ev

    def __str__(self) -> str:
        p = self.parametros
        estado = "" if self.convergio else "  [NO CONVERGIO]"
        return (f"ETAS temporal (n={self.n}): mu={p.mu:.4g}/d K={p.K:.4g} "
                f"alpha={p.alpha:.3g} c={p.c:.4g} p={p.p:.3g}{estado}")


def _menos_log_verosimilitud(
    theta: np.ndarray, t: np.ndarray, m: np.ndarray, m0: float,
    t_ini: float, t_fin: float,
) -> float:
    """-log L de ETAS temporal. ``theta`` esta en escala logaritmica salvo alpha."""
    log_mu, log_K, alpha, log_c, log_p = theta
    mu, K, c = math.exp(log_mu), math.exp(log_K), math.exp(log_c)
    p = math.exp(log_p)
    if not (0.05 < p < 5.0) or not (-1.0 < alpha < 6.0) or c > 10.0:
        return 1e12
    prod = K * np.exp(alpha * (m - m0))

    # Termino de suma: solo eventos dentro de la ventana de ajuste contribuyen,
    # pero TODOS los anteriores actuan como historial.
    sel = t >= t_ini
    if not sel.any():
        return 1e12
    suma = 0.0
    idx = np.nonzero(sel)[0]
    for j in idx:
        dt = t[j] - t[:j]
        lam = mu
        if dt.size:
            lam += float(np.sum(prod[:j] / np.power(dt + c, p)))
        if lam <= 0:
            return 1e12
        suma += math.log(lam)

    # Termino integral sobre [t_ini, t_fin].
    integral = mu * (t_fin - t_ini)
    for i in range(t.size):
        if t[i] >= t_fin:
            break
        desde = max(t_ini - t[i], 0.0)
        hasta = t_fin - t[i]
        if hasta <= desde:
            continue
        integral += prod[i] * integral_omori(c, p, desde, hasta)
    ll = suma - integral
    return -ll if math.isfinite(ll) else 1e12


def ajustar_etas(
    tiempos_dias: np.ndarray,
    magnitudes: np.ndarray,
    m0: float,
    *,
    t_fin: float | None = None,
    t_inicio_ajuste: float | None = None,
    inicial: ParametrosETAS | None = None,
    b_para_ramificacion: float = 1.0,
) -> AjusteETAS:
    """Estima (mu, K, alpha, c, p) por maxima verosimilitud.

    Parametros
    ----------
    t_inicio_ajuste:
        Instante desde el que se cuenta la verosimilitud. Los eventos anteriores
        siguen actuando como historial pero no aportan al termino de suma. Sirve
        para mitigar el efecto de borde inicial. Por defecto, el 5% de la
        ventana.
    b_para_ramificacion:
        Valor de b usado solo para calcular el parametro de ramificacion en el
        diagnostico. Debe venir de :func:`~sismolat.estadistica.gutenberg_richter.b_aki_utsu`
        sobre el mismo catalogo.
    """
    t = np.asarray(tiempos_dias, dtype=float)
    m = np.asarray(magnitudes, dtype=float)
    orden = np.argsort(t)
    t, m = t[orden], m[orden]
    valido = np.isfinite(t) & np.isfinite(m) & (m >= m0 - 1e-9)
    t, m = t[valido], m[valido]
    if t.size < 50:
        raise ValueError(
            f"solo {t.size} eventos sobre m0={m0:g}; ETAS necesita al menos ~50 para que "
            "los parametros esten identificados, y en la practica bastantes mas"
        )
    t0 = float(t[0])
    t_fin = float(t[-1]) if t_fin is None else float(t_fin)
    if t_inicio_ajuste is None:
        t_inicio_ajuste = t0 + 0.05 * (t_fin - t0)

    ini = inicial or ParametrosETAS(
        mu=max(t.size / (t_fin - t0) * 0.5, 1e-4), K=0.02, alpha=1.5, c=0.01, p=1.1, m0=m0
    )
    x0 = np.array([
        math.log(ini.mu), math.log(ini.K), ini.alpha, math.log(ini.c), math.log(ini.p)
    ])
    res = optimize.minimize(
        _menos_log_verosimilitud, x0,
        args=(t, m, m0, float(t_inicio_ajuste), t_fin),
        method="Nelder-Mead",
        options={"xatol": 1e-6, "fatol": 1e-6, "maxiter": 20000, "maxfev": 20000},
    )
    log_mu, log_K, alpha, log_c, log_p = res.x
    par = ParametrosETAS(
        mu=math.exp(log_mu), K=math.exp(log_K), alpha=alpha,
        c=math.exp(log_c), p=math.exp(log_p), m0=m0,
    )

    def mll_natural(v: np.ndarray) -> float:
        mu_, K_, a_, c_, p_ = v
        if min(mu_, K_, c_, p_) <= 0:
            return 1e12
        return _menos_log_verosimilitud(
            np.array([math.log(mu_), math.log(K_), a_, math.log(c_), math.log(p_)]),
            t, m, m0, float(t_inicio_ajuste), t_fin,
        )

    from .omori import _covarianza_numerica
    cov = _covarianza_numerica(mll_natural, np.array(par.a_tupla()), paso_rel=1e-3)
    sigmas = np.sqrt(np.clip(np.diag(cov), 0, None)) if np.all(np.isfinite(cov)) \
        else np.full(5, np.nan)

    fuente = f"MLE ETAS temporal sobre n={t.size} eventos, m0={m0:g}, ventana [{t0:g},{t_fin:g}] d"
    unidades = ["eventos/dia", "adimensional", "adimensional", "dias", "adimensional"]
    nombres = ["mu", "K", "alpha", "c", "p"]
    cantidades = {
        nom: Cantidad(val, uni, Procedencia.DERIVADO, fuente=fuente,
                      incertidumbre=(float(s) if math.isfinite(s) else None))
        for nom, val, uni, s in zip(nombres, par.a_tupla(), unidades, sigmas)
    }

    avisos: list[str] = []
    if not res.success:
        avisos.append(f"El optimizador no reporto convergencia: {res.message}")
    n_ram = par.ramificacion(b_para_ramificacion)
    if not math.isfinite(n_ram) or n_ram >= 1.0:
        avisos.append(
            f"Parametro de ramificacion n = {n_ram:.3f} >= 1: el proceso ajustado es "
            "SUPERCRITICO y no es utilizable para pronostico (la tasa esperada diverge). "
            "Suele indicar incompletitud del catalogo o una ventana que contiene una sola "
            "secuencia grande."
        )
    else:
        avisos.append(
            f"Parametro de ramificacion n = {n_ram:.3f} (fraccion de eventos disparados). "
            f"Fondo estimado: {100 * (1 - n_ram):.0f}% de la sismicidad."
        )
    if par.p <= 1.0:
        avisos.append(
            f"p = {par.p:.3f} <= 1: la integral de productividad diverge y n_hijos es infinito. "
            "El ajuste no es utilizable sin truncamiento temporal explicito."
        )
    if not np.all(np.isfinite(sigmas)):
        avisos.append(
            "El hessiano no es definido positivo: las incertidumbres no son fiables. "
            "K y alpha estan fuertemente correlacionados en ETAS; considera fijar alpha."
        )
    avisos.append(
        "ETAS es muy sensible a la completitud. Si Mc varia en el tiempo dentro de la "
        "ventana (o se degrada tras los eventos grandes), estos parametros estan sesgados."
    )

    return AjusteETAS(
        parametros=par, cantidades=cantidades, log_verosimilitud=-res.fun, n=int(t.size),
        ventana=(t0, t_fin), t_inicio_ajuste=float(t_inicio_ajuste),
        convergio=bool(res.success), covarianza=cov, advertencias=avisos,
    )


def simular_etas(
    par: ParametrosETAS,
    b: float,
    t_fin: float,
    *,
    dm: float = 0.1,
    m_max: float | None = None,
    rng: np.random.Generator | None = None,
    max_generaciones: int = 100,
) -> tuple[np.ndarray, np.ndarray]:
    """Simula un catalogo ETAS temporal por proceso de ramificacion.

    El proceso de ramificacion es **exacto** (no aproximado por adelgazamiento):
    los eventos de fondo son un Poisson homogeneo y la descendencia de cada
    evento es un Poisson no homogeneo de Omori, simulado por inversion. Esto
    hace que las pruebas de recuperacion de parametros midan el estimador y no
    el simulador.

    Devuelve ``(tiempos, magnitudes)`` ordenados por tiempo.
    """
    from ..sintetico import magnitudes_gr, tiempos_omori
    rng = rng or np.random.default_rng()
    if par.p <= 1.0:
        raise ValueError("la simulacion por ramificacion requiere p > 1")

    n_fondo = int(rng.poisson(par.mu * t_fin))
    t_actual = np.sort(rng.random(n_fondo) * t_fin)
    m_actual = magnitudes_gr(n_fondo, b, par.m0, dm, m_max=m_max, rng=rng)
    todos_t, todos_m = [t_actual], [m_actual]

    for _ in range(max_generaciones):
        if t_actual.size == 0:
            break
        hijos_t, hijos_m = [], []
        prod = par.K * np.exp(par.alpha * (m_actual - par.m0))
        for ti, Ki in zip(t_actual, prod):
            restante = t_fin - ti
            if restante <= 0:
                continue
            # Poisson no homogeneo de Omori con K=Ki sobre [0, restante].
            s = tiempos_omori(Ki, par.c, par.p, 0.0, restante, rng=rng)
            if s.size:
                hijos_t.append(ti + s)
                hijos_m.append(magnitudes_gr(s.size, b, par.m0, dm, m_max=m_max, rng=rng))
        if not hijos_t:
            break
        t_actual = np.concatenate(hijos_t)
        m_actual = np.concatenate(hijos_m)
        todos_t.append(t_actual)
        todos_m.append(m_actual)
    else:
        raise RuntimeError(
            f"la simulacion no se extinguio en {max_generaciones} generaciones: el proceso "
            "es probablemente supercritico (revisa el parametro de ramificacion)"
        )

    t = np.concatenate(todos_t)
    m = np.concatenate(todos_m)
    orden = np.argsort(t)
    return t[orden], m[orden]


def simular_espacio_temporal(
    par: ParametrosETAS,
    b: float,
    t_fin: float,
    caja: tuple[float, float, float, float],
    *,
    d_km: float = 5.0,
    q: float = 1.5,
    gamma: float = 0.5,
    r_max_km: float = 200.0,
    dm: float = 0.1,
    m_max: float | None = None,
    muestrear_fondo: "Callable[[int, np.random.Generator], tuple[np.ndarray, np.ndarray]] | None" = None,
    rng: np.random.Generator | None = None,
) -> "pd.DataFrame":
    """Simula ETAS espacio-temporal. El nucleo espacial es de tipo potencia isotropo.

    .. math::
        f(r \\mid m) = \\frac{q-1}{\\pi D(m)}
            \\left(1 + \\frac{r^2}{D(m)}\\right)^{-q},
        \\quad D(m) = d^2 e^{\\gamma (m - m_0)}

    Truncamiento espacial obligatorio
    ---------------------------------
    Con ``q <= 1.5`` la distancia radial tiene **media infinita**: la cola de la
    potencia es tan pesada que una fraccion no despreciable de las replicas
    simuladas cae a miles de kilometros del padre, e incluso fuera del planeta.
    Por eso ``r_max_km`` no es un refinamiento opcional sino parte del modelo, y
    su valor es un **[SUPUESTO] declarado** que afecta al resultado: truncar mas
    corto concentra la sismicidad simulada. Debe reportarse junto a cualquier
    resultado que dependa de esta simulacion.

    **Alcance**: esta funcion simula, no ajusta. Los parametros espaciales
    ``d``, ``q`` y ``gamma`` deben darse; su estimacion por MLE no esta
    implementada en esta fase (ver docs/03-pendientes.md). La simulacion existe
    porque las pruebas CSEP basadas en catalogo (fase 4) la necesitan para
    construir la distribucion de referencia del modelo.

    Fondo espacial
    --------------
    Por defecto el fondo es **uniforme en la caja**, lo cual no es realista: la
    sismicidad de fondo real es fuertemente heterogenea (concentrada en la zona
    sismogenica interfase, en la losa intermedia, en fallas corticales
    concretas). El parametro ``muestrear_fondo`` permite pasar cualquier
    distribucion espacial; :func:`fondo_de_mezcla` construye una a partir de
    focos gaussianos.

    La eleccion importa para evaluar: con fondo uniforme **no existe estructura
    espacial persistente que aprender**, asi que cualquier modelo espacial debe
    dar ganancia nula. Con fondo heterogeneo, un buen modelo debe encontrarla.
    Ambos casos son necesarios para comprobar que el modulo de evaluacion ni
    inventa destreza ni la pasa por alto.
    """
    import pandas as pd
    from ..sintetico import magnitudes_gr, tiempos_omori
    rng = rng or np.random.default_rng()
    if par.p <= 1.0:
        raise ValueError("la simulacion por ramificacion requiere p > 1")
    if q <= 1.0:
        raise ValueError("el nucleo espacial requiere q > 1")
    if r_max_km <= 0:
        raise ValueError("r_max_km debe ser positivo")
    lon0, lon1, lat0, lat1 = caja
    km_por_grado_lat = 111.19
    lat_media = 0.5 * (lat0 + lat1)
    km_por_grado_lon = km_por_grado_lat * math.cos(math.radians(lat_media))

    n_fondo = int(rng.poisson(par.mu * t_fin))
    t_act = np.sort(rng.random(n_fondo) * t_fin)
    m_act = magnitudes_gr(n_fondo, b, par.m0, dm, m_max=m_max, rng=rng)
    if muestrear_fondo is None:
        x_act = rng.uniform(lon0, lon1, n_fondo)
        y_act = rng.uniform(lat0, lat1, n_fondo)
    else:
        x_act, y_act = muestrear_fondo(n_fondo, rng)
        x_act = np.asarray(x_act, dtype=float)
        y_act = np.asarray(y_act, dtype=float)
        if x_act.size != n_fondo or y_act.size != n_fondo:
            raise ValueError(
                f"muestrear_fondo devolvio {x_act.size} posiciones, se pidieron {n_fondo}"
            )
    gen_act = np.zeros(n_fondo, dtype=int)
    acum = [(t_act, m_act, x_act, y_act, gen_act)]

    for g in range(1, 100):
        if t_act.size == 0:
            break
        ht, hm, hx, hy = [], [], [], []
        prod = par.K * np.exp(par.alpha * (m_act - par.m0))
        for ti, mi, xi, yi, Ki in zip(t_act, m_act, x_act, y_act, prod):
            restante = t_fin - ti
            if restante <= 0:
                continue
            s = tiempos_omori(Ki, par.c, par.p, 0.0, restante, rng=rng)
            if not s.size:
                continue
            # Muestreo del nucleo espacial por inversion en r^2, truncado en
            # r_max_km: se reescala u por la masa acumulada hasta el truncamiento,
            # de modo que la distribucion resultante es la condicional a r <= r_max.
            D = d_km ** 2 * math.exp(gamma * (mi - par.m0))
            masa_max = 1.0 - (1.0 + r_max_km ** 2 / D) ** (1.0 - q)
            u = rng.random(s.size) * masa_max
            r = np.sqrt(D * ((1.0 - u) ** (1.0 / (1.0 - q)) - 1.0))
            th = rng.random(s.size) * 2 * math.pi
            ht.append(ti + s)
            hm.append(magnitudes_gr(s.size, b, par.m0, dm, m_max=m_max, rng=rng))
            hx.append(xi + r * np.cos(th) / km_por_grado_lon)
            hy.append(yi + r * np.sin(th) / km_por_grado_lat)
        if not ht:
            break
        t_act = np.concatenate(ht); m_act = np.concatenate(hm)
        x_act = np.concatenate(hx); y_act = np.concatenate(hy)
        acum.append((t_act, m_act, x_act, y_act, np.full(t_act.size, g)))

    t = np.concatenate([a[0] for a in acum])
    m = np.concatenate([a[1] for a in acum])
    x = np.concatenate([a[2] for a in acum])
    y = np.concatenate([a[3] for a in acum])
    gen = np.concatenate([a[4] for a in acum])
    orden = np.argsort(t)
    salida = pd.DataFrame({
        "t_dias": t[orden], "mag": m[orden], "lon": x[orden], "lat": y[orden],
        "generacion": gen[orden],
    })
    salida.attrs["r_max_km"] = r_max_km
    salida.attrs["advertencia"] = (
        f"Nucleo espacial truncado en r_max_km={r_max_km:g} [SUPUESTO]. Con q={q:g} la "
        "distancia radial tiene media infinita sin truncar; el valor elegido afecta a la "
        "concentracion espacial del catalogo simulado y debe reportarse."
    )
    return salida
