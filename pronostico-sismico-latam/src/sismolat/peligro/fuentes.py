"""Fuentes sismogenicas con distribucion de magnitudes y geometria explicita.

Alcance de esta implementacion
------------------------------
Se modelan **fuentes de area** discretizadas en fuentes puntuales sobre una
rejilla, cada una con la misma distribucion de magnitudes. Es el modelo clasico
y es adecuado para sismicidad difusa (sismicidad de fondo, zonas de subduccion
tratadas como volumenes).

**No** se modelan fallas con geometria finita ni rupturas extensas. Para un
sismo de M8 en la interfase, tratar la fuente como puntual subestima la
distancia mas corta a la ruptura y por tanto **sobreestima** el movimiento del
terreno cerca, y lo subestima lejos. Es una limitacion real y esta declarada en
cada resultado.

Magnitud maxima
---------------
``m_max`` es el parametro peor restringido de todo el PSHA y el que mas influye
en la cola del peligro. No hay forma de estimarlo bien con catalogos de decadas.
Por eso :class:`DistribucionMagnitudes` lo exige como :class:`Cantidad` con
procedencia declarada, y la forma correcta de usarlo es como **rama del arbol
logico** (varios valores con pesos), no como un numero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..procedencia import Cantidad, Procedencia
from .gmm import RegimenTectonico

__all__ = ["DistribucionMagnitudes", "FuenteArea", "PuntosDeFuente"]

_RADIO_TIERRA_KM = 6371.0


@dataclass(frozen=True)
class DistribucionMagnitudes:
    """Gutenberg-Richter truncada entre ``m_min`` y ``m_max``.

    La densidad de magnitudes es

    .. math::
        f(m) = \\frac{\\beta e^{-\\beta (m - m_{min})}}
                     {1 - e^{-\\beta (m_{max} - m_{min})}},
        \\qquad \\beta = b \\ln 10

    y la tasa total de eventos con :math:`m \\ge m_{min}` es ``tasa_total``.
    """

    tasa_total: Cantidad     # eventos/ano con m >= m_min
    b: Cantidad
    m_min: float
    m_max: Cantidad

    def __post_init__(self) -> None:
        for nombre, c in (("tasa_total", self.tasa_total), ("b", self.b),
                          ("m_max", self.m_max)):
            if not isinstance(c, Cantidad):
                raise TypeError(
                    f"'{nombre}' debe ser una Cantidad con procedencia declarada, no "
                    f"{type(c).__name__}. En PSHA, un numero sin procedencia es un bug: "
                    "m_max en particular es el parametro peor restringido del calculo."
                )
        if self.m_max.valor <= self.m_min:
            raise ValueError(f"m_max ({self.m_max.valor}) debe superar m_min ({self.m_min})")
        if self.tasa_total.valor <= 0:
            raise ValueError("la tasa total debe ser positiva")

    @property
    def beta(self) -> float:
        return self.b.valor * math.log(10.0)

    def tasas_por_bin(self, dm: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
        """Tasa anual de eventos en cada bin de magnitud.

        Devuelve ``(centros, tasas)``. La suma de ``tasas`` es exactamente
        ``tasa_total``: la discretizacion no pierde ni inventa eventos.
        """
        bordes = np.arange(self.m_min, self.m_max.valor + dm / 2, dm)
        # El ultimo borde puede pasarse de m_max cuando dm no divide al rango.
        # Recortarlo NO es cosmetico: sin recortar, la masa acumulada supera 1 y
        # la discretizacion inventa eventos por encima de la magnitud maxima.
        bordes = bordes[bordes < self.m_max.valor - 1e-12]
        bordes = np.append(bordes, self.m_max.valor)
        if bordes.size < 2:
            raise ValueError(
                f"dm={dm} es demasiado grande para el rango [{self.m_min}, "
                f"{self.m_max.valor}]"
            )
        centros = 0.5 * (bordes[:-1] + bordes[1:])
        beta, m0, m1 = self.beta, self.m_min, self.m_max.valor
        norm = 1.0 - math.exp(-beta * (m1 - m0))
        # Masa acumulada exacta en cada bin (no la densidad por el ancho).
        acum = (1.0 - np.exp(-beta * (bordes - m0))) / norm
        masa = np.diff(acum)
        return centros, self.tasa_total.valor * masa

    def momento_anual_nm(self, dm: float = 0.05) -> float:
        """Tasa anual de momento sismico liberado, en N m/ano.

        Usa la relacion de Hanks-Kanamori ``log10 M0 = 1.5 Mw + 9.1`` (definicion,
        no regresion). Sirve para contrastar la tasa sismica declarada con el
        presupuesto geodesico de momento (ver :mod:`sismolat.tectonica.momento`).
        """
        centros, tasas = self.tasas_por_bin(dm)
        m0 = np.power(10.0, 1.5 * centros + 9.1)
        return float(np.sum(tasas * m0))

    def advertencias(self) -> list[str]:
        avisos = []
        if self.m_max.procedencia.es_debil:
            avisos.append(
                f"m_max = {self.m_max.valor:g} tiene procedencia "
                f"{self.m_max.procedencia.value}. Es el parametro que mas influye en la "
                "cola del peligro y el peor restringido: usalo como rama del arbol "
                "logico con varios valores y pesos, no como un numero unico."
            )
        if self.m_max.incertidumbre is None:
            avisos.append("m_max no declara incertidumbre.")
        if self.b.incertidumbre is None:
            avisos.append("b no declara incertidumbre; el peligro es sensible a b.")
        return avisos


@dataclass(frozen=True)
class PuntosDeFuente:
    """Fuentes puntuales resultantes de discretizar una fuente de area."""

    lon: np.ndarray
    lat: np.ndarray
    prof_km: np.ndarray
    peso: np.ndarray          # fraccion de la tasa total en cada punto (suma = 1)

    def distancias_km(self, sitio_lon: float, sitio_lat: float) -> np.ndarray:
        """Distancia 3D desde un sitio en superficie a cada fuente puntual."""
        p1 = math.radians(sitio_lat)
        p2 = np.radians(self.lat)
        dlat = p2 - p1
        dlon = np.radians(self.lon - sitio_lon)
        a = np.sin(dlat / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
        horiz = 2 * _RADIO_TIERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        return np.sqrt(horiz ** 2 + self.prof_km ** 2)


@dataclass(frozen=True)
class FuenteArea:
    """Fuente sismogenica de area, discretizada en fuentes puntuales.

    Parametros
    ----------
    caja:
        ``(lon_min, lon_max, lat_min, lat_max)`` en grados.
    profundidades_km:
        Profundidades a las que se reparte la sismicidad.
    pesos_profundidad:
        Fraccion de la tasa en cada profundidad. Si es ``None``, uniforme.
    """

    nombre: str
    caja: tuple[float, float, float, float]
    profundidades_km: tuple[float, ...]
    regimen: RegimenTectonico
    magnitudes: DistribucionMagnitudes
    paso_grados: float = 0.2
    pesos_profundidad: tuple[float, ...] | None = None
    notas: str = ""

    def __post_init__(self) -> None:
        if not self.profundidades_km:
            raise ValueError("se requiere al menos una profundidad")
        if any(p < 0 for p in self.profundidades_km):
            raise ValueError("las profundidades deben ser no negativas")
        if self.pesos_profundidad is not None:
            if len(self.pesos_profundidad) != len(self.profundidades_km):
                raise ValueError("pesos_profundidad debe tener la misma longitud")
            if abs(sum(self.pesos_profundidad) - 1.0) > 1e-9:
                raise ValueError(
                    f"los pesos de profundidad suman {sum(self.pesos_profundidad)}, "
                    "deben sumar 1"
                )
        lon0, lon1, lat0, lat1 = self.caja
        if lon1 <= lon0 or lat1 <= lat0:
            raise ValueError("caja mal formada: se espera (lon_min, lon_max, lat_min, lat_max)")

    def discretizar(self) -> PuntosDeFuente:
        """Rejilla de fuentes puntuales con sus pesos.

        Los pesos horizontales se ponderan por el **area real** de cada celda
        (corregida por el coseno de la latitud), no por conteo de celdas: una
        rejilla regular en grados no es equiarea y usarla sin corregir concentra
        artificialmente la tasa hacia latitudes altas.
        """
        lon0, lon1, lat0, lat1 = self.caja
        paso = self.paso_grados
        clon = np.arange(lon0 + paso / 2, lon1, paso)
        clat = np.arange(lat0 + paso / 2, lat1, paso)
        if clon.size == 0 or clat.size == 0:
            raise ValueError(
                f"paso_grados={paso} es demasiado grande para la caja {self.caja}"
            )
        gl, ga = np.meshgrid(clon, clat, indexing="ij")
        area = np.cos(np.radians(ga))          # proporcional al area real de la celda
        pesos_h = (area / area.sum()).ravel()

        pz = (np.array(self.pesos_profundidad, dtype=float)
              if self.pesos_profundidad is not None
              else np.full(len(self.profundidades_km), 1.0 / len(self.profundidades_km)))

        lon = np.tile(gl.ravel(), len(self.profundidades_km))
        lat = np.tile(ga.ravel(), len(self.profundidades_km))
        prof = np.repeat(np.array(self.profundidades_km, dtype=float), pesos_h.size)
        peso = np.concatenate([pesos_h * w for w in pz])
        return PuntosDeFuente(lon=lon, lat=lat, prof_km=prof, peso=peso)

    def advertencias(self) -> list[str]:
        avisos = list(self.magnitudes.advertencias())
        avisos.append(
            f"'{self.nombre}' se trata como fuente PUNTUAL discretizada. Para magnitudes "
            "grandes, cuya ruptura mide decenas o centenares de km, esto sobreestima el "
            "movimiento cerca de la fuente y lo subestima lejos. No modela rupturas finitas."
        )
        return avisos
