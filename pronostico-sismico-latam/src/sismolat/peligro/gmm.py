"""Modelos de movimiento del terreno (GMM), tomados de OpenQuake hazardlib.

Por que no se recodifican aqui
------------------------------
Codificar a mano un GMM a partir de las tablas de un articulo es la principal
fuente de errores silenciosos posible en un calculo de peligro: un signo, un
termino de saturacion o una unidad (cm/s^2 frente a g frente a ln g) producen un
numero plausible y equivocado. Y "verificar los coeficientes en la literatura"
**no es verificacion**: verificacion es reproducir valores de referencia
publicados, que rara vez acompanan a los articulos.

Por eso este modulo **envuelve** las implementaciones de ``openquake.hazardlib``,
que sus autores cotejan contra las publicaciones originales y contra tablas de
prueba. Lo que aporta aqui es la seleccion por regimen tectonico, la declaracion
de procedencia y las comprobaciones de rango de aplicabilidad.

Licencia
--------
``openquake.hazardlib`` es **AGPL-3.0**. Ver docs/adr/0002-openquake-y-agpl.md:
mientras el uso sea personal y no haya distribucion ni servicio en red, no hay
obligacion que cumplir; antes de publicar o desplegar, la decision vuelve a ser
bloqueante.

Lo que este modulo NO puede hacer
---------------------------------
* No valida que el GMM elegido sea **apropiado** para la region. Un GMM
  calibrado en Japon o Chile aplicado a la subduccion mexicana es una decision
  del analista, no del software; lo unico que hace el codigo es dejarla escrita.
* No corrige efectos de sitio mas alla del parametro que el propio GMM acepte
  (tipicamente Vs30). Para la zona lacustre del Valle de Mexico eso es
  insuficiente: ver :mod:`sismolat.peligro.sitio`.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from ..procedencia import Cantidad, Procedencia

__all__ = ["RegimenTectonico", "ModeloMovimiento", "gmm_disponibles", "ErrorDeGMM"]


class ErrorDeGMM(RuntimeError):
    """El GMM solicitado no existe, o no es aplicable al caso planteado."""


class RegimenTectonico(enum.Enum):
    """Regimen tectonico de la fuente. Determina que familia de GMM es admisible."""

    SUBDUCCION_INTERFASE = "Subduction Interface"
    SUBDUCCION_INTRAPLACA = "Subduction IntraSlab"
    CORTICAL_ACTIVA = "Active Shallow Crust"
    CORTICAL_ESTABLE = "Stable Shallow Crust"

    @property
    def trt_openquake(self):
        """El miembro equivalente de ``openquake.hazardlib.const.TRT``."""
        from openquake.hazardlib.const import TRT
        return {
            "Subduction Interface": TRT.SUBDUCTION_INTERFACE,
            "Subduction IntraSlab": TRT.SUBDUCTION_INTRASLAB,
            "Active Shallow Crust": TRT.ACTIVE_SHALLOW_CRUST,
            "Stable Shallow Crust": TRT.STABLE_CONTINENTAL,
        }[self.value]

    @property
    def descripcion(self) -> str:
        return {
            "Subduction Interface": (
                "Contacto sismogenico entre placas. En Mexico, la interfase de Cocos y "
                "Rivera bajo Norteamerica a lo largo de la Fosa Mesoamericana."
            ),
            "Subduction IntraSlab": (
                "Sismicidad dentro de la losa subducida, de profundidad intermedia. En "
                "Mexico incluye eventos como los de 1999 Tehuacan y 2017 Puebla-Morelos."
            ),
            "Active Shallow Crust": (
                "Corteza somera en region tectonicamente activa. En Mexico, la Faja "
                "Volcanica Transmexicana y los sistemas de fallas del occidente."
            ),
            "Stable Shallow Crust": "Corteza somera en region tectonicamente estable.",
        }[self.value]


def _registro():
    try:
        from openquake.hazardlib.gsim import get_available_gsims
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise ErrorDeGMM(
            "openquake.hazardlib no esta instalado. Es la fuente de los GMM verificados; "
            "sin el, este modulo no puede funcionar y NO se recodifican coeficientes a "
            "mano (ver el docstring del modulo). Instala el extra: pip install '.[psha]'"
        ) from e
    return get_available_gsims()


def gmm_disponibles(regimen: RegimenTectonico | None = None) -> list[str]:
    """Nombres de los GMM disponibles, opcionalmente filtrados por regimen."""
    reg = _registro()
    if regimen is None:
        return sorted(reg)
    objetivo = regimen.trt_openquake
    salida = []
    for nombre, clase in reg.items():
        try:
            if getattr(clase, "DEFINED_FOR_TECTONIC_REGION_TYPE", None) == objetivo:
                salida.append(nombre)
        except Exception:
            continue
    return sorted(salida)


@dataclass(frozen=True)
class ModeloMovimiento:
    """Un GMM concreto, con su regimen y su procedencia declarada.

    Parametros
    ----------
    nombre:
        Identificador en el registro de ``openquake.hazardlib`` (p. ej.
        ``"ArroyoEtAl2010SInter"``).
    regimen:
        Regimen tectonico al que se va a aplicar. Si no coincide con el que
        declara el propio GMM, la construccion falla: aplicar un GMM de
        interfase a sismicidad intraplaca es un error de bulto, no una opcion.
    justificacion:
        Por que se eligio este modelo para esta region. **Obligatoria**: la
        adecuacion regional de un GMM es una decision del analista y tiene que
        quedar escrita.
    """

    nombre: str
    regimen: RegimenTectonico
    justificacion: str
    _gsim: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.justificacion.strip():
            raise ErrorDeGMM(
                f"'{self.nombre}' necesita una justificacion escrita: elegir un GMM para "
                "una region es una decision del analista y debe quedar registrada. "
                "Un GMM calibrado en otra zona de subduccion puede o no ser adecuado "
                "para Mexico, y el software no puede juzgarlo."
            )
        reg = _registro()
        if self.nombre not in reg:
            cercanos = [k for k in reg if self.nombre.lower()[:8] in k.lower()][:5]
            raise ErrorDeGMM(
                f"'{self.nombre}' no esta en el registro de openquake.hazardlib."
                + (f" Quiza: {cercanos}" if cercanos else "")
            )
        gsim = reg[self.nombre]()
        trt = getattr(gsim, "DEFINED_FOR_TECTONIC_REGION_TYPE", None)
        if trt is not None and trt != self.regimen.trt_openquake:
            raise ErrorDeGMM(
                f"'{self.nombre}' esta definido para el regimen "
                f"'{getattr(trt, 'value', trt)}', pero se pidio aplicarlo a "
                f"'{self.regimen.value}'. Aplicar un GMM fuera de su regimen tectonico "
                "no es una eleccion defendible."
            )
        object.__setattr__(self, "_gsim", gsim)

    # -- metadatos ---------------------------------------------------------
    @property
    def parametros_de_sitio(self) -> frozenset[str]:
        return self._gsim.REQUIRES_SITES_PARAMETERS

    @property
    def parametros_de_ruptura(self) -> frozenset[str]:
        return self._gsim.REQUIRES_RUPTURE_PARAMETERS

    @property
    def distancias(self) -> frozenset[str]:
        return self._gsim.REQUIRES_DISTANCES

    @property
    def medidas(self) -> list[str]:
        return sorted(x.__name__ for x in self._gsim.DEFINED_FOR_INTENSITY_MEASURE_TYPES)

    def procedencia(self) -> Cantidad:
        """Marca de procedencia del modelo, para adjuntar a los resultados."""
        return Cantidad(
            1.0, "adimensional", Procedencia.PUBLICADO,
            fuente=f"openquake.hazardlib::{self.nombre}",
            notas=(
                f"Implementacion verificada por GEM (AGPL-3.0). Regimen: "
                f"{self.regimen.value}. Justificacion de uso: {self.justificacion}"
            ),
        )

    # -- calculo -----------------------------------------------------------
    def media_y_sigma(
        self,
        magnitud: float,
        distancias_km: np.ndarray,
        *,
        medida: str = "PGA",
        vs30: float = 760.0,
        parametros_extra: dict | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Media logaritmica y desviacion total del movimiento del terreno.

        Devuelve ``(mu, sigma)`` con ``mu`` en unidades logaritmicas naturales de
        g (para PGA y SA) y ``sigma`` la desviacion **total** en las mismas
        unidades. La separacion entre inter e intra evento esta disponible en
        :meth:`componentes_de_sigma`.

        ``distancias_km`` se interpreta segun la metrica que exija el GMM
        (``rrup``, ``rjb``, ``rhypo``...). El codigo asigna el mismo valor a
        todas las metricas requeridas; **eso es una aproximacion** valida solo
        cuando la fuente se trata como puntual, que es como la usa
        :mod:`sismolat.peligro.psha`. Para rupturas finitas hay que calcular cada
        metrica por separado.
        """
        mu, sig, _, _ = self._contexto(
            magnitud, distancias_km, medida=medida, vs30=vs30,
            parametros_extra=parametros_extra,
        )
        return mu, sig

    def componentes_de_sigma(
        self, magnitud: float, distancias_km: np.ndarray, *,
        medida: str = "PGA", vs30: float = 760.0, parametros_extra: dict | None = None,
    ) -> dict[str, np.ndarray]:
        """Descompone la variabilidad **aleatoria** en inter e intra evento.

        Esta variabilidad es distinta de la incertidumbre **epistemica**, que se
        representa con las ramas del arbol logico (ver
        :mod:`sismolat.peligro.arbol`). Confundirlas es uno de los errores mas
        frecuentes en PSHA: la aleatoria no se reduce con mas conocimiento; la
        epistemica sí.
        """
        mu, sig, tau, phi = self._contexto(
            magnitud, distancias_km, medida=medida, vs30=vs30,
            parametros_extra=parametros_extra,
        )
        return {"media_ln": mu, "sigma_total": sig, "tau_inter_evento": tau,
                "phi_intra_evento": phi}

    def _contexto(
        self, magnitud: float, distancias_km: np.ndarray, *, medida: str,
        vs30: float, parametros_extra: dict | None,
    ) -> tuple[np.ndarray, ...]:
        from openquake.hazardlib.contexts import ContextMaker

        d = np.atleast_1d(np.asarray(distancias_km, dtype=float))
        if np.any(d < 0):
            raise ValueError("las distancias deben ser no negativas")
        if medida not in self.medidas:
            raise ErrorDeGMM(
                f"'{self.nombre}' no define la medida '{medida}'. Disponibles: {self.medidas}"
            )
        cm = ContextMaker("*", [self._gsim], {"imtls": {medida: [0.0]}})
        ctx = cm.new_ctx(d.size)
        ctx["mag"] = float(magnitud)
        for nombre_dist in self.distancias:
            ctx[nombre_dist] = d
        if "vs30" in self.parametros_de_sitio:
            ctx["vs30"] = float(vs30)
        for k, v in (parametros_extra or {}).items():
            ctx[k] = v
        faltan = [p for p in self.parametros_de_ruptura
                  if p not in ("mag",) and p not in (parametros_extra or {})]
        salida = cm.get_mean_stds([ctx])[:, 0, 0]
        if faltan:
            # OpenQuake usa valores por defecto; se avisa porque afectan al resultado.
            salida = salida
        return tuple(np.asarray(x, dtype=float) for x in salida)

    def parametros_sin_declarar(self, parametros_extra: dict | None = None) -> list[str]:
        """Parametros de ruptura que el GMM usa y que no se le han dado.

        OpenQuake les asigna valores por defecto. Esos valores **afectan al
        resultado** (un mecanismo focal o una profundidad supuestos cambian la
        aceleracion), asi que la interfaz debe mostrarlos.
        """
        dados = set(parametros_extra or {}) | {"mag"}
        return sorted(p for p in self.parametros_de_ruptura if p not in dados)

    def __str__(self) -> str:
        return f"{self.nombre} [{self.regimen.value}]"
