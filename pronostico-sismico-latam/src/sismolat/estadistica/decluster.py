"""Decluster de catalogos: separacion entre sismicidad de fondo y racimos.

El decluster es una **decision metodologica, no un hecho**
--------------------------------------------------------
No existe una particion verdadera entre "sismo principal" y "replica": la
distincion la produce el algoritmo, no la naturaleza. Tres metodos sobre el
mismo catalogo eliminan fracciones de eventos que pueden diferir en un factor
de dos. Por eso :func:`comparar_metodos` no es un extra: es la forma correcta
de usar este modulo.

Para que sirve y para que no
----------------------------
* **Se usa** para obtener un catalogo aproximadamente poissoniano, que es lo
  que exige el PSHA clasico y lo que hace comparable la linea base de Poisson.
* **No se usa** antes de ajustar ETAS. ETAS modela explicitamente la parte que
  el decluster elimina; declusterizar primero destruye la senal que ETAS
  estima. Esta confusion es frecuente y la funcion :func:`advertir_uso` la
  senala.
* El valor **b estimado sobre catalogo declusterizado difiere** del estimado
  sobre el catalogo completo. Ninguno de los dos es "el correcto": dependen del
  proposito. La eleccion debe declararse.

Coeficientes
------------
Los coeficientes de las ventanas se cargan de ``parametros/ventanas_decluster.toml``
y estan marcados como **no verificados**. Ver la cabecera de ese archivo.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from ..catalogo import Catalogo

__all__ = [
    "ResultadoDecluster",
    "cargar_parametros",
    "gardner_knopoff",
    "zaliapin_ben_zion",
    "reasenberg",
    "comparar_metodos",
    "advertir_uso",
    "ErrorDeParametrosNoVerificados",
]

_RUTA_PARAMETROS = Path(__file__).resolve().parents[3] / "parametros" / "ventanas_decluster.toml"
_RADIO_TIERRA_KM = 6371.0


class ErrorDeParametrosNoVerificados(RuntimeError):
    """Se intento usar coeficientes marcados como no verificados sin autorizarlo."""


def cargar_parametros(
    metodo: str,
    *,
    permitir_no_verificado: bool = False,
    ruta: Path | None = None,
) -> dict:
    """Carga el bloque de parametros de un metodo, exigiendo verificacion explicita."""
    ruta = ruta or _RUTA_PARAMETROS
    with open(ruta, "rb") as fh:
        todo = tomllib.load(fh)
    if metodo not in todo:
        raise KeyError(f"no hay bloque '{metodo}' en {ruta}")
    bloque = todo[metodo]
    if not bloque.get("verificado", False) and not permitir_no_verificado:
        raise ErrorDeParametrosNoVerificados(
            f"Los coeficientes de '{metodo}' estan marcados como NO VERIFICADOS en {ruta}.\n"
            f"  fuente declarada : {bloque.get('fuente', '(sin declarar)')}\n"
            f"  que verificar    : {bloque.get('donde_verificar', '(sin declarar)')}\n"
            "Verificalos contra la publicacion original y pon verificado = true, o pasa "
            "permitir_no_verificado=True para continuar sabiendo que todo resultado derivado "
            "quedara marcado [NO-VERIFICADO]."
        )
    return bloque


def _distancia_km(lon1, lat1, lon2, lat2) -> np.ndarray:
    """Distancia de circulo maximo (haversine), en km."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * _RADIO_TIERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


@dataclass(frozen=True)
class ResultadoDecluster:
    """Particion del catalogo en fondo y racimos."""

    metodo: str
    #: Indices (posicionales en el catalogo original) considerados de fondo.
    indices_fondo: np.ndarray
    #: Etiqueta de racimo por evento; -1 = evento de fondo aislado.
    id_racimo: np.ndarray
    n_original: int
    parametros: dict
    verificado: bool
    advertencias: list[str]

    @property
    def n_fondo(self) -> int:
        return int(self.indices_fondo.size)

    @property
    def fraccion_eliminada(self) -> float:
        return 1.0 - self.n_fondo / self.n_original if self.n_original else 0.0

    @property
    def n_racimos(self) -> int:
        return int(len({c for c in self.id_racimo if c >= 0}))

    def aplicar(self, catalogo: Catalogo) -> Catalogo:
        """Devuelve el catalogo de fondo."""
        etiqueta = "" if self.verificado else "/NO-VERIFICADO"
        return Catalogo(
            catalogo.df.iloc[self.indices_fondo].reset_index(drop=True),
            origen=f"{catalogo.origen}|decluster:{self.metodo}{etiqueta}",
        )

    def __str__(self) -> str:
        v = "" if self.verificado else " [PARAMETROS NO VERIFICADOS]"
        return (
            f"{self.metodo}: {self.n_fondo}/{self.n_original} eventos de fondo "
            f"({100 * self.fraccion_eliminada:.1f}% eliminado, {self.n_racimos} racimos){v}"
        )


