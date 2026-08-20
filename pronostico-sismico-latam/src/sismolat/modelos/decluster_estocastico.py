"""Decluster estocastico: estimacion conjunta del fondo y de los parametros ETAS.

El problema que resuelve
------------------------
:func:`~sismolat.modelos.etas.ajustar_etas_espacial` supone **fondo uniforme**, y
ese supuesto domina el resultado: la sismicidad de fondo real es fuertemente
heterogenea, y la parte de su estructura espacial que el modelo no puede
atribuir al fondo se la atribuye al disparo. El efecto medido sobre catalogos
sinteticos es una subestimacion clara de ``mu`` y un sesgo de los parametros
espaciales hacia radios menores.

Este modulo estima el fondo **a la vez** que los parametros, sin suponer su
forma.

La idea
-------
Cada evento no se clasifica como "fondo" o "replica": se le asigna una
**probabilidad** de ser de fondo, que sale directamente del modelo,

.. math::
    \\varphi_j = \\frac{\\mu\\, u(x_j, y_j)}{\\lambda(t_j, x_j, y_j)}

es decir, la fraccion de la intensidad total en ese punto que aporta el fondo.
El mapa de fondo se reconstruye entonces suavizando los epicentros **ponderados
por esa probabilidad**: un evento que casi seguro es una replica apenas
contribuye al mapa de fondo, y uno aislado contribuye casi entero.

El procedimiento alterna dos pasos hasta converger:

1. Con el fondo fijo, estimar los parametros ETAS por maxima verosimilitud.
2. Con los parametros fijos, recalcular las probabilidades de fondo y rehacer el
   mapa suavizando con esos pesos.

Es un esquema de tipo EM y, como todos ellos, converge a un optimo local: el
resultado depende del punto de partida, y por eso el estado inicial queda
registrado en el resultado.

Frente al decluster clasico
---------------------------
Gardner-Knopoff, Reasenberg y Zaliapin-Ben-Zion producen una **particion dura**:
cada evento es fondo o no lo es. Aqui no hay particion: hay un peso continuo. La
diferencia importa porque la particion dura obliga a decidir en los casos
ambiguos --que son muchos-- y esa decision se propaga sin dejar rastro. Un peso
de 0.5 se propaga como 0.5.

Lo que este modulo NO puede hacer
---------------------------------
* No garantiza el optimo global. Distintos puntos de partida pueden dar fondos
  distintos; conviene repetir con varios y comparar.
* Hereda todas las limitaciones del ETAS espacial: sin efecto de borde, con las
  ventanas de truncamiento como supuesto declarado.
* No separa sismicidad inducida ni enjambres, que no encajan en el modelo de
  fondo estacionario mas disparo.
* El ancho del nucleo de suavizado es un supuesto: mas estrecho concentra el
  fondo en los epicentros observados y puede absorber replicas como fondo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..evaluacion.pronostico import Rejilla
from ..procedencia import Cantidad, Procedencia
from .etas import (
    ParametrosEspaciales, ParametrosETAS, _NOMBRES_ESPACIAL, _desempaquetar,
    _empaquetar, _mll_espacial, _pares_vecinos, intensidad_en_eventos,
)
from .suavizado import anchos_adaptativos, campo_suavizado

__all__ = ["AjusteConFondo", "estimar_fondo_estocastico", "probabilidades_de_fondo"]

_RADIO_TIERRA_KM = 6371.0


def _areas_celda_km2(rejilla: Rejilla) -> np.ndarray:
    """Area de cada celda espacial, corregida por latitud. Forma (nlon, nlat)."""
    return rejilla.areas_km2


def _densidad_en_puntos(
    campo: np.ndarray, rejilla: Rejilla, lon: np.ndarray, lat: np.ndarray,
) -> np.ndarray:
    """Evalua un campo de densidad definido en la rejilla, en puntos arbitrarios."""
    i = np.clip(np.digitize(lon, rejilla.lon_bordes) - 1, 0, campo.shape[0] - 1)
    j = np.clip(np.digitize(lat, rejilla.lat_bordes) - 1, 0, campo.shape[1] - 1)
    return campo[i, j]


@dataclass(frozen=True)
class AjusteConFondo:
    """Resultado del ajuste conjunto de fondo y parametros."""

    temporales: ParametrosETAS
    espaciales: ParametrosEspaciales
    #: Densidad de fondo normalizada sobre la rejilla, en 1/km2 (integra a 1).
    densidad_fondo: np.ndarray
    rejilla: Rejilla
    #: Probabilidad de ser evento de fondo, por evento.
    probabilidad_fondo: np.ndarray
    mu_total: Cantidad
    n_iteraciones: int
    convergio: bool
    historia: tuple[dict, ...]
    ancho_suavizado_km: float | str
    advertencias: tuple[str, ...] = ()

    @property
    def n_fondo_esperado(self) -> float:
        """Numero esperado de eventos de fondo en el catalogo."""
        return float(self.probabilidad_fondo.sum())

    @property
    def fraccion_disparada(self) -> float:
        """Fraccion del catalogo atribuida a disparo. Equivale al parametro de ramificacion."""
        n = self.probabilidad_fondo.size
        return 1.0 - self.n_fondo_esperado / n if n else float("nan")

    def tasa_fondo_por_celda(self, dias: float) -> np.ndarray:
        """Numero esperado de eventos de fondo por celda en una ventana de ``dias``."""
        return self.densidad_fondo * _areas_celda_km2(self.rejilla) * self.mu_total.valor * dias

    def __str__(self) -> str:
        estado = "" if self.convergio else "  [NO CONVERGIO]"
        t, e = self.temporales, self.espaciales
        return (f"ETAS con fondo estimado ({self.n_iteraciones} iteraciones): "
                f"mu={t.mu:.4g}/d ({self.n_fondo_esperado:.0f} eventos de fondo, "
                f"{100 * self.fraccion_disparada:.0f}% disparado) K={t.K:.4g} "
                f"alpha={t.alpha:.3g} p={t.p:.3g} d={e.d_km:.3g}km{estado}")


def probabilidades_de_fondo(
    t: np.ndarray, m: np.ndarray, lon: np.ndarray, lat: np.ndarray, m0: float,
    temporales: ParametrosETAS, espaciales: ParametrosEspaciales,
    densidad_fondo_en_eventos: np.ndarray, *,
    ventana_dias: float = 1000.0,
) -> np.ndarray:
    """Probabilidad de que cada evento sea de fondo, dado un modelo ajustado."""
    pj, pi, pdt, pr = _pares_vecinos(t, lon, lat, ventana_dias, espaciales.r_max_km)
    lam, lam_fondo = intensidad_en_eventos(
        t, m, m0, temporales.mu, densidad_fondo_en_eventos, temporales, espaciales,
        pj, pi, pdt, pr,
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        phi = np.where(lam > 0, lam_fondo / lam, 1.0)
    return np.clip(phi, 0.0, 1.0)


def estimar_fondo_estocastico(
    tiempos_dias: np.ndarray,
    magnitudes: np.ndarray,
    lon: np.ndarray,
    lat: np.ndarray,
    m0: float,
    rejilla: Rejilla,
    *,
    t_fin: float | None = None,
    t_inicio_ajuste: float | None = None,
    r_max_km: float = 200.0,
    ventana_dias: float = 800.0,
    k_vecinos: int = 10,
    ancho_min_km: float = 2.0,
    max_iteraciones: int = 12,
    tolerancia: float = 1e-3,
    inicial: dict[str, float] | None = None,
    fijos: dict[str, float] | None = None,
    iteraciones_optimizador: int = 20000,
) -> AjusteConFondo:
    """Estima conjuntamente el fondo espacial y los parametros de ETAS.

    Parametros
    ----------
    rejilla:
        Rejilla sobre la que se representa el fondo. Su extension define la
        region: los eventos fuera de ella se descartan.
    k_vecinos:
        Ancho adaptativo del nucleo de suavizado del fondo. Es un **SUPUESTO**
        que afecta al resultado: mas estrecho concentra el fondo en los
        epicentros observados y puede absorber replicas como fondo.
    tolerancia:
        Convergencia relativa de ``mu`` entre iteraciones consecutivas.
    """
    t = np.asarray(tiempos_dias, dtype=float)
    m = np.asarray(magnitudes, dtype=float)
    x = np.asarray(lon, dtype=float)
    y = np.asarray(lat, dtype=float)
    orden = np.argsort(t)
    t, m, x, y = t[orden], m[orden], x[orden], y[orden]

    dentro = (
        np.isfinite(t) & np.isfinite(m) & (m >= m0 - 1e-9)
        & (x >= rejilla.lon_bordes[0]) & (x <= rejilla.lon_bordes[-1])
        & (y >= rejilla.lat_bordes[0]) & (y <= rejilla.lat_bordes[-1])
    )
    n_fuera = int((~dentro).sum())
    t, m, x, y = t[dentro], m[dentro], x[dentro], y[dentro]
    n = t.size
    if n < 200:
        raise ValueError(
            f"solo {n} eventos dentro de la rejilla; el ajuste conjunto estima el fondo "
            "ademas de ocho parametros y necesita bastantes mas"
        )

    t0 = float(t[0])
    t_fin = float(t[-1]) if t_fin is None else float(t_fin)
    if t_inicio_ajuste is None:
        t_inicio_ajuste = t0 + 0.05 * (t_fin - t0)
    duracion = t_fin - float(t_inicio_ajuste)

    pj, pi, pdt, pr = _pares_vecinos(t, x, y, ventana_dias, r_max_km)
    if pj.size == 0:
        raise ValueError("ningun par de eventos dentro de las ventanas de truncamiento")

    areas = _areas_celda_km2(rejilla)
    area_total = float(areas.sum())
    anchos = anchos_adaptativos(x, y, k_vecinos=k_vecinos, ancho_min_km=ancho_min_km)

    # Punto de partida: fondo uniforme. Se registra porque el esquema EM converge
    # a un optimo local y el resultado depende de donde se empiece.
    densidad = np.full(areas.shape, 1.0 / area_total)
    dens_eventos = np.full(n, 1.0 / area_total)

    partida = {
        "mu": max(n / (t_fin - t0) * 0.5, 1e-4), "K": 0.02, "alpha": 1.5,
        "c": 0.01, "p": 1.15, "d_km": 5.0, "q": 1.6, "gamma": 0.5,
    }
    partida.update(inicial or {})
    fijos = dict(fijos or {})
    partida.update(fijos)

    from scipy import optimize

    historia: list[dict] = []
    convergio = False
    mu_previo = partida["mu"]
    phi = np.full(n, 0.5)

    for iteracion in range(1, max_iteraciones + 1):
        # --- paso 1: parametros con el fondo fijo -------------------------
        def objetivo(v_libres: np.ndarray, activos: list[int]) -> float:
            completo = _empaquetar(partida).copy()
            completo[activos] = v_libres
            return _mll_espacial(completo, t, m, m0, dens_eventos,
                                 float(t_inicio_ajuste), t_fin, pj, pi, pdt, pr, r_max_km)

        activos = [_NOMBRES_ESPACIAL.index(k) for k in _NOMBRES_ESPACIAL if k not in fijos]
        res = optimize.minimize(
            objetivo, _empaquetar(partida)[activos], args=(activos,),
            method="Nelder-Mead",
            options={"xatol": 1e-6, "fatol": 1e-6,
                     "maxiter": iteraciones_optimizador, "maxfev": iteraciones_optimizador},
        )
        completo = _empaquetar(partida).copy()
        completo[activos] = res.x
        partida.update(_desempaquetar(completo))
        partida.update(fijos)

        temporales = ParametrosETAS(mu=partida["mu"], K=partida["K"],
                                    alpha=partida["alpha"], c=partida["c"],
                                    p=partida["p"], m0=m0)
        espaciales = ParametrosEspaciales(d_km=partida["d_km"], q=partida["q"],
                                          gamma=partida["gamma"], r_max_km=r_max_km)

        # --- paso 2: fondo con los parametros fijos -----------------------
        lam, lam_fondo = intensidad_en_eventos(
            t, m, m0, temporales.mu, dens_eventos, temporales, espaciales,
            pj, pi, pdt, pr,
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            phi = np.clip(np.where(lam > 0, lam_fondo / lam, 1.0), 0.0, 1.0)

        # Mapa de fondo: suavizado de los epicentros ponderados por phi.
        masa = campo_suavizado(x, y, rejilla, ancho_km=anchos, pesos=phi)
        densidad_cruda = masa / areas                      # eventos de fondo por km2
        integral = float((densidad_cruda * areas).sum())
        if integral <= 0:
            raise RuntimeError(
                "el mapa de fondo salio nulo: ningun evento conserva probabilidad de "
                "fondo. Suele indicar que el ajuste se fue a un optimo degenerado."
            )
        densidad = densidad_cruda / integral                # normalizada: integra a 1
        dens_eventos = np.maximum(
            _densidad_en_puntos(densidad, rejilla, x, y), 1e-12 / area_total)

        # mu total: los eventos de fondo esperados repartidos en la ventana.
        mu_nuevo = float(phi.sum()) / duracion
        partida["mu"] = fijos.get("mu", mu_nuevo)

        cambio = abs(partida["mu"] - mu_previo) / max(mu_previo, 1e-12)
        historia.append({
            "iteracion": iteracion, "mu": partida["mu"],
            "n_fondo": float(phi.sum()), "cambio_relativo_mu": cambio,
            "log_verosimilitud": -res.fun,
            **{k: partida[k] for k in ("K", "alpha", "c", "p", "d_km", "q", "gamma")},
        })
        if cambio < tolerancia:
            convergio = True
            break
        mu_previo = partida["mu"]

    temporales = ParametrosETAS(mu=partida["mu"], K=partida["K"], alpha=partida["alpha"],
                                c=partida["c"], p=partida["p"], m0=m0)
    espaciales = ParametrosEspaciales(d_km=partida["d_km"], q=partida["q"],
                                      gamma=partida["gamma"], r_max_km=r_max_km)

    avisos: list[str] = []
    if not convergio:
        avisos.append(
            f"El esquema no convergio en {max_iteraciones} iteraciones (ultimo cambio "
            f"relativo de mu: {historia[-1]['cambio_relativo_mu']:.3g}). Aumenta "
            "max_iteraciones o revisa si el catalogo tiene suficientes eventos."
        )
    avisos.append(
        f"El ancho del nucleo de fondo es adaptativo con k={k_vecinos} [SUPUESTO]: mas "
        "estrecho concentra el fondo en los epicentros observados y puede absorber "
        "replicas como fondo. Repite con otro valor y compara."
    )
    avisos.append(
        "Esquema tipo EM: converge a un optimo LOCAL. El resultado depende del punto de "
        "partida; repite con varios y compara antes de interpretar."
    )
    if n_fuera:
        avisos.append(f"{n_fuera} eventos caian fuera de la rejilla y se descartaron.")
    frac = 1.0 - float(phi.sum()) / n
    if frac > 0.9:
        avisos.append(
            f"El {100 * frac:.0f}% del catalogo se atribuye a disparo. Con fracciones tan "
            "altas el fondo esta mal determinado y mu es poco fiable."
        )

    return AjusteConFondo(
        temporales=temporales, espaciales=espaciales, densidad_fondo=densidad,
        rejilla=rejilla, probabilidad_fondo=phi,
        mu_total=Cantidad(
            partida["mu"], "eventos/dia", Procedencia.DERIVADO,
            fuente=(f"decluster estocastico sobre n={n} eventos, "
                    f"{len(historia)} iteraciones"),
            notas="tasa TOTAL de fondo sobre la region de la rejilla",
        ),
        n_iteraciones=len(historia), convergio=convergio, historia=tuple(historia),
        ancho_suavizado_km=f"adaptativo k={k_vecinos}", advertencias=tuple(avisos),
    )
