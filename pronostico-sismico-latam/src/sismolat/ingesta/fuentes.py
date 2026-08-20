"""Registro de fuentes con verificacion obligatoria de endpoint y licencia.

Por que no hay ninguna URL por defecto
--------------------------------------
Una URL de API escrita de memoria es indistinguible, al leer el codigo, de una
comprobada. Si esta mal, el conector falla de una forma confusa; si esta *casi*
bien (una version antigua del servicio, por ejemplo), puede devolver datos
silenciosamente distintos de los que el usuario cree estar pidiendo. Por eso
:func:`cargar_fuente` exige que alguien haya abierto la documentacion oficial y
marcado la fuente como verificada.

La misma logica se aplica a la licencia: ``puede_cachearse`` empieza en
``False`` para todas las fuentes, de modo que la capa de ingesta no persiste
nada hasta que alguien haya leido los terminos de uso.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Fuente", "cargar_fuente", "listar_fuentes", "resumen_estado",
    "ErrorDeFuenteNoVerificada",
]

_RUTA = Path(__file__).resolve().parents[3] / "parametros" / "fuentes.toml"


class ErrorDeFuenteNoVerificada(RuntimeError):
    """Se intento usar una fuente cuyo endpoint o licencia no fueron comprobados."""


@dataclass(frozen=True)
class Fuente:
    """Una fuente de datos con su estado de verificacion."""

    clave: str
    nombre: str
    protocolo: str
    url_base: str
    verificado: bool
    documentacion: str
    licencia: str
    puede_cachearse: bool
    cobertura: str = ""
    notas: str = ""
    verificado_el: str = ""
    verificado_por: str = ""

    def exigir_verificacion(self) -> None:
        if not self.verificado or not self.url_base.strip():
            raise ErrorDeFuenteNoVerificada(
                f"La fuente '{self.clave}' ({self.nombre}) no esta verificada.\n"
                f"  url_base       : {self.url_base!r}\n"
                f"  documentacion  : {self.documentacion}\n"
                f"  licencia       : {self.licencia}\n"
                "Abre la documentacion oficial, comprueba la URL base real del servicio y "
                f"rellena url_base + verificado = true en {_RUTA}. "
                "No se usa ninguna URL por defecto a proposito: una ruta de API escrita de "
                "memoria puede fallar de forma silenciosa."
            )

    def exigir_permiso_de_cache(self) -> None:
        if not self.puede_cachearse:
            raise ErrorDeFuenteNoVerificada(
                f"La fuente '{self.clave}' tiene puede_cachearse = false: sus terminos de uso "
                "no han sido leidos, o no permiten redistribucion. La capa de ingesta no "
                "persistira estos datos. Lee la licencia en "
                f"{self.documentacion} y actualiza {_RUTA} si procede."
            )


def _construir(clave: str, d: dict) -> Fuente:
    return Fuente(
        clave=clave, nombre=d.get("nombre", clave), protocolo=d.get("protocolo", ""),
        url_base=d.get("url_base", ""), verificado=bool(d.get("verificado", False)),
        documentacion=d.get("documentacion", ""), licencia=d.get("licencia", "POR VERIFICAR"),
        puede_cachearse=bool(d.get("puede_cachearse", False)),
        cobertura=d.get("cobertura", ""), notas=d.get("notas", ""),
        verificado_el=d.get("verificado_el", ""), verificado_por=d.get("verificado_por", ""),
    )


def cargar_fuente(clave: str, *, ruta: Path | None = None) -> Fuente:
    """Carga una fuente del registro. No comprueba verificacion: eso lo hace el conector."""
    ruta = ruta or _RUTA
    with open(ruta, "rb") as fh:
        todo = tomllib.load(fh)
    if clave not in todo:
        raise KeyError(f"no hay fuente '{clave}' en {ruta}. Disponibles: {sorted(todo)}")
    return _construir(clave, todo[clave])


def listar_fuentes(*, ruta: Path | None = None) -> list[Fuente]:
    """Todas las fuentes del registro, verificadas o no."""
    ruta = ruta or _RUTA
    with open(ruta, "rb") as fh:
        todo = tomllib.load(fh)
    return [_construir(k, v) for k, v in todo.items()]


def resumen_estado(*, ruta: Path | None = None) -> str:
    """Texto para mostrar en la interfaz: que fuentes estan realmente disponibles."""
    fuentes = listar_fuentes(ruta=ruta)
    lineas = ["Estado de las fuentes de datos:"]
    for f in fuentes:
        marca = "OK " if f.verificado and f.url_base.strip() else "SIN VERIFICAR"
        cache = "cacheable" if f.puede_cachearse else "sin permiso de cache"
        lineas.append(f"  [{marca:>13}] {f.clave:12s} {f.nombre} ({cache})")
    n_ok = sum(1 for f in fuentes if f.verificado and f.url_base.strip())
    lineas.append(f"  {n_ok} de {len(fuentes)} fuentes verificadas.")
    if n_ok == 0:
        lineas.append(
            "  NINGUNA fuente esta verificada: la aplicacion no puede ingerir datos reales. "
            "Ver docs/01-fuentes-verificadas.md."
        )
    return "\n".join(lineas)