def _ordenar(catalogo: Catalogo, columna_mag: str) -> tuple[np.ndarray, ...]:
    d = catalogo.df
    t = catalogo.tiempos_dias()
    return (
        t,
        d["lon"].to_numpy(float),
        d["lat"].to_numpy(float),
        d[columna_mag].to_numpy(float),
    )


def gardner_knopoff(
    catalogo: Catalogo,
    *,
    permitir_no_verificado: bool = False,
    columna_mag: str = "mag",
    ruta_parametros: Path | None = None,
) -> ResultadoDecluster:
    """Decluster por ventanas deterministas espacio-temporales.

    Barre los eventos en orden de magnitud decreciente. Cada evento aun no
    asignado se declara sismo principal y absorbe como replicas todos los
    eventos de menor magnitud dentro de su ventana ``L(M)`` en distancia y
    ``T(M)`` en tiempo posterior.

    El barrido por magnitud decreciente (en lugar de por tiempo) evita que un
    evento pequeno capture a uno grande, pero el resultado sigue dependiendo del
    orden de desempate.
    """
    p = cargar_parametros("gardner_knopoff", permitir_no_verificado=permitir_no_verificado,
                          ruta=ruta_parametros)
    t, lon, lat, mag = _ordenar(catalogo, columna_mag)
    n = t.size
    if n == 0:
        raise ValueError("catalogo vacio")

    def ventana_km(m: np.ndarray) -> np.ndarray:
        return np.power(10.0, p["a_dist"] * m + p["b_dist"])

    def ventana_dias(m: np.ndarray) -> np.ndarray:
        alto = m >= p["magnitud_quiebre"]
        out = np.power(10.0, p["a_tiempo_bajo"] * m + p["b_tiempo_bajo"])
        out[alto] = np.power(10.0, p["a_tiempo_alto"] * m[alto] + p["b_tiempo_alto"])
        return out

    L = ventana_km(mag)
    T = ventana_dias(mag)

    id_racimo = np.full(n, -1, dtype=int)
    es_principal = np.zeros(n, dtype=bool)
    orden = np.argsort(-mag, kind="stable")  # magnitud decreciente

    siguiente = 0
    for i in orden:
        if id_racimo[i] != -1:
            continue
        es_principal[i] = True
        # Candidatos: posteriores en tiempo, menor o igual magnitud, sin asignar.
        cand = np.nonzero((t > t[i]) & (t <= t[i] + T[i]) & (id_racimo == -1) & (mag <= mag[i]))[0]
        if cand.size:
            dist = _distancia_km(lon[i], lat[i], lon[cand], lat[cand])
            dentro = cand[dist <= L[i]]
            if dentro.size:
                id_racimo[i] = siguiente
                id_racimo[dentro] = siguiente
                siguiente += 1

    indices_fondo = np.nonzero(es_principal)[0]
    avisos = [
        "Gardner-Knopoff usa ventanas calibradas sobre un catalogo de California de los "
        "anos 70. Aplicarlas a subduccion mexicana es extrapolacion fuera del rango de "
        "calibracion: las secuencias interfase tienen extension espacial mucho mayor.",
    ]
    if not p.get("verificado", False):
        avisos.append(
            "Los coeficientes de las ventanas NO fueron verificados contra la publicacion "
            "original. Todo resultado derivado esta marcado como no verificado."
        )
    return ResultadoDecluster(
        metodo="Gardner-Knopoff", indices_fondo=indices_fondo, id_racimo=id_racimo,
        n_original=n, parametros=dict(p), verificado=bool(p.get("verificado", False)),
        advertencias=avisos,
    )


