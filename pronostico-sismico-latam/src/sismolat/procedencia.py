"""Tipos base que hacen imposible construir una cantidad sin procedencia.

Este modulo implementa la regla 4 del contrato epistemologico: *un valor sin
procedencia es un bug*. La regla no se impone por convencion ni por comentario,
sino por el constructor: no existe forma de crear una `Cantidad` sin declarar
unidad y procedencia, y las procedencias que afirman respaldo empirico exigen
ademas una fuente citable.

La motivacion esta desarrollada en docs/00-contrato-epistemologico.md.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field, replace
from typing import Any

__all__ = [
    "Procedencia",
    "Cantidad",
    "ErrorDeProcedencia",
    "adimensional",
    "convencion",
    "supuesto",
]


class ErrorDeProcedencia(ValueError):
    """Se intento construir o usar una cantidad sin procedencia valida."""


class Procedencia(enum.Enum):
    """Vocabulario controlado de origen de un valor.

    El vocabulario es cerrado a proposito. Un campo de texto libre se degrada a
    cadena vacia en dos semanas; un enum no.
    """

    #: Observacion instrumental directa (p. ej. un tiempo de arribo leido).
    MEDIDO = "MEDIDO"
    #: Calculado por este software a partir de otras cantidades.
    DERIVADO = "DERIVADO"
    #: Tomado de una publicacion o de un catalogo institucional identificable.
    PUBLICADO = "PUBLICADO"
    #: Valor elegido por quien analiza, sin respaldo empirico especifico.
    SUPUESTO = "SUPUESTO"
    #: Uso establecido en la disciplina, no una medicion (p. ej. b = 1).
    CONVENCION = "CONVENCION"
    #: Estimacion aproximada, de orden de magnitud.
    ESTIMACION = "ESTIMACION"

    @property
    def exige_fuente(self) -> bool:
        """Procedencias que afirman respaldo externo y por tanto deben citarlo."""
        return self in (Procedencia.MEDIDO, Procedencia.PUBLICADO, Procedencia.DERIVADO)

    @property
    def es_debil(self) -> bool:
        """Procedencias que la interfaz debe marcar visualmente como no empiricas."""
        return self in (Procedencia.SUPUESTO, Procedencia.CONVENCION, Procedencia.ESTIMACION)


@dataclass(frozen=True, slots=True)
class Cantidad:
    """Un numero con unidad, incertidumbre y procedencia. Nunca un numero desnudo.

    Parametros
    ----------
    valor:
        Valor central. Debe ser finito.
    unidad:
        Unidad fisica como cadena. Para cantidades sin dimension usar
        ``"adimensional"`` de forma explicita: omitirla no es una opcion.
    procedencia:
        Miembro de :class:`Procedencia`.
    fuente:
        Cita, DOI, nombre de agencia o identificador del catalogo. Obligatoria
        cuando ``procedencia.exige_fuente``.
    incertidumbre:
        Desviacion estandar (1-sigma) en las mismas unidades que ``valor``.
        ``None`` significa *no cuantificada*, que no es lo mismo que cero y se
        muestra como tal.
    verificado:
        ``False`` marca un valor cuya fuente no ha sido comprobada contra el
        documento original. Se propaga a todo lo que se derive de el.
    notas:
        Texto libre para condiciones de validez, rango de calibracion, etc.
    """

    valor: float
    unidad: str
    procedencia: Procedencia
    fuente: str | None = None
    incertidumbre: float | None = None
    verificado: bool = True
    notas: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.procedencia, Procedencia):
            raise ErrorDeProcedencia(
                f"procedencia debe ser un miembro de Procedencia, no {type(self.procedencia)!r}"
            )
        if not isinstance(self.unidad, str) or not self.unidad.strip():
            raise ErrorDeProcedencia(
                "unidad es obligatoria; usa 'adimensional' explicitamente si no tiene dimension"
            )
        valor = float(self.valor)
        if not math.isfinite(valor):
            raise ErrorDeProcedencia(f"valor debe ser finito, se recibio {self.valor!r}")
        object.__setattr__(self, "valor", valor)

        if self.procedencia.exige_fuente and not (self.fuente or "").strip():
            raise ErrorDeProcedencia(
                f"procedencia {self.procedencia.value} exige una fuente citable "
                "(publicacion, DOI, agencia o identificador de catalogo)"
            )
        if self.incertidumbre is not None:
            inc = float(self.incertidumbre)
            if not math.isfinite(inc) or inc < 0:
                raise ErrorDeProcedencia(
                    f"incertidumbre debe ser finita y no negativa, se recibio {self.incertidumbre!r}"
                )
            object.__setattr__(self, "incertidumbre", inc)

    # -- presentacion -----------------------------------------------------
    def __str__(self) -> str:
        if self.incertidumbre is None:
            nucleo = f"{self.valor:.4g} {self.unidad} (sigma no cuantificada)"
        else:
            nucleo = f"{self.valor:.4g} +/- {self.incertidumbre:.2g} {self.unidad}"
        etiqueta = self.procedencia.value
        if not self.verificado:
            etiqueta += "/NO-VERIFICADO"
        if self.fuente:
            return f"{nucleo} [{etiqueta}: {self.fuente}]"
        return f"{nucleo} [{etiqueta}]"

    @property
    def etiqueta_ui(self) -> str:
        """Marca corta que la interfaz debe mostrar pegada al numero."""
        if not self.verificado:
            return f"[{self.procedencia.value}/NO-VERIFICADO]"
        return f"[{self.procedencia.value}]"

    # -- derivacion -------------------------------------------------------
    def derivar(
        self,
        valor: float,
        *,
        unidad: str,
        fuente: str,
        incertidumbre: float | None = None,
        notas: str = "",
    ) -> "Cantidad":
        """Produce una cantidad DERIVADA que hereda el estado de verificacion.

        Si esta cantidad no estaba verificada, nada calculado a partir de ella
        puede estarlo. La contaminacion se propaga hacia adelante a proposito.
        """
        return Cantidad(
            valor=valor,
            unidad=unidad,
            procedencia=Procedencia.DERIVADO,
            fuente=fuente,
            incertidumbre=incertidumbre,
            verificado=self.verificado,
            notas=notas,
        )

    def marcar_no_verificado(self, motivo: str) -> "Cantidad":
        """Degrada la cantidad a no verificada, acumulando el motivo en notas."""
        notas = f"{self.notas} | NO VERIFICADO: {motivo}".strip(" |")
        return replace(self, verificado=False, notas=notas)

    def a_dict(self) -> dict[str, Any]:
        """Serializacion plana para base de datos, JSON o exportacion."""
        return {
            "valor": self.valor,
            "unidad": self.unidad,
            "procedencia": self.procedencia.value,
            "fuente": self.fuente,
            "incertidumbre": self.incertidumbre,
            "verificado": self.verificado,
            "notas": self.notas,
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "Cantidad":
        return cls(
            valor=d["valor"],
            unidad=d["unidad"],
            procedencia=Procedencia(d["procedencia"]),
            fuente=d.get("fuente"),
            incertidumbre=d.get("incertidumbre"),
            verificado=d.get("verificado", True),
            notas=d.get("notas", ""),
        )


def combinar_verificacion(*cantidades: Cantidad) -> bool:
    """Una derivacion esta verificada solo si todos sus insumos lo estan."""
    return all(c.verificado for c in cantidades)


# -- constructores de conveniencia ---------------------------------------
def adimensional(
    valor: float,
    procedencia: Procedencia,
    *,
    fuente: str | None = None,
    incertidumbre: float | None = None,
    verificado: bool = True,
    notas: str = "",
) -> Cantidad:
    """Cantidad sin dimension, con la unidad declarada explicitamente."""
    return Cantidad(
        valor=valor,
        unidad="adimensional",
        procedencia=procedencia,
        fuente=fuente,
        incertidumbre=incertidumbre,
        verificado=verificado,
        notas=notas,
    )


def convencion(valor: float, unidad: str, *, motivo: str, fuente: str | None = None) -> Cantidad:
    """Valor de uso establecido en la disciplina. `motivo` explica por que se usa.

    Una convencion sin motivo es indistinguible de un numero magico, asi que el
    motivo es obligatorio.
    """
    if not motivo.strip():
        raise ErrorDeProcedencia("una CONVENCION debe declarar por que se adopta")
    return Cantidad(
        valor=valor,
        unidad=unidad,
        procedencia=Procedencia.CONVENCION,
        fuente=fuente,
        incertidumbre=None,
        notas=motivo,
    )


def supuesto(valor: float, unidad: str, *, motivo: str) -> Cantidad:
    """Valor elegido por quien analiza. `motivo` es obligatorio."""
    if not motivo.strip():
        raise ErrorDeProcedencia("un SUPUESTO debe declarar en que se basa")
    return Cantidad(
        valor=valor,
        unidad=unidad,
        procedencia=Procedencia.SUPUESTO,
        incertidumbre=None,
        notas=motivo,
    )
