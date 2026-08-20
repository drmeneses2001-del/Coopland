"""Escalas de esfuerzo: por que el clima no puede causar un sismo.

El calculo explicito
--------------------
La pregunta "¿puede el clima disparar sismos?" se contesta comparando ordenes de
magnitud, y el calculo cabe en unas lineas. Lo que hay que comparar no es
energia total sino **cambio de esfuerzo** en la zona sismogenica, porque es el
esfuerzo lo que lleva una falla a la ruptura.

Las cantidades relevantes:

* **Caida de esfuerzo de un sismo**: 1 a 10 MPa. Es lo que se libera al romper.
* **Acumulacion tectonica**: :math:`\\dot\\sigma = \\mu \\dot\\varepsilon`. Con
  :math:`\\mu = 3\\times10^{10}` Pa y una tasa de deformacion de
  :math:`10^{-7}` por ano, salen unos 3 kPa al ano. Cargar una falla hasta su
  caida de esfuerzo tipica lleva, por tanto, del orden de mil anos.
* **Variacion de presion atmosferica**: un sistema de tormentas cambia la
  presion en superficie unos 20 hPa = 2 kPa.
* **Marea terrestre**: del orden de 1 a 5 kPa.
* **Carga estacional de agua y nieve**: unos pocos kPa.
* **Embalse grande**: hasta ~1 MPa bajo la presa.

La conclusion honesta, que no es la que suele darse
---------------------------------------------------
El resultado **no** es que los efectos atmosfericos sean despreciables sin mas.
Un cambio de 2 kPa es comparable a lo que la tectonica acumula en **un ano**.
Lo que es despreciable es frente a la **caida de esfuerzo**: 2 kPa son unas mil
veces menos que 1 MPa.

De ahi se sigue lo que se puede y no se puede afirmar:

* **No pueden causar un sismo.** No hay forma de que 2 kPa generen una ruptura
  que necesita liberar 10³ veces mas.
* **Podrian adelantar o retrasar marginalmente** la ruptura de una falla que ya
  estaba a punto de romper por causas tectonicas. Ese es el mecanismo por el que
  el efecto de marea es fisicamente plausible, y por el que su tamano observado
  es pequeno: solo actua sobre la pequena fraccion de fallas que estan en el
  filo en ese momento.
* **Los embalses son otra cosa.** Un MPa bajo una presa grande es del orden de
  la caida de esfuerzo, y ahi sí hay mecanismo para inducir sismicidad. Por eso
  la sismicidad inducida por embalses es un fenomeno documentado y la
  "prediccion meteorologica de sismos" no lo es.

Esta distincion —entre modulacion marginal del momento de ruptura y causacion—
es la que separa una hipotesis falsable de la pseudociencia.
Lo que este modulo NO puede hacer
---------------------------------
* Todos sus valores son ESTIMACIONES de orden de magnitud, no mediciones.
  Sirven para comparar potencias de diez y nada mas.
* No calcula el esfuerzo real en ningun sitio concreto. La transmision de una
  carga superficial a profundidad depende de la geometria, la estructura y la
  difusion de presion de poro, y aqui se trata como si fuera directa.
* No sustituye a un analisis de sismicidad inducida, que requiere modelar la
  hidrogeologia del emplazamiento.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..procedencia import Cantidad, Procedencia, supuesto

__all__ = ["EscalaDeEsfuerzo", "escalas_tipicas", "comparar_con_caida_de_esfuerzo",
           "tiempo_de_recarga_tectonica", "informe_de_escalas"]


@dataclass(frozen=True)
class EscalaDeEsfuerzo:
    """Un mecanismo y el cambio de esfuerzo que produce en la zona sismogenica."""

    nombre: str
    esfuerzo_pa: Cantidad
    escala_temporal: str
    mecanismo: str

    def __str__(self) -> str:
        v = self.esfuerzo_pa.valor
        unidad = ("MPa", 1e6) if v >= 1e5 else ("kPa", 1e3)
        return (f"{self.nombre:38s} {v / unidad[1]:8.3g} {unidad[0]:4s} "
                f"({self.escala_temporal})")


def tiempo_de_recarga_tectonica(
    caida_de_esfuerzo_pa: float = 3.0e6,
    mu_pa: float = 3.0e10,
    tasa_deformacion_por_ano: float = 1.0e-7,
) -> float:
    """Anios que tarda la tectonica en recargar una caida de esfuerzo tipica.

    .. math:: t = \\frac{\\Delta\\sigma}{\\mu \\dot\\varepsilon}

    Con los valores por defecto salen unos mil anios, que es el orden de los
    intervalos de recurrencia observados en fallas mayores. Que el numero salga
    bien es una comprobacion de que las escalas son las correctas.
    """
    tasa_esfuerzo = mu_pa * tasa_deformacion_por_ano
    return caida_de_esfuerzo_pa / tasa_esfuerzo


def escalas_tipicas() -> list[EscalaDeEsfuerzo]:
    """Cambios de esfuerzo tipicos de cada mecanismo, con procedencia declarada.

    Todos los valores son **ESTIMACIONES de orden de magnitud**, no mediciones.
    Sirven para comparar potencias de diez, que es lo unico que la comparacion
    necesita; usarlos como si fueran datos seria un error.
    """
    def est(v: float, motivo: str) -> Cantidad:
        return Cantidad(v, "Pa", Procedencia.ESTIMACION, notas=motivo)

    mu, eps = 3.0e10, 1.0e-7
    return [
        EscalaDeEsfuerzo(
            "Caida de esfuerzo de un sismo", est(3.0e6, "rango habitual 1-10 MPa"),
            "instantanea",
            "lo que la falla libera al romper; es la referencia de comparacion"),
        EscalaDeEsfuerzo(
            "Carga bajo un embalse grande", est(1.0e6, "columna de agua de ~100 m"),
            "anios",
            "presion de la columna de agua mas difusion de presion de poro"),
        EscalaDeEsfuerzo(
            "Acumulacion tectonica anual", est(mu * eps, f"mu={mu:.0e} Pa por eps={eps:.0e}/ano"),
            "por ano",
            "deformacion elastica impuesta por el movimiento de placas"),
        EscalaDeEsfuerzo(
            "Marea terrestre", est(3.0e3, "rango publicado 1-5 kPa"),
            "12 h y 24 h",
            "deformacion de la Tierra solida por atraccion lunisolar"),
        EscalaDeEsfuerzo(
            "Variacion de presion atmosferica", est(2.0e3, "20 hPa en un sistema de tormentas"),
            "dias",
            "carga superficial que se transmite en profundidad"),
        EscalaDeEsfuerzo(
            "Carga estacional de agua y nieve", est(3.0e3, "1-3 m de columna equivalente"),
            "estacional",
            "carga superficial mas cambios de presion de poro"),
        EscalaDeEsfuerzo(
            "Oleaje y microsismos", est(1.0e2, "carga oscilante de periodo corto"),
            "segundos",
            "presion sobre el fondo marino"),
    ]


def comparar_con_caida_de_esfuerzo(escala: EscalaDeEsfuerzo,
                                   caida_pa: float = 3.0e6) -> dict:
    """Cuantas veces menor es este mecanismo que la caida de esfuerzo de un sismo."""
    razon = caida_pa / escala.esfuerzo_pa.valor
    # Los cortes NO son arbitrarios, y su posicion importa. El corte superior esta
    # en 1e4 y no en 1e3 por una razon empirica: la marea terrestre perturba unos
    # 1-3 kPa (unas 1000 veces menos que la caida de esfuerzo) y SI produce una
    # modulacion pequena y detectable, publicada. La presion atmosferica es del
    # mismo orden. Poner el corte en 1e3 los separaria artificialmente en dos
    # categorias distintas siendo fisicamente comparables.
    if razon < 10:
        lectura = ("Del mismo orden que la caida de esfuerzo: hay mecanismo plausible "
                   "para INDUCIR sismicidad, no solo para modularla.")
    elif razon < 1.0e4:
        lectura = ("Entre uno y cuatro ordenes por debajo: puede modular marginalmente "
                   "el momento de ruptura de fallas ya criticamente cargadas, no causar "
                   "rupturas. Es el rango de la marea terrestre, cuyo efecto pequeno esta "
                   "documentado.")
    else:
        lectura = ("Mas de cuatro ordenes por debajo: no hay mecanismo por el que pueda "
                   "influir de forma detectable.")
    return {"mecanismo": escala.nombre, "razon": razon,
            "ordenes_de_magnitud": math.log10(razon), "interpretacion": lectura}


def informe_de_escalas(caida_pa: float = 3.0e6) -> str:
    """Texto didactico completo, con el calculo explicito.

    Pensado para mostrarse en el modulo exploratorio antes de que el usuario
    formule ninguna hipotesis climatica: el orden de magnitud acota de antemano
    lo que es razonable esperar.
    """
    lineas = [
        "ESCALAS DE ESFUERZO EN LA ZONA SISMOGENICA",
        "=" * 66,
        "",
        "Lo que importa no es la energia total de un fenomeno, sino cuanto cambia",
        "el ESFUERZO en la falla: es el esfuerzo lo que lleva a la ruptura.",
        "",
    ]
    for e in escalas_tipicas():
        lineas.append("  " + str(e))
    t = tiempo_de_recarga_tectonica(caida_pa)
    lineas += [
        "",
        f"Recarga tectonica de una caida de {caida_pa / 1e6:.0f} MPa: {t:.0f} anios.",
        "Que ese numero coincida con los intervalos de recurrencia observados en",
        "fallas mayores es una comprobacion de que las escalas son las correctas.",
        "",
        "COMPARACION CON LA CAIDA DE ESFUERZO",
        "-" * 66,
    ]
    for e in escalas_tipicas():
        if e.nombre.startswith("Caida"):
            continue
        c = comparar_con_caida_de_esfuerzo(e, caida_pa)
        lineas.append(f"  {e.nombre:38s} {c['razon']:9.0f}x menor "
                      f"({c['ordenes_de_magnitud']:.1f} ordenes)")
    lineas += [
        "",
        "QUE SE SIGUE DE ESTO",
        "-" * 66,
        "  * Los efectos atmosfericos NO son despreciables sin mas: 2 kPa es",
        "    comparable a lo que la tectonica acumula en un ano.",
        "  * Lo que es despreciable es frente a la CAIDA DE ESFUERZO, unas mil",
        "    veces mayor. Por eso no pueden causar un sismo.",
        "  * Podrian adelantar o retrasar marginalmente la ruptura de una falla",
        "    que ya estaba a punto de romper. Ese es el mecanismo por el que el",
        "    efecto de marea es plausible, y por el que su tamano es pequeno.",
        "  * Los embalses son distintos: ~1 MPa es del orden de la caida de",
        "    esfuerzo, y ahi sí hay mecanismo para inducir sismicidad.",
        "",
        "Esa distincion --modulacion marginal frente a causacion-- es la que",
        "separa una hipotesis falsable de la pseudociencia.",
        "",
        "TODOS los valores de arriba son ESTIMACIONES de orden de magnitud, no",
        "mediciones. Sirven para comparar potencias de diez y nada mas.",
    ]
    return "\n".join(lineas)
