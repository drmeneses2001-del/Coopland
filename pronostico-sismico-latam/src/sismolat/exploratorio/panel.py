"""Panel de resultados exploratorios: el nulo con la misma prominencia que el positivo.

Por que existe este modulo
--------------------------
El sesgo de publicacion en este terreno es enorme: las correlaciones aparentes
entre sismicidad y variables ambientales se difunden, y los cientos de pruebas
que no encontraron nada no se cuentan. Una herramienta que muestre un resultado
positivo con graficas y uno nulo con una linea de texto reproduce ese sesgo.

Por eso :func:`presentar` da **el mismo formato y la misma extension** a ambos
casos, e incluye siempre:

* el numero de hipotesis probadas en el proyecto y el umbral corregido,
* el tamano de efecto antes que el p-valor,
* la potencia, sin la cual un no rechazo no significa nada,
* una lectura explicita de lo que el resultado permite y no permite afirmar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..reproducibilidad import RegistroDePruebas

__all__ = ["ResultadoExploratorio", "presentar", "ejecutar_preregistrada"]


@dataclass(frozen=True)
class ResultadoExploratorio:
    """Resultado de una hipotesis exploratoria, lista para presentar."""

    hipotesis: str
    metodo: str
    identificador: str
    n: int
    tamano_efecto: float
    unidad_efecto: str
    p_valor: float
    potencia: float | None
    n_pruebas_proyecto: int
    alfa_corregido: float
    advertencias: tuple[str, ...] = ()
    detalle: dict[str, Any] | None = None

    @property
    def rechaza_nulo(self) -> bool:
        return self.p_valor < self.alfa_corregido


def ejecutar_preregistrada(
    registro: RegistroDePruebas,
    hipotesis: str,
    metodo: str,
    funcion,
    *,
    extraer_efecto,
    extraer_p,
    extraer_potencia=None,
    extraer_n=None,
    alfa_global: float = 0.05,
    unidad_efecto: str = "adimensional",
) -> ResultadoExploratorio:
    """Preregistra la hipotesis, ejecuta la prueba y registra su resultado.

    El orden importa: la hipotesis se registra **antes** de ver el resultado, y
    el registro es append-only con cadena de hashes. Probar la misma hipotesis
    con otros parametros cuenta como prueba nueva y hay que preregistrarla otra
    vez, lo que impide ajustar hasta que salga.
    """
    identificador = registro.preregistrar(hipotesis, metodo, alfa=alfa_global)
    salida = funcion()
    efecto = float(extraer_efecto(salida))
    p = float(extraer_p(salida))
    potencia = float(extraer_potencia(salida)) if extraer_potencia else None
    n = int(extraer_n(salida)) if extraer_n else 0
    registro.registrar_resultado(identificador, p, tamano_efecto=efecto, potencia=potencia)

    avisos = tuple(getattr(salida, "advertencias", ()) or ())
    return ResultadoExploratorio(
        hipotesis=hipotesis, metodo=metodo, identificador=identificador, n=n,
        tamano_efecto=efecto, unidad_efecto=unidad_efecto, p_valor=p, potencia=potencia,
        n_pruebas_proyecto=registro.n_pruebas,
        alfa_corregido=registro.alfa_corregido(alfa_global),
        advertencias=avisos, detalle={"resultado": salida},
    )


def presentar(r: ResultadoExploratorio, *, ancho: int = 74) -> str:
    """Texto del panel. Identico en estructura tanto si rechaza como si no."""
    linea = "=" * ancho
    veredicto = ("SE RECHAZA LA HIPOTESIS NULA" if r.rechaza_nulo
                 else "NO SE RECHAZA LA HIPOTESIS NULA")
    out = [
        linea,
        f"RESULTADO EXPLORATORIO -- {veredicto}",
        linea,
        "",
        f"  Hipotesis preregistrada : {r.hipotesis}",
        f"  Metodo                  : {r.metodo}",
        f"  Identificador           : {r.identificador[:16]}",
        f"  Eventos analizados      : {r.n}",
        "",
        "  TAMANO DE EFECTO (lo que dice si el resultado importa)",
        f"    {r.tamano_efecto:+.5f} {r.unidad_efecto}",
        "",
        "  POTENCIA (sin ella, un no rechazo no significa nada)",
    ]
    if r.potencia is None:
        out.append("    NO CALCULADA. Sin potencia, este resultado no es interpretable "
                   "si no rechaza.")
    else:
        out.append(f"    {r.potencia:.3f}")
        if r.potencia < 0.5 and not r.rechaza_nulo:
            out.append("    ATENCION: potencia por debajo de 0.5. No rechazar el nulo aqui")
            out.append("    NO es evidencia de ausencia de efecto: es falta de datos.")
    out += [
        "",
        "  SIGNIFICANCIA (se lee al final, y nunca sola)",
        f"    p = {r.p_valor:.5g}",
        f"    umbral corregido por multiplicidad = {r.alfa_corregido:.5g}",
        f"    hipotesis probadas en este proyecto = {r.n_pruebas_proyecto}",
    ]
    if r.n_pruebas_proyecto > 1:
        esperados = r.n_pruebas_proyecto * 0.05
        out.append(f"    con {r.n_pruebas_proyecto} pruebas y umbral 0.05 sin corregir se")
        out.append(f"    esperarian {esperados:.1f} falsos positivos solo por azar.")
    out += ["", "  QUE PERMITE AFIRMAR ESTE RESULTADO", ""]
    if r.rechaza_nulo:
        out += [
            "    Los datos son incompatibles con la hipotesis nula al umbral corregido.",
            "    Eso NO establece causalidad, ni que el mecanismo propuesto sea el",
            "    correcto, ni que el efecto sirva para pronosticar. Un efecto pequeno y",
            "    real puede ser estadisticamente solido y practicamente inutil.",
        ]
        if abs(r.tamano_efecto) < 0.05:
            out.append("    El tamano de efecto es diminuto: revisa si tiene alguna")
            out.append("    consecuencia practica antes de darle importancia.")
    else:
        out += [
            "    Los datos son compatibles con la hipotesis nula. Eso NO demuestra que",
            "    el efecto no exista: solo que, si existe, este analisis no lo detecta.",
        ]
        if r.potencia is not None and r.potencia >= 0.8:
            out.append(f"    Con potencia {r.potencia:.2f}, un efecto del tamano supuesto")
            out.append("    se habria detectado con alta probabilidad. Eso sí acota el")
            out.append("    tamano de un posible efecto real.")
        else:
            out.append("    La potencia no permite acotar el tamano de un posible efecto.")
    if r.advertencias:
        out += ["", "  ADVERTENCIAS DEL METODO"]
        for a in r.advertencias:
            out.append(f"    - {a}")
    out += ["", linea]
    return "\n".join(out)