def zaliapin_ben_zion(
    catalogo: Catalogo,
    *,
    b: float,
    permitir_no_verificado: bool = False,
    columna_mag: str = "mag",
    umbral_log_eta: float | None = None,
    ruta_parametros: Path | None = None,
) -> ResultadoDecluster:
    """Decluster por distancia de vecino mas cercano en espacio-tiempo-magnitud.

    Para cada evento se busca su "padre" mas proximo entre los anteriores segun

    .. math::
        \\eta_{ij} = t_{ij} \\cdot r_{ij}^{\\,d} \\cdot 10^{-b\\,m_i}

    con ``t`` en anios y ``r`` en km. La distribucion de ``log10(eta)`` suele ser
    bimodal: el modo de valores pequenos corresponde a eventos disparados y el de
    valores grandes al fondo. El umbral se toma en el minimo entre modos.

    A diferencia de Gardner-Knopoff, el metodo **no impone escalas espaciales ni
    temporales fijas**: las deduce del propio catalogo. Su punto debil es que
    depende de ``b`` y de la dimension fractal ``d``, y que exige bimodalidad
    real: si el histograma no es bimodal, la funcion lo dice en lugar de partir
    por un umbral arbitrario.
    """
    p = cargar_parametros("zaliapin_ben_zion", permitir_no_verificado=permitir_no_verificado,
                          ruta=ruta_parametros)
    d_fractal = float(p["d_fractal"])
    t, lon, lat, mag = _ordenar(catalogo, columna_mag)
    n = t.size
    if n < 3:
        raise ValueError("se requieren al menos 3 eventos")
    t_anios = t / 365.25

    eta = np.full(n, np.inf)
    padre = np.full(n, -1, dtype=int)
    for j in range(1, n):
        dt = t_anios[j] - t_anios[:j]
        valido = dt > 0
        if not valido.any():
            continue
        r = _distancia_km(lon[:j], lat[:j], lon[j], lat[j])
        # Distancia minima no nula para evitar log(0) en eventos colocalizados.
        r = np.maximum(r, 1e-3)
        e = dt * np.power(r, d_fractal) * np.power(10.0, -b * mag[:j])
        e[~valido] = np.inf
        k = int(np.argmin(e))
        eta[j] = e[k]
        padre[j] = k

    finitos = np.isfinite(eta) & (eta > 0)
    log_eta = np.full(n, np.nan)
    log_eta[finitos] = np.log10(eta[finitos])
    muestras = log_eta[finitos]

    avisos: list[str] = []
    if umbral_log_eta is None:
        umbral_log_eta, bimodal, diag = _umbral_bimodal(muestras)
        if not bimodal:
            avisos.append(
                "El histograma de log10(eta) NO es claramente bimodal "
                f"(separacion entre modos = {diag:.2f} decadas). El supuesto del metodo no se "
                "cumple: la particion resultante es arbitraria. Considera que este catalogo "
                "puede no tener una separacion limpia fondo/racimo, o que faltan eventos."
            )
    else:
        avisos.append(f"Umbral log10(eta) fijado a mano en {umbral_log_eta:g}.")

    es_fondo = ~np.isfinite(eta) | (log_eta >= umbral_log_eta)
    es_fondo[0] = True  # el primer evento no tiene padre posible

    # Etiquetado de racimos: cada evento disparado hereda la raiz de su padre.
    id_racimo = np.full(n, -1, dtype=int)
    raiz = np.arange(n)
    for j in range(n):
        if not es_fondo[j] and padre[j] >= 0:
            raiz[j] = raiz[padre[j]]
    from collections import Counter
    tamanos = Counter(raiz)
    siguiente = 0
    mapa: dict[int, int] = {}
    for j in range(n):
        r0 = raiz[j]
        if tamanos[r0] > 1:
            if r0 not in mapa:
                mapa[r0] = siguiente
                siguiente += 1
            id_racimo[j] = mapa[r0]

    avisos.append(
        f"El resultado depende de b={b:g} y d={d_fractal:g}. Repite con b en su intervalo "
        "de confianza para ver cuanto se mueve la fraccion eliminada."
    )
    if not p.get("verificado", False):
        avisos.append("d_fractal NO verificado contra la publicacion original.")

    return ResultadoDecluster(
        metodo="Zaliapin-Ben-Zion", indices_fondo=np.nonzero(es_fondo)[0], id_racimo=id_racimo,
        n_original=n,
        parametros={**p, "b": b, "umbral_log_eta": float(umbral_log_eta)},
        verificado=bool(p.get("verificado", False)), advertencias=avisos,
    )


