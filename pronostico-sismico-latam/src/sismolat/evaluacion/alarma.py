"""Diagrama de Molchan, curvas ROC y Brier score con diagrama de confiabilidad.

Advertencia de encuadre (importante)
------------------------------------
El diagrama de Molchan es un instrumento para evaluar **estrategias de alarma**:
su eje horizontal es la fraccion de espacio-tiempo declarada en alarma. Esta
biblioteca **no emite alarmas**, y usar Molchan aqui evalua unicamente el
*poder discriminante* de un pronostico -- su capacidad de concentrar la tasa
donde ocurren los eventos. No debe leerse como una propuesta de alarmas
operativas, ni compararse con sistemas de alerta temprana (SASMEX, SNAM/CSN,
ShakeAlert), que actuan sobre ondas P ya generadas y no son pronostico.

La medida de referencia no es opcional
--------------------------------------
Un diagrama de Molchan **no es interpretable sin declarar la medida de
referencia** que define el eje ``tau``. "El 10% del espacio" significa cosas
distintas segun se mida por area, por tasa de fondo o por poblacion expuesta.
:func:`molchan` exige la medida explicitamente y la deja registrada en el
resultado. Comparar dos diagramas construidos con medidas distintas no
significa nada.

Definicion del evento objetivo
------------------------------
El Brier score y el diagrama de confiabilidad requieren un evento binario. La
definicion (magnitud umbral, tamano de celda, ventana temporal) **cambia el
resultado** y debe fijarse antes de mirar los datos. :class:`EventoObjetivo`
la hace explicita y la arrastra a todos los resultados.
Lo que este modulo NO puede hacer
---------------------------------
* No propone alarmas ni umbrales de accion. Mide poder discriminante; convertir
  eso en una decision operativa exige un analisis de costes y consecuencias que
  esta fuera del alcance de esta biblioteca y, sobre todo, fuera del de un
  calculo estadistico.
* No pondera las consecuencias. Un fallo y una falsa alarma cuentan igual en
  estas curvas, y en la realidad no cuestan lo mismo.
* No corrige por el hecho de que el conjunto de alarma se haya elegido mirando
  los mismos datos con los que se evalua.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

__all__ = [
    "EventoObjetivo", "ResultadoMolchan", "ResultadoROC", "ResultadoBrier",
    "molchan", "roc", "brier", "diagrama_confiabilidad",
]


@dataclass(frozen=True)
class EventoObjetivo:
    """Definicion explicita del evento binario que se pronostica.

    Sin esta definicion, ni el Brier score ni las curvas ROC/Molchan tienen
    significado. Se arrastra a todos los resultados para que no pueda perderse
    por el camino.
    """

    magnitud_umbral: float
    ventana_dias: float
    lado_celda_grados: float
    region: str
    descripcion: str = ""

    def __str__(self) -> str:
        return (f"al menos un evento M>={self.magnitud_umbral:g} en una celda de "
                f"{self.lado_celda_grados:g} grados durante {self.ventana_dias:g} dias "
                f"({self.region})")


def _cortes_por_empate(valores_ordenados: np.ndarray) -> np.ndarray:
    """Indices (1-based, fin de bloque) donde el valor ordenado cambia.

    Las celdas con **la misma tasa pronosticada** no pueden ordenarse entre si:
    el pronostico no las distingue. Si se las desempata por indice de arreglo,
    la curva resultante atraviesa el bloque en zigzag y produce destreza
    aparente que el modelo no tiene -- un pronostico uniforme llega a dar
    AUC != 0.5. Agrupando los empates, la curva cruza cada bloque en linea
    recta, que es el comportamiento correcto.
    """
    n = valores_ordenados.size
    if n == 0:
        return np.array([], dtype=int)
    cambia = np.nonzero(np.diff(valores_ordenados) != 0)[0] + 1
    return np.concatenate((cambia, [n]))


@dataclass(frozen=True)
class ResultadoMolchan:
    """Trayectoria de Molchan: tasa de fallos frente a fraccion en alarma."""

    tau: np.ndarray          # fraccion de la medida de referencia en alarma
    nu: np.ndarray           # tasa de fallos (eventos no cubiertos)
    area_bajo_curva: float
    #: 1 - 2*area. Vale 0 para una estrategia aleatoria y 1 para una perfecta.
    ganancia_area: float
    medida_referencia: str
    n_eventos: int
    evento: EventoObjetivo | None
    advertencias: tuple[str, ...] = ()

    def __str__(self) -> str:
        return (f"Molchan (referencia: {self.medida_referencia}, n={self.n_eventos}): "
                f"ASS = {self.ganancia_area:.3f} (0 = azar, 1 = perfecto)")


def molchan(
    tasas_espaciales: np.ndarray,
    conteos_observados: np.ndarray,
    *,
    medida_referencia: Literal["area", "tasa_fondo", "celdas"] = "area",
    areas_celda: np.ndarray | None = None,
    tasa_fondo: np.ndarray | None = None,
    evento: EventoObjetivo | None = None,
) -> ResultadoMolchan:
    """Construye la trayectoria de Molchan de un campo de tasas.

    Las celdas se ordenan por tasa pronosticada decreciente. Para cada umbral,
    el conjunto de alarma es el de las celdas por encima; ``tau`` es la
    fraccion de la medida de referencia que ocupan y ``nu`` la fraccion de
    eventos observados que quedan fuera.

    Parametros
    ----------
    medida_referencia:
        ``"area"`` pondera cada celda por su area real en km2 (requiere
        ``areas_celda``); ``"tasa_fondo"`` la pondera por la tasa de un modelo
        de referencia (requiere ``tasa_fondo``); ``"celdas"`` cuenta celdas sin
        ponderar, que solo es valido si todas tienen la misma area.
    """
    tasas = np.asarray(tasas_espaciales, float).ravel()
    obs = np.asarray(conteos_observados, float).ravel()
    if tasas.shape != obs.shape:
        raise ValueError("tasas y conteos deben tener la misma forma")
    n_ev = float(obs.sum())
    if n_ev == 0:
        raise ValueError("no hay eventos observados: la trayectoria no esta definida")

    avisos: list[str] = []
    if medida_referencia == "area":
        if areas_celda is None:
            raise ValueError(
                "medida_referencia='area' requiere areas_celda (usa Rejilla.areas_km2). "
                "Sin la medida declarada, el eje tau no es interpretable."
            )
        peso = np.asarray(areas_celda, float).ravel()
    elif medida_referencia == "tasa_fondo":
        if tasa_fondo is None:
            raise ValueError("medida_referencia='tasa_fondo' requiere tasa_fondo")
        peso = np.asarray(tasa_fondo, float).ravel()
    elif medida_referencia == "celdas":
        peso = np.ones_like(tasas)
        avisos.append(
            "Medida de referencia por conteo de celdas: solo es valida si todas las celdas "
            "tienen la misma area. En una rejilla regular en grados no la tienen."
        )
    else:
        raise ValueError(f"medida_referencia desconocida: {medida_referencia!r}")

    if peso.shape != tasas.shape:
        raise ValueError("la medida de referencia debe tener la misma forma que las tasas")
    peso_total = float(peso.sum())

    orden = np.argsort(-tasas, kind="stable")
    cortes = _cortes_por_empate(tasas[orden])
    peso_acum = (np.cumsum(peso[orden]) / peso_total)[cortes - 1]
    ev_acum = (np.cumsum(obs[orden]) / n_ev)[cortes - 1]
    # Se antepone el origen: alarma vacia -> tau=0, nu=1. Los vertices de la
    # trayectoria son solo los finales de bloque de tasa constante.
    tau = np.concatenate(([0.0], peso_acum))
    nu = np.concatenate(([1.0], 1.0 - ev_acum))

    area = float(np.trapezoid(nu, tau)) if hasattr(np, "trapezoid") else float(np.trapz(nu, tau))
    ass = 1.0 - 2.0 * area

    if n_ev < 20:
        avisos.append(
            f"Solo {int(n_ev)} eventos objetivo. La trayectoria de Molchan es muy ruidosa por "
            "debajo de ~20 eventos y la ganancia de area no es distinguible del azar. "
            "Reporta un intervalo por remuestreo antes de concluir nada."
        )
    if np.any(tasas < 0):
        avisos.append("Hay tasas negativas en el campo pronosticado.")
    return ResultadoMolchan(
        tau=tau, nu=nu, area_bajo_curva=area, ganancia_area=ass,
        medida_referencia=medida_referencia, n_eventos=int(n_ev), evento=evento,
        advertencias=tuple(avisos),
    )


@dataclass(frozen=True)
class ResultadoROC:
    """Curva ROC sobre celdas: tasa de aciertos frente a tasa de falsas alarmas."""

    tasa_falsas_alarmas: np.ndarray
    tasa_aciertos: np.ndarray
    area_bajo_curva: float
    n_celdas_con_evento: int
    n_celdas_sin_evento: int
    evento: EventoObjetivo | None
    advertencias: tuple[str, ...] = ()

    def __str__(self) -> str:
        return (f"ROC: AUC = {self.area_bajo_curva:.3f} "
                f"({self.n_celdas_con_evento} celdas con evento, "
                f"{self.n_celdas_sin_evento} sin evento)")


def roc(
    tasas_espaciales: np.ndarray, conteos_observados: np.ndarray,
    *, evento: EventoObjetivo | None = None,
) -> ResultadoROC:
    """Curva ROC binarizando cada celda en "hubo evento" / "no hubo evento".

    Se diferencia de Molchan en el eje horizontal: ROC usa la fraccion de
    **celdas sin evento** declaradas en alarma, mientras que Molchan usa la
    fraccion de la medida de referencia. En un problema muy desbalanceado
    (pocas celdas con evento, que es el caso normal en sismicidad) la ROC tiende
    a parecer optimista: casi todas las celdas son negativas, asi que la tasa de
    falsas alarmas baja facilmente. Molchan es mas informativo aqui.
    """
    tasas = np.asarray(tasas_espaciales, float).ravel()
    obs = (np.asarray(conteos_observados, float).ravel() > 0).astype(float)
    n_pos, n_neg = float(obs.sum()), float((1 - obs).sum())
    if n_pos == 0 or n_neg == 0:
        raise ValueError("se requieren celdas con y sin evento para construir la ROC")

    orden = np.argsort(-tasas, kind="stable")
    cortes = _cortes_por_empate(tasas[orden])
    aciertos = np.concatenate(([0.0], (np.cumsum(obs[orden]) / n_pos)[cortes - 1]))
    falsas = np.concatenate(([0.0], (np.cumsum(1 - obs[orden]) / n_neg)[cortes - 1]))
    auc = float(np.trapezoid(aciertos, falsas)) if hasattr(np, "trapezoid") \
        else float(np.trapz(aciertos, falsas))

    avisos = []
    n_distintas = int(np.unique(tasas).size)
    if n_distintas < tasas.size / 2:
        avisos.append(
            f"Solo {n_distintas} tasas distintas entre {tasas.size} celdas: hay muchos "
            "empates. Los empates se agrupan (la curva los cruza en linea recta), asi que "
            "el AUC no puede inflarse por el desempate, pero la resolucion de la curva es "
            "limitada."
        )
    prevalencia = n_pos / (n_pos + n_neg)
    if prevalencia < 0.05:
        avisos.append(
            f"Solo el {100 * prevalencia:.1f}% de las celdas tienen evento. Con esta "
            "prevalencia el AUC parece alto incluso para pronosticos poco utiles; usa el "
            "diagrama de Molchan o la ganancia de informacion para juzgar utilidad real."
        )
    return ResultadoROC(
        tasa_falsas_alarmas=falsas, tasa_aciertos=aciertos, area_bajo_curva=auc,
        n_celdas_con_evento=int(n_pos), n_celdas_sin_evento=int(n_neg),
        evento=evento, advertencias=tuple(avisos),
    )


@dataclass(frozen=True)
class ResultadoBrier:
    """Brier score con la descomposicion de Murphy."""

    brier: float
    confiabilidad: float   # reliability: menor es mejor
    resolucion: float      # resolution: mayor es mejor
    incertidumbre: float   # uncertainty: propiedad del dato, no del modelo
    brier_climatologico: float
    #: 1 - brier/brier_climatologico. Positivo = mejor que la climatologia.
    destreza: float
    n_celdas: int
    evento: EventoObjetivo | None
    advertencias: tuple[str, ...] = ()

    def __str__(self) -> str:
        return (f"Brier = {self.brier:.5f} (climatologia {self.brier_climatologico:.5f}, "
                f"destreza {self.destreza:+.3f}); confiabilidad {self.confiabilidad:.5f}, "
                f"resolucion {self.resolucion:.5f}")


def brier(
    tasas_esperadas: np.ndarray,
    conteos_observados: np.ndarray,
    *,
    n_bins: int = 10,
    evento: EventoObjetivo | None = None,
) -> ResultadoBrier:
    """Brier score de la probabilidad de al menos un evento por celda.

    La probabilidad se obtiene de la tasa esperada suponiendo Poisson dentro de
    la celda: ``p = 1 - exp(-lambda)``. Ese paso **asume Poisson**; para un
    modelo autoexcitado la probabilidad correcta debe estimarse de las
    simulaciones, no de la tasa media.

    Descomposicion de Murphy: ``BS = confiabilidad - resolucion + incertidumbre``.
    La incertidumbre no depende del modelo (es la varianza de la climatologia);
    la destreza compara contra pronosticar siempre la frecuencia base.
    """
    lam = np.asarray(tasas_esperadas, float).ravel()
    obs = (np.asarray(conteos_observados, float).ravel() > 0).astype(float)
    if lam.shape != obs.shape:
        raise ValueError("tasas y conteos deben tener la misma forma")
    p = 1.0 - np.exp(-np.clip(lam, 0, None))
    bs = float(np.mean((p - obs) ** 2))
    base = float(obs.mean())
    bs_clim = base * (1.0 - base)

    conf, reso = _descomponer(p, obs, n_bins)
    destreza = 1.0 - bs / bs_clim if bs_clim > 0 else float("nan")

    avisos = []
    if base == 0:
        avisos.append(
            "Ninguna celda registro evento en la ventana. El Brier score es calculable pero "
            "no distingue entre modelos: cualquier pronostico de probabilidad baja acierta."
        )
    if obs.size < 100:
        avisos.append(
            f"Solo {obs.size} celdas. El diagrama de confiabilidad con {n_bins} bins tendra "
            "muy pocos casos por bin y sera ruidoso."
        )
    return ResultadoBrier(
        brier=bs, confiabilidad=conf, resolucion=reso, incertidumbre=bs_clim,
        brier_climatologico=bs_clim, destreza=destreza, n_celdas=int(obs.size),
        evento=evento, advertencias=tuple(avisos),
    )


def _descomponer(p: np.ndarray, obs: np.ndarray, n_bins: int) -> tuple[float, float]:
    """Terminos de confiabilidad y resolucion de la descomposicion de Murphy."""
    bordes = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, bordes) - 1, 0, n_bins - 1)
    base = float(obs.mean())
    n = obs.size
    conf = reso = 0.0
    for k in range(n_bins):
        sel = idx == k
        nk = int(sel.sum())
        if nk == 0:
            continue
        p_k = float(p[sel].mean())
        o_k = float(obs[sel].mean())
        conf += nk * (p_k - o_k) ** 2
        reso += nk * (o_k - base) ** 2
    return conf / n, reso / n


def diagrama_confiabilidad(
    tasas_esperadas: np.ndarray, conteos_observados: np.ndarray, *, n_bins: int = 10,
) -> dict[str, np.ndarray]:
    """Datos del diagrama de confiabilidad: probabilidad pronosticada vs. frecuencia observada.

    Un modelo bien calibrado cae sobre la diagonal. La desviacion de la diagonal
    es el termino de confiabilidad del Brier score. **El numero de casos por bin
    debe mostrarse siempre**: un punto muy alejado de la diagonal construido con
    tres celdas no dice nada, y sin el conteo el diagrama induce a error.
    """
    lam = np.asarray(tasas_esperadas, float).ravel()
    obs = (np.asarray(conteos_observados, float).ravel() > 0).astype(float)
    p = 1.0 - np.exp(-np.clip(lam, 0, None))
    bordes = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, bordes) - 1, 0, n_bins - 1)
    pron, frec, cuenta = [], [], []
    for k in range(n_bins):
        sel = idx == k
        nk = int(sel.sum())
        cuenta.append(nk)
        pron.append(float(p[sel].mean()) if nk else np.nan)
        frec.append(float(obs[sel].mean()) if nk else np.nan)
    return {
        "prob_pronosticada": np.array(pron),
        "frec_observada": np.array(frec),
        "n_casos": np.array(cuenta),
        "bordes": bordes,
    }
