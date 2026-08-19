"""Magnitud de completitud Mc por varios metodos, y Mc variable en el espacio.

Por que hay varios metodos
--------------------------
Mc no es una cantidad medida: es el resultado de un criterio. Metodos distintos
sobre el mismo catalogo dan valores que difieren tipicamente en 0.2-0.4
unidades, y esa diferencia se propaga a b con mucho mas peso que el error
estadistico de b. Por eso la interfaz debe mostrar **los tres** y su dispersion,
nunca uno solo.

Por que Mc(x, y) importa en America Latina
------------------------------------------
La densidad de estaciones es muy desigual: la costa de Guerrero y el centro de
Mexico estan mucho mejor cubiertos que el Golfo de Tehuantepec o el Pacifico
abierto. Estimar b sobre un Mc escalar en una region con Mc variable produce
**estructura espacial falsa en el mapa de b**, con aspecto tectonico. Esta es
la razon de que :func:`mc_espacial` no sea un extra sino un prerequisito de
cualquier mapa de b.

Lo que este modulo NO puede hacer
---------------------------------
* No puede detectar completitud variable en el **tiempo** de forma automatica
  para todo el catalogo; :func:`mc_por_ventanas` lo muestra, pero interpretarlo
  (expansiones de red, cambios de procedimiento) requiere el historial de la
  agencia, que no esta en el catalogo.
* No corrige el catalogo. Solo dice desde donde es utilizable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..procedencia import Cantidad, Procedencia, convencion
from .gutenberg_richter import b_aki_utsu, fmd

__all__ = [
    "ResultadoMc",
    "mc_maxima_curvatura",
    "mc_bondad_ajuste",
    "mc_estabilidad_b",
    "comparar_metodos_mc",
    "mc_espacial",
    "mc_por_ventanas",
    "CORRECCION_MAXC_POR_DEFECTO",
]

#: Correccion aditiva al maximo de la FMD incremental. MAXC subestima Mc de
#: forma sistematica; la literatura de calibracion propone anadir del orden de
#: +0.2. Es una CONVENCION calibrada sobre catalogos que no son los de esta
#: region: el usuario deberia recalibrarla o, al menos, ver el efecto de
#: cambiarla.
CORRECCION_MAXC_POR_DEFECTO = convencion(
    0.2,
    "unidades de magnitud",
    motivo=(
        "MAXC subestima Mc sistematicamente; correccion aditiva de calibracion "
        "propuesta en la literatura de completitud. NO calibrada para catalogos "
        "latinoamericanos: tratar como punto de partida, no como valor correcto."
    ),
    fuente="convencion de la literatura de completitud (no verificada en esta sesion)",
)


@dataclass(frozen=True)
class ResultadoMc:
    """Mc estimado por un metodo, con el diagnostico que permite juzgarlo."""

    mc: Cantidad
    metodo: str
    n_sobre_mc: int
    #: Diagnostico especifico del metodo (R de bondad de ajuste, etc.).
    diagnostico: dict[str, float]
    #: True si el metodo alcanzo su criterio; False si tuvo que recurrir a un respaldo.
    criterio_alcanzado: bool = True
    advertencia: str = ""

    def __str__(self) -> str:
        estado = "" if self.criterio_alcanzado else "  [CRITERIO NO ALCANZADO]"
        return f"Mc({self.metodo}) = {self.mc}  n={self.n_sobre_mc}{estado}"


def _rejilla_mc(magnitudes: np.ndarray, dm: float) -> np.ndarray:
    centros, _, _ = fmd(magnitudes, dm)
    return centros


def mc_maxima_curvatura(
    magnitudes: np.ndarray,
    dm: float = 0.1,
    *,
    correccion: Cantidad | None = None,
) -> ResultadoMc:
    """Mc por maxima curvatura: el modo de la FMD incremental, mas una correccion.

    Es el metodo mas rapido y el mas sesgado hacia abajo. Sirve como punto de
    partida y como respaldo cuando los otros no convergen; no deberia ser el
    valor que se reporta solo.
    """
    correccion = correccion or CORRECCION_MAXC_POR_DEFECTO
    m = np.asarray(magnitudes, dtype=float)
    m = m[np.isfinite(m)]
    if m.size == 0:
        raise ValueError("no hay magnitudes finitas")
    centros, incremental, _ = fmd(m, dm)
    modo = float(centros[int(np.argmax(incremental))])
    mc_valor = modo + correccion.valor
    n = int(np.sum(m >= mc_valor - dm / 100.0))
    cantidad = Cantidad(
        valor=mc_valor,
        unidad="unidades de magnitud",
        procedencia=Procedencia.DERIVADO,
        fuente=f"maxima curvatura (modo={modo:.2f}) + correccion {correccion.valor:g}",
        # La incertidumbre de Mc por MAXC no es estadistica sino de metodo:
        # se declara del orden del paso de magnitud, no cero.
        incertidumbre=dm,
        verificado=correccion.verificado,
        notas=(
            f"correccion aplicada: {correccion.valor:g} [{correccion.procedencia.value}]. "
            "La incertidumbre declarada es el paso de magnitud, no un error estadistico: "
            "la dispersion real entre metodos es mayor (ver comparar_metodos_mc)."
        ),
    )
    return ResultadoMc(
        mc=cantidad, metodo="maxima curvatura", n_sobre_mc=n,
        diagnostico={"modo_fmd": modo, "correccion": correccion.valor},
    )


def mc_bondad_ajuste(
    magnitudes: np.ndarray,
    dm: float = 0.1,
    *,
    nivel_r: float = 90.0,
    n_minimo: int = 50,
) -> ResultadoMc:
    """Mc por bondad de ajuste (goodness-of-fit) a la FMD acumulada.

    Para cada Mc candidato se ajusta G-R sobre los eventos por encima y se
    compara la FMD acumulada observada con la sintetica:

    .. math::
        R(M_c) = 100 \\left(1 - \\frac{\\sum_i |B_i - S_i|}{\\sum_i B_i}\\right)

    Se elige el menor Mc cuyo R alcanza ``nivel_r``. Si ningun candidato lo
    alcanza, el criterio **no se da por cumplido**: se devuelve el Mc de mejor R
    con ``criterio_alcanzado=False`` y una advertencia, en lugar de fingir que
    convergio.

    Referencia: Wiemer y Wyss (2000), no verificada en esta sesion.
    """
    m = np.asarray(magnitudes, dtype=float)
    m = m[np.isfinite(m)]
    centros, _, acumulada = fmd(m, dm)
    resultados: list[tuple[float, float]] = []
    for i, mc_cand in enumerate(centros):
        sel = m >= (mc_cand - dm / 100.0)
        if int(sel.sum()) < n_minimo:
            break
        try:
            b = b_aki_utsu(m, float(mc_cand), dm, n_minimo=n_minimo)
        except ValueError:
            break
        n_obs = float(sel.sum())
        a = math.log10(n_obs) + b.valor * mc_cand
        mags = centros[i:]
        sintetica = np.power(10.0, a - b.valor * mags)
        observada = acumulada[i:]
        denom = float(observada.sum())
        if denom <= 0:
            break
        r = 100.0 * (1.0 - float(np.abs(observada - sintetica).sum()) / denom)
        resultados.append((float(mc_cand), r))

    if not resultados:
        raise ValueError(
            f"no hay ningun umbral con al menos {n_minimo} eventos; el catalogo es "
            "demasiado pequeno para estimar Mc por bondad de ajuste"
        )

    alcanzan = [(mc, r) for mc, r in resultados if r >= nivel_r]
    if alcanzan:
        mc_valor, r = alcanzan[0]
        alcanzado, aviso = True, ""
    else:
        mc_valor, r = max(resultados, key=lambda t: t[1])
        alcanzado = False
        aviso = (
            f"Ningun umbral alcanzo R>={nivel_r:g}% (maximo observado: {r:.1f}% en "
            f"Mc={mc_valor:.2f}). La FMD no sigue G-R en ningun rango probado: puede "
            "indicar mezcla de escalas de magnitud, mezcla de regimenes tectonicos, "
            "o completitud variable dentro de la muestra. No uses este Mc sin mirar la FMD."
        )

    n = int(np.sum(m >= mc_valor - dm / 100.0))
    cantidad = Cantidad(
        valor=mc_valor,
        unidad="unidades de magnitud",
        procedencia=Procedencia.DERIVADO,
        fuente=f"bondad de ajuste R>={nivel_r:g}% sobre FMD acumulada",
        incertidumbre=dm,
        verificado=alcanzado,
        notas=aviso or f"R alcanzado = {r:.1f}%",
    )
    return ResultadoMc(
        mc=cantidad, metodo=f"bondad de ajuste ({nivel_r:g}%)", n_sobre_mc=n,
        diagnostico={"R": r, "nivel_exigido": nivel_r},
        criterio_alcanzado=alcanzado, advertencia=aviso,
    )


def mc_estabilidad_b(
    magnitudes: np.ndarray,
    dm: float = 0.1,
    *,
    ancho_ventana: float = 0.5,
    n_minimo: int = 50,
) -> ResultadoMc:
    """Mc por estabilidad del valor b (MBS).

    Se calcula b(Mc) para umbrales crecientes y se elige el primero en que b
    deja de variar: el promedio de b en ``[Mc, Mc + ancho_ventana]`` difiere de
    b(Mc) en menos que la incertidumbre de b(Mc).

    Es el metodo mas exigente en numero de eventos y el que suele dar el Mc mas
    alto de los tres. Si no converge, lo dice en lugar de devolver el ultimo
    umbral probado.

    Referencia: Cao y Gao (2002); Woessner y Wiemer (2005). No verificadas en
    esta sesion.
    """
    m = np.asarray(magnitudes, dtype=float)
    m = m[np.isfinite(m)]
    centros, _, _ = fmd(m, dm)
    umbrales: list[float] = []
    bs: list[float] = []
    sigmas: list[float] = []
    for mc_cand in centros:
        try:
            b = b_aki_utsu(m, float(mc_cand), dm, n_minimo=n_minimo)
        except ValueError:
            break
        umbrales.append(float(mc_cand))
        bs.append(b.valor)
        sigmas.append(b.incertidumbre or float("inf"))

    n_ventana = max(int(round(ancho_ventana / dm)), 1)
    for i in range(len(umbrales) - n_ventana):
        b_promedio = float(np.mean(bs[i: i + n_ventana + 1]))
        if abs(b_promedio - bs[i]) <= sigmas[i]:
            mc_valor = umbrales[i]
            n = int(np.sum(m >= mc_valor - dm / 100.0))
            cantidad = Cantidad(
                valor=mc_valor,
                unidad="unidades de magnitud",
                procedencia=Procedencia.DERIVADO,
                fuente=f"estabilidad de b en ventana de {ancho_ventana:g} unidades",
                incertidumbre=dm,
                notas=f"b en el umbral = {bs[i]:.3f} +/- {sigmas[i]:.3f}",
            )
            return ResultadoMc(
                mc=cantidad, metodo="estabilidad de b (MBS)", n_sobre_mc=n,
                diagnostico={"b_en_mc": bs[i], "sigma_b": sigmas[i], "b_promedio": b_promedio},
            )

    aviso = (
        "El valor de b nunca se estabilizo dentro de su propia incertidumbre en el rango "
        "probado. Suele significar que el catalogo tiene pocos eventos, que la FMD no es "
        "G-R, o que la completitud varia dentro de la muestra. No hay Mc por este metodo."
    )
    if not umbrales:
        raise ValueError(
            f"no hay ningun umbral con al menos {n_minimo} eventos para probar estabilidad de b"
        )
    mc_valor = umbrales[0]
    cantidad = Cantidad(
        valor=mc_valor, unidad="unidades de magnitud", procedencia=Procedencia.DERIVADO,
        fuente="estabilidad de b (NO CONVERGIO; se devuelve el umbral minimo probado)",
        incertidumbre=dm, verificado=False, notas=aviso,
    )
    return ResultadoMc(
        mc=cantidad, metodo="estabilidad de b (MBS)",
        n_sobre_mc=int(np.sum(m >= mc_valor - dm / 100.0)),
        diagnostico={}, criterio_alcanzado=False, advertencia=aviso,
    )


def comparar_metodos_mc(magnitudes: np.ndarray, dm: float = 0.1, **kw) -> dict[str, object]:
    """Corre los tres metodos y reporta su dispersion.

    La dispersion entre metodos es la incertidumbre honesta de Mc, y suele ser
    varias veces mayor que la incertidumbre estadistica que cada metodo declara
    por separado. La interfaz debe mostrar este numero, no el de un solo metodo.
    """
    resultados: dict[str, ResultadoMc] = {}
    fallos: dict[str, str] = {}
    for nombre, fn in (
        ("maxima_curvatura", mc_maxima_curvatura),
        ("bondad_ajuste", mc_bondad_ajuste),
        ("estabilidad_b", mc_estabilidad_b),
    ):
        try:
            resultados[nombre] = fn(magnitudes, dm, **{k: v for k, v in kw.items()
                                                       if k in fn.__code__.co_varnames})
        except ValueError as e:
            fallos[nombre] = str(e)

    if not resultados:
        raise ValueError(f"ningun metodo de Mc pudo aplicarse: {fallos}")

    valores = np.array([r.mc.valor for r in resultados.values()])
    dispersion = float(valores.max() - valores.min())
    convergieron = [n for n, r in resultados.items() if r.criterio_alcanzado]
    aviso = ""
    if dispersion > 3 * dm:
        aviso = (
            f"Los metodos de Mc discrepan en {dispersion:.2f} unidades de magnitud "
            f"({valores.min():.2f} a {valores.max():.2f}). Esa discrepancia se propaga a b "
            "con mas peso que su error estadistico. Reporta el rango, no un valor unico, "
            "y repite el analisis en los extremos para ver si la conclusion cambia."
        )
    return {
        "resultados": resultados,
        "fallos": fallos,
        "mc_min": float(valores.min()),
        "mc_max": float(valores.max()),
        "mc_mediana": float(np.median(valores)),
        "dispersion": dispersion,
        "metodos_convergidos": convergieron,
        "advertencia": aviso,
    }


def mc_espacial(
    df: pd.DataFrame,
    *,
    paso_grados: float = 0.5,
    radio_grados: float = 1.0,
    n_minimo: int = 100,
    dm: float = 0.1,
    columna_mag: str = "mag",
    metodo=mc_maxima_curvatura,
) -> pd.DataFrame:
    """Mc en una rejilla geografica, por vecindad circular en grados.

    Devuelve un DataFrame con ``lon``, ``lat``, ``mc``, ``n`` y ``suficiente``.
    Las celdas con menos de ``n_minimo`` eventos devuelven ``mc = NaN``: es la
    respuesta correcta, y rellenarlas por interpolacion inventaria completitud
    donde no hay datos para juzgarla.

    Advertencia de metodo
    ---------------------
    La vecindad es circular **en grados**, no en kilometros: a latitudes altas
    el area real se distorsiona. Para las latitudes de Mexico (14-33 N) el error
    de area es del orden del 3-15%, aceptable para diagnostico pero no para
    calculo de tasas. Para tasas, usar una rejilla equiarea.
    """
    for col in ("lon", "lat", columna_mag):
        if col not in df.columns:
            raise KeyError(f"falta la columna '{col}'")
    d = df[["lon", "lat", columna_mag]].dropna()
    lon = d["lon"].to_numpy(float)
    lat = d["lat"].to_numpy(float)
    mag = d[columna_mag].to_numpy(float)

    lons = np.arange(np.floor(lon.min()), np.ceil(lon.max()) + paso_grados / 2, paso_grados)
    lats = np.arange(np.floor(lat.min()), np.ceil(lat.max()) + paso_grados / 2, paso_grados)

    filas = []
    for glat in lats:
        for glon in lons:
            d2 = (lon - glon) ** 2 + (lat - glat) ** 2
            sel = d2 <= radio_grados ** 2
            n = int(sel.sum())
            mc_val = np.nan
            if n >= n_minimo:
                try:
                    mc_val = metodo(mag[sel], dm).mc.valor
                except ValueError:
                    mc_val = np.nan
            filas.append({
                "lon": float(glon), "lat": float(glat), "n": n,
                "mc": mc_val, "suficiente": bool(n >= n_minimo and np.isfinite(mc_val)),
            })
    salida = pd.DataFrame(filas)
    salida.attrs["advertencia"] = (
        "Mc varia en el espacio. Si vas a producir un mapa de b, usa este Mc por celda: "
        "un Mc escalar sobre completitud heterogenea genera estructura espacial falsa en b."
    )
    return salida


def mc_por_ventanas(
    df: pd.DataFrame,
    *,
    ventana: str = "365D",
    n_minimo: int = 100,
    dm: float = 0.1,
    columna_mag: str = "mag",
    columna_tiempo: str = "tiempo",
    metodo=mc_maxima_curvatura,
) -> pd.DataFrame:
    """Mc en ventanas temporales sucesivas, para ver expansiones de red.

    Un salto brusco hacia abajo en Mc casi siempre corresponde a una mejora de
    la red, no a un cambio en la sismicidad. Analizar un periodo que cruza ese
    salto con un Mc unico introduce un cambio artificial de tasa.
    """
    d = df[[columna_tiempo, columna_mag]].dropna().sort_values(columna_tiempo)
    filas = []
    for inicio, grupo in d.resample(ventana, on=columna_tiempo):
        mags = grupo[columna_mag].to_numpy(float)
        mc_val = np.nan
        if mags.size >= n_minimo:
            try:
                mc_val = metodo(mags, dm).mc.valor
            except ValueError:
                mc_val = np.nan
        filas.append({
            "inicio": inicio, "n": int(mags.size), "mc": mc_val,
            "suficiente": bool(mags.size >= n_minimo and np.isfinite(mc_val)),
        })
    return pd.DataFrame(filas)
