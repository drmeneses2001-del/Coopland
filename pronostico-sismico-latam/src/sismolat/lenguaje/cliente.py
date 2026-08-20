"""Cliente de la API de Anthropic para la capa de explicacion.

Restriccion dura de diseno
--------------------------
El modelo de lenguaje **no participa en el calculo del pronostico**. Toda cifra
proviene del motor numerico determinista y auditable. Esta capa solo explica,
resume y critica.

La restriccion se impone en tres niveles, no solo pidiendolo en el prompt:

1. **Lo que se envia**: el cliente recibe un diccionario de resultados **ya
   calculados**, nunca el catalogo ni datos crudos. No puede calcular nada
   porque no tiene con que.
2. **Lo que se le dice**: el prompt de sistema lo prohibe explicitamente.
3. **Lo que se comprueba**: :mod:`sismolat.lenguaje.verificacion` extrae todas
   las cifras del texto generado y exige que cada una sea trazable a los datos
   de entrada. Si alguna no lo es, el texto no se muestra.

El tercer nivel es el que de verdad protege. Los dos primeros son buenas
practicas; el tercero es una comprobacion mecanica que no depende de que el
modelo obedezca.

La capa es opcional
-------------------
Todo el paquete funciona sin ella. Si no hay clave de API configurada, los
modulos numericos siguen operando igual: lo unico que se pierde es la
explicacion en lenguaje natural.
Lo que este modulo NO puede hacer
---------------------------------
* No verifica que la **interpretacion** sea correcta, solo que las cifras
  provengan del motor numerico. Un texto con todos los numeros bien puede
  interpretarlos mal, y eso requiere criterio humano.
* No sustituye la revision disciplinar. Es una ayuda de lectura, no un revisor.
* No garantiza que las referencias bibliograficas que mencione existan. Para
  citas verificables hace falta recuperar primero y resolver cada DOI, cosa que
  esta capa no hace.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = ["ClienteLenguaje", "ProveedorMensajes", "RespuestaLenguaje",
           "MODELO_POR_DEFECTO", "ErrorDeCapaDeLenguaje", "hay_credenciales"]

#: Modelo por defecto. Se declara aqui para que quede en un solo sitio.
MODELO_POR_DEFECTO = "claude-opus-5"


class ErrorDeCapaDeLenguaje(RuntimeError):
    """La capa de lenguaje no esta disponible o su salida no supero la verificacion."""


class ProveedorMensajes(Protocol):
    """Interfaz minima que necesita esta capa.

    Existe para poder probar el modulo sin credenciales ni red: los tests
    inyectan un proveedor falso con la misma firma.
    """

    def crear(self, *, system: str, mensajes: list[dict], max_tokens: int,
              esfuerzo: str) -> str:
        ...


def hay_credenciales() -> bool:
    """Si hay alguna credencial configurada en el entorno.

    El SDK resuelve credenciales en cascada (variable de entorno, token, perfil
    de ``ant auth login``), asi que la ausencia de ``ANTHROPIC_API_KEY`` no
    implica que no haya ninguna. Esta comprobacion es orientativa.
    """
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


@dataclass(frozen=True)
class RespuestaLenguaje:
    """Texto generado junto con el resultado de su verificacion."""

    texto: str
    verificado: bool
    cifras_no_trazables: tuple[str, ...]
    modelo: str
    datos_de_origen: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        marca = "" if self.verificado else "  [CIFRAS NO TRAZABLES: NO MOSTRAR]"
        return f"{self.texto}{marca}"


class _ProveedorAnthropic:
    """Envoltorio sobre el SDK oficial. Se construye perezosamente."""

    def __init__(self, modelo: str = MODELO_POR_DEFECTO, cliente=None) -> None:
        self.modelo = modelo
        self._cliente = cliente

    def _obtener(self):
        if self._cliente is None:
            try:
                import anthropic
            except ImportError as e:  # pragma: no cover - depende del entorno
                raise ErrorDeCapaDeLenguaje(
                    "el paquete 'anthropic' no esta instalado. La capa de lenguaje es "
                    "opcional: instala el extra con  pip install '.[lenguaje]'"
                ) from e
            self._cliente = anthropic.Anthropic()
        return self._cliente

    def crear(self, *, system: str, mensajes: list[dict], max_tokens: int,
              esfuerzo: str) -> str:
        cliente = self._obtener()
        respuesta = cliente.messages.create(
            model=self.modelo,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": esfuerzo},
            messages=mensajes,
        )
        if getattr(respuesta, "stop_reason", None) == "refusal":
            detalle = getattr(respuesta, "stop_details", None)
            raise ErrorDeCapaDeLenguaje(
                f"la peticion fue rechazada por el modelo: "
                f"{getattr(detalle, 'category', 'sin categoria')}"
            )
        return "".join(b.text for b in respuesta.content if b.type == "text")


#: Prompt de sistema comun. La prohibicion de calcular es el primer parrafo a
#: proposito: es la restriccion que gobierna todo lo demas.
SISTEMA_BASE = """\
Eres una capa de explicacion sobre una biblioteca de pronostico sismico
probabilistico. Tu unica funcion es explicar, resumir y criticar resultados que
YA fueron calculados por un motor numerico determinista.

