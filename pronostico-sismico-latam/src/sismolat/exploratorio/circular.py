"""Estadistica circular: la prueba correcta para hipotesis de fase.

Por que no vale una correlacion de Pearson
------------------------------------------
Cuando se pregunta "¿ocurren mas sismos en cierta fase de la marea?", la
variable es **circular**: la fase 0 y la fase 2π son la misma. Una correlacion
de Pearson sobre una variable circular es sencillamente incorrecta —su resultado
depende de donde se corte el circulo— y sin embargo aparece con frecuencia.

La prueba adecuada es la de **Schuster**, que trata cada evento como un vector
unitario en la direccion de su fase y mide la longitud de la suma:

.. math::
    R = \\left| \\sum_{i=1}^{N} e^{i\\theta_i} \\right|,
    \\qquad p = \\exp\\!\\left(-\\frac{R^2}{N}\\right)

Bajo la hipotesis nula de fases uniformes, los vectores se cancelan y R es
pequeno. El p-valor de arriba es la aproximacion asintotica clasica; para N
pequeno esta implementacion ofrece ademas el p-valor exacto por simulacion.

Tamano de efecto, no solo significancia
---------------------------------------
Con un catalogo grande, una concentracion minuscula da un p-valor diminuto. Lo
que importa es **cuanta** modulacion hay, y eso lo mide la longitud resultante
media :math:`\\bar{R} = R/N`, que va de 0 (uniforme) a 1 (todos en la misma
fase). Los efectos de marea publicados son del orden de unos pocos por ciento de
exceso: significativos con N grande y de magnitud pequena.

Potencia
--------
Un resultado no significativo **no dice nada** sin la potencia. Con N pequeno,
no rechazar el nulo es lo esperable aunque el efecto exista.
:func:`potencia_schuster` la calcula por simulacion, y el panel de resultado
nulo la exige.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = [
    "ResultadoSchuster", "prueba_de_schuster", "potencia_schuster",
    "fase_por_periodo", "fase_entre_eventos", "n_minimo_para_detectar",
]


@dataclass(frozen=True)
class ResultadoSchuster:
    """Resultado de la prueba de Schuster sobre un conjunto de fases."""

    n: int
    #: Longitud del vector resultante.
    R: float
    #: Longitud resultante media, R/N: el tamano de efecto (0 a 1).
    R_medio: float
    #: Fase preferente, en radianes, si la hubiera.
    fase_media_rad: float
    p_valor: float
    p_exacto: float | None
    #: Exceso porcentual de eventos en la mitad favorable del ciclo.
    exceso_porcentual: float
    potencia: float | None = None
    advertencias: tuple[str, ...] = ()

    @property
    def fase_media_grados(self) -> float:
        return math.degrees(self.fase_media_rad) % 360.0

    def __str__(self) -> str:
        pot = f", potencia={self.potencia:.2f}" if self.potencia is not None else ""
        return (f"Schuster (n={self.n}): R_medio={self.R_medio:.4f} "
                f"(exceso {self.exceso_porcentual:+.1f}%), fase media "
                f"{self.fase_media_grados:.0f} grados, p={self.p_valor:.4g}{pot}")


def fase_por_periodo(
    tiempos_dias: np.ndarray, periodo_dias: float, origen_dias: float = 0.0,
) -> np.ndarray:
    """Fase de cada evento dentro de un ciclo de periodo conocido, en radianes.

    Sirve para periodos **definicionales** —el dia solar, el ano, el periodo de
    una componente de marea— donde el ciclo se conoce sin ajustar nada.

    No sirve para calcular esfuerzo de marea real: eso requiere efemerides y
    numeros de Love, que este paquete no incluye. Si quieres probar el esfuerzo
    de marea, calcula la serie con una herramienta especializada y pasa su fase
    con :func:`fase_de_serie`.
    """
    if periodo_dias <= 0:
        raise ValueError("el periodo debe ser positivo")
    t = np.asarray(tiempos_dias, dtype=float)
    return (2.0 * math.pi * ((t - origen_dias) / periodo_dias % 1.0))


def fase_entre_eventos(tiempos_dias: np.ndarray, marcas_dias: np.ndarray) -> np.ndarray:
    """Fase de cada evento entre dos marcas consecutivas de una serie de referencia.

    Util cuando el ciclo no tiene periodo constante: por ejemplo, la fase entre
    maximos sucesivos de una serie de esfuerzo de marea calculada aparte.
    """
    t = np.sort(np.asarray(tiempos_dias, dtype=float))
    m = np.sort(np.asarray(marcas_dias, dtype=float))
    if m.size < 2:
        raise ValueError("se requieren al menos dos marcas de referencia")
    idx = np.searchsorted(m, t) - 1
    dentro = (idx >= 0) & (idx < m.size - 1)
    if not dentro.any():
        raise ValueError("ningun evento cae entre dos marcas consecutivas")
    ini = m[idx[dentro]]
    fin = m[idx[dentro] + 1]
    return 2.0 * math.pi * (t[dentro] - ini) / (fin - ini)


def prueba_de_schuster(
    fases_rad: np.ndarray, *, n_simulaciones: int = 0, semilla: int = 0,
    calcular_potencia_para: float | None = None,
) -> ResultadoSchuster:
    """Prueba de Schuster de uniformidad de fases.

    Parametros
    ----------
    n_simulaciones:
        Si es mayor que cero, calcula tambien el p-valor exacto por simulacion
        de Monte Carlo. Conviene con N pequeno, donde la aproximacion asintotica
        no es fiable.
    calcular_potencia_para:
        Si se da una longitud resultante media, calcula la potencia de la prueba
        para detectar un efecto de ese tamano con este N.
    """
    th = np.asarray(fases_rad, dtype=float)
    th = th[np.isfinite(th)]
    n = th.size
    if n < 3:
        raise ValueError(f"solo {n} fases; se requieren al menos 3")

    c, s = float(np.cos(th).sum()), float(np.sin(th).sum())
    R = math.hypot(c, s)
    R_medio = R / n
    fase_media = math.atan2(s, c) % (2 * math.pi)
    p = math.exp(-R * R / n)

    p_exacto = None
    if n_simulaciones > 0:
        rng = np.random.default_rng(semilla)
        sim = rng.random((n_simulaciones, n)) * 2 * math.pi
        R_sim = np.hypot(np.cos(sim).sum(axis=1), np.sin(sim).sum(axis=1))
        p_exacto = float((np.sum(R_sim >= R) + 1) / (n_simulaciones + 1))

    # Exceso en la mitad del ciclo centrada en la fase media.
    d = np.abs((th - fase_media + math.pi) % (2 * math.pi) - math.pi)
    favorables = int(np.sum(d <= math.pi / 2))
    exceso = 100.0 * (favorables / n - 0.5) / 0.5

    avisos: list[str] = []
    if n < 50:
        avisos.append(
            f"Solo {n} eventos. La aproximacion asintotica del p-valor no es fiable con "
            "N pequeno; usa n_simulaciones > 0 para el p exacto, y comprueba la potencia "
            "antes de interpretar un resultado no significativo."
        )
    if R_medio < 0.05 and p < 0.05:
        avisos.append(
            f"El efecto es significativo pero diminuto (R_medio={R_medio:.4f}, exceso "
            f"{exceso:+.1f}%). Con N grande, cualquier desviacion minima sale "
            "significativa. Reporta el tamano de efecto, no el p-valor."
        )

    potencia = None
    if calcular_potencia_para is not None:
        potencia = potencia_schuster(n, calcular_potencia_para, semilla=semilla)

    return ResultadoSchuster(
        n=n, R=R, R_medio=R_medio, fase_media_rad=fase_media, p_valor=p,
        p_exacto=p_exacto, exceso_porcentual=exceso, potencia=potencia,
        advertencias=tuple(avisos),
    )


def _kappa_desde_r(r_objetivo: float) -> float:
    """Concentracion de von Mises que produce una longitud resultante media dada."""
    from scipy import optimize, special
    if not 0 < r_objetivo < 1:
        raise ValueError("la longitud resultante media debe estar en (0, 1)")

    def f(k):
        return special.i1(k) / special.i0(k) - r_objetivo

    return float(optimize.brentq(f, 1e-6, 700.0))


def potencia_schuster(
    n: int, r_verdadero: float, *, alfa: float = 0.05, n_simulaciones: int = 2000,
    semilla: int = 0,
) -> float:
    """Probabilidad de detectar una modulacion de tamano ``r_verdadero`` con ``n`` eventos.

    Se simulan fases de una distribucion de von Mises con la concentracion que
    produce esa longitud resultante media, y se cuenta cuantas veces la prueba
    rechaza el nulo.

    **Este numero es obligatorio para interpretar un resultado no
    significativo.** Con potencia 0.2, no rechazar el nulo no distingue "no hay
    efecto" de "no habia datos suficientes".
    """
    if n < 3:
        raise ValueError("se requieren al menos 3 eventos")
    kappa = _kappa_desde_r(r_verdadero)
    rng = np.random.default_rng(semilla)
    muestras = rng.vonmises(0.0, kappa, size=(n_simulaciones, n))
    R = np.hypot(np.cos(muestras).sum(axis=1), np.sin(muestras).sum(axis=1))
    p = np.exp(-R ** 2 / n)
    return float(np.mean(p < alfa))


def n_minimo_para_detectar(
    r_verdadero: float, *, potencia_objetivo: float = 0.8, alfa: float = 0.05,
    semilla: int = 0,
) -> int:
    """Cuantos eventos hacen falta para detectar una modulacion de ese tamano.

    Sirve para decidir **antes** de mirar los datos si la pregunta es contestable
    con el catalogo disponible. Preguntar algo que el catalogo no puede
    responder, y luego reportar el no rechazo como evidencia de ausencia, es uno
    de los errores mas comunes en este terreno.
    """
    n = 10
    while n < 2_000_000:
        if potencia_schuster(n, r_verdadero, alfa=alfa, n_simulaciones=800,
                             semilla=semilla) >= potencia_objetivo:
            return n
        n = int(n * 1.5)
    raise ValueError(
        f"detectar r={r_verdadero:g} con potencia {potencia_objetivo:g} requiere mas de "
        "2 millones de eventos: la pregunta no es contestable con ningun catalogo real"
    )
