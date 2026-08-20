"""Pruebas de consistencia estilo CSEP, en version poissoniana y basada en catalogo.

Que prueba cada una
-------------------
* **N-test**: el numero total de eventos pronosticado, ignorando donde y de que
  magnitud.
* **L-test**: la verosimilitud conjunta (numero, espacio y magnitud a la vez).
* **CL-test**: la verosimilitud *condicionada* al numero observado, para que un
  fallo de tasa global no contamine el diagnostico espacial y de magnitud.
* **S-test**: solo la distribucion espacial, normalizada al numero observado.
* **M-test**: solo la distribucion de magnitudes, normalizada igual.

Interpretacion honesta de un p-valor de consistencia
----------------------------------------------------
Estas pruebas responden "¿es el dato compatible con el modelo?". **No** dicen
que el modelo sea bueno: un modelo vago y ancho pasa todas las pruebas de
consistencia y es inutil. La comparacion util es la **ganancia de informacion
frente a Poisson homogeneo** (:func:`ganancia_informacion`), que sí penaliza la
vaguedad.

Ademas, aplicar las cinco pruebas a varios modelos multiplica las
comparaciones. Registra cada prueba en
:class:`~sismolat.reproducibilidad.RegistroDePruebas` y corrige por
multiplicidad antes de declarar que un modelo "fallo".
Lo que este modulo NO puede hacer
---------------------------------
* No dice si un modelo es **util**. Las pruebas de consistencia responden si el
  dato es compatible con el modelo, y un modelo suficientemente vago pasa todas.
  Para utilidad esta :func:`ganancia_informacion`.
* No corrige por multiplicidad entre pruebas ni entre modelos. Aplicar cinco
  pruebas a tres modelos son quince comparaciones, y ese conteo lo lleva
  :class:`~sismolat.reproducibilidad.RegistroDePruebas`, no este modulo.
* No verifica que el pronostico se construyera sin ver el periodo de prueba.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import special, stats

from .pronostico import ErrorDeSupuesto, PronosticoCatalogo, PronosticoRejilla, Rejilla

__all__ = [
    "ResultadoPrueba", "n_test", "l_test", "cl_test", "s_test", "m_test",
    "n_test_catalogo", "l_test_catalogo", "s_test_catalogo", "m_test_catalogo",
    "ganancia_informacion", "log_verosimilitud_poisson",
]


@dataclass(frozen=True)
class ResultadoPrueba:
    """Resultado de una prueba de consistencia."""

    nombre: str
    estadistico_observado: float
    #: Cuantil del observado en la distribucion de referencia (0 a 1).
    cuantil: float
    #: p-valor de la prueba tal como se define para esa prueba.
    p_valor: float
    rechaza: bool
    alfa: float
    metodo: str
    distribucion_referencia: np.ndarray | None = None
    advertencias: tuple[str, ...] = ()

    def __str__(self) -> str:
        veredicto = "RECHAZA" if self.rechaza else "no rechaza"
        return (f"{self.nombre} [{self.metodo}]: obs={self.estadistico_observado:.4g} "
                f"cuantil={self.cuantil:.4f} p={self.p_valor:.4g} -> {veredicto} "
                f"(alfa={self.alfa:g})")


def _verificar_poisson(pron: PronosticoRejilla, prueba: str) -> None:
    if not pron.poisson_valido:
        raise ErrorDeSupuesto(
            f"{prueba} en su version poissoniana no es aplicable a '{pron.nombre}': el "
            "pronostico esta marcado como no poissoniano (tipicamente un modelo "
            "autoexcitado como ETAS, cuya varianza excede la media). Aplicarla produciria "
            "rechazos espurios. Usa la version basada en catalogo (*_catalogo) con un "
            "PronosticoCatalogo de simulaciones del modelo."
        )


def log_verosimilitud_poisson(tasas: np.ndarray, conteos: np.ndarray) -> float:
    """Log-verosimilitud conjunta de conteos poissonianos independientes por celda.

    Las celdas con tasa cero y conteo positivo dan verosimilitud cero
    (log = -inf), lo cual es correcto: el modelo declaro imposible algo que
    ocurrio. La funcion devuelve ``-inf`` en lugar de recortar, porque recortar
    esconde exactamente el fallo mas grave que puede tener un pronostico.
    """
    tasas = np.asarray(tasas, float)
    conteos = np.asarray(conteos, float)
    if np.any((tasas <= 0) & (conteos > 0)):
        return -np.inf
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(tasas > 0, -tasas + conteos * np.log(tasas), 0.0)
    return float(np.sum(term) - np.sum(special.gammaln(conteos + 1)))


def n_test(
    pron: PronosticoRejilla, observado: pd.DataFrame, *, alfa: float = 0.05,
    columna_mag: str = "mag",
) -> ResultadoPrueba:
    """Prueba del numero total de eventos, bajo Poisson.

    Se calculan los dos cuantiles unilaterales habituales en CSEP:
    ``delta1 = P(N >= N_obs)`` y ``delta2 = P(N <= N_obs)``. Se rechaza si
    cualquiera de los dos cae por debajo de ``alfa/2`` (prueba bilateral).
    """
    _verificar_poisson(pron, "N-test")
    n_obs = float(pron.rejilla.contar(observado, columna_mag=columna_mag).sum())
    lam = pron.total
    if lam <= 0:
        raise ValueError("el pronostico tiene tasa total nula")
    delta1 = float(stats.poisson.sf(n_obs - 1, lam))   # P(N >= n_obs)
    delta2 = float(stats.poisson.cdf(n_obs, lam))      # P(N <= n_obs)
    p = 2.0 * min(delta1, delta2)
    avisos = []
    if n_obs == 0:
        avisos.append("No se observo ningun evento en la ventana: la prueba tiene poca potencia.")
    return ResultadoPrueba(
        nombre="N-test", estadistico_observado=n_obs, cuantil=delta2,
        p_valor=min(p, 1.0), rechaza=bool(min(delta1, delta2) < alfa / 2), alfa=alfa,
        metodo="Poisson", advertencias=tuple(avisos),
    )


def _simular_conteos_poisson(tasas: np.ndarray, n_sim: int, rng) -> np.ndarray:
    return rng.poisson(tasas[None, ...], size=(n_sim,) + tasas.shape)


def l_test(
    pron: PronosticoRejilla, observado: pd.DataFrame, *, alfa: float = 0.05,
    n_sim: int = 5000, semilla: int = 0, columna_mag: str = "mag",
) -> ResultadoPrueba:
    """Prueba de verosimilitud conjunta bajo Poisson.

    Se compara la log-verosimilitud observada con la distribucion obtenida
    simulando catalogos poissonianos del propio pronostico. Es unilateral por
    la izquierda: solo se rechaza cuando el dato es *menos* verosimil de lo que
    el modelo espera de si mismo.
    """
    _verificar_poisson(pron, "L-test")
    rng = np.random.default_rng(semilla)
    conteos = pron.rejilla.contar(observado, columna_mag=columna_mag)
    ll_obs = log_verosimilitud_poisson(pron.tasas, conteos)
    sims = _simular_conteos_poisson(pron.tasas, n_sim, rng)
    ll_sim = np.array([log_verosimilitud_poisson(pron.tasas, s) for s in sims])
    gamma = float(np.mean(ll_sim <= ll_obs))
    avisos = []
    if not math.isfinite(ll_obs):
        avisos.append(
            "La log-verosimilitud observada es -infinito: hubo al menos un evento en una "
            "celda con tasa pronosticada cero. Es el fallo mas grave posible de un "
            "pronostico y ninguna prueba de consistencia lo matiza."
        )
    return ResultadoPrueba(
        nombre="L-test", estadistico_observado=ll_obs, cuantil=gamma, p_valor=gamma,
        rechaza=bool(gamma < alfa), alfa=alfa, metodo="Poisson (simulacion)",
        distribucion_referencia=ll_sim, advertencias=tuple(avisos),
    )


def cl_test(
    pron: PronosticoRejilla, observado: pd.DataFrame, *, alfa: float = 0.05,
    n_sim: int = 5000, semilla: int = 0, columna_mag: str = "mag",
) -> ResultadoPrueba:
    """L-test condicionado al numero observado.

    Normaliza el pronostico al N observado antes de evaluar. Aisla el
    diagnostico de forma (espacio y magnitud) del diagnostico de tasa, que ya
    cubre el N-test.
    """
    _verificar_poisson(pron, "CL-test")
    conteos = pron.rejilla.contar(observado, columna_mag=columna_mag)
    n_obs = int(conteos.sum())
    if n_obs == 0:
        raise ValueError("no hay eventos observados: la prueba CL no esta definida")
    tasas = pron.tasas * (n_obs / pron.total)
    return _prueba_condicionada(
        tasas, conteos, n_obs, "CL-test", alfa, n_sim, semilla,
        "Poisson condicionado a N observado (multinomial)",
    )


def _prueba_condicionada(
    tasas: np.ndarray, conteos_obs: np.ndarray, n_obs: int, nombre: str,
    alfa: float, n_sim: int, semilla: int, metodo: str,
) -> ResultadoPrueba:
    """Prueba de verosimilitud con el numero total de eventos FIJADO al observado.

    Los catalogos de referencia se generan repartiendo exactamente ``n_obs``
    eventos entre las celdas por una **multinomial** con probabilidades
    proporcionales a la tasa pronosticada, no por Poissons independientes.

    Esto no es un detalle: si se simula sin condicionar, los catalogos de
    referencia tienen total aleatorio mientras que el observado tiene
    exactamente ``n_obs``, lo que eleva sistematicamente la verosimilitud
    observada por encima de la distribucion de referencia. El efecto anula la
    potencia de la prueba -- un modelo espacialmente equivocado deja de ser
    rechazado nunca. Las pruebas condicionales (CL, S, M) solo tienen sentido
    condicionadas.
    """
    rng = np.random.default_rng(semilla)
    plano = tasas.ravel()
    total = plano.sum()
    if total <= 0:
        raise ValueError(f"{nombre}: la tasa total del pronostico es nula")
    prob = plano / total
    ll_obs = log_verosimilitud_poisson(tasas, conteos_obs)
    sims = rng.multinomial(n_obs, prob, size=n_sim)
    ll_sim = np.array([
        log_verosimilitud_poisson(tasas, s.reshape(tasas.shape)) for s in sims
    ])
    gamma = float(np.mean(ll_sim <= ll_obs))
    avisos = []
    if not math.isfinite(ll_obs):
        avisos.append(
            "Log-verosimilitud observada -infinito: hubo un evento en una celda con tasa "
            "pronosticada cero."
        )
    return ResultadoPrueba(
        nombre=nombre, estadistico_observado=ll_obs, cuantil=gamma, p_valor=gamma,
        rechaza=bool(gamma < alfa), alfa=alfa, metodo=metodo,
        distribucion_referencia=ll_sim, advertencias=tuple(avisos),
    )


def _prueba_marginal(
    pron: PronosticoRejilla, observado: pd.DataFrame, ejes: tuple[int, ...],
    nombre: str, alfa: float, n_sim: int, semilla: int, columna_mag: str,
) -> ResultadoPrueba:
    _verificar_poisson(pron, nombre)
    conteos = pron.rejilla.contar(observado, columna_mag=columna_mag)
    n_obs = int(conteos.sum())
    if n_obs == 0:
        raise ValueError(f"no hay eventos observados: la prueba {nombre} no esta definida")
    tasas_m = pron.tasas.sum(axis=ejes)
    conteos_m = conteos.sum(axis=ejes)
    tasas_m = tasas_m * (n_obs / tasas_m.sum())
    return _prueba_condicionada(
        tasas_m, conteos_m, n_obs, nombre, alfa, n_sim, semilla,
        "marginal condicionada a N observado (multinomial)",
    )


def s_test(pron: PronosticoRejilla, observado: pd.DataFrame, *, alfa: float = 0.05,
           n_sim: int = 5000, semilla: int = 0, columna_mag: str = "mag") -> ResultadoPrueba:
    """Prueba de la distribucion espacial, marginalizando la magnitud."""
    return _prueba_marginal(pron, observado, (2,), "S-test", alfa, n_sim, semilla, columna_mag)


def m_test(pron: PronosticoRejilla, observado: pd.DataFrame, *, alfa: float = 0.05,
           n_sim: int = 5000, semilla: int = 0, columna_mag: str = "mag") -> ResultadoPrueba:
    """Prueba de la distribucion de magnitudes, marginalizando el espacio."""
    return _prueba_marginal(pron, observado, (0, 1), "M-test", alfa, n_sim, semilla, columna_mag)


# ---------------------------------------------------------------------------
# Versiones basadas en catalogo, validas para modelos autoexcitados
# ---------------------------------------------------------------------------

def n_test_catalogo(
    pron: PronosticoCatalogo, observado: pd.DataFrame, *, alfa: float = 0.05,
    columna_mag: str = "mag",
) -> ResultadoPrueba:
    """N-test con distribucion de referencia empirica de los catalogos simulados.

    Es la version correcta para ETAS y cualquier modelo sobredisperso. El
    p-valor sale del cuantil empirico del N observado en los N simulados, sin
    suponer forma alguna para la distribucion.
    """
    n_sim = pron.conteos_totales()
    _, _, _, dentro = pron.rejilla.indexar(
        observado["lon"], observado["lat"], observado[columna_mag]
    )
    n_obs = float(dentro.sum())
    delta1 = float(np.mean(n_sim >= n_obs))
    delta2 = float(np.mean(n_sim <= n_obs))
    p = 2.0 * min(delta1, delta2)
    disp = pron.dispersion_relativa()
    avisos = [
        f"Dispersion relativa var(N)/media(N) = {disp:.2f} en las simulaciones. "
        f"{'Compatible con Poisson.' if abs(disp - 1) < 0.5 else 'Muy por encima de Poisson: la prueba poissoniana habria dado un rechazo espurio.'}"
    ]
    resolucion = 1.0 / pron.n_simulaciones
    if p < 5 * resolucion:
        avisos.append(
            f"El p-valor ({p:.4g}) esta cerca de la resolucion de {pron.n_simulaciones} "
            f"simulaciones ({resolucion:.4g}). Aumenta el numero de simulaciones antes de "
            "reportar un rechazo."
        )
    return ResultadoPrueba(
        nombre="N-test", estadistico_observado=n_obs, cuantil=delta2, p_valor=min(p, 1.0),
        rechaza=bool(min(delta1, delta2) < alfa / 2), alfa=alfa,
        metodo="basado en catalogo (empirico)", distribucion_referencia=n_sim,
        advertencias=tuple(avisos),
    )


def l_test_catalogo(
    pron: PronosticoCatalogo, observado: pd.DataFrame, *, alfa: float = 0.05,
    columna_mag: str = "mag", suavizado: float = 0.1,
) -> ResultadoPrueba:
    """L-test basado en catalogo.

    La tasa por celda se estima como la media de los catalogos simulados y la
    log-verosimilitud del catalogo observado se compara con la de los propios
    catalogos simulados (validacion cruzada implicita). ``suavizado`` es una
    tasa minima anadida a cada celda para evitar verosimilitudes infinitas por
    celdas vacias en el muestreo finito de simulaciones; es un [SUPUESTO]
    declarado, no un valor derivado, y su efecto debe comprobarse.
    """
    media = pron.tasa_media().tasas
    tasas = media + suavizado * media[media > 0].mean() if np.any(media > 0) else media
    conteos_obs = pron.rejilla.contar(observado, columna_mag=columna_mag)
    ll_obs = log_verosimilitud_poisson(tasas, conteos_obs)
    ll_sim = np.array([
        log_verosimilitud_poisson(tasas, pron.rejilla.contar(c, columna_mag=columna_mag))
        for c in pron.catalogos
    ])
    gamma = float(np.mean(ll_sim <= ll_obs))
    return ResultadoPrueba(
        nombre="L-test", estadistico_observado=ll_obs, cuantil=gamma, p_valor=gamma,
        rechaza=bool(gamma < alfa), alfa=alfa, metodo="basado en catalogo (empirico)",
        distribucion_referencia=ll_sim,
        advertencias=(
            f"Se aplico un suavizado de {suavizado:g} (relativo a la tasa media no nula) para "
            "evitar celdas de tasa cero por muestreo finito. Es un SUPUESTO: repite con otro "
            "valor y comprueba que la conclusion no cambia.",
        ),
    )


def ganancia_informacion(
    pron: PronosticoRejilla, referencia: PronosticoRejilla, observado: pd.DataFrame,
    *, columna_mag: str = "mag",
) -> dict[str, float]:
    """Ganancia de log-verosimilitud por evento frente a un modelo de referencia.

    .. math::
        IG = \\frac{\\ell_{modelo} - \\ell_{referencia}}{N_{obs}}

    Esta es la comparacion que **sí** distingue un modelo util de uno vago: las
    pruebas de consistencia solo dicen si el dato es compatible con el modelo, y
    un modelo suficientemente ancho siempre lo es.

    La referencia obligatoria es el Poisson homogeneo. Una ganancia negativa
    significa que el modelo es peor que suponer sismicidad uniforme.
    """
    if pron.rejilla.forma != referencia.rejilla.forma:
        raise ValueError("los dos pronosticos deben usar la misma rejilla")
    conteos = pron.rejilla.contar(observado, columna_mag=columna_mag)
    n_obs = float(conteos.sum())
    if n_obs == 0:
        raise ValueError("no hay eventos observados: la ganancia no esta definida")
    ll_m = log_verosimilitud_poisson(pron.tasas, conteos)
    ll_r = log_verosimilitud_poisson(referencia.tasas, conteos)
    ig = (ll_m - ll_r) / n_obs
    return {
        "ganancia_por_evento": float(ig),
        "factor_probabilidad_por_evento": float(math.exp(ig)) if math.isfinite(ig) else float("nan"),
        "log_verosimilitud_modelo": float(ll_m),
        "log_verosimilitud_referencia": float(ll_r),
        "n_observado": n_obs,
    }


def _prueba_marginal_catalogo(
    pron: PronosticoCatalogo, observado: pd.DataFrame, ejes: tuple[int, ...],
    nombre: str, alfa: float, semilla: int, columna_mag: str, suavizado: float,
) -> ResultadoPrueba:
    """Prueba marginal con distribucion de referencia tomada de los catalogos simulados.

    El estadistico es la **log-verosimilitud espacial (o de magnitud) media por
    evento**:

    .. math::
        T = \\frac{1}{N} \\sum_{k=1}^{N} \\log p(\\text{celda del evento } k)

    donde ``p`` es el campo de probabilidad normalizado del modelo. Al ser una
    media por evento, es **independiente del numero de eventos**, de modo que los
    catalogos simulados se pueden comparar con el observado aunque sus totales
    difieran mucho -- que es justo lo que pasa con un modelo autoexcitado, cuyos
    conteos son muy dispersos.

    Por que no se remuestrea a N fijo
    ---------------------------------
    Un diseno alternativo seria extraer ``N_obs`` eventos de cada catalogo
    simulado. No funciona aqui: con ETAS, la mayoria de las simulaciones tiene
    menos eventos que el observado y habria que descartarlas, lo que sesga la
    referencia hacia las realizaciones mas productivas. Y hacerlo **con**
    reemplazo introduce localizaciones repetidas que agrupan artificialmente la
    referencia, hunden su verosimilitud y dejan al observado siempre por encima:
    la prueba pierde toda su potencia.
    """
    rej = pron.rejilla
    media = pron.tasa_media().tasas.sum(axis=ejes)
    if media.sum() <= 0:
        raise ValueError(f"{nombre}: la tasa media simulada es nula")
    piso = suavizado * media[media > 0].mean() if np.any(media > 0) else 0.0
    prob = media + piso
    prob = prob / prob.sum()
    log_prob = np.log(prob)

    def estadistico(cat: pd.DataFrame) -> float:
        i, j, k, dentro = rej.indexar(cat["lon"], cat["lat"], cat[columna_mag])
        if not dentro.any():
            return float("nan")
        c = np.zeros(rej.forma)
        np.add.at(c, (i[dentro], j[dentro], k[dentro]), 1.0)
        cm = c.sum(axis=ejes)
        n = cm.sum()
        return float(np.sum(cm * log_prob) / n)

    t_obs = estadistico(observado)
    if not math.isfinite(t_obs):
        raise ValueError(f"{nombre}: ningun evento observado cae dentro de la rejilla")

    t_sim = np.array([estadistico(c) for c in pron.catalogos], dtype=float)
    validos = np.isfinite(t_sim)
    if int(validos.sum()) < 50:
        raise ValueError(
            f"{nombre}: solo {int(validos.sum())} catalogos simulados tienen eventos dentro "
            "de la rejilla. La distribucion de referencia no tiene resolucion util."
        )
    t_sim = t_sim[validos]

    gamma = float(np.mean(t_sim <= t_obs))
    avisos = [
        f"Piso de suavizado {suavizado:g} aplicado para evitar celdas de probabilidad cero; "
        "es un SUPUESTO, comprueba que la conclusion no cambia con otro valor.",
    ]
    n_descartados = int((~validos).sum())
    if n_descartados:
        avisos.append(
            f"{n_descartados} de {pron.n_simulaciones} catalogos simulados no tenian ningun "
            "evento dentro de la rejilla y se excluyeron de la referencia."
        )
    resolucion = 1.0 / t_sim.size
    if min(gamma, 1 - gamma) < 5 * resolucion:
        avisos.append(
            f"El cuantil ({gamma:.4g}) esta cerca de la resolucion de {t_sim.size} "
            f"simulaciones ({resolucion:.4g}). Aumenta las simulaciones antes de reportar."
        )
    return ResultadoPrueba(
        nombre=nombre, estadistico_observado=t_obs, cuantil=gamma, p_valor=gamma,
        rechaza=bool(gamma < alfa), alfa=alfa,
        metodo="basado en catalogo (log-verosimilitud media por evento)",
        distribucion_referencia=t_sim, advertencias=tuple(avisos),
    )


def s_test_catalogo(
    pron: PronosticoCatalogo, observado: pd.DataFrame, *, alfa: float = 0.05,
    semilla: int = 0, columna_mag: str = "mag", suavizado: float = 0.1,
) -> ResultadoPrueba:
    """S-test basado en catalogo: valido para modelos que producen agrupamiento."""
    return _prueba_marginal_catalogo(
        pron, observado, (2,), "S-test", alfa, semilla, columna_mag, suavizado
    )


def m_test_catalogo(
    pron: PronosticoCatalogo, observado: pd.DataFrame, *, alfa: float = 0.05,
    semilla: int = 0, columna_mag: str = "mag", suavizado: float = 0.1,
) -> ResultadoPrueba:
    """M-test basado en catalogo."""
    return _prueba_marginal_catalogo(
        pron, observado, (0, 1), "M-test", alfa, semilla, columna_mag, suavizado
    )