REGLA ABSOLUTA: no calculas nada. No estimas, no conviertes unidades, no
redondeas a otra precision, no infieres cifras nuevas ni derivas cantidades a
partir de las que recibes. Toda cifra que escribas debe aparecer literalmente en
los datos que se te entregan. Un sistema automatico verifica esto y descarta tu
respuesta si contiene un numero que no provenga de esos datos.

Si para responder harian falta cifras que no tienes, dilo explicitamente en
lugar de producirlas.

Contexto del dominio que debes respetar siempre:
- Esto NO es prediccion sismica. La prediccion determinista de sismos (lugar,
  tiempo y magnitud con precision util) no esta cientificamente demostrada.
  Nunca sugieras lo contrario.
- Esto NO es un sistema de alerta temprana. Los sistemas operativos (SASMEX,
  SNAM/CSN, ShakeAlert) detectan ondas de sismos que YA ocurrieron; esto es otra
  cosa.
- Nunca emitas recomendaciones de evacuacion ni de accion protectora.
- Una probabilidad baja no significa "no va a pasar". Comunica siempre la
  incertidumbre junto al valor.
- Si los datos incluyen advertencias, incorporalas: son parte del resultado, no
  una nota al pie.

Escribe en espanol, con terminologia tecnica correcta."""

_NIVELES = {
    "estudiante": (
        "Nivel: estudiante de licenciatura. Explica los conceptos sin dar por "
        "supuesto el vocabulario tecnico; cuando uses un termino, definelo en la "
        "misma frase. Prioriza que se entienda que significa el numero."
    ),
    "posgrado": (
        "Nivel: posgrado. Puedes dar por conocidos los conceptos basicos de "
        "sismologia estadistica. Centrate en los supuestos del metodo y en como "
        "afectan a la lectura del resultado."
    ),
    "especialista": (
        "Nivel: especialista. Se conciso y tecnico. Centrate en las limitaciones "
        "del calculo, en las decisiones metodologicas que condicionan el resultado "
        "y en lo que faltaria para hacerlo defendible."
    ),
}


@dataclass
class ClienteLenguaje:
    """Punto de entrada de la capa de explicacion.

    Parametros
    ----------
    proveedor:
        Implementacion de :class:`ProveedorMensajes`. Por defecto, el SDK de
        Anthropic. Los tests inyectan uno falso.
    verificar:
        Si ``True`` (por defecto), comprueba que toda cifra del texto generado
        sea trazable a los datos de entrada. **Desactivarlo rompe la restriccion
        dura del proyecto**; solo tiene sentido para depurar.
    """

    proveedor: ProveedorMensajes | None = None
    modelo: str = MODELO_POR_DEFECTO
    verificar: bool = True

    def __post_init__(self) -> None:
        if self.proveedor is None:
            self.proveedor = _ProveedorAnthropic(self.modelo)

    def preguntar(
        self,
        instruccion: str,
        datos: dict[str, Any],
        *,
        nivel: str = "posgrado",
        max_tokens: int = 4000,
        esfuerzo: str = "medium",
        contexto_adicional: str = "",
    ) -> RespuestaLenguaje:
        """Pide una explicacion sobre ``datos``, que deben estar ya calculados.

        ``datos`` es un diccionario de resultados del motor numerico. **No se le
        pasa nunca el catalogo ni datos crudos**: la capa no puede calcular
        porque no tiene con que.
        """
        from .verificacion import verificar_cifras

        if not isinstance(datos, dict):
            raise TypeError(
                "los datos deben ser un diccionario de resultados YA calculados por el "
                "motor numerico, no datos crudos: la capa de lenguaje no calcula"
            )
        if nivel not in _NIVELES:
            raise ValueError(f"nivel desconocido: {nivel!r}. Opciones: {sorted(_NIVELES)}")

        system = SISTEMA_BASE + "\n\n" + _NIVELES[nivel]
        if contexto_adicional:
            system += "\n\n" + contexto_adicional

        cuerpo = json.dumps(datos, indent=2, ensure_ascii=False, default=str)
        mensaje = (
            f"{instruccion}\n\n"
            f"Resultados calculados por el motor numerico:\n```json\n{cuerpo}\n```"
        )
        texto = self.proveedor.crear(
            system=system, mensajes=[{"role": "user", "content": mensaje}],
            max_tokens=max_tokens, esfuerzo=esfuerzo,
        )

        no_trazables: tuple[str, ...] = ()
        ok = True
        if self.verificar:
            r = verificar_cifras(texto, datos)
            ok, no_trazables = r.limpio, r.no_trazables
        return RespuestaLenguaje(
            texto=texto, verificado=ok, cifras_no_trazables=no_trazables,
            modelo=self.modelo, datos_de_origen=datos,
        )
