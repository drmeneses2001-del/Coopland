"""Homogenizacion de magnitudes con propagacion del error de conversion.

Lo esencial
-----------
Convertir entre escalas de magnitud **no es cambiar de unidad**: es aplicar una
regresion empirica con dispersion residual. Tratarla como exacta es el error mas
frecuente en el tratamiento de catalogos, y sus consecuencias son concretas:

* El error de conversion (tipicamente 0.2-0.3 unidades) suele ser **mayor** que
  el error de la magnitud original y que el error estadistico de b. Propagarlo
  cambia los intervalos de confianza de todo lo que venga despues.
* Aplicar una regresion fuera de su rango de calibracion es extrapolar. Las
  escalas **saturan** (ML y mb dejan de crecer con el tamano real del sismo),
  asi que una regresion ajustada entre 4 y 6 no dice nada a 7.5.
* Las agencias cambian de escala a lo largo del tiempo sin documentarlo bien.
  El resultado son **saltos artificiales** en la serie que se confunden con
  cambios reales de tasa.

Este modulo nunca sobrescribe ``mag``: escribe en ``mag_homog``,
``mag_homog_sigma`` y ``mag_homog_metodo``, de modo que la magnitud reportada
por la agencia siempre pueda recuperarse.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "Conversion", "cargar_conversiones", "homogenizar", "momento_a_mw",
    "ErrorDeConversionNoVerificada",
]

_RUTA = Path(__file__).resolve().parents[3] / "parametros" / "conversiones_magnitud.toml"


class ErrorDeConversionNoVerificada(RuntimeError):
    """Se intento convertir con una regresion no verificada."""


@dataclass(frozen=True)
class Conversion:
    """Regresion lineal ``M_destino = a + b * M_origen`` con dispersion ``sigma``."""

    clave: str
    escala_origen: str
    escala_destino: str
    a: float
    b: float
    sigma: float
    rango_min: float
    rango_max: float
    fuente: str
    verificado: bool
    activo: bool
    doi: str = ""
    region_calibracion: str = ""
    notas: str = ""

    def aplicar(self, m: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Devuelve ``(convertida, sigma, dentro_de_rango)``.

        ``sigma`` es la dispersion residual de la regresion. Si la agencia
        publicaba una incertidumbre de la magnitud original, hay que sumarla en
        cuadratura aparte: esta funcion solo aporta el error de la conversion.
        """
        m = np.asarray(m, dtype=float)
        convertida = self.a + self.b * m
        sigma = np.full(m.shape, self.sigma, dtype=float)
        dentro = (m >= self.rango_min) & (m <= self.rango_max)
        return convertida, sigma, dentro


def cargar_conversiones(*, ruta: Path | None = None) -> dict[str, Conversion]:
    """Carga todas las conversiones declaradas, activas o no."""
    ruta = ruta or _RUTA
    with open(ruta, "rb") as fh:
        todo = tomllib.load(fh)
    salida = {}
    for clave, d in todo.items():
        salida[clave] = Conversion(
            clave=clave, escala_origen=d.get("escala_origen", ""),
            escala_destino=d.get("escala_destino", ""),
            a=float(d.get("a", 0.0)), b=float(d.get("b", 1.0)),
            sigma=float(d.get("sigma", 0.0)),
            rango_min=float(d.get("rango_min", 0.0)),
            rango_max=float(d.get("rango_max", 0.0)),
            fuente=d.get("fuente", ""), verificado=bool(d.get("verificado", False)),
            activo=bool(d.get("activo", False)), doi=d.get("doi", ""),
            region_calibracion=d.get("region_calibracion", ""), notas=d.get("notas", ""),
        )
    return salida


def momento_a_mw(m0_nm: np.ndarray) -> np.ndarray:
    """Convierte momento sismico (N m) a Mw por la relacion de Hanks-Kanamori.

    .. math:: M_w = \\frac{2}{3}\\left(\\log_{10} M_0 - 9.1\\right)

    A diferencia de las conversiones entre escalas empiricas, esta **es una
    definicion**, no una regresion: no lleva error propio. Lo que sí tiene error
    es el momento sismico estimado por la inversion, que debe propagarse aparte:

    .. math:: \\sigma_{M_w} = \\frac{2}{3 \\ln 10} \\frac{\\sigma_{M_0}}{M_0}

    La constante 9.1 depende del convenio de unidades (N m frente a dyn cm) y de
    la version de la definicion. Se usa el convenio en N m; comprobar cual usa el
    catalogo de origen antes de aplicar esto.
    """
    m0 = np.asarray(m0_nm, dtype=float)
    if np.any(m0 <= 0):
        raise ValueError("el momento sismico debe ser positivo")
    return (2.0 / 3.0) * (np.log10(m0) - 9.1)


