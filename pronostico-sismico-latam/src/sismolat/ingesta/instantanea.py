"""Instantaneas versionadas del catalogo y modo sin conexion.

Por que versionar el catalogo
-----------------------------
Los catalogos se revisan retroactivamente: una agencia puede recalcular la
magnitud o el hipocentro de un evento de hace cinco anos. Un analisis que no
declare **con que estado del catalogo** corrio no es reproducible, aunque el
codigo y la semilla sean los mismos.

Una instantanea guarda el catalogo junto con su huella, el momento de descarga
y la fuente. :func:`edad_dias` permite que la interfaz muestre siempre la
antiguedad de lo que se esta viendo: un usuario que mira datos de hace ocho
meses creyendo que son de hoy sacara conclusiones equivocadas sobre la
actividad reciente.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..catalogo import Catalogo

__all__ = ["Instantanea", "guardar", "cargar", "listar", "mensaje_de_antiguedad"]


@dataclass(frozen=True)
class Instantanea:
    """Un catalogo congelado con su procedencia y momento de descarga."""

    catalogo: Catalogo
    fuente: str
    momento_utc: str
    huella: str
    consulta: dict

    @property
    def edad_dias(self) -> float:
        t = datetime.fromisoformat(self.momento_utc)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 86400.0


def guardar(
    catalogo: Catalogo, directorio: Path | str, *, fuente: str, consulta: dict | None = None,
) -> Path:
    """Guarda una instantanea. El nombre del fichero incluye la huella del contenido."""
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    huella = catalogo.huella()
    momento = datetime.now(timezone.utc).isoformat()
    nombre = f"{fuente}_{momento[:10]}_{huella[:12]}"
    catalogo.df.to_parquet(directorio / f"{nombre}.parquet", index=False)
    (directorio / f"{nombre}.json").write_text(
        json.dumps({
            "fuente": fuente, "momento_utc": momento, "huella": huella,
            "consulta": consulta or {}, "n_eventos": catalogo.n,
            "origen": catalogo.origen,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return directorio / f"{nombre}.parquet"


def cargar(ruta_parquet: Path | str) -> Instantanea:
    """Carga una instantanea y comprueba que su contenido no cambio."""
    ruta = Path(ruta_parquet)
    meta = json.loads(ruta.with_suffix(".json").read_text(encoding="utf-8"))
    cat = Catalogo(pd.read_parquet(ruta), origen=meta.get("origen", "instantanea"))
    if cat.huella() != meta["huella"]:
        raise ValueError(
            f"la huella del fichero ({cat.huella()[:12]}) no coincide con la registrada "
            f"({meta['huella'][:12]}): la instantanea fue modificada despues de guardarse y "
            "no puede usarse para reproducir un analisis"
        )
    return Instantanea(
        catalogo=cat, fuente=meta["fuente"], momento_utc=meta["momento_utc"],
        huella=meta["huella"], consulta=meta.get("consulta", {}),
    )


def listar(directorio: Path | str) -> list[dict]:
    """Metadatos de todas las instantaneas del directorio, de la mas reciente a la mas antigua."""
    directorio = Path(directorio)
    if not directorio.exists():
        return []
    metas = []
    for j in sorted(directorio.glob("*.json")):
        m = json.loads(j.read_text(encoding="utf-8"))
        m["ruta"] = str(j.with_suffix(".parquet"))
        metas.append(m)
    return sorted(metas, key=lambda m: m["momento_utc"], reverse=True)


def mensaje_de_antiguedad(inst: Instantanea) -> str:
    """Texto que la interfaz debe mostrar de forma permanente en modo sin conexion."""
    d = inst.edad_dias
    if d < 1:
        cuando = f"{d * 24:.0f} horas"
    elif d < 60:
        cuando = f"{d:.0f} dias"
    else:
        cuando = f"{d / 30.4:.0f} meses"
    aviso = ""
    if d > 30:
        aviso = (
            "  ATENCION: con datos de mas de un mes, cualquier lectura sobre actividad "
            "reciente o secuencias en curso es incorrecta."
        )
    return (
        f"MODO SIN CONEXION -- datos de {inst.fuente} descargados hace {cuando} "
        f"({inst.momento_utc[:16]} UTC), {inst.catalogo.n} eventos, "
        f"huella {inst.huella[:12]}.{aviso}"
    )
