"""Sismicidad suavizada: el modelo de referencia espacial serio.

Por que hace falta
------------------
Un Poisson espacialmente uniforme es un rival trivial: casi cualquier cosa lo
supera, y una ganancia medida contra el no dice si el modelo tiene destreza real.
El modelo de referencia con el que se comparan los pronosticos en la practica es
la **sismicidad suavizada**: la hipotesis de que los sismos futuros ocurriran
donde ocurrieron los pasados.

Es un rival exigente. Buena parte de los modelos publicados apenas lo superan, y
un modelo que no lo supere no ha demostrado nada.

La matematica
-------------
Se coloca un nucleo sobre cada epicentro del catalogo de entrenamiento y se suma:

.. math::
    \\lambda(x, y) \\propto \\sum_i \\frac{1}{2\\pi\\sigma_i^2}
        \\exp\\!\\left(-\\frac{d_i(x,y)^2}{2\\sigma_i^2}\\right)

Con **ancho fijo**, todos los ``sigma_i`` son iguales. Con **ancho adaptativo**,
``sigma_i`` es la distancia al k-esimo vecino mas cercano del evento ``i``: el
nucleo se estrecha donde la sismicidad es densa y se ensancha donde es escasa,
lo que resuelve el problema de que un ancho unico sobresuavice los racimos y
subsuavice las zonas vacias.

Supuestos y condiciones de validez
----------------------------------
* **La sismicidad futura ocurre donde la pasada.** Es exactamente la hipotesis
  que el modelo encarna, y es falsa en el caso que mas importa: los sismos
  grandes en brechas sismicas, por definicion, ocurren donde no ha habido
  sismicidad reciente.
* **Sobre catalogo declusterizado** si el pronostico va a evaluarse con pruebas
  poissonianas. Suavizar el catalogo completo mete las replicas del pasado en el
  mapa de fondo y concentra el pronostico donde hubo secuencias, que es
  precisamente donde es menos probable que se repitan a medio plazo.
* **El ancho del nucleo no es libre**: elegirlo mirando el periodo de prueba es
  fuga de informacion. :func:`optimizar_ancho` solo acepta datos anteriores al
  corte y lo comprueba.

Lo que este modulo NO puede hacer
---------------------------------
* No incorpora geometria de fallas, tasas de deslizamiento ni geodesia. Es un
  modelo puramente empirico sobre el catalogo.
* No extrapola a magnitudes por encima de las observadas: la distribucion de
  magnitudes es G-R con el b que se le pase, y el problema del Mmax queda fuera.
* No dice nada sobre **cuando**. Es un pronostico de tasa media.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..evaluacion.pronostico import PronosticoRejilla, Rejilla
from ..procedencia import Cantidad, Procedencia, supuesto

__all__ = [
    "campo_suavizado", "anchos_adaptativos", "pronostico_suavizado",
    "optimizar_ancho", "ResultadoOptimizacion", "PISO_RELATIVO_POR_DEFECTO",
]

_RADIO_TIERRA_KM = 6371.0

#: Fraccion de la tasa total que se reparte uniformemente por la region.
#:
#: Sin este piso, una celda sin sismicidad historica recibe tasa cero, y un solo
#: evento alli produce log-verosimilitud -infinito: el modelo declaro imposible
#: algo que ocurrio. Ningun pronostico honesto afirma imposibilidad absoluta
#: sobre la base de unas decadas de catalogo.
#:
#: El valor es un SUPUESTO y **afecta al resultado**: un piso mas alto acerca el
#: modelo al uniforme y reduce tanto su ganancia potencial como su riesgo de
#: catastrofe. Debe reportarse y conviene comprobar la sensibilidad.
PISO_RELATIVO_POR_DEFECTO = supuesto(
    0.01, "adimensional",
    motivo=(
        "piso uniforme del 1% de la tasa total para evitar celdas de probabilidad cero. "
        "No calibrado: es una eleccion de quien analiza, no un valor derivado."
    ),
)


def _distancias_km(lon_a, lat_a, lon_b, lat_b) -> np.ndarray:
    """Matriz de distancias de circulo maximo (km) entre dos conjuntos de puntos."""
    la = np.radians(np.asarray(lat_a, float))[:, None]
    lb = np.radians(np.asarray(lat_b, float))[None, :]
    dla = lb - la
    dlo = np.radians(np.asarray(lon_b, float))[None, :] - np.radians(np.asarray(lon_a, float))[:, None]
    a = np.sin(dla / 2) ** 2 + np.cos(la) * np.cos(lb) * np.sin(dlo / 2) ** 2
    return 2 * _RADIO_TIERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def anchos_adaptativos(
    lon: np.ndarray, lat: np.ndarray, *, k_vecinos: int = 5, ancho_min_km: float = 2.0,
) -> np.ndarray:
    """Ancho de nucleo por evento: distancia al k-esimo vecino mas cercano.

    Estrecha el nucleo donde la sismicidad es densa y lo ensancha donde es
    escasa. ``ancho_min_km`` evita que dos epicentros practicamente coincidentes
    produzcan un nucleo de anchura cero, que concentraria toda la masa en una
    celda.
    """
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    n = lon.size
    if n == 0:
        return np.array([])
    if n <= k_vecinos:
        return np.full(n, float(ancho_min_km))
    d = _distancias_km(lon, lat, lon, lat)
    np.fill_diagonal(d, np.inf)
    # k-esima distancia mas pequena de cada fila.
    kth = np.partition(d, k_vecinos - 1, axis=1)[:, k_vecinos - 1]
    return np.maximum(kth, ancho_min_km)


def campo_suavizado(
    lon: np.ndarray,
    lat: np.ndarray,
    rejilla: Rejilla,
    *,
    ancho_km: float | np.ndarray,
    pesos: np.ndarray | None = None,
    trozo: int = 500,
) -> np.ndarray:
    """Campo espacial suavizado, en masa por celda (suma = suma de los pesos).

    ``ancho_km`` puede ser un escalar (ancho fijo) o un arreglo por evento
    (ancho adaptativo, ver :func:`anchos_adaptativos`).

    ``pesos`` permite que cada evento aporte una masa distinta de 1. Lo usa el
    decluster estocastico (:mod:`sismolat.modelos.decluster_estocastico`), donde
    cada evento contribuye al mapa de fondo en proporcion a su **probabilidad de
    ser un evento de fondo**, en lugar de contarse entero o descartarse entero.
    Con ``pesos=None`` cada evento aporta 1 y la suma es el numero de eventos.

    Normalizacion por evento
    ------------------------
    El nucleo de cada evento se **renormaliza sobre la rejilla**, de modo que
    cada evento aporta exactamente masa 1 aunque su nucleo se salga del borde.
    La alternativa —dejar que la masa se pierda fuera— haria que el pronostico
    total fuera menor que el numero de eventos y sesgaria las tasas cerca del
    borde. La renormalizacion distorsiona ligeramente la forma en el borde; es
    el mal menor y queda declarado aqui.
    """
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    n = lon.size
    nlon, nlat, _ = rejilla.forma
    if n == 0:
        raise ValueError("no hay eventos que suavizar")

    cx = 0.5 * (rejilla.lon_bordes[:-1] + rejilla.lon_bordes[1:])
    cy = 0.5 * (rejilla.lat_bordes[:-1] + rejilla.lat_bordes[1:])
    gx, gy = np.meshgrid(cx, cy, indexing="ij")
    gx, gy = gx.ravel(), gy.ravel()

    anchos = np.full(n, float(ancho_km)) if np.isscalar(ancho_km) else np.asarray(ancho_km, float)
    if anchos.size != n:
        raise ValueError(f"ancho_km tiene {anchos.size} valores para {n} eventos")
    if np.any(anchos <= 0):
        raise ValueError("todos los anchos deben ser positivos")

    w = np.ones(n) if pesos is None else np.asarray(pesos, dtype=float)
    if w.size != n:
        raise ValueError(f"pesos tiene {w.size} valores para {n} eventos")
    if np.any(w < 0):
        raise ValueError("los pesos deben ser no negativos")

    campo = np.zeros(gx.size)
    for ini in range(0, n, trozo):
        fin = min(ini + trozo, n)
        d = _distancias_km(lon[ini:fin], lat[ini:fin], gx, gy)   # (m_eventos, n_celdas)
        s = anchos[ini:fin][:, None]
        k = np.exp(-0.5 * (d / s) ** 2)
        suma = k.sum(axis=1, keepdims=True)
        # Un evento cuyo nucleo no alcanza ninguna celda (muy estrecho y lejos)
        # se asigna integro a la celda mas proxima, en vez de perderse.
        vacio = (suma[:, 0] <= 0)
        if np.any(vacio):
            k[vacio] = 0.0
            k[vacio, np.argmin(d[vacio], axis=1)] = 1.0
            suma[vacio, 0] = 1.0
        campo += ((k / suma) * w[ini:fin, None]).sum(axis=0)
    return campo.reshape(nlon, nlat)


def pronostico_suavizado(
    df_entrenamiento: pd.DataFrame,
    rejilla: Rejilla,
    *,
    b: float,
    dias_entrenamiento: float,
    dias_pronostico: float,
    ancho_km: float | None = None,
    k_vecinos: int | None = 5,
    ancho_min_km: float = 2.0,
    piso_relativo: Cantidad | None = None,
    columna_mag: str = "mag",
    nombre: str = "sismicidad suavizada",
) -> PronosticoRejilla:
    """Pronostico de referencia por sismicidad suavizada, con magnitudes G-R.

    Se da **o** ``ancho_km`` (ancho fijo) **o** ``k_vecinos`` (adaptativo), no
    ambos.

    La distribucion de magnitudes es Gutenberg-Richter con el ``b`` que se pase,
    lo que hace de este un rival justo: una referencia uniforme tambien en
    magnitud seria un hombre de paja, porque cualquier modelo que solo acierte la
    forma de la FMD la superaria sin tener destreza espacial alguna.

    La tasa se escala de ``dias_entrenamiento`` a ``dias_pronostico`` suponiendo
    **estacionariedad**: que la tasa media no cambia entre ambos periodos. Es un
    supuesto fuerte y comprobable a posteriori con el N-test.
    """
    if (ancho_km is None) == (k_vecinos is None):
        raise ValueError(
            "da exactamente uno: ancho_km (nucleo fijo) o k_vecinos (nucleo adaptativo)"
        )
    piso_relativo = piso_relativo or PISO_RELATIVO_POR_DEFECTO
    d = df_entrenamiento.dropna(subset=["lon", "lat", columna_mag])
    n_ev = len(d)
    if n_ev == 0:
        raise ValueError("el catalogo de entrenamiento esta vacio")

    lon = d["lon"].to_numpy(float)
    lat = d["lat"].to_numpy(float)
    if k_vecinos is not None:
        anchos = anchos_adaptativos(lon, lat, k_vecinos=k_vecinos, ancho_min_km=ancho_min_km)
        etiqueta_ancho = f"adaptativo k={k_vecinos} (mediana {np.median(anchos):.1f} km)"
    else:
        anchos = float(ancho_km)
        etiqueta_ancho = f"fijo {ancho_km:g} km"

    espacial = campo_suavizado(lon, lat, rejilla, ancho_km=anchos)
    espacial = espacial / espacial.sum()

    # Piso uniforme para que ninguna celda tenga probabilidad exactamente cero.
    n_celdas = espacial.size
    espacial = (1.0 - piso_relativo.valor) * espacial + piso_relativo.valor / n_celdas

    # Distribucion de magnitudes G-R sobre los bins de la rejilla.
    centros = 0.5 * (rejilla.mag_bordes[:-1] + rejilla.mag_bordes[1:])
    ancho_mag = np.diff(rejilla.mag_bordes)
    beta = b * math.log(10.0)
    peso_mag = np.exp(-beta * (centros - rejilla.mag_bordes[0])) * ancho_mag
    peso_mag = peso_mag / peso_mag.sum()

    escala = dias_pronostico / dias_entrenamiento
    tasas = (n_ev * escala) * espacial[:, :, None] * peso_mag[None, None, :]

    return PronosticoRejilla(
        rejilla, tasas, f"{nombre} [{etiqueta_ancho}]", dias_pronostico,
        poisson_valido=True,
        notas=(
            f"n_entrenamiento={n_ev}, escala temporal={escala:.3f}, b={b:.3f}, "
            f"piso relativo={piso_relativo.valor:g} [{piso_relativo.procedencia.value}]. "
            "Supone estacionariedad de la tasa entre entrenamiento y pronostico."
        ),
    )


@dataclass(frozen=True)
class ResultadoOptimizacion:
    """Ancho de nucleo elegido por verosimilitud, con la traza de la busqueda."""

    mejor: float
    parametro: str
    candidatos: np.ndarray
    log_verosimilitudes: np.ndarray
    corte_interno: pd.Timestamp
    advertencias: tuple[str, ...] = ()

    def __str__(self) -> str:
        return (f"{self.parametro} optimo = {self.mejor:g} "
                f"(entre {self.candidatos.min():g} y {self.candidatos.max():g}, "
                f"corte interno {self.corte_interno.date()})")


def optimizar_ancho(
    df_entrenamiento: pd.DataFrame,
    rejilla: Rejilla,
    *,
    b: float,
    candidatos: np.ndarray,
    adaptativo: bool = True,
    fraccion_ajuste: float = 0.7,
    columna_mag: str = "mag",
    columna_tiempo: str = "tiempo",
) -> ResultadoOptimizacion:
    """Elige el ancho de nucleo por verosimilitud, **sin tocar el periodo de prueba**.

    El entrenamiento se parte internamente en dos por un corte temporal: la
    primera fraccion construye el campo suavizado y la segunda lo puntua. Asi la
    eleccion del ancho usa solo informacion anterior al corte principal.

    Elegir el ancho mirando el periodo de prueba es fuga de informacion, y es una
    de las formas mas comunes de inflar el desempeno aparente de un modelo de
    pronostico. Esta funcion no puede acceder al periodo de prueba porque no lo
    recibe: la salvaguarda es estructural, no una comprobacion posterior.
    """
    from ..evaluacion.csep import log_verosimilitud_poisson

    d = df_entrenamiento.dropna(subset=["lon", "lat", columna_mag]).sort_values(columna_tiempo)
    if len(d) < 50:
        raise ValueError(f"solo {len(d)} eventos: insuficiente para partir y optimizar")
    t0, t1 = d[columna_tiempo].min(), d[columna_tiempo].max()
    corte = t0 + (t1 - t0) * fraccion_ajuste
    ajuste = d[d[columna_tiempo] <= corte]
    puntua = d[d[columna_tiempo] > corte]
    if len(ajuste) < 20 or len(puntua) < 10:
        raise ValueError(
            f"la particion interna deja {len(ajuste)} y {len(puntua)} eventos: "
            "insuficiente. Amplia el periodo de entrenamiento o cambia fraccion_ajuste."
        )

    dias_ajuste = (corte - t0) / pd.Timedelta(days=1)
    dias_puntua = (t1 - corte) / pd.Timedelta(days=1)
    conteos = rejilla.contar(puntua, columna_mag=columna_mag)

    lls = []
    for c in candidatos:
        kw = {"k_vecinos": int(c)} if adaptativo else {"ancho_km": float(c), "k_vecinos": None}
        pron = pronostico_suavizado(
            ajuste, rejilla, b=b, dias_entrenamiento=dias_ajuste,
            dias_pronostico=dias_puntua, columna_mag=columna_mag, **kw,
        )
        lls.append(log_verosimilitud_poisson(pron.tasas, conteos))
    lls = np.array(lls, dtype=float)

    if not np.any(np.isfinite(lls)):
        raise ValueError("ningun candidato produjo verosimilitud finita")
    mejor = float(candidatos[int(np.nanargmax(np.where(np.isfinite(lls), lls, -np.inf)))])

    avisos = []
    finitos = lls[np.isfinite(lls)]
    if finitos.size and (finitos.max() - finitos.min()) < 1.0:
        avisos.append(
            "La verosimilitud apenas varia entre candidatos: el ancho esta mal determinado "
            "por estos datos. Cualquier valor del rango es defendible; no reportes el optimo "
            "como si estuviera bien restringido."
        )
    if mejor in (candidatos[0], candidatos[-1]):
        avisos.append(
            f"El optimo ({mejor:g}) cae en un extremo del rango probado. Amplia los "
            "candidatos: el verdadero optimo puede estar fuera."
        )
    return ResultadoOptimizacion(
        mejor=mejor, parametro="k_vecinos" if adaptativo else "ancho_km",
        candidatos=np.asarray(candidatos, float), log_verosimilitudes=lls,
        corte_interno=corte, advertencias=tuple(avisos),
    )
