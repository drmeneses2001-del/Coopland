"""Representacion de pronosticos evaluables.

Dos representaciones, porque las pruebas correctas son distintas
---------------------------------------------------------------
* :class:`PronosticoRejilla` -- tasas esperadas por celda espacial y bin de
  magnitud, con supuesto **poissoniano**. Es el formato clasico de CSEP y el
  adecuado para modelos de tasa (Poisson homogeneo, sismicidad suavizada).

* :class:`PronosticoCatalogo` -- una coleccion de catalogos simulados del
  modelo. Es el formato adecuado para modelos **autoexcitados** como ETAS.

Por que la distincion no es opcional
------------------------------------
Un pronostico ETAS es **sobredisperso** respecto a Poisson: el numero de
eventos en la ventana tiene varianza mucho mayor que su media, porque una sola
secuencia grande puede dominar el conteo. Aplicarle una prueba N poissoniana
produce **rechazos espurios**: el modelo se declara fallido por una
sobredispersion que el modelo mismo predice correctamente.

Por eso :meth:`PronosticoRejilla.desde_simulaciones` exige declarar
explicitamente que se acepta el supuesto de Poisson, y las pruebas del modulo
:mod:`sismolat.evaluacion.csep` rechazan aplicar la version poissoniana a un
pronostico basado en catalogo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

__all__ = ["Rejilla", "PronosticoRejilla", "PronosticoCatalogo", "ErrorDeSupuesto"]


class ErrorDeSupuesto(RuntimeError):
    """Se intento aplicar una prueba cuyo supuesto no corresponde al pronostico."""


@dataclass(frozen=True)
class Rejilla:
    """Rejilla regular en longitud/latitud y magnitud.

    Advertencia de area
    -------------------
    Una rejilla regular en grados **no es equiarea**: a 20 N una celda de
    0.1x0.1 grados tiene aproximadamente un 6% menos de area que en el ecuador,
    y la diferencia crece con la latitud. Para tasas por unidad de area, usar
    :attr:`areas_km2`, que corrige el coseno de la latitud. Para comparaciones
    dentro de una region estrecha en latitud el efecto es pequeno, pero debe
    declararse.
    """

    lon_bordes: np.ndarray
    lat_bordes: np.ndarray
    mag_bordes: np.ndarray

    @property
    def forma(self) -> tuple[int, int, int]:
        return (self.lon_bordes.size - 1, self.lat_bordes.size - 1, self.mag_bordes.size - 1)

    @property
    def n_celdas_espaciales(self) -> int:
        return (self.lon_bordes.size - 1) * (self.lat_bordes.size - 1)

    @property
    def areas_km2(self) -> np.ndarray:
        """Area de cada celda espacial, con la correccion por latitud. Forma (nlon, nlat)."""
        r = 6371.0
        dlon = np.radians(np.diff(self.lon_bordes))
        s = np.sin(np.radians(self.lat_bordes))
        dlat_area = np.diff(s)
        return np.outer(dlon, dlat_area) * r ** 2

    def indexar(self, lon, lat, mag) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Indices de celda de cada evento y mascara de los que caen dentro."""
        i = np.digitize(np.asarray(lon, float), self.lon_bordes) - 1
        j = np.digitize(np.asarray(lat, float), self.lat_bordes) - 1
        k = np.digitize(np.asarray(mag, float), self.mag_bordes) - 1
        nl, na, nm = self.forma
        dentro = (i >= 0) & (i < nl) & (j >= 0) & (j < na) & (k >= 0) & (k < nm)
        return i, j, k, dentro

    def contar(self, df: pd.DataFrame, *, columna_mag: str = "mag") -> np.ndarray:
        """Conteo observado por celda. Forma (nlon, nlat, nmag)."""
        i, j, k, dentro = self.indexar(df["lon"], df["lat"], df[columna_mag])
        conteo = np.zeros(self.forma)
        np.add.at(conteo, (i[dentro], j[dentro], k[dentro]), 1.0)
        return conteo

    @classmethod
    def regular(
        cls, caja: tuple[float, float, float, float], paso: float,
        mag_min: float, mag_max: float, paso_mag: float = 0.1,
    ) -> "Rejilla":
        lon0, lon1, lat0, lat1 = caja
        return cls(
            lon_bordes=np.arange(lon0, lon1 + paso / 2, paso),
            lat_bordes=np.arange(lat0, lat1 + paso / 2, paso),
            mag_bordes=np.round(np.arange(mag_min, mag_max + paso_mag / 2, paso_mag), 6),
        )


