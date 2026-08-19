"""Cliente para servicios de eventos FDSN.

Que esta verificado y que no
----------------------------
* **El protocolo sí**: los nombres de parametro (``starttime``, ``endtime``,
  ``minmagnitude``, ``minlatitude``, ...) y el formato de texto delimitado por
  ``|`` pertenecen a la especificacion publica de los FDSN Web Services, que es
  un estandar, no una conjetura sobre una API concreta.
* **Las URL base no**. Ninguna se incluye por defecto: se toman del registro de
  :mod:`sismolat.ingesta.fuentes`, que exige que alguien las haya comprobado
  contra la documentacion oficial del servicio.
* **Este cliente no ha sido ejecutado contra ningun servicio real** durante su
  desarrollo (el entorno de construccion tenia el egreso bloqueado). El parseo
  esta probado contra respuestas de ejemplo con el formato del estandar, no
  contra respuestas reales. Ver docs/03-pendientes.md.

Fallos visibles
---------------
Si una fuente no responde, :class:`RespuestaIngesta` lo registra y la interfaz
debe mostrarlo. Nunca se rellena con datos de otra fuente ni se silencia: un
hueco en el catalogo que parece ausencia de sismicidad es peor que un error.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlencode

import pandas as pd

from .fuentes import Fuente, cargar_fuente

__all__ = ["ConsultaEventos", "RespuestaIngesta", "construir_url", "parsear_texto_fdsn"]


@dataclass(frozen=True)
class ConsultaEventos:
    """Parametros de consulta con los nombres del estandar FDSN."""

    t_inicio: str
    t_fin: str
    mag_min: float | None = None
    mag_max: float | None = None
    lat_min: float | None = None
    lat_max: float | None = None
    lon_min: float | None = None
    lon_max: float | None = None
    prof_min_km: float | None = None
    prof_max_km: float | None = None
    limite: int | None = None
    formato: str = "text"

    def a_parametros(self) -> dict[str, str]:
        """Traduce a los nombres de parametro del estandar FDSN."""
        crudo = {
            "starttime": self.t_inicio,
            "endtime": self.t_fin,
            "minmagnitude": self.mag_min,
            "maxmagnitude": self.mag_max,
            "minlatitude": self.lat_min,
            "maxlatitude": self.lat_max,
            "minlongitude": self.lon_min,
            "maxlongitude": self.lon_max,
            "mindepth": self.prof_min_km,
            "maxdepth": self.prof_max_km,
            "limit": self.limite,
            "format": self.formato,
        }
        return {k: str(v) for k, v in crudo.items() if v is not None}


def construir_url(fuente: Fuente, consulta: ConsultaEventos) -> str:
    """URL completa de la consulta. Exige que la fuente este verificada."""
    fuente.exigir_verificacion()
    base = fuente.url_base.rstrip("/")
    return f"{base}/query?{urlencode(consulta.a_parametros())}"


@dataclass
class RespuestaIngesta:
    """Resultado de un intento de ingesta, incluido el fracaso.

    Un fallo de conexion se representa explicitamente y con marca de tiempo,
    para que la interfaz pueda decir "esta fuente no respondio" en lugar de
    mostrar un catalogo incompleto sin avisar.
    """

    fuente: str
    exito: bool
    momento_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    datos: pd.DataFrame | None = None
    url: str = ""
    error: str = ""
    n_eventos: int = 0

    def __str__(self) -> str:
        if self.exito:
            return f"{self.fuente}: {self.n_eventos} eventos ({self.momento_utc})"
        return f"{self.fuente}: SIN RESPUESTA -- {self.error} ({self.momento_utc})"


#: Correspondencia entre las columnas del formato de texto FDSN y el esquema interno.
_COLUMNAS_FDSN = {
    "EventID": "id_evento",
    "Time": "tiempo",
    "Latitude": "lat",
    "Longitude": "lon",
    "Depth/km": "prof_km",
    "Magnitude": "mag",
    "MagType": "mag_escala",
    "Author": "autor",
    "Catalog": "catalogo",
    "Contributor": "contribuidor",
    "ContributorID": "id_contribuidor",
    "MagAuthor": "autor_magnitud",
    "EventLocationName": "localizacion",
}


def parsear_texto_fdsn(texto: str, agencia: str) -> pd.DataFrame:
    """Parsea el formato de texto delimitado por ``|`` del estandar FDSN.

    La primera linea es una cabecera que empieza por ``#``. Las columnas que el
    esquema interno no reconoce se conservan con su nombre original en lugar de
    descartarse, para no perder informacion de procedencia.
    """
    lineas = [l for l in texto.splitlines() if l.strip()]
    if not lineas:
        return pd.DataFrame()
    cabecera = lineas[0].lstrip("#").strip()
    cuerpo = "\n".join(lineas[1:])
    columnas = [c.strip() for c in cabecera.split("|")]
    d = pd.read_csv(io.StringIO(cuerpo), sep="|", names=columnas, dtype=str)
    d = d.rename(columns={k: v for k, v in _COLUMNAS_FDSN.items() if k in d.columns})

    if "tiempo" in d.columns:
        d["tiempo"] = pd.to_datetime(d["tiempo"], utc=True, format="mixed").dt.tz_localize(None)
    for col in ("lat", "lon", "prof_km", "mag"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
    for col in ("id_evento", "mag_escala"):
        if col in d.columns:
            d[col] = d[col].astype(str).str.strip()
    d["agencia"] = agencia
    return d


def ingerir(
    clave_fuente: str,
    consulta: ConsultaEventos,
    *,
    tiempo_espera_s: float = 60.0,
    ruta_registro=None,
) -> RespuestaIngesta:
    """Ejecuta la consulta contra una fuente verificada.

    Requiere que la fuente este verificada en el registro. Cualquier fallo
    devuelve una :class:`RespuestaIngesta` con ``exito=False`` y el motivo, en
    lugar de lanzar: la aplicacion debe seguir funcionando con las fuentes que
    sí respondieron y decir cuales no.
    """
    import urllib.error
    import urllib.request

    try:
        fuente = cargar_fuente(clave_fuente, ruta=ruta_registro)
        url = construir_url(fuente, consulta)
    except Exception as e:  # fuente inexistente o sin verificar
        return RespuestaIngesta(fuente=clave_fuente, exito=False, error=str(e))

    try:
        with urllib.request.urlopen(url, timeout=tiempo_espera_s) as r:
            texto = r.read().decode("utf-8", errors="replace")
        datos = parsear_texto_fdsn(texto, agencia=clave_fuente.upper())
        return RespuestaIngesta(
            fuente=clave_fuente, exito=True, datos=datos, url=url, n_eventos=len(datos)
        )
    except (urllib.error.URLError, OSError, ValueError) as e:
        return RespuestaIngesta(fuente=clave_fuente, exito=False, url=url, error=repr(e))