def homogenizar(
    df: pd.DataFrame,
    escala_destino: str = "Mw",
    *,
    conversiones: dict[str, Conversion] | None = None,
    permitir_no_verificado: bool = False,
    columna_mag: str = "mag",
    columna_escala: str = "mag_escala",
    escalas_equivalentes: tuple[str, ...] = ("Mw", "Mww", "Mwc", "Mwb", "Mwr"),
) -> tuple[pd.DataFrame, list[str]]:
    """Anade ``mag_homog``, ``mag_homog_sigma`` y ``mag_homog_metodo``.

    Nunca modifica ``mag`` ni ``mag_escala``.

    Los eventos cuya escala no tiene una conversion verificada quedan con
    ``mag_homog = NaN``. **Eso es lo correcto**: rellenarlos con la magnitud
    original como si ya estuviera en la escala destino es el error silencioso
    que este modulo existe para evitar.

    Devuelve ``(dataframe, advertencias)``.
    """
    conversiones = conversiones if conversiones is not None else cargar_conversiones()
    d = df.copy()
    n = len(d)
    homog = np.full(n, np.nan)
    sigma = np.full(n, np.nan)
    metodo = np.array([""] * n, dtype=object)
    avisos: list[str] = []

    escalas = d[columna_escala].astype(str)
    mags = d[columna_mag].to_numpy(float)

    # 1) Las escalas ya equivalentes al destino pasan sin conversion.
    ya = escalas.isin(escalas_equivalentes).to_numpy()
    homog[ya] = mags[ya]
    sigma[ya] = d["mag_sigma"].to_numpy(float)[ya] if "mag_sigma" in d.columns else np.nan
    metodo[ya] = "sin conversion (escala ya equivalente)"
    if ya.any():
        variantes = sorted(set(escalas[ya]))
        if len(variantes) > 1:
            avisos.append(
                f"Se tratan como equivalentes a {escala_destino} las escalas {variantes}. "
                "Son variantes del mismo momento tensor pero proceden de inversiones "
                "distintas y pueden diferir en algunas centesimas; si esa diferencia importa "
                "para tu analisis, no las mezcles."
            )

    # 2) El resto, por regresion declarada.
    usables = {
        c.escala_origen: c for c in conversiones.values()
        if c.activo and c.escala_destino == escala_destino
        and (c.verificado or permitir_no_verificado)
    }
    for escala_origen, conv in usables.items():
        sel = (escalas == escala_origen).to_numpy() & ~ya
        if not sel.any():
            continue
        convertida, s, dentro = conv.aplicar(mags[sel])
        idx = np.nonzero(sel)[0]
        homog[idx] = convertida
        sigma[idx] = s
        etiqueta = conv.clave + ("" if conv.verificado else " [NO VERIFICADA]")
        metodo[idx] = etiqueta
        fuera = int((~dentro).sum())
        if fuera:
            avisos.append(
                f"{fuera} eventos en escala {escala_origen} caen FUERA del rango de "
                f"calibracion [{conv.rango_min:g}, {conv.rango_max:g}] de la conversion "
                f"'{conv.clave}'. Convertirlos es extrapolar; las escalas saturan, asi que "
                "el error real ahi es mucho mayor que sigma."
            )
        if not conv.verificado:
            avisos.append(
                f"La conversion '{conv.clave}' NO esta verificada. Toda magnitud convertida "
                "con ella queda marcada como no verificada."
            )

    # 3) Lo que no se pudo convertir.
    sin_convertir = np.isnan(homog)
    if sin_convertir.any():
        faltan = sorted(set(escalas[sin_convertir]))
        avisos.append(
            f"{int(sin_convertir.sum())} eventos quedan SIN homogenizar por falta de una "
            f"conversion verificada para las escalas {faltan}. Se dejan como NaN a proposito: "
            "usarlos como si ya estuvieran en la escala destino introduce un sesgo silencioso. "
            f"Anade la regresion correspondiente en {_RUTA}."
        )

    if np.any(~np.isnan(homog)) and np.all(np.isnan(sigma[~np.isnan(homog)])):
        avisos.append(
            "Ninguna magnitud homogenizada tiene incertidumbre asociada. El error de la "
            "regresion suele dominar la incertidumbre final: no propagarlo hace que los "
            "intervalos de confianza de b, de las tasas y del peligro salgan demasiado "
            "estrechos."
        )

    d["mag_homog"] = homog
    d["mag_homog_sigma"] = sigma
    d["mag_homog_metodo"] = metodo
    return d, avisos