@dataclass(frozen=True)
class PronosticoRejilla:
    """Tasas esperadas por celda con supuesto poissoniano.

    ``tasas`` tiene forma ``rejilla.forma`` y unidades de *numero esperado de
    eventos en la ventana* (no por unidad de tiempo).
    """

    rejilla: Rejilla
    tasas: np.ndarray
    nombre: str
    ventana_dias: float
    #: Declara si el supuesto de Poisson es defendible para este modelo.
    poisson_valido: bool = True
    notas: str = ""

    def __post_init__(self) -> None:
        if self.tasas.shape != self.rejilla.forma:
            raise ValueError(
                f"tasas con forma {self.tasas.shape} no coincide con la rejilla "
                f"{self.rejilla.forma}"
            )
        if np.any(self.tasas < 0):
            raise ValueError("hay tasas negativas")

    @property
    def total(self) -> float:
        return float(self.tasas.sum())

    @property
    def espacial(self) -> np.ndarray:
        """Tasas marginalizadas sobre magnitud. Forma (nlon, nlat)."""
        return self.tasas.sum(axis=2)

    @property
    def magnitud(self) -> np.ndarray:
        """Tasas marginalizadas sobre el espacio. Forma (nmag,)."""
        return self.tasas.sum(axis=(0, 1))

    def normalizado_a(self, n: float) -> "PronosticoRejilla":
        """Reescala para que el total sea ``n``. Usado por las pruebas S y M."""
        if self.total <= 0:
            raise ValueError("no se puede normalizar un pronostico de tasa total nula")
        return PronosticoRejilla(
            self.rejilla, self.tasas * (n / self.total), f"{self.nombre}|normalizado",
            self.ventana_dias, self.poisson_valido, self.notas,
        )


@dataclass(frozen=True)
class PronosticoCatalogo:
    """Coleccion de catalogos simulados del modelo.

    Es la representacion correcta para modelos autoexcitados. Las pruebas
    construyen la distribucion de referencia por simulacion en lugar de
    suponerla poissoniana.
    """

    catalogos: Sequence[pd.DataFrame]
    rejilla: Rejilla
    nombre: str
    ventana_dias: float
    semilla: int | None = None
    notas: str = ""

    def __post_init__(self) -> None:
        if len(self.catalogos) < 100:
            raise ValueError(
                f"solo {len(self.catalogos)} catalogos simulados. Las pruebas basadas en "
                "catalogo necesitan al menos ~100 para que los cuantiles empiricos tengan "
                "resolucion util; para p-valores en la cola, varios miles."
            )

    @property
    def n_simulaciones(self) -> int:
        return len(self.catalogos)

    def conteos_totales(self) -> np.ndarray:
        """Numero de eventos dentro de la rejilla en cada catalogo simulado."""
        salida = np.empty(len(self.catalogos))
        for s, cat in enumerate(self.catalogos):
            _, _, _, dentro = self.rejilla.indexar(cat["lon"], cat["lat"], cat["mag"])
            salida[s] = float(dentro.sum())
        return salida

    def tasa_media(self) -> PronosticoRejilla:
        """Media de los conteos simulados por celda.

        Devuelve un :class:`PronosticoRejilla` con ``poisson_valido=False``: la
        media es correcta, pero su dispersion **no** es poissoniana y las
        pruebas que lo supongan estaran mal calibradas.
        """
        acumulado = np.zeros(self.rejilla.forma)
        for cat in self.catalogos:
            acumulado += self.rejilla.contar(cat)
        return PronosticoRejilla(
            self.rejilla, acumulado / len(self.catalogos), f"{self.nombre}|media",
            self.ventana_dias, poisson_valido=False,
            notas=("Media de catalogos simulados de un modelo autoexcitado. La varianza real "
                   "por celda excede la poissoniana; usa las pruebas basadas en catalogo."),
        )

    def dispersion_relativa(self) -> float:
        """var(N)/media(N). Vale 1 bajo Poisson; mucho mas bajo ETAS.

        Es el diagnostico que justifica no usar las pruebas poissonianas.
        """
        n = self.conteos_totales()
        media = float(n.mean())
        return float(n.var(ddof=1) / media) if media > 0 else float("nan")
