"""Deteccion de eventos duplicados entre agencias.

Por que esto no es un paso de limpieza trivial
----------------------------------------------
Emparejar el mismo sismo reportado por dos agencias no es una regla, es un
problema de asociacion con errores en ambos sentidos:

* Los hipocentros de dos agencias para el mismo evento pueden diferir en
  decenas de kilometros, y sus tiempos de origen en varios segundos.
* En una secuencia de replicas activa hay eventos **genuinamente distintos**
  dentro de esa misma ventana espacio-temporal.

Por tanto no existe un umbral que separe limpiamente. Lo que hace este modulo
es aplicar umbrales **declarados**, estimar la tasa de error que implican, y
**exponer los casos ambiguos** en lugar de resolverlos en silencio. Un
emparejamiento silencioso que se equivoca duplica o borra eventos, y ambos
errores se propagan a las tasas.

Procedencia por campo
---------------------
Cuando dos agencias aportan el mismo evento, la fusion registra de cual salio
cada campo (``origen_<campo>``), de modo que un analisis pueda reconstruir de
donde vino cada numero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

__all__ = ["CriterioDuplicado", "ResultadoDedup", "detectar_duplicados", "fusionar"]

_RADIO_TIERRA_KM = 6371.0


def _distancia_km(lon1, lat1, lon2, lat2) -> np.ndarray:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = np.radians(np.asarray(lat2) - np.asarray(lat1))
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * _RADIO_TIERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


@dataclass(frozen=True)
class CriterioDuplicado:
    """Umbrales de emparejamiento. Todos deben declararse explicitamente.

    Los valores por defecto son [CONVENCION]: no salen de una calibracion sobre
    catalogos latinoamericanos. Cambiarlos cambia el resultado, asi que quedan
    registrados en :attr:`ResultadoDedup.criterio`.
    """

    delta_t_s: float = 16.0
    delta_r_km: float = 100.0
    delta_m: float = 1.0
    #: Orden de preferencia entre agencias, de mayor a menor.
    prioridad: tuple[str, ...] = ()
    #: Margen dentro del cual un emparejamiento se considera dudoso y se reporta.
    margen_ambiguo: float = 0.5

    def descripcion(self) -> str:
        return (f"|dt| <= {self.delta_t_s:g} s, distancia <= {self.delta_r_km:g} km, "
                f"|dM| <= {self.delta_m:g}")


@dataclass
class ResultadoDedup:
    """Emparejamientos encontrados, con los casos dudosos separados."""

    parejas: pd.DataFrame
    ambiguos: pd.DataFrame
    criterio: CriterioDuplicado
    n_entrada: int
    n_grupos: int
    #: El catalogo de entrada con la columna 'id_fusion' anadida, listo para fusionar().
    etiquetado: pd.DataFrame
    advertencias: list[str] = field(default_factory=list)

    @property
    def n_duplicados(self) -> int:
        return self.n_entrada - self.n_grupos

    def __str__(self) -> str:
        return (f"Dedup ({self.criterio.descripcion()}): {self.n_entrada} eventos -> "
                f"{self.n_grupos} grupos ({self.n_duplicados} duplicados, "
                f"{len(self.ambiguos)} emparejamientos dudosos)")


def detectar_duplicados(
    df: pd.DataFrame,
    criterio: CriterioDuplicado | None = None,
    *,
    columna_mag: str = "mag",
) -> ResultadoDedup:
    """Agrupa eventos de distintas agencias que probablemente sean el mismo sismo.

    Devuelve un :class:`ResultadoDedup` con la columna ``id_fusion`` asignable
    al catalogo. Los emparejamientos que caen cerca de los umbrales se listan
    aparte en ``ambiguos``: **no** se resuelven automaticamente.
    """
    criterio = criterio or CriterioDuplicado()
    d = df.sort_values("tiempo").reset_index(drop=True)
    n = len(d)
    t = d["tiempo"].to_numpy("datetime64[ns]").astype("int64") / 1e9  # segundos
    lon = d["lon"].to_numpy(float)
    lat = d["lat"].to_numpy(float)
    mag = d[columna_mag].to_numpy(float)
    agencia = d["agencia"].to_numpy(str)

    padre = np.arange(n)

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def unir(i: int, j: int) -> None:
        ri, rj = raiz(i), raiz(j)
        if ri != rj:
            padre[max(ri, rj)] = min(ri, rj)

    filas, dudosos = [], []
    for i in range(n):
        # El catalogo esta ordenado por tiempo, asi que en cuanto dt supera el
        # umbral podemos cortar: no hay candidatos mas alla.
        for j in range(i + 1, n):
            dt = t[j] - t[i]
            if dt > criterio.delta_t_s:
                break
            if agencia[i] == agencia[j]:
                continue  # una agencia no duplica sus propios eventos
            dr = float(_distancia_km(lon[i], lat[i], lon[j], lat[j]))
            dm = abs(mag[i] - mag[j]) if np.isfinite(mag[i]) and np.isfinite(mag[j]) else np.nan
            if dr > criterio.delta_r_km:
                continue
            if np.isfinite(dm) and dm > criterio.delta_m:
                continue
            registro = {
                "i": i, "j": j, "id_i": d.loc[i, "id_evento"], "id_j": d.loc[j, "id_evento"],
                "agencia_i": agencia[i], "agencia_j": agencia[j],
                "dt_s": float(dt), "dr_km": dr, "dm": float(dm) if np.isfinite(dm) else np.nan,
            }
            # Cerca de cualquiera de los umbrales -> dudoso.
            cerca = (
                dt > (1 - criterio.margen_ambiguo) * criterio.delta_t_s
                or dr > (1 - criterio.margen_ambiguo) * criterio.delta_r_km
                or (np.isfinite(dm) and dm > (1 - criterio.margen_ambiguo) * criterio.delta_m)
            )
            registro["dudoso"] = bool(cerca)
            filas.append(registro)
            if cerca:
                dudosos.append(registro)
            unir(i, j)

    grupos = np.array([raiz(i) for i in range(n)])
    _, id_fusion = np.unique(grupos, return_inverse=True)
    d["id_fusion"] = id_fusion

    avisos = [
        f"Umbrales usados: {criterio.descripcion()}. Son [CONVENCION], no calibrados sobre "
        "catalogos de esta region. Repite con umbrales distintos para ver cuantos "
        "emparejamientos cambian."
    ]
    if dudosos:
        avisos.append(
            f"{len(dudosos)} emparejamientos caen cerca de los umbrales y pueden ser eventos "
            "distintos. Estan listados en .ambiguos y NO se han resuelto automaticamente."
        )
    n_grupos = int(len(np.unique(id_fusion)))
    if n_grupos == n and len(df["agencia"].unique()) > 1:
        avisos.append(
            "No se encontro ningun duplicado entre agencias distintas. Comprueba que los "
            "tiempos estan realmente en UTC: un desfase de zona horaria impide todo "
            "emparejamiento y pasa desapercibido."
        )
    return ResultadoDedup(
        parejas=pd.DataFrame(filas), ambiguos=pd.DataFrame(dudosos), criterio=criterio,
        n_entrada=n, n_grupos=n_grupos, etiquetado=d, advertencias=avisos,
    )


def fusionar(
    resultado: ResultadoDedup,
    *,
    prioridad: tuple[str, ...] | None = None,
    columna_mag: str = "mag",
) -> pd.DataFrame:
    """Colapsa cada grupo a un evento, registrando de que agencia sale cada campo.

    La agencia preferida se elige por ``prioridad``; dentro de un grupo, los
    campos se toman del reporte de la agencia de mayor prioridad presente. Se
    anaden columnas ``origen_<campo>`` y ``agencias_del_grupo`` para que la
    procedencia por campo sea reconstruible.
    """
    prioridad = prioridad or resultado.criterio.prioridad
    df = resultado.etiquetado
    if "id_fusion" not in df.columns:
        raise KeyError("el resultado no trae 'id_fusion'; reejecuta detectar_duplicados")
    if not prioridad:
        raise ValueError(
            "fusionar() exige un orden de prioridad entre agencias: sin el, la eleccion de "
            "que reporte sobrevive queda al azar del orden alfabetico y deja de ser "
            "reproducible. Declaralo en CriterioDuplicado(prioridad=(...)) o aqui."
        )

    rango = {a: k for k, a in enumerate(prioridad)}
    d = df.copy()
    d["_rango"] = d["agencia"].map(lambda a: rango.get(a, len(rango)))
    campos = ["tiempo", "lon", "lat", "prof_km", columna_mag, "mag_escala"]

    salidas = []
    for _, grupo in d.groupby("id_fusion", sort=True):
        elegido = grupo.sort_values(["_rango", "agencia"]).iloc[0]
        fila = elegido.drop(labels=["_rango"]).to_dict()
        for c in campos:
            fila[f"origen_{c}"] = elegido["agencia"]
        fila["agencias_del_grupo"] = ",".join(sorted(grupo["agencia"].unique()))
        fila["n_reportes"] = int(len(grupo))
        if len(grupo) > 1 and grupo[columna_mag].notna().sum() > 1:
            fila["dispersion_mag_entre_agencias"] = float(
                grupo[columna_mag].max() - grupo[columna_mag].min()
            )
        else:
            fila["dispersion_mag_entre_agencias"] = np.nan
        salidas.append(fila)
    return pd.DataFrame(salidas).sort_values("tiempo").reset_index(drop=True)
