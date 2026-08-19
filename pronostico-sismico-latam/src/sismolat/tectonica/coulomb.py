"""Transferencia de esfuerzo de Coulomb entre fallas.

La matematica
-------------
El cambio de esfuerzo de Coulomb sobre un plano receptor es

.. math:: \\Delta CFS = \\Delta\\tau + \\mu' \\, \\Delta\\sigma_n

donde :math:`\\Delta\\tau` es el cambio de esfuerzo de cizalla proyectado en la
direccion de deslizamiento del receptor, :math:`\\Delta\\sigma_n` el cambio de
esfuerzo normal (positivo cuando la falla se **desconfina**) y :math:`\\mu'` el
coeficiente de friccion aparente, que engloba la friccion y el efecto de la
presion de poro.

Valores positivos se interpretan como acercamiento a la ruptura; negativos, como
alejamiento. Esa interpretacion supone que la falla receptora ya estaba proxima
a fallar, cosa que no se sabe.

Por que la salida por defecto es un conjunto de mapas
-----------------------------------------------------
Un mapa unico de lobulos rojos y azules se lee como un hecho, y no lo es. El
resultado depende criticamente de tres cosas que no se conocen bien:

1. **La orientacion del plano receptor.** Cambiarla cambia el signo de
   :math:`\\Delta CFS` en amplias zonas del mapa.
2. **El coeficiente de friccion aparente**, mal restringido y que suele
   suponerse entre 0.0 y 0.8.
3. **El modelo de deslizamiento de la fuente**, que es a su vez una inversion
   con incertidumbre grande y rara vez publicada.

Por eso :func:`barrido_de_sensibilidad` calcula el resultado sobre el rango de
receptores y fricciones plausibles, y :func:`fraccion_con_signo_estable` dice en
que fraccion del dominio el signo **no** depende de esas elecciones. Solo esa
fraccion es defendible.

Ademas: disparo estatico frente a dinamico
------------------------------------------
Este modulo calcula transferencia **estatica**: el cambio permanente de esfuerzo
tras la ruptura. El disparo **dinamico** —por el paso de las ondas sismicas— es
un mecanismo distinto, actua a distancias mucho mayores, es transitorio y no se
modela aqui. Atribuir a transferencia estatica un disparo a cientos de
kilometros es un error de mecanismo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .elastico import (
    MedioElastico, PlanoDeFalla, esfuerzo_falla_finita, _versores,
)

__all__ = [
    "cambio_de_coulomb", "ReceptorCoulomb", "barrido_de_sensibilidad",
    "fraccion_con_signo_estable", "FRICCION_APARENTE_TIPICA",
]

#: Rango de friccion aparente que se suele explorar. Es un SUPUESTO declarado.
FRICCION_APARENTE_TIPICA = (0.0, 0.2, 0.4, 0.6, 0.8)


@dataclass(frozen=True)
class ReceptorCoulomb:
    """Orientacion del plano receptor sobre el que se evalua el cambio."""

    strike_deg: float
    dip_deg: float
    rake_deg: float

    @property
    def versores(self) -> tuple[np.ndarray, np.ndarray]:
        return _versores(self.strike_deg, self.dip_deg, self.rake_deg)


def _mascara_campo_cercano(
    puntos_km: np.ndarray, fuente: PlanoDeFalla, n_largo: int, n_ancho: int,
    factor: float = 2.0,
) -> np.ndarray:
    """Puntos demasiado proximos a la falla para que la suma de parches converja.

    Al representar la falla como suma de fuentes puntuales, el campo diverge al
    acercarse a cada parche. La regla practica es exigir una separacion de al
    menos ``factor`` veces el tamano de parche. Los puntos que no la cumplen se
    marcan como no fiables: **dejarlos en el mapa produce valores enormes y sin
    significado que dominan la escala de color y hacen ilegible el resto**.
    """
    p = np.atleast_2d(np.asarray(puntos_km, dtype=float))
    lado = max(fuente.largo_km / n_largo, fuente.ancho_km / n_ancho)
    n = fuente.normal
    centro = np.asarray(fuente.centro_km, dtype=float)
    rel = p - centro
    # Distancia al plano y proyeccion sobre el, para saber si cae "dentro" del rectangulo.
    dist_plano = np.abs(rel @ n)
    dist_centro = np.linalg.norm(rel, axis=1)
    semidiagonal = 0.5 * math.hypot(fuente.largo_km, fuente.ancho_km)
    cerca_del_plano = dist_plano < factor * lado
    dentro_del_contorno = dist_centro < semidiagonal + factor * lado
    return cerca_del_plano & dentro_del_contorno


def cambio_de_coulomb(
    puntos_km: np.ndarray,
    fuente: PlanoDeFalla,
    receptor: ReceptorCoulomb,
    medio: MedioElastico,
    *,
    friccion_aparente: float = 0.4,
    n_largo: int = 10,
    n_ancho: int = 10,
    enmascarar_campo_cercano: bool = True,
) -> dict[str, np.ndarray]:
    """Cambio de Coulomb en cada punto, en Pa.

    Devuelve ``delta_cfs``, ``delta_tau`` y ``delta_sigma_n``, todos en Pa.
    Para leerlos en bar, dividir por 1e5: la literatura suele usar bares y el
    umbral que se cita como potencialmente significativo es del orden de 0.1 bar
    (1e4 Pa), aunque ese umbral es una **CONVENCION** discutida, no un valor
    medido.
    """
    if not 0.0 <= friccion_aparente <= 1.0:
        raise ValueError("la friccion aparente debe estar en [0, 1]")
    sigma = esfuerzo_falla_finita(puntos_km, fuente, medio,
                                  n_largo=n_largo, n_ancho=n_ancho)
    n, d = receptor.versores
    traccion = np.einsum("nij,j->ni", sigma, n)
    delta_sigma_n = traccion @ n            # positivo = desconfinamiento
    delta_tau = traccion @ d                # cizalla en la direccion de deslizamiento
    cfs = delta_tau + friccion_aparente * delta_sigma_n

    no_fiable = _mascara_campo_cercano(puntos_km, fuente, n_largo, n_ancho)
    if enmascarar_campo_cercano and no_fiable.any():
        cfs = np.where(no_fiable, np.nan, cfs)
        delta_tau = np.where(no_fiable, np.nan, delta_tau)
        delta_sigma_n = np.where(no_fiable, np.nan, delta_sigma_n)

    return {
        "delta_cfs": cfs,
        "delta_tau": delta_tau,
        "delta_sigma_n": delta_sigma_n,
        "friccion_aparente": friccion_aparente,
        "no_fiable": no_fiable,
        "n_enmascarados": int(no_fiable.sum()),
    }


def barrido_de_sensibilidad(
    puntos_km: np.ndarray,
    fuente: PlanoDeFalla,
    receptores: list[ReceptorCoulomb],
    medio: MedioElastico,
    *,
    fricciones: tuple[float, ...] = FRICCION_APARENTE_TIPICA,
    n_largo: int = 10,
    n_ancho: int = 10,
) -> dict:
    """Calcula ``delta_cfs`` sobre todas las combinaciones receptor x friccion.

    Es la salida por defecto recomendada: un mapa unico oculta que el resultado
    depende de elecciones que nadie conoce bien.
    """
    if not receptores:
        raise ValueError("se requiere al menos un receptor")
    filas = []
    etiquetas = []
    for r in receptores:
        for f in fricciones:
            filas.append(cambio_de_coulomb(puntos_km, fuente, r, medio,
                                           friccion_aparente=f,
                                           n_largo=n_largo, n_ancho=n_ancho)["delta_cfs"])
            etiquetas.append(
                f"strike={r.strike_deg:g} dip={r.dip_deg:g} rake={r.rake_deg:g} mu'={f:g}"
            )
    matriz = np.array(filas)
    return {
        "delta_cfs": matriz,            # (n_combinaciones, n_puntos)
        "etiquetas": tuple(etiquetas),
        "mediana": np.median(matriz, axis=0),
        "minimo": matriz.min(axis=0),
        "maximo": matriz.max(axis=0),
        "advertencia": (
            f"{matriz.shape[0]} combinaciones de receptor y friccion. Presentar una sola "
            "como si fuera el resultado seria enganoso: usa fraccion_con_signo_estable "
            "para saber en que parte del dominio la conclusion no depende de esas elecciones."
        ),
    }


def fraccion_con_signo_estable(barrido: dict, *, umbral_pa: float = 1e4) -> dict:
    """Que fraccion del dominio tiene el mismo signo en todas las combinaciones.

    Solo en esos puntos la conclusion "aqui aumento el esfuerzo" (o disminuyo) es
    independiente de la eleccion de receptor y friccion. En el resto, el mapa
    dice mas sobre las suposiciones que sobre la Tierra.

    ``umbral_pa`` descarta los puntos donde el cambio es despreciable en todas
    las combinaciones; por defecto 1e4 Pa (0.1 bar), el orden de magnitud que la
    literatura suele citar como potencialmente relevante. Es una CONVENCION
    discutida, no un valor medido.
    """
    m = barrido["delta_cfs"]
    valido = np.all(np.isfinite(m), axis=0)
    # Las columnas enmascaradas por campo cercano se excluyen antes de reducir,
    # en vez de reducir sobre NaN y filtrar despues.
    seguro = np.where(valido[None, :], m, 0.0)
    relevante = (np.abs(seguro).max(axis=0) >= umbral_pa) & valido
    todos_positivos = np.all(seguro > 0, axis=0) & valido
    todos_negativos = np.all(seguro < 0, axis=0) & valido
    estable = (todos_positivos | todos_negativos) & relevante
    n = int(valido.sum())
    if n == 0:
        raise ValueError(
            "todos los puntos quedaron enmascarados por campo cercano: alejalos de la "
            "falla o afina la discretizacion (n_largo, n_ancho)"
        )
    return {
        "fraccion_estable": float(estable.sum() / n),
        "fraccion_relevante": float(relevante.sum() / n),
        "fraccion_positiva_estable": float((todos_positivos & relevante).sum() / n),
        "fraccion_negativa_estable": float((todos_negativos & relevante).sum() / n),
        "mascara_estable": estable,
        "umbral_pa": umbral_pa,
        "interpretacion": (
            f"En el {100 * estable.sum() / n:.0f}% del dominio el signo del cambio de "
            "Coulomb no depende de la eleccion de receptor ni de friccion. En el resto, "
            "el mapa refleja las suposiciones tanto como la fisica."
        ),
    }
