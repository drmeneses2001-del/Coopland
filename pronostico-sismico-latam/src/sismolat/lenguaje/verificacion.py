"""Verificacion de que el texto generado no contiene cifras inventadas.

La restriccion dura, impuesta estructuralmente
----------------------------------------------
El contrato del proyecto dice que el modelo de lenguaje **no participa en el
calculo del pronostico**: toda cifra proviene del motor numerico determinista.
Pedirselo en el prompt no basta -- un modelo puede redondear, recalcular o
inventar un numero de aspecto plausible, y nadie lo notaria.

Este modulo lo convierte en una comprobacion mecanica: se extraen todas las
cifras del texto generado y se comprueba que **cada una** sea trazable a los
valores que se le pasaron. Las que no lo sean se marcan, y
:func:`exigir_cifras_trazables` lanza una excepcion en lugar de devolver el
texto.

Que se considera trazable
-------------------------
Un numero del texto es trazable si coincide con alguno de los valores de entrada
dentro de la tolerancia de redondeo correspondiente a las cifras que muestra: si
el texto dice "0.089", basta con que el valor de origen redondeado a tres
decimales sea 0.089. Tambien se aceptan sin marcar los numeros de una lista
blanca de cantidades convencionales (anios de periodo de retorno, porcentajes de
probabilidad de la normativa, potencias de diez), porque aparecen legitimamente
en cualquier explicacion.

Lo que este modulo NO puede hacer
---------------------------------
* No detecta afirmaciones cualitativas falsas. "El peligro es alto" no contiene
  cifras y pasa la comprobacion; juzgarlo requiere criterio humano.
* No verifica que la interpretacion sea correcta, solo que las cifras sean las
  que el motor calculo.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable

__all__ = [
    "extraer_numeros", "aplanar_valores", "verificar_cifras", "ResultadoVerificacion",
    "exigir_cifras_trazables", "ErrorDeCifraNoTrazable", "CONVENCIONALES",
]

#: Numeros que pueden aparecer legitimamente en una explicacion sin venir de los
#: datos: periodos de retorno normativos, porcentajes de referencia, unidades.
CONVENCIONALES: frozenset[float] = frozenset({
    0.0, 1.0, 2.0, 3.0, 5.0, 10.0, 50.0, 100.0,
    475.0, 2475.0, 2.0, 90.0, 95.0, 99.0, 68.0,
    1e3, 1e6, 1e9,
})

_PATRON_NUMERO = re.compile(
    r"(?<![\w.])[-+]?(?:\d{1,3}(?:[  ]\d{3})+|\d+)(?:[.,]\d+)?(?:[eE][-+]?\d+)?(?![\w])"
)


class ErrorDeCifraNoTrazable(RuntimeError):
    """El texto generado contiene cifras que no provienen del motor numerico."""


def extraer_numeros(texto: str) -> list[tuple[str, float]]:
    """Todas las cifras del texto, como pares ``(literal, valor)``.

    Acepta separador decimal de punto o de coma y separadores de millar con
    espacio, que es como se escriben en espanol.
    """
    salida: list[tuple[str, float]] = []
    for m in _PATRON_NUMERO.finditer(texto):
        literal = m.group(0)
        limpio = literal.replace(" ", "").replace(" ", "")
        # Coma como decimal solo si va seguida de digitos hasta el final del numero.
        if "," in limpio and "." not in limpio:
            limpio = limpio.replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
        try:
            salida.append((literal, float(limpio)))
        except ValueError:
            continue
    return salida


def aplanar_valores(datos: Any, _profundidad: int = 0) -> list[float]:
    """Todos los valores numericos contenidos en una estructura anidada."""
    if _profundidad > 12:
        return []
    out: list[float] = []
    if isinstance(datos, bool):
        return []
    if isinstance(datos, (int, float)):
        return [float(datos)] if math.isfinite(float(datos)) else []
    if isinstance(datos, dict):
        for k, v in datos.items():
            out.extend(aplanar_valores(k, _profundidad + 1))
            out.extend(aplanar_valores(v, _profundidad + 1))
        return out
    if isinstance(datos, str):
        return [v for _, v in extraer_numeros(datos)]
    if hasattr(datos, "tolist"):
        return aplanar_valores(datos.tolist(), _profundidad + 1)
    if isinstance(datos, Iterable):
        for v in datos:
            out.extend(aplanar_valores(v, _profundidad + 1))
        return out
    if hasattr(datos, "a_dict"):
        return aplanar_valores(datos.a_dict(), _profundidad + 1)
    return out


def _decimales(literal: str) -> int:
    cuerpo = literal.split("e")[0].split("E")[0]
    for sep in (".", ","):
        if sep in cuerpo:
            return len(cuerpo.rsplit(sep, 1)[1])
    return 0


def _coincide(valor_texto: float, literal: str, candidatos: list[float]) -> bool:
    """Un numero del texto coincide si algun candidato lo produce al redondear."""
    d = _decimales(literal)
    for c in candidatos:
        if round(c, d) == round(valor_texto, d):
            return True
        # Tolerancia relativa para notacion cientifica y numeros grandes.
        if c != 0 and abs(valor_texto - c) <= 5e-3 * abs(c):
            return True
        # Multiplos de diez habituales al cambiar de unidad (Pa -> kPa, etc.).
        for factor in (1e-6, 1e-3, 1e-2, 1e2, 1e3, 1e6):
            if c != 0 and abs(valor_texto - c * factor) <= 5e-3 * abs(c * factor):
                return True
    return False


@dataclass(frozen=True)
class ResultadoVerificacion:
    """Resultado de comprobar las cifras de un texto contra los datos de origen."""

    texto: str
    n_cifras: int
    trazables: tuple[str, ...]
    no_trazables: tuple[str, ...]

    @property
    def limpio(self) -> bool:
        return not self.no_trazables

    def informe(self) -> str:
        if self.limpio:
            return (f"Verificacion de cifras: {self.n_cifras} cifras, todas trazables a "
                    "los valores calculados por el motor numerico.")
        return (
            f"VERIFICACION FALLIDA: {len(self.no_trazables)} de {self.n_cifras} cifras no "
            f"provienen del motor numerico: {', '.join(self.no_trazables)}. "
            "El texto no debe mostrarse: contiene numeros que la capa de lenguaje produjo "
            "por su cuenta."
        )


def verificar_cifras(
    texto: str, datos: Any, *, convencionales: Iterable[float] = CONVENCIONALES,
) -> ResultadoVerificacion:
    """Comprueba que toda cifra del texto sea trazable a ``datos``."""
    candidatos = aplanar_valores(datos) + [float(x) for x in convencionales]
    trazables, no_trazables = [], []
    numeros = extraer_numeros(texto)
    for literal, valor in numeros:
        (trazables if _coincide(valor, literal, candidatos) else no_trazables).append(literal)
    return ResultadoVerificacion(
        texto=texto, n_cifras=len(numeros), trazables=tuple(trazables),
        no_trazables=tuple(no_trazables),
    )


def exigir_cifras_trazables(texto: str, datos: Any, **kw) -> str:
    """Devuelve el texto solo si todas sus cifras son trazables; si no, lanza.

    Es la funcion que debe usar la interfaz: prefiere no mostrar nada a mostrar
    un texto con un numero inventado.
    """
    r = verificar_cifras(texto, datos, **kw)
    if not r.limpio:
        raise ErrorDeCifraNoTrazable(r.informe())
    return texto
