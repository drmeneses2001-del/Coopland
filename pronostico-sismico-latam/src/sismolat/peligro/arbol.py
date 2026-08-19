"""Arbol logico: incertidumbre epistemica con pesos explicitos.

Que representa y que no
-----------------------
El arbol logico representa **incertidumbre epistemica**: no saber que modelo,
que valor de b o que m_max es el correcto. Cada rama es una hipotesis
alternativa con un peso que expresa credibilidad relativa, y el resultado es una
**distribucion de curvas de peligro**, no una curva.

La variabilidad **aleatoria** —la dispersion de los registros alrededor de la
mediana del GMM— ya esta dentro de cada curva, en la sigma del modelo. Las dos
son distintas y no deben mezclarse: la epistemica se reduce con mas
conocimiento, la aleatoria no.

Sobre los pesos
---------------
Los pesos son juicio experto, no probabilidades medidas. Un arbol con pesos
inventados produce fractiles con apariencia de rigor y sin contenido. Por eso
:class:`NodoLogico` exige una justificacion escrita por nodo, y el resultado
arrastra esas justificaciones.

Un aviso practico: los fractiles del arbol **no son intervalos de confianza**.
Son cuantiles de una distribucion construida a partir de juicios, y su anchura
depende tanto de cuantas ramas se pusieron como de cuanta incertidumbre real
hay. Anadir ramas parecidas estrecha los fractiles sin reducir la ignorancia.
Lo que este modulo NO puede hacer
---------------------------------
* No valida los pesos. Que sumen 1 es lo unico comprobable; que expresen
  credibilidad relativa razonable es juicio experto y el codigo no lo juzga.
* No detecta ramas correlacionadas. Dos GMM casi identicos con pesos
  independientes cuentan como dos alternativas y estrechan artificialmente los
  fractiles.
* No completa el arbol: si falta una fuente de incertidumbre epistemica
  relevante, el resultado parecera mejor restringido de lo que esta.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from .psha import CurvaDePeligro, Sitio, curva_de_peligro

__all__ = ["Rama", "NodoLogico", "ArbolLogico", "ResultadoArbol", "peligro_con_arbol"]


@dataclass(frozen=True)
class Rama:
    """Una alternativa dentro de un nodo, con su peso y su valor."""

    etiqueta: str
    peso: float
    valor: Any

    def __post_init__(self) -> None:
        if not 0 < self.peso <= 1:
            raise ValueError(f"el peso de '{self.etiqueta}' debe estar en (0, 1]")


@dataclass(frozen=True)
class NodoLogico:
    """Un punto de decision del arbol: alternativas excluyentes con pesos."""

    nombre: str
    ramas: tuple[Rama, ...]
    justificacion: str

    def __post_init__(self) -> None:
        if len(self.ramas) < 1:
            raise ValueError(f"el nodo '{self.nombre}' no tiene ramas")
        suma = sum(r.peso for r in self.ramas)
        if abs(suma - 1.0) > 1e-9:
            raise ValueError(
                f"los pesos del nodo '{self.nombre}' suman {suma:.6f}, deben sumar 1. "
                "Un nodo cuyos pesos no suman 1 no representa alternativas excluyentes."
            )
        if not self.justificacion.strip():
            raise ValueError(
                f"el nodo '{self.nombre}' necesita justificacion escrita: los pesos de un "
                "arbol logico son juicio experto, y sin justificacion producen fractiles "
                "con apariencia de rigor y sin contenido."
            )


@dataclass(frozen=True)
class ArbolLogico:
    """Conjunto de nodos. Las combinaciones son el producto cartesiano."""

    nodos: tuple[NodoLogico, ...]

    @property
    def n_combinaciones(self) -> int:
        n = 1
        for nodo in self.nodos:
            n *= len(nodo.ramas)
        return n

    def combinaciones(self):
        """Genera ``(asignacion, peso, etiquetas)`` por cada hoja del arbol."""
        for combo in itertools.product(*[nodo.ramas for nodo in self.nodos]):
            asignacion = {nodo.nombre: rama.valor
                          for nodo, rama in zip(self.nodos, combo)}
            etiquetas = tuple(f"{nodo.nombre}={rama.etiqueta}"
                              for nodo, rama in zip(self.nodos, combo))
            peso = 1.0
            for rama in combo:
                peso *= rama.peso
            yield asignacion, peso, etiquetas

    def resumen(self) -> str:
        lineas = [f"Arbol logico: {len(self.nodos)} nodos, "
                  f"{self.n_combinaciones} combinaciones"]
        for nodo in self.nodos:
            lineas.append(f"  {nodo.nombre}: " + ", ".join(
                f"{r.etiqueta} ({r.peso:g})" for r in nodo.ramas))
            lineas.append(f"     porque: {nodo.justificacion}")
        return "\n".join(lineas)


@dataclass(frozen=True)
class ResultadoArbol:
    """Distribucion de curvas de peligro sobre las hojas del arbol."""

    niveles: np.ndarray
    #: Matriz (n_hojas, n_niveles) con la tasa de excedencia de cada hoja.
    tasas: np.ndarray
    pesos: np.ndarray
    etiquetas: tuple[tuple[str, ...], ...]
    sitio: Sitio
    medida: str
    arbol: ArbolLogico
    advertencias: tuple[str, ...] = ()

    @property
    def media(self) -> np.ndarray:
        """Curva media ponderada por pesos. Es la que suele usarse en normativa."""
        return np.average(self.tasas, axis=0, weights=self.pesos)

    def fractil(self, q: float) -> np.ndarray:
        """Fractil ponderado de la tasa de excedencia en cada nivel.

        **No es un intervalo de confianza**: es un cuantil de una distribucion
        construida a partir de juicios expertos.
        """
        if not 0 <= q <= 1:
            raise ValueError("q debe estar en [0, 1]")
        salida = np.empty(self.niveles.size)
        for k in range(self.niveles.size):
            columna = self.tasas[:, k]
            orden = np.argsort(columna)
            acum = np.cumsum(self.pesos[orden])
            acum /= acum[-1]
            i = int(np.searchsorted(acum, q, side="left"))
            salida[k] = columna[orden][min(i, orden.size - 1)]
        return salida

    def curva_media(self) -> CurvaDePeligro:
        """Envuelve la curva media como :class:`CurvaDePeligro` para reutilizar su API."""
        return CurvaDePeligro(
            niveles=self.niveles, tasas=self.media, sitio=self.sitio, medida=self.medida,
            modelos=("media del arbol logico",), advertencias=self.advertencias,
        )

    def dispersion_epistemica(self, periodo_retorno_anios: float = 475.0) -> dict[str, float]:
        """Cuanto se mueve el nivel de diseno entre las ramas del arbol.

        Es la medida honesta de "cuanto de este resultado es ignorancia". Si el
        cociente entre el fractil 84 y el 16 es grande, el peligro esta mal
        restringido y presentar solo la media lo oculta.
        """
        def nivel(tasas: np.ndarray) -> float:
            objetivo = 1.0 / periodo_retorno_anios
            val = tasas > 0
            t, n = tasas[val], self.niveles[val]
            if objetivo > t.max() or objetivo < t.min():
                return float("nan")
            orden = np.argsort(t)
            return float(np.exp(np.interp(np.log(objetivo), np.log(t[orden]),
                                          np.log(n[orden]))))
        n16, n50, n84 = (nivel(self.fractil(q)) for q in (0.16, 0.50, 0.84))
        nm = nivel(self.media)
        return {"periodo_retorno": periodo_retorno_anios, "media": nm,
                "fractil_16": n16, "fractil_50": n50, "fractil_84": n84,
                "razon_84_16": n84 / n16 if n16 and np.isfinite(n16) else float("nan")}


def peligro_con_arbol(
    sitio: Sitio,
    arbol: ArbolLogico,
    constructor: Callable[[dict[str, Any]], Sequence[tuple]],
    niveles: np.ndarray,
    *,
    medida: str = "PGA",
    dm: float = 0.1,
    **kw,
) -> ResultadoArbol:
    """Calcula una curva de peligro por cada hoja del arbol logico.

    ``constructor`` recibe la asignacion de valores de una hoja y devuelve la
    lista de pares ``(FuenteArea, ModeloMovimiento)`` correspondiente.
    """
    niveles = np.asarray(niveles, dtype=float)
    filas, pesos, etiquetas, avisos = [], [], [], []
    for asignacion, peso, etiqueta in arbol.combinaciones():
        curva = curva_de_peligro(sitio, constructor(asignacion), niveles,
                                 medida=medida, dm=dm, **kw)
        filas.append(curva.tasas)
        pesos.append(peso)
        etiquetas.append(etiqueta)
        avisos.extend(curva.advertencias)

    avisos.append(
        f"Arbol de {arbol.n_combinaciones} hojas. Los pesos son juicio experto: los "
        "fractiles NO son intervalos de confianza y su anchura depende de cuantas ramas "
        "se incluyeron, no solo de la incertidumbre real."
    )
    return ResultadoArbol(
        niveles=niveles, tasas=np.array(filas), pesos=np.array(pesos, dtype=float),
        etiquetas=tuple(etiquetas), sitio=sitio, medida=medida, arbol=arbol,
        advertencias=tuple(dict.fromkeys(avisos)),
    )
