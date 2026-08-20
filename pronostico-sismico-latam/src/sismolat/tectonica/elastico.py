"""Deformacion elastostatica por dislocacion, en medio infinito homogeneo.

Que se implementa y por que asi
-------------------------------
Se parte de la solucion de Kelvin —el campo de desplazamiento de una fuerza
puntual en un medio elastico infinito, homogeneo e isotropo— y se deriva de ella
el campo de un doble par puntual. Una falla finita se obtiene integrando
numericamente sobre el plano de ruptura.

**No se usa la solucion de semiespacio de Okada.** La razon es el contrato
epistemologico: las formulas de Okada para deformacion interna son largas y
llenas de terminos con signos y singularidades delicadas, y reproducirlas sin
poder cotejarlas contra el articulo original —el egreso de red a los
repositorios bibliograficos esta bloqueado— produciria codigo que *parece*
verificado y no lo esta. Un signo equivocado en un termino da un mapa de lobulos
plausible y falso.

La solucion de Kelvin, en cambio, se deriva en pocas lineas a partir de un
resultado que puede comprobarse numericamente: equilibrio elastico, decaimiento
correcto con la distancia, convergencia de la falla finita a la fuente puntual y
recuperacion del tensor de momento. Las pruebas hacen esas comprobaciones.

La limitacion que esto impone, y como se declara
------------------------------------------------
Un medio infinito **no tiene superficie libre**. La corteza sí la tiene, y su
efecto es de primer orden para fuentes someras: cerca de la superficie, los
esfuerzos reales difieren sustancialmente de los que da este modulo.

En lugar de esconder esa limitacion, :func:`error_de_superficie_libre` la
**cuantifica**: calcula la traccion residual que este modelo deja sobre el plano
z=0, que en la realidad debe ser nula. Cuanto mayor sea esa traccion comparada
con los esfuerzos de interes, menos utilizable es el resultado.

Regla practica que se desprende de esa comprobacion: el error es tolerable
cuando el punto de observacion y la fuente estan ambos a profundidad mayor que
su separacion horizontal; deja de serlo para fuentes someras observadas lejos.

Lo que este modulo NO puede hacer
---------------------------------
* No modela superficie libre, estratificacion, ni topografia. Para subduccion
  —donde la geometria de la interfase, la batimetria y la estructura de
  velocidades importan— es una aproximacion gruesa.
* No modela viscoelasticidad ni deformacion postsismica.
* No estima el modelo de deslizamiento de la fuente: hay que darselo, y su
  incertidumbre suele ser grande y rara vez publicada.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = [
    "MedioElastico", "PlanoDeFalla", "tensor_de_momento", "desplazamiento_punto",
    "esfuerzo_punto", "esfuerzo_falla_finita", "error_de_superficie_libre",
]


@dataclass(frozen=True)
class MedioElastico:
    """Medio homogeneo isotropo. ``mu`` en Pa, ``nu`` adimensional."""

    mu_pa: float = 3.0e10
    nu: float = 0.25

    def __post_init__(self) -> None:
        if self.mu_pa <= 0:
            raise ValueError("el modulo de corte debe ser positivo")
        if not -1.0 < self.nu < 0.5:
            raise ValueError("el coeficiente de Poisson debe estar en (-1, 0.5)")

    @property
    def lambda_pa(self) -> float:
        """Primer parametro de Lame."""
        return 2.0 * self.mu_pa * self.nu / (1.0 - 2.0 * self.nu)


def _versores(strike_deg: float, dip_deg: float, rake_deg: float
              ) -> tuple[np.ndarray, np.ndarray]:
    """Normal al plano y direccion de deslizamiento, en (Este, Norte, Arriba).

    Convenio: ``strike`` medido desde el Norte en sentido horario; ``dip`` desde
    la horizontal; ``rake`` en el plano de falla desde la direccion de strike.
    """
    s, d, r = (math.radians(x) for x in (strike_deg, dip_deg, rake_deg))
    # Vector unitario a lo largo del strike (Este, Norte, Arriba).
    e_strike = np.array([math.sin(s), math.cos(s), 0.0])
    # Vector buzamiento: perpendicular al strike, inclinado dip hacia abajo.
    e_buz = np.array([math.cos(s) * math.cos(d), -math.sin(s) * math.cos(d),
                      -math.sin(d)])
    normal = np.cross(e_strike, e_buz)
    normal /= np.linalg.norm(normal)
    deslizamiento = math.cos(r) * e_strike + math.sin(r) * (-e_buz)
    deslizamiento /= np.linalg.norm(deslizamiento)
    return normal, deslizamiento


@dataclass(frozen=True)
class PlanoDeFalla:
    """Plano de falla con su orientacion y, opcionalmente, geometria y deslizamiento.

    Coordenadas en km, con origen elegido por quien usa el modulo. El eje z es
    positivo hacia **arriba**, de modo que las profundidades son negativas.
    """

    strike_deg: float
    dip_deg: float
    rake_deg: float
    #: Centro del plano (x=Este, y=Norte, z=Arriba), en km.
    centro_km: tuple[float, float, float] = (0.0, 0.0, -10.0)
    largo_km: float = 10.0
    ancho_km: float = 10.0
    deslizamiento_m: float = 1.0

    @property
    def normal(self) -> np.ndarray:
        return _versores(self.strike_deg, self.dip_deg, self.rake_deg)[0]

    @property
    def direccion_deslizamiento(self) -> np.ndarray:
        return _versores(self.strike_deg, self.dip_deg, self.rake_deg)[1]

    @property
    def area_km2(self) -> float:
        return self.largo_km * self.ancho_km

    def momento_nm(self, medio: MedioElastico) -> float:
        """``M0 = mu * A * deslizamiento``, en N m."""
        return medio.mu_pa * self.area_km2 * 1e6 * self.deslizamiento_m

    def magnitud(self, medio: MedioElastico) -> float:
        """Mw equivalente por Hanks-Kanamori."""
        return (2.0 / 3.0) * (math.log10(self.momento_nm(medio)) - 9.1)


def tensor_de_momento(normal: np.ndarray, deslizamiento: np.ndarray, m0: float
                      ) -> np.ndarray:
    """Tensor de momento de una dislocacion de cizalla: ``M = M0 (n d + d n)``."""
    n = np.asarray(normal, float)
    d = np.asarray(deslizamiento, float)
    return m0 * (np.outer(n, d) + np.outer(d, n))


def desplazamiento_punto(
    puntos_km: np.ndarray, momento: np.ndarray, medio: MedioElastico,
    fuente_km: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> np.ndarray:
    """Desplazamiento de un doble par puntual en medio infinito.

    Parte de la funcion de Green de Kelvin

    .. math::
        G_{ij} = \\frac{1}{16\\pi\\mu(1-\\nu)}
            \\left[ \\frac{(3-4\\nu)\\delta_{ij}}{r} + \\frac{x_i x_j}{r^3} \\right]

    y aplica :math:`u_i = -M_{jk}\\, \\partial G_{ij} / \\partial x_k`, cuya
    derivada es

    .. math::
        \\frac{\\partial G_{ij}}{\\partial x_k} = A\\left[
            -\\frac{(3-4\\nu)\\delta_{ij} x_k}{r^3}
            + \\frac{\\delta_{ik} x_j + \\delta_{jk} x_i}{r^3}
            - \\frac{3 x_i x_j x_k}{r^5} \\right]

    Devuelve el desplazamiento en metros si el momento va en N m y las
    coordenadas en km.
    """
    p = np.atleast_2d(np.asarray(puntos_km, dtype=float))
    x = (p - np.asarray(fuente_km, dtype=float)) * 1000.0     # a metros
    r = np.linalg.norm(x, axis=1)
    if np.any(r == 0):
        raise ValueError("hay puntos de observacion coincidentes con la fuente")

    A = 1.0 / (16.0 * math.pi * medio.mu_pa * (1.0 - medio.nu))
    c = 3.0 - 4.0 * medio.nu
    M = np.asarray(momento, dtype=float)
    delta = np.eye(3)

    r3 = r ** 3
    r5 = r ** 5
    # dG[n, i, j, k] = dG_ij/dx_k en el punto n
    dG = A * (
        -c * delta[None, :, :, None] * x[:, None, None, :] / r3[:, None, None, None]
        + (delta[None, :, None, :] * x[:, None, :, None]
           + delta[None, None, :, :] * x[:, :, None, None]) / r3[:, None, None, None]
        - 3.0 * x[:, :, None, None] * x[:, None, :, None] * x[:, None, None, :]
        / r5[:, None, None, None]
    )
    return -np.einsum("jk,nijk->ni", M, dG)


def esfuerzo_punto(
    puntos_km: np.ndarray, momento: np.ndarray, medio: MedioElastico,
    fuente_km: tuple[float, float, float] = (0.0, 0.0, 0.0),
    paso_km: float = 0.01,
) -> np.ndarray:
    """Tensor de esfuerzos (Pa) por diferencias finitas del desplazamiento.

    Se derivan numericamente las componentes del desplazamiento y se aplica la
    ley de Hooke isotropa. El paso por defecto (10 m) es pequeno frente a las
    escalas de interes y grande frente al error de redondeo; las pruebas
    comprueban que el resultado no depende de el.
    """
    p = np.atleast_2d(np.asarray(puntos_km, dtype=float))
    h = paso_km
    grad = np.empty((p.shape[0], 3, 3))   # grad[n, i, j] = du_i/dx_j
    for j in range(3):
        dp = np.zeros(3)
        dp[j] = h
        mas = desplazamiento_punto(p + dp, momento, medio, fuente_km)
        menos = desplazamiento_punto(p - dp, momento, medio, fuente_km)
        grad[:, :, j] = (mas - menos) / (2.0 * h * 1000.0)   # por metro

    eps = 0.5 * (grad + np.transpose(grad, (0, 2, 1)))
    traza = np.trace(eps, axis1=1, axis2=2)
    return (medio.lambda_pa * traza[:, None, None] * np.eye(3)[None, :, :]
            + 2.0 * medio.mu_pa * eps)


def esfuerzo_falla_finita(
    puntos_km: np.ndarray, falla: PlanoDeFalla, medio: MedioElastico,
    *, n_largo: int = 10, n_ancho: int = 10, paso_km: float = 0.01,
) -> np.ndarray:
    """Esfuerzo de una falla rectangular, integrando sobre parches puntuales.

    La falla se divide en ``n_largo x n_ancho`` parches, cada uno tratado como
    doble par puntual con el momento que le corresponde. La discretizacion debe
    ser fina frente a la distancia de observacion; cerca de la falla, la suma de
    fuentes puntuales no converge y el resultado no es utilizable.
    """
    n, d = falla.normal, falla.direccion_deslizamiento
    _, e_buz = _versores(falla.strike_deg, falla.dip_deg, 0.0)[0], None
    s = math.radians(falla.strike_deg)
    dip = math.radians(falla.dip_deg)
    e_strike = np.array([math.sin(s), math.cos(s), 0.0])
    e_buz = np.array([math.cos(s) * math.cos(dip), -math.sin(s) * math.cos(dip),
                      -math.sin(dip)])

    m0_total = falla.momento_nm(medio)
    m0_parche = m0_total / (n_largo * n_ancho)
    M = tensor_de_momento(n, d, m0_parche)

    us = (np.arange(n_largo) + 0.5) / n_largo - 0.5
    vs = (np.arange(n_ancho) + 0.5) / n_ancho - 0.5
    centro = np.asarray(falla.centro_km, dtype=float)

    total = np.zeros((np.atleast_2d(puntos_km).shape[0], 3, 3))
    for u in us:
        for v in vs:
            fuente = centro + u * falla.largo_km * e_strike + v * falla.ancho_km * e_buz
            total += esfuerzo_punto(puntos_km, M, medio, tuple(fuente), paso_km)
    return total


def error_de_superficie_libre(
    falla: PlanoDeFalla, medio: MedioElastico, *, extension_km: float = 50.0,
    n: int = 21,
) -> dict[str, float]:
    """Cuantifica el error que introduce no modelar la superficie libre.

    En la corteza real, la traccion sobre la superficie z=0 es nula. Un medio
    infinito no lo cumple, y la traccion residual que deja este modelo mide
    directamente cuanto se aparta de la realidad.

    Devuelve la traccion residual maxima y media sobre una rejilla en z=0, y su
    razon respecto al esfuerzo tipico a la profundidad de la falla. **Una razon
    grande significa que el resultado no es utilizable para esa geometria.**
    """
    lim = extension_km
    g = np.linspace(-lim, lim, n)
    gx, gy = np.meshgrid(g, g, indexing="ij")
    superficie = np.column_stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)])
    sigma_sup = esfuerzo_falla_finita(superficie, falla, medio)
    normal_sup = np.array([0.0, 0.0, 1.0])
    traccion = np.einsum("nij,j->ni", sigma_sup, normal_sup)
    mag_traccion = np.linalg.norm(traccion, axis=1)

    # Referencia: esfuerzo sobre una rejilla a la profundidad de la falla, la misma
    # extension que la de superficie. Se comparan magnitudes homologas --maximo con
    # maximo y mediana con mediana--: cotejar el maximo de una con la mediana de la
    # otra infla la razon y hace parecer inutilizable un calculo que no lo es.
    z_falla = falla.centro_km[2]
    ref_puntos = np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, z_falla)])
    sigma_ref = esfuerzo_falla_finita(ref_puntos, falla, medio)
    mag_ref = np.abs(sigma_ref).max(axis=(1, 2))
    # Se excluyen los puntos pegados a la falla, donde la suma de parches diverge.
    dist_centro = np.linalg.norm(ref_puntos - np.asarray(falla.centro_km), axis=1)
    lejos = dist_centro > 0.5 * math.hypot(falla.largo_km, falla.ancho_km)
    if not lejos.any():
        lejos = np.ones(mag_ref.size, dtype=bool)
    ref_max = float(mag_ref[lejos].max())
    ref_mediana = float(np.median(mag_ref[lejos]))

    razon_max = float(mag_traccion.max() / ref_max) if ref_max > 0 else float("inf")
    razon_mediana = (float(np.median(mag_traccion) / ref_mediana)
                     if ref_mediana > 0 else float("inf"))
    if razon_mediana < 0.1:
        lectura = ("El error de superficie libre es pequeno frente a los esfuerzos de "
                   "interes: el resultado es utilizable con la salvedad declarada.")
    elif razon_mediana < 0.5:
        lectura = ("El error de superficie libre es apreciable: usa el resultado de forma "
                   "cualitativa (donde sube y donde baja), no cuantitativa.")
    else:
        lectura = ("El error de superficie libre es del orden de los esfuerzos de interes: "
                   "para esta geometria el modelo de medio infinito NO es utilizable. Hace "
                   "falta una solucion de semiespacio.")

    return {
        "traccion_maxima_pa": float(mag_traccion.max()),
        "traccion_mediana_pa": float(np.median(mag_traccion)),
        "esfuerzo_referencia_maximo_pa": ref_max,
        "esfuerzo_referencia_mediano_pa": ref_mediana,
        "razon_maxima": razon_max,
        "razon_mediana": razon_mediana,
        "profundidad_falla_km": abs(z_falla),
        "interpretacion": lectura,
    }
