"""Esquema de catalogo sismico con procedencia por campo y por evento.

Decisiones de diseno que responden al contrato epistemologico:

* La magnitud original **nunca** se sobrescribe. La homogenizacion escribe en
  columnas nuevas (`mag_homog`, `mag_homog_sigma`) y deja `mag` y `mag_escala`
  intactas.
* Mezclar escalas de magnitud en un mismo analisis es un error frecuente y
  silencioso. :meth:`Catalogo.escalas_presentes` y :meth:`advertencias` lo
  hacen ruidoso.
* Cada evento arrastra la agencia que lo aporto, de modo que un analisis puede
  reconstruir de donde salio cada numero.
Lo que este modulo NO puede hacer
---------------------------------
* No corrige el catalogo. Detecta problemas de esquema y avisa de riesgos
  conocidos; reparar hipocentros, magnitudes o duplicados es trabajo de la capa
  de ingesta y, en ultimo termino, de la agencia.
* No juzga si el catalogo es adecuado para el analisis que se pretende. Un
  catalogo bien formado puede ser demasiado corto, demasiado incompleto o de la
  region equivocada, y nada de eso dispara una advertencia.
* No detecta errores de localizacion ni magnitudes mal calculadas: solo ve lo
  que la agencia publico.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

__all__ = ["Catalogo", "COLUMNAS_REQUERIDAS", "COLUMNAS_OPCIONALES", "ErrorDeCatalogo"]


class ErrorDeCatalogo(ValueError):
    """El DataFrame no cumple el esquema minimo de catalogo."""


#: Columnas sin las cuales un catalogo no es utilizable. Cada una con su unidad.
COLUMNAS_REQUERIDAS: dict[str, str] = {
    "id_evento": "identificador unico dentro de la agencia",
    "tiempo": "UTC, datetime64[ns], sin zona (se asume UTC)",
    "lon": "grados decimales, -180..180",
    "lat": "grados decimales, -90..90",
    "prof_km": "km bajo el nivel del mar, positivo hacia abajo",
    "mag": "magnitud tal como la reporto la agencia, sin convertir",
    "mag_escala": "etiqueta de escala: Mw, Mww, mb, Ms, ML, MD, Me, ...",
    "agencia": "codigo de la agencia que reporta (SSN, USGS, GCMT, ...)",
}

#: Columnas opcionales reconocidas por el resto de la biblioteca.
COLUMNAS_OPCIONALES: dict[str, str] = {
    "mag_sigma": "1-sigma de la magnitud reportada, si la agencia la publica",
    "mag_homog": "magnitud convertida a la escala objetivo (nunca sobrescribe mag)",
    "mag_homog_sigma": "1-sigma de mag_homog, incluye el error de la regresion",
    "mag_homog_metodo": "identificador de la relacion de conversion empleada",
    "prof_sigma_km": "1-sigma de la profundidad",
    "loc_sigma_km": "1-sigma horizontal de la localizacion",
    "id_fusion": "identificador del evento tras la deduplicacion entre agencias",
}


@dataclass(frozen=True)
class Catalogo:
    """Envoltorio validado sobre un ``pandas.DataFrame`` de eventos.

    El envoltorio es deliberadamente delgado: expone ``.df`` para que el
    usuario haga pandas normal, pero garantiza que el esquema se valido al
    construir y ofrece las operaciones donde es facil equivocarse.
    """

    df: pd.DataFrame
    #: Etiqueta libre para saber de que corrida vino este catalogo.
    origen: str = "sin declarar"

    def __post_init__(self) -> None:
        faltan = [c for c in COLUMNAS_REQUERIDAS if c not in self.df.columns]
        if faltan:
            raise ErrorDeCatalogo(
                "faltan columnas requeridas: "
                + ", ".join(f"{c} ({COLUMNAS_REQUERIDAS[c]})" for c in faltan)
            )
        if not pd.api.types.is_datetime64_any_dtype(self.df["tiempo"]):
            raise ErrorDeCatalogo("la columna 'tiempo' debe ser datetime64 (UTC, sin zona)")
        if getattr(self.df["tiempo"].dtype, "tz", None) is not None:
            raise ErrorDeCatalogo(
                "la columna 'tiempo' debe ser naive en UTC; convierte con "
                ".dt.tz_convert('UTC').dt.tz_localize(None)"
            )
        for col, (lo, hi) in {"lon": (-180.0, 180.0), "lat": (-90.0, 90.0)}.items():
            v = self.df[col].to_numpy(dtype=float)
            if v.size and (np.nanmin(v) < lo or np.nanmax(v) > hi):
                raise ErrorDeCatalogo(f"'{col}' fuera del rango [{lo}, {hi}]")
        if self.df["id_evento"].duplicated().any():
            raise ErrorDeCatalogo(
                "hay 'id_evento' duplicados; la deduplicacion entre agencias debe "
                "resolverse antes de construir el Catalogo (ver sismolat.ingesta.dedup)"
            )
        object.__setattr__(self, "df", self.df.sort_values("tiempo").reset_index(drop=True))

    # -- descripcion ------------------------------------------------------
    def __len__(self) -> int:
        return len(self.df)

    @property
    def n(self) -> int:
        return len(self.df)

    @property
    def ventana_temporal(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.df["tiempo"].min(), self.df["tiempo"].max()

    @property
    def duracion_anios(self) -> float:
        t0, t1 = self.ventana_temporal
        return float((t1 - t0) / pd.Timedelta(days=365.25))

    def escalas_presentes(self) -> dict[str, int]:
        """Cuenta de eventos por escala de magnitud reportada."""
        return self.df["mag_escala"].value_counts(dropna=False).to_dict()

    def agencias_presentes(self) -> dict[str, int]:
        return self.df["agencia"].value_counts(dropna=False).to_dict()

    def advertencias(self) -> list[str]:
        """Problemas del catalogo que deben mostrarse antes de cualquier analisis.

        Devuelve texto para la interfaz. Una lista vacia no significa que el
        catalogo sea bueno, solo que no dispara estas comprobaciones.
        """
        avisos: list[str] = []
        escalas = {k for k in self.escalas_presentes() if isinstance(k, str)}
        if len(escalas) > 1:
            avisos.append(
                f"El catalogo mezcla {len(escalas)} escalas de magnitud "
                f"({', '.join(sorted(escalas))}). Estimar b o Mc sobre escalas mezcladas "
                "produce resultados sin significado fisico. Homogeniza primero, o filtra "
                "a una sola escala."
            )
        if "mag_homog" in self.df.columns and self.df["mag_homog"].notna().any():
            if "mag_homog_sigma" not in self.df.columns or self.df["mag_homog_sigma"].isna().all():
                avisos.append(
                    "Hay magnitudes homogenizadas sin incertidumbre asociada. El error de la "
                    "regresion de conversion puede dominar la incertidumbre final."
                )
        if len(self.agencias_presentes()) > 1 and "id_fusion" not in self.df.columns:
            avisos.append(
                "El catalogo combina varias agencias sin columna 'id_fusion': es probable "
                "que contenga el mismo sismo repetido. Ejecuta la deduplicacion."
            )
        if self.df["mag"].isna().any():
            n = int(self.df["mag"].isna().sum())
            avisos.append(
                f"{n} eventos sin magnitud. Quedaran fuera de todo analisis de frecuencia."
            )
        if self.df["prof_km"].isna().any():
            n = int(self.df["prof_km"].isna().sum())
            avisos.append(
                f"{n} eventos sin profundidad; no podran separarse por regimen tectonico."
            )
        return avisos

    # -- seleccion --------------------------------------------------------
    def filtrar(
        self,
        *,
        mag_min: float | None = None,
        mag_max: float | None = None,
        t_inicio: str | pd.Timestamp | None = None,
        t_fin: str | pd.Timestamp | None = None,
        prof_min_km: float | None = None,
        prof_max_km: float | None = None,
        caja: tuple[float, float, float, float] | None = None,
        columna_mag: str = "mag",
    ) -> "Catalogo":
        """Subconjunto del catalogo. ``caja`` es (lon_min, lon_max, lat_min, lat_max)."""
        d = self.df
        m = pd.Series(True, index=d.index)
        if mag_min is not None:
            m &= d[columna_mag] >= mag_min
        if mag_max is not None:
            m &= d[columna_mag] <= mag_max
        if t_inicio is not None:
            m &= d["tiempo"] >= pd.Timestamp(t_inicio)
        if t_fin is not None:
            m &= d["tiempo"] <= pd.Timestamp(t_fin)
        if prof_min_km is not None:
            m &= d["prof_km"] >= prof_min_km
        if prof_max_km is not None:
            m &= d["prof_km"] <= prof_max_km
        if caja is not None:
            lon0, lon1, lat0, lat1 = caja
            m &= d["lon"].between(lon0, lon1) & d["lat"].between(lat0, lat1)
        return Catalogo(d[m].reset_index(drop=True), origen=f"{self.origen}|filtrado")

    def magnitudes(self, columna: str = "mag", *, sin_nan: bool = True) -> np.ndarray:
        v = self.df[columna].to_numpy(dtype=float)
        return v[~np.isnan(v)] if sin_nan else v

    def tiempos_dias(self, t_ref: pd.Timestamp | None = None) -> np.ndarray:
        """Tiempos en dias decimales desde ``t_ref`` (por defecto, el primer evento)."""
        t0 = pd.Timestamp(t_ref) if t_ref is not None else self.df["tiempo"].min()
        return ((self.df["tiempo"] - t0) / pd.Timedelta(days=1)).to_numpy(dtype=float)

    # -- reproducibilidad -------------------------------------------------
    def huella(self) -> str:
        """SHA-256 del contenido del catalogo, estable ante reordenamientos.

        Se usa para que un analisis pueda declarar exactamente sobre que datos
        corrio, incluso si el catalogo de la agencia se revisa despues.
        """
        cols = [c for c in COLUMNAS_REQUERIDAS if c in self.df.columns]
        d = self.df[cols].sort_values("id_evento").reset_index(drop=True)
        h = hashlib.sha256()
        h.update(",".join(cols).encode())
        for col in cols:
            serie = d[col]
            if pd.api.types.is_datetime64_any_dtype(serie):
                h.update(np.ascontiguousarray(serie.astype("int64").to_numpy()).tobytes())
            elif pd.api.types.is_numeric_dtype(serie):
                h.update(np.ascontiguousarray(np.round(serie.to_numpy(dtype=float), 6)).tobytes())
            else:
                h.update("\x1f".join(serie.astype(str)).encode())
        return h.hexdigest()

    @classmethod
    def desde_registros(cls, registros: Iterable[dict], origen: str = "sin declarar") -> "Catalogo":
        df = pd.DataFrame(list(registros))
        if "tiempo" in df.columns:
            df["tiempo"] = pd.to_datetime(df["tiempo"], utc=True).dt.tz_localize(None)
        return cls(df, origen=origen)