def _umbral_bimodal(muestras: np.ndarray, n_bins: int = 60) -> tuple[float, bool, float]:
    """Minimo entre los dos modos del histograma. Devuelve (umbral, es_bimodal, separacion)."""
    if muestras.size < 20:
        return float(np.median(muestras)), False, 0.0
    conteo, bordes = np.histogram(muestras, bins=n_bins)
    centros = 0.5 * (bordes[:-1] + bordes[1:])
    # Suavizado ligero para no quedarse en ruido de conteo.
    nucleo = np.ones(3) / 3.0
    suave = np.convolve(conteo.astype(float), nucleo, mode="same")
    # Modos: maximos locales, tomados los dos mayores bien separados.
    picos = [i for i in range(1, len(suave) - 1) if suave[i] >= suave[i - 1] and suave[i] > suave[i + 1]]
    if len(picos) < 2:
        return float(np.median(muestras)), False, 0.0
    picos.sort(key=lambda i: suave[i], reverse=True)
    i1, i2 = sorted(picos[:2])
    separacion = float(centros[i2] - centros[i1])
    valle = i1 + int(np.argmin(suave[i1: i2 + 1]))
    profundidad = 1.0 - suave[valle] / max(min(suave[i1], suave[i2]), 1e-9)
    es_bimodal = separacion >= 1.0 and profundidad >= 0.3
    return float(centros[valle]), bool(es_bimodal), separacion


def reasenberg(
    catalogo: Catalogo,
    *,
    permitir_no_verificado: bool = False,
    columna_mag: str = "mag",
    ruta_parametros: Path | None = None,
) -> ResultadoDecluster:
    """Decluster por encadenamiento de racimos con ventana temporal adaptativa.

    A diferencia de Gardner-Knopoff, la ventana temporal no depende solo de la
    magnitud del principal: se acorta conforme pasa el tiempo sin nuevos eventos,
    siguiendo implicitamente un decaimiento tipo Omori. La ventana espacial es un
    multiplo del radio de la zona de interaccion, estimado a partir de la
    magnitud del mayor evento del racimo.

    Es el metodo con mas parametros libres de los tres, y por tanto el mas facil
    de ajustar hasta obtener el resultado que uno esperaba. Declara los
    parametros usados junto al resultado.
    """
    p = cargar_parametros("reasenberg", permitir_no_verificado=permitir_no_verificado,
                          ruta=ruta_parametros)
    t, lon, lat, mag = _ordenar(catalogo, columna_mag)
    n = t.size
    if n == 0:
        raise ValueError("catalogo vacio")

    tau_min, tau_max = float(p["tau_min_dias"]), float(p["tau_max_dias"])
    p_conf = float(p["p_confianza"])
    r_factor = float(p["r_factor"])
    m_offset = float(p["m_efectiva_offset"])
    radio_max = float(p["radio_max_km"])

    id_racimo = np.full(n, -1, dtype=int)
    # Estado por racimo: indice del mayor evento y del ultimo evento.
    mayor_de: dict[int, int] = {}
    ultimo_de: dict[int, int] = {}
    siguiente = 0

    def radio_interaccion_km(m: float) -> float:
        """Radio de la zona de interaccion a partir de la magnitud.

        Se usa una relacion de escala longitud-magnitud generica; ``r_factor``
        multiplica ese radio. La relacion de escala es un [SUPUESTO] declarado,
        no un valor tomado de una publicacion verificada.
        """
        # log10(L_km) ~ 0.5*M - 1.8 es una relacion de escala de orden de magnitud.
        long_km = 10.0 ** (0.5 * m - 1.8)
        return min(r_factor * long_km, radio_max)

    for j in range(n):
        asignado = False
        for c in list(ultimo_de.keys()):
            i_mayor, i_ultimo = mayor_de[c], ultimo_de[c]
            dt_desde_mayor = t[j] - t[i_mayor]
            if dt_desde_mayor < 0:
                continue
            # Ventana temporal adaptativa: crece con el tiempo transcurrido desde
            # el mayor evento, acotada entre tau_min y tau_max.
            if dt_desde_mayor <= 0:
                tau = tau_min
            else:
                delta_m = mag[i_mayor] - m_offset
                tau = -math.log(1.0 - p_conf) * dt_desde_mayor / max(10.0 ** (delta_m / 2.0), 1e-6)
                tau = min(max(tau, tau_min), tau_max)
            if t[j] - t[i_ultimo] > tau:
                del ultimo_de[c]
                continue
            radio = radio_interaccion_km(mag[i_mayor])
            d1 = float(_distancia_km(lon[i_mayor], lat[i_mayor], lon[j], lat[j]))
            d2 = float(_distancia_km(lon[i_ultimo], lat[i_ultimo], lon[j], lat[j]))
            if min(d1, d2) <= radio:
                id_racimo[j] = c
                ultimo_de[c] = j
                if mag[j] > mag[i_mayor]:
                    mayor_de[c] = j
                asignado = True
                break
        if not asignado:
            id_racimo[j] = siguiente
            mayor_de[siguiente] = j
            ultimo_de[siguiente] = j
            siguiente += 1

    # De cada racimo sobrevive su mayor evento; los racimos unitarios son fondo.
    from collections import defaultdict
    miembros: dict[int, list[int]] = defaultdict(list)
    for j in range(n):
        miembros[int(id_racimo[j])].append(j)
    fondo = []
    id_final = np.full(n, -1, dtype=int)
    k = 0
    for c, idxs in miembros.items():
        mayor = max(idxs, key=lambda j: mag[j])
        fondo.append(mayor)
        if len(idxs) > 1:
            for j in idxs:
                id_final[j] = k
            k += 1

    avisos = [
        "Reasenberg tiene seis parametros libres. Cambiar tau_max o r_factor mueve la "
        "fraccion eliminada de forma apreciable: no ajustes los parametros mirando el "
        "resultado que quieres obtener.",
        "El radio de interaccion usa una relacion de escala longitud-magnitud generica "
        "marcada como [SUPUESTO] en el codigo, no una relacion publicada y verificada.",
    ]
    if not p.get("verificado", False):
        avisos.append("Los parametros del algoritmo NO fueron verificados contra el original.")

    return ResultadoDecluster(
        metodo="Reasenberg", indices_fondo=np.array(sorted(fondo), dtype=int),
        id_racimo=id_final, n_original=n, parametros=dict(p),
        verificado=bool(p.get("verificado", False)), advertencias=avisos,
    )


