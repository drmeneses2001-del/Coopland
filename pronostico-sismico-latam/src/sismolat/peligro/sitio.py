"""Efecto de sitio: clasificacion por Vs30 y el caso de la zona lacustre de la CDMX.

Por que Vs30 no basta en el Valle de Mexico
-------------------------------------------
La practica habitual describe el sitio con ``Vs30`` (velocidad media de las
ondas de corte en los 30 m superiores) y deja que el GMM aplique su termino de
sitio. En la mayoria de los emplazamientos es una aproximacion razonable. **En
la zona lacustre de la Ciudad de Mexico no lo es**, por tres razones que se
suman:

1. **El espesor domina, no los 30 m superiores.** Los depositos lacustres
   alcanzan decenas de metros y su periodo dominante varia de menos de 1 s a
   mas de 4 s en pocos kilometros. Dos sitios con el mismo Vs30 pueden tener
   periodos dominantes muy distintos y responder de forma opuesta al mismo
   sismo.
2. **La amplificacion es estrechamente resonante.** No es un factor plano sobre
   todo el espectro: concentra energia cerca del periodo del sitio. Un factor
   unico aplicado a PGA no describe eso.
3. **La duracion se prolonga.** El movimiento dura mucho mas que en roca, lo
   que importa para el dano acumulado y no aparece en PGA ni en Sa.

Este modulo **no** aplica un factor de amplificacion para la zona lacustre,
porque no existe uno defendible. Lo que ofrece es la funcion de transferencia
1D de un estrato sobre semiespacio, que es una solucion analitica exacta y
verificable, y que exige al usuario declarar espesor, velocidad, densidades y
amortiguamiento. Si no se conocen, la respuesta honesta es que no se puede
calcular el efecto de sitio ahi.

Lo que este modulo NO puede hacer
---------------------------------
* El modelo 1D **no** captura efectos de cuenca 2D/3D (ondas superficiales
  generadas en los bordes, focalizacion), que en el Valle de Mexico contribuyen
  de forma sustancial a la duracion prolongada.
* No modela comportamiento no lineal del suelo, relevante para movimientos
  fuertes.
* No sustituye a una microzonificacion ni a la normativa vigente.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass

import numpy as np

from ..procedencia import Cantidad, Procedencia, convencion

__all__ = [
    "ClaseDeSitio", "clasificar_vs30", "EstratoSobreSemiespacio",
    "ADVERTENCIA_ZONA_LACUSTRE", "LIMITES_VS30",
]

#: Limites de clase de sitio por Vs30, en m/s.
LIMITES_VS30 = convencion(
    0.0, "m/s",
    motivo=(
        "los limites 1500 / 760 / 360 / 180 m/s son la clasificacion de uso extendido en "
        "normativa sismica. Son una CONVENCION de clasificacion, no una medicion: la "
        "respuesta de un sitio no cambia bruscamente al cruzar 360 m/s."
    ),
)


class ClaseDeSitio(enum.Enum):
    """Clase de sitio por Vs30, con la nomenclatura de uso extendido."""

    ROCA_DURA = "A"
    ROCA = "B"
    SUELO_MUY_DENSO = "C"
    SUELO_RIGIDO = "D"
    SUELO_BLANDO = "E"

    @property
    def rango_vs30(self) -> tuple[float, float]:
        return {
            "A": (1500.0, float("inf")), "B": (760.0, 1500.0),
            "C": (360.0, 760.0), "D": (180.0, 360.0), "E": (0.0, 180.0),
        }[self.value]


def clasificar_vs30(vs30: Cantidad) -> tuple[ClaseDeSitio, list[str]]:
    """Clase de sitio a partir de Vs30, con las advertencias pertinentes."""
    if not isinstance(vs30, Cantidad):
        raise TypeError("vs30 debe ser una Cantidad con procedencia declarada")
    v = vs30.valor
    for clase in ClaseDeSitio:
        lo, hi = clase.rango_vs30
        if lo <= v < hi:
            elegida = clase
            break
    else:  # pragma: no cover
        elegida = ClaseDeSitio.ROCA_DURA

    avisos = []
    lo, hi = elegida.rango_vs30
    margen = 0.1 * (min(hi, 2000.0) - lo)
    if v - lo < margen or (math.isfinite(hi) and hi - v < margen):
        avisos.append(
            f"Vs30 = {v:g} m/s cae cerca del limite de la clase {elegida.value}. La "
            "clasificacion es una CONVENCION discreta sobre una variable continua: "
            "comprueba el efecto de usar la clase contigua."
        )
    if vs30.procedencia.es_debil:
        avisos.append(
            f"Vs30 tiene procedencia {vs30.procedencia.value}. Los mapas globales de Vs30 "
            "derivados de la pendiente topografica tienen error grande a escala local."
        )
    if v < 180:
        avisos.append(
            "Vs30 por debajo de 180 m/s indica suelo blando. En depositos lacustres "
            "profundos, Vs30 NO describe la respuesta: usa EstratoSobreSemiespacio y "
            "consulta ADVERTENCIA_ZONA_LACUSTRE."
        )
    return elegida, avisos


ADVERTENCIA_ZONA_LACUSTRE = (
    "ZONA LACUSTRE DEL VALLE DE MEXICO: no apliques aqui el termino de sitio de un GMM "
    "basado en Vs30. El periodo dominante varia de menos de 1 s a mas de 4 s en pocos "
    "kilometros, la amplificacion es resonante (no un factor plano) y la duracion se "
    "prolonga mucho respecto a roca. Dos sitios con el mismo Vs30 pueden responder de "
    "forma opuesta. Calcula el peligro en ROCA DE REFERENCIA y trata la respuesta del "
    "sitio aparte, con el periodo dominante medido en ese punto."
)


@dataclass(frozen=True)
class EstratoSobreSemiespacio:
    """Funcion de transferencia 1D de un estrato de suelo sobre semiespacio elastico.

    La matematica
    -------------
    Para ondas SH con incidencia vertical, la razon entre el movimiento en la
    superficie del estrato y el del afloramiento rocoso es

    .. math::
        H(\\omega) = \\frac{1}{\\cos(k^* h) + i\\, \\alpha_z \\sin(k^* h)},
        \\qquad k^* = \\frac{\\omega}{V_s (1 + i\\xi)},
        \\qquad \\alpha_z = \\frac{\\rho_1 V_{s1}}{\\rho_2 V_{s2}}

    donde :math:`\\alpha_z` es la razon de impedancias. Sin amortiguamiento, el
    primer maximo esta en el **periodo dominante**

    .. math:: T_0 = \\frac{4h}{V_s}

    con amplificacion :math:`1/\\alpha_z`, y hay maximos sucesivos en
    :math:`T_0/3`, :math:`T_0/5`, ...

    Es una solucion exacta del problema 1D, no una correlacion empirica: puede
    verificarse comprobando la posicion de los maximos y su amplitud, y las
    pruebas lo hacen.
    """

    espesor_m: float
    vs_suelo_ms: float
    vs_roca_ms: float
    densidad_suelo: float = 1600.0     # kg/m^3
    densidad_roca: float = 2400.0      # kg/m^3
    amortiguamiento: float = 0.05      # fraccion del critico

    def __post_init__(self) -> None:
        for nombre, v in (("espesor_m", self.espesor_m), ("vs_suelo_ms", self.vs_suelo_ms),
                          ("vs_roca_ms", self.vs_roca_ms)):
            if v <= 0:
                raise ValueError(f"{nombre} debe ser positivo")
        if not 0 <= self.amortiguamiento < 1:
            raise ValueError("el amortiguamiento debe estar en [0, 1)")
        if self.vs_suelo_ms >= self.vs_roca_ms:
            raise ValueError(
                "vs_suelo_ms debe ser menor que vs_roca_ms: sin contraste de impedancia "
                "no hay amplificacion que calcular"
            )

    @property
    def periodo_dominante_s(self) -> float:
        """``T0 = 4h / Vs``. Es el parametro que gobierna la respuesta, no Vs30."""
        return 4.0 * self.espesor_m / self.vs_suelo_ms

    @property
    def razon_de_impedancias(self) -> float:
        return ((self.densidad_suelo * self.vs_suelo_ms) /
                (self.densidad_roca * self.vs_roca_ms))

    @property
    def amplificacion_maxima_teorica(self) -> float:
        """Amplificacion en T0 sin amortiguamiento: el inverso de la impedancia."""
        return 1.0 / self.razon_de_impedancias

    def transferencia(self, periodos_s: np.ndarray) -> np.ndarray:
        """Modulo de la funcion de transferencia en los periodos dados."""
        T = np.asarray(periodos_s, dtype=float)
        if np.any(T <= 0):
            raise ValueError("los periodos deben ser positivos")
        omega = 2.0 * math.pi / T
        vs_complejo = self.vs_suelo_ms * (1.0 + 1j * self.amortiguamiento)
        k = omega / vs_complejo
        kh = k * self.espesor_m
        alpha = self.razon_de_impedancias
        return np.abs(1.0 / (np.cos(kh) + 1j * alpha * np.sin(kh)))

    def resumen(self) -> str:
        return (f"Estrato de {self.espesor_m:g} m, Vs={self.vs_suelo_ms:g} m/s sobre roca "
                f"Vs={self.vs_roca_ms:g} m/s: T0={self.periodo_dominante_s:.2f} s, "
                f"amplificacion maxima teorica={self.amplificacion_maxima_teorica:.1f}x")

    def advertencias(self) -> list[str]:
        return [
            "Modelo 1D de un solo estrato: no captura efectos de cuenca 2D/3D, que en el "
            "Valle de Mexico contribuyen de forma sustancial a la duracion prolongada.",
            "Modelo lineal: no representa el comportamiento no lineal del suelo bajo "
            "movimientos fuertes, que reduce la amplificacion y alarga el periodo efectivo.",
            f"El periodo dominante ({self.periodo_dominante_s:.2f} s) es el parametro que "
            "gobierna la respuesta. Si no lo conoces para el sitio concreto, no puedes "
            "calcular su efecto: Vs30 no lo determina.",
        ]
