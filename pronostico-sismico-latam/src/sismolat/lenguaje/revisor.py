"""Revisor metodologico. Las comprobaciones son deterministas, no del modelo.

Reparto de trabajo
------------------
La revision metodologica que **puede** automatizarse se hace con codigo, no
preguntandole a un modelo de lenguaje: fuga temporal, pruebas multiples sin
corregir, extrapolacion fuera del rango de calibracion, parametros no
verificados propagados, resultados nulos sin potencia. Son comprobaciones
mecanicas y su respuesta debe ser reproducible.

La capa de lenguaje solo **narra** esos hallazgos: los explica al nivel pedido y
los ordena por importancia. No decide si hay un problema; eso ya lo decidio el
codigo.

Lo que este modulo NO puede hacer
---------------------------------
Detectar la fuga que importa de verdad: elegir el modelo, la region de prueba o
los hiperparametros despues de haber visto el catalogo completo. Eso es
indecidible desde el codigo, y lo unico honesto es exigir que quede constancia
(:class:`~sismolat.reproducibilidad.BitacoraDeDecisiones`). Este revisor lo dice
en su propio informe en vez de dar una falsa sensacion de cobertura.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Gravedad", "Hallazgo", "revisar", "InformeDeRevision"]


class Gravedad(enum.Enum):
    """Cuanto compromete el hallazgo la validez del resultado."""

    INVALIDA = "invalida el resultado"
    COMPROMETE = "compromete la interpretacion"
    ADVIERTE = "conviene tenerlo en cuenta"


@dataclass(frozen=True)
class Hallazgo:
    """Un problema metodologico detectado."""

    gravedad: Gravedad
    categoria: str
    descripcion: str
    remedio: str

    def __str__(self) -> str:
        return f"[{self.gravedad.value.upper()}] {self.categoria}: {self.descripcion}"


@dataclass(frozen=True)
class InformeDeRevision:
    """Hallazgos ordenados por gravedad, mas lo que la revision no cubre."""

    hallazgos: tuple[Hallazgo, ...]
    no_cubierto: tuple[str, ...]

    @property
    def invalidantes(self) -> tuple[Hallazgo, ...]:
        return tuple(h for h in self.hallazgos if h.gravedad is Gravedad.INVALIDA)

    @property
    def utilizable(self) -> bool:
        return not self.invalidantes

    def a_dict(self) -> dict[str, Any]:
        """Forma serializable, apta para pasar a la capa de lenguaje."""
        return {
            "n_hallazgos": len(self.hallazgos),
            "n_invalidantes": len(self.invalidantes),
            "utilizable": self.utilizable,
            "hallazgos": [
                {"gravedad": h.gravedad.name, "categoria": h.categoria,
                 "descripcion": h.descripcion, "remedio": h.remedio}
                for h in self.hallazgos
            ],
            "no_cubierto_por_la_revision": list(self.no_cubierto),
        }

    def texto(self) -> str:
        orden = {Gravedad.INVALIDA: 0, Gravedad.COMPROMETE: 1, Gravedad.ADVIERTE: 2}
        lineas = ["REVISION METODOLOGICA", "=" * 66]
        if not self.hallazgos:
            lineas.append("  Sin hallazgos en las comprobaciones automatizables.")
        for h in sorted(self.hallazgos, key=lambda x: orden[x.gravedad]):
            lineas += ["", f"  {h}", f"     remedio: {h.remedio}"]
        lineas += ["", "LO QUE ESTA REVISION NO CUBRE", "-" * 66]
        for n in self.no_cubierto:
            lineas.append(f"  - {n}")
        return "\n".join(lineas)


def revisar(
    *,
    registro_pruebas=None,
    bitacora=None,
    entrenamiento=None,
    corte_temporal=None,
    resultados_nulos: list = (),
    cantidades: list = (),
    pronosticos: list = (),
    curva_de_peligro=None,
    periodos_solicitados: tuple[float, ...] = (),
) -> InformeDeRevision:
    """Ejecuta las comprobaciones metodologicas automatizables.

    Todos los argumentos son opcionales: se comprueba lo que se le da.
    """
    from ..reproducibilidad import verificar_corte_temporal

    hallazgos: list[Hallazgo] = []

    # 1. Fuga temporal por marcas de tiempo.
    if entrenamiento is not None and corte_temporal is not None:
        problemas = verificar_corte_temporal(entrenamiento, corte_temporal, estricto=False)
        for p in problemas:
            hallazgos.append(Hallazgo(
                Gravedad.INVALIDA, "fuga temporal", p,
                "recorta el conjunto de entrenamiento al corte y repite la validacion",
            ))

    # 2. Decisiones tomadas viendo datos posteriores al corte.
    if bitacora is not None:
        for a in bitacora.advertencias():
            hallazgos.append(Hallazgo(
                Gravedad.INVALIDA, "seleccion informada", a,
                "repite el analisis fijando las decisiones antes de mirar el periodo de "
                "prueba, o presenta el resultado como retrospectivo, no pseudo-prospectivo",
            ))

    # 3. Pruebas multiples sin corregir.
    if registro_pruebas is not None and registro_pruebas.n_pruebas > 1:
        n = registro_pruebas.n_pruebas
        alfa_c = registro_pruebas.alfa_corregido(0.05)
        sospechosas = [e for e in registro_pruebas.pruebas
                       if e.get("p_valor") is not None and alfa_c <= e["p_valor"] < 0.05]
        if sospechosas:
            hallazgos.append(Hallazgo(
                Gravedad.COMPROMETE, "pruebas multiples",
                f"{len(sospechosas)} de {n} hipotesis son significativas al 0.05 pero no al "
                f"umbral corregido ({alfa_c:.4g}). Con {n} pruebas se esperan "
                f"{n * 0.05:.1f} falsos positivos solo por azar.",
                "aplica correccion por multiplicidad (Bonferroni o Benjamini-Hochberg) y "
                "reporta el numero total de pruebas del proyecto",
            ))
        if not registro_pruebas.integra():
            hallazgos.append(Hallazgo(
                Gravedad.INVALIDA, "registro manipulado",
                "la cadena de hashes del registro de pruebas esta rota: alguna entrada se "
                "edito despues de crearse",
                "el preregistro no es valido; el analisis debe rehacerse desde un registro "
                "limpio",
            ))

    # 4. Resultados nulos sin potencia.
    for r in resultados_nulos:
        pot = getattr(r, "potencia", None)
        rechaza = getattr(r, "rechaza_nulo", None)
        if rechaza is False:
            if pot is None:
                hallazgos.append(Hallazgo(
                    Gravedad.COMPROMETE, "nulo sin potencia",
                    f"'{getattr(r, 'hipotesis', 'sin nombre')}' no rechaza el nulo y no "
                    "declara potencia: no distingue ausencia de efecto de falta de datos",
                    "calcula la potencia para el tamano de efecto de interes antes de "
                    "interpretar el no rechazo",
                ))
            elif pot < 0.5:
                hallazgos.append(Hallazgo(
                    Gravedad.COMPROMETE, "potencia insuficiente",
                    f"'{getattr(r, 'hipotesis', 'sin nombre')}' no rechaza el nulo con "
                    f"potencia {pot:.2f}: el resultado no es evidencia de ausencia",
                    "amplia el catalogo o reformula la hipotesis a un efecto detectable "
                    "con los datos disponibles",
                ))

    # 5. Cantidades no verificadas propagadas al resultado.
    no_verificadas = [c for c in cantidades if getattr(c, "verificado", True) is False]
    if no_verificadas:
        fuentes = {getattr(c, "fuente", None) or "sin fuente" for c in no_verificadas}
        hallazgos.append(Hallazgo(
            Gravedad.COMPROMETE, "parametros no verificados",
            f"{len(no_verificadas)} cantidades del resultado derivan de parametros no "
            f"cotejados contra su fuente original: {sorted(fuentes)[:3]}",
            "verifica los coeficientes contra la publicacion citada y marca verificado = "
            "true, o presenta el resultado como no verificado",
        ))

    # 6. Prueba poissoniana sobre pronostico sobredisperso.
    for p in pronosticos:
        if getattr(p, "poisson_valido", True) is False:
            hallazgos.append(Hallazgo(
                Gravedad.ADVIERTE, "supuesto de Poisson",
                f"el pronostico '{getattr(p, 'nombre', '?')}' esta marcado como no "
                "poissoniano: las pruebas poissonianas produciran rechazos espurios",
                "usa las versiones basadas en catalogo (n_test_catalogo, s_test_catalogo, "
                "m_test_catalogo)",
            ))

    # 7. Extrapolacion fuera del rango calculado de la curva de peligro.
    if curva_de_peligro is not None and periodos_solicitados:
        tasas = getattr(curva_de_peligro, "tasas", None)
        if tasas is not None and len(tasas):
            positivas = [t for t in tasas if t > 0]
            if positivas:
                t_min, t_max = min(positivas), max(positivas)
                for T in periodos_solicitados:
                    objetivo = 1.0 / T
                    if objetivo > t_max or objetivo < t_min:
                        hallazgos.append(Hallazgo(
                            Gravedad.INVALIDA, "extrapolacion",
                            f"se pidio un periodo de retorno de {T:g} anios, fuera del "
                            f"rango de niveles evaluados [{1/t_max:.0f}, {1/t_min:.0f}] anios",
                            "amplia los niveles de intensidad de la curva en lugar de "
                            "extrapolar",
                        ))

    no_cubierto = (
        "La fuga por SELECCION: elegir modelo, region de prueba o hiperparametros "
        "despues de haber visto el catalogo completo. Es indecidible desde el codigo; "
        "solo queda exigir constancia escrita en la bitacora de decisiones.",
        "Si el GMM elegido es apropiado para la region. Es juicio disciplinar.",
        "Si las decisiones por defecto (correccion de Mc, umbrales de deduplicacion, "
        "metodo de decluster) son defendibles para este catalogo concreto.",
        "Si la interpretacion cualitativa del resultado es correcta.",
    )
    return InformeDeRevision(hallazgos=tuple(hallazgos), no_cubierto=no_cubierto)