def comparar_metodos(
    catalogo: Catalogo, *, b: float, permitir_no_verificado: bool = False, **kw
) -> dict:
    """Corre los tres metodos sobre el mismo catalogo y contrasta sus resultados.

    Esta es la forma correcta de usar el modulo: la divergencia entre metodos es
    el resultado informativo, no un estorbo que haya que resolver eligiendo uno.
    """
    salidas: dict[str, ResultadoDecluster] = {}
    fallos: dict[str, str] = {}
    for nombre, fn, extra in (
        ("gardner_knopoff", gardner_knopoff, {}),
        ("zaliapin_ben_zion", zaliapin_ben_zion, {"b": b}),
        ("reasenberg", reasenberg, {}),
    ):
        try:
            salidas[nombre] = fn(catalogo, permitir_no_verificado=permitir_no_verificado,
                                 **extra, **kw)
        except (ValueError, ErrorDeParametrosNoVerificados) as e:
            fallos[nombre] = str(e)

    if not salidas:
        raise ValueError(f"ningun metodo de decluster pudo aplicarse: {fallos}")

    fracciones = {k: v.fraccion_eliminada for k, v in salidas.items()}
    rango = max(fracciones.values()) - min(fracciones.values())
    aviso = ""
    if rango > 0.10:
        aviso = (
            f"Los metodos eliminan fracciones que difieren en {100 * rango:.0f} puntos "
            f"porcentuales ({', '.join(f'{k}: {100*v:.0f}%' for k, v in fracciones.items())}). "
            "El decluster no es un paso de limpieza: es una hipotesis sobre la estructura del "
            "catalogo. Reporta con cual se obtuvo cada resultado y repite el analisis con los "
            "otros para ver si la conclusion sobrevive."
        )
    return {
        "resultados": salidas, "fallos": fallos,
        "fracciones_eliminadas": fracciones, "rango_fracciones": rango,
        "advertencia": aviso,
    }


def advertir_uso(proposito: Literal["psha", "poisson", "etas", "valor_b"]) -> list[str]:
    """Advertencias segun para que se va a usar el catalogo declusterizado."""
    comunes = [
        "El decluster produce la particion; no la descubre. Declara siempre que metodo usaste."
    ]
    if proposito == "etas":
        return comunes + [
            "ERROR DE METODO: no declusterices antes de ajustar ETAS. ETAS modela "
            "explicitamente el disparo entre eventos; eliminar las replicas destruye "
            "justamente la senal que el modelo estima. Ajusta ETAS sobre el catalogo completo."
        ]
    if proposito == "valor_b":
        return comunes + [
            "El valor de b sobre catalogo declusterizado difiere del valor sobre catalogo "
            "completo, y ninguno es 'el correcto'. Si vas a comparar b entre regiones o "
            "periodos, usa el mismo tratamiento en ambos o la comparacion no significa nada."
        ]
    if proposito in ("psha", "poisson"):
        return comunes + [
            "Para PSHA clasico y para la linea base de Poisson, el decluster es necesario "
            "porque ambos suponen independencia. Ten en cuenta que eliminar replicas reduce "
            "la tasa: el peligro calculado excluye deliberadamente la contribucion de las "
            "secuencias, que no es despreciable en el corto plazo."
        ]
    return comunes
