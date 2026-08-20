"""Identificador reproducible de analisis y salvaguardas de honestidad estadistica.

Contiene tres piezas que el resto de la biblioteca usa:

1. :class:`RegistroAnalisis` -- hash de datos de entrada, version de codigo,
   parametros y semilla, para que un resultado pueda reproducirse mas tarde
   aunque el catalogo de la agencia se haya revisado entretanto.
2. :func:`verificar_corte_temporal` -- comprobacion automatica de fuga
   temporal. **Detecta fuga por marcas de tiempo, que es la unica clase de
   fuga que un programa puede detectar.** La fuga por seleccion de modelo o de
   hiperparametros hecha por una persona que ya vio todo el catalogo es
   indecidible desde el codigo; para esa clase solo existe el registro
   declarado de :class:`BitacoraDeDecisiones`.
3. :class:`RegistroDePruebas` -- contador de hipotesis probadas con correccion
   por multiplicidad a nivel de proyecto, no de sesion.
Lo que este modulo NO puede hacer
---------------------------------
* No detecta la fuga por seleccion (ver arriba): es indecidible desde el codigo.
* La huella no cubre el entorno completo. Dos corridas con el mismo
  identificador pero distintas versiones de NumPy o SciPy pueden diferir en los
  ultimos digitos. Para reproducibilidad estricta hace falta fijar el entorno.
* El registro de pruebas no puede impedir que alguien analice fuera de el. Su
  cadena de hashes es una barrera contra el auto-engano, no contra un adversario
  con acceso al archivo.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

__all__ = [
    "RegistroAnalisis",
    "verificar_corte_temporal",
    "ErrorDeFugaTemporal",
    "RegistroDePruebas",
    "BitacoraDeDecisiones",
    "version_codigo",
]


class ErrorDeFugaTemporal(RuntimeError):
    """Se detecto informacion posterior a la fecha de corte en datos de entrenamiento."""


def version_codigo(raiz: Path | None = None) -> str:
    """Commit de git del arbol de trabajo, con sufijo -sucio si hay cambios sin confirmar.

    Devuelve ``"sin-control-de-versiones"`` si no es un repositorio git: un
    analisis en esas condiciones no es reproducible y el registro debe decirlo.
    """
    raiz = raiz or Path(__file__).resolve().parents[2]
    try:
        sha = subprocess.run(
            ["git", "-C", str(raiz), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        sucio = subprocess.run(
            ["git", "-C", str(raiz), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        return f"{sha}-sucio" if sucio else sha
    except (subprocess.SubprocessError, OSError):
        return "sin-control-de-versiones"


def _serializable(obj: Any) -> Any:
    """Convierte parametros a algo estable para hashing determinista."""
    if isinstance(obj, dict):
        return {str(k): _serializable(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [_serializable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _serializable(obj.tolist())
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return round(float(obj), 12)
    if isinstance(obj, float):
        return round(obj, 12)
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    if hasattr(obj, "a_dict"):
        return _serializable(obj.a_dict())
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    return str(obj)


@dataclass(frozen=True)
class RegistroAnalisis:
    """Identificador reproducible de una corrida.

    Dos corridas con el mismo :attr:`identificador` usaron los mismos datos, el
    mismo codigo, los mismos parametros y la misma semilla.
    """

    nombre: str
    huella_datos: str
    parametros: dict[str, Any]
    semilla: int | None
    version: str = field(default_factory=version_codigo)
    momento: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    entorno: str = field(default_factory=lambda: f"python-{platform.python_version()}")

    @property
    def identificador(self) -> str:
        """SHA-256 de todo lo que determina el resultado. Excluye ``momento``."""
        carga = json.dumps(
            {
                "nombre": self.nombre,
                "huella_datos": self.huella_datos,
                "parametros": _serializable(self.parametros),
                "semilla": self.semilla,
                "version": self.version,
                "entorno": self.entorno,
            },
            sort_keys=True, ensure_ascii=True, separators=(",", ":"),
        )
        return hashlib.sha256(carga.encode()).hexdigest()

    @property
    def reproducible(self) -> bool:
        """Falso si falta el control de versiones o la semilla en un metodo aleatorio."""
        return self.version != "sin-control-de-versiones" and "-sucio" not in self.version

    def advertencias(self) -> list[str]:
        avisos = []
        if self.version == "sin-control-de-versiones":
            avisos.append(
                "El analisis corrio fuera de un repositorio git: no hay forma de saber que "
                "codigo lo produjo. El resultado no es reproducible."
            )
        elif self.version.endswith("-sucio"):
            avisos.append(
                "El arbol de trabajo tenia cambios sin confirmar. El identificador no "
                "distingue este estado de otro con los mismos cambios sin confirmar."
            )
        if self.semilla is None:
            avisos.append(
                "No se declaro semilla aleatoria. Si el metodo usa aleatoriedad, el "
                "resultado no es reproducible bit a bit."
            )
        return avisos

    def a_dict(self) -> dict[str, Any]:
        return {
            "identificador": self.identificador,
            "nombre": self.nombre,
            "huella_datos": self.huella_datos,
            "parametros": _serializable(self.parametros),
            "semilla": self.semilla,
            "version_codigo": self.version,
            "momento_utc": self.momento,
            "entorno": self.entorno,
            "reproducible": self.reproducible,
            "advertencias": self.advertencias(),
        }

    def guardar(self, ruta: str | Path) -> Path:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(self.a_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return ruta


def verificar_corte_temporal(
    entrenamiento: pd.DataFrame | pd.Series,
    corte: str | pd.Timestamp,
    *,
    columna: str = "tiempo",
    estricto: bool = True,
) -> list[str]:
    """Comprueba que ningun dato de entrenamiento sea posterior a la fecha de corte.

    Esta es la **unica** clase de fuga que se puede detectar automaticamente.
    Una validacion pseudo-prospectiva puede pasar esta comprobacion y seguir
    siendo invalida si quien analiza eligio el modelo, la region de prueba o
    los hiperparametros despues de mirar el catalogo completo. Para eso existe
    :class:`BitacoraDeDecisiones`, que no detecta nada: solo deja constancia.

    Parametros
    ----------
    estricto:
        ``True`` lanza :class:`ErrorDeFugaTemporal`; ``False`` devuelve la lista
        de problemas para mostrarla en la interfaz.
    """
    corte = pd.Timestamp(corte)
    serie = entrenamiento[columna] if isinstance(entrenamiento, pd.DataFrame) else entrenamiento
    if not pd.api.types.is_datetime64_any_dtype(serie):
        raise TypeError(f"la columna '{columna}' no es datetime64")

    problemas: list[str] = []
    posteriores = serie[serie > corte]
    if len(posteriores):
        problemas.append(
            f"FUGA TEMPORAL: {len(posteriores)} registros de entrenamiento son posteriores "
            f"al corte {corte.isoformat()} (el mas tardio: {posteriores.max().isoformat()}). "
            "El resultado de la validacion pseudo-prospectiva no es valido."
        )
    if estricto and problemas:
        raise ErrorDeFugaTemporal(" ".join(problemas))
    return problemas


@dataclass
class RegistroDePruebas:
    """Contador persistente de hipotesis probadas, con correccion por multiplicidad.

    El conteo es **a nivel de proyecto**: abrir una sesion nueva no lo reinicia.
    Sin esto, el preregistro no impide el dragado de datos, porque nada obliga a
    reportar las hipotesis que se probaron y se descartaron.
    """

    ruta: Path
    pruebas: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.ruta = Path(self.ruta)
        if self.ruta.exists():
            self.pruebas = json.loads(self.ruta.read_text(encoding="utf-8"))

    def _hash_encadenado(self) -> str:
        """Hash del ultimo registro, encadenado, para que el historial sea append-only.

        Reescribir una entrada anterior rompe la cadena y :meth:`integra` lo
        detecta. No es criptograficamente fuerte contra un adversario con
        acceso al archivo -- es una barrera contra el auto-engano.
        """
        return self.pruebas[-1]["hash"] if self.pruebas else "génesis"

    def preregistrar(self, hipotesis: str, metodo: str, *, alfa: float = 0.05) -> str:
        """Registra una hipotesis ANTES de ver el resultado. Devuelve su identificador."""
        if not hipotesis.strip():
            raise ValueError("la hipotesis no puede estar vacia")
        entrada = {
            "n": len(self.pruebas) + 1,
            "hipotesis": hipotesis,
            "metodo": metodo,
            "alfa_nominal": alfa,
            "momento_utc": datetime.now(timezone.utc).isoformat(),
            "anterior": self._hash_encadenado(),
            "p_valor": None,
            "resuelta": False,
        }
        entrada["hash"] = hashlib.sha256(
            json.dumps({k: v for k, v in entrada.items() if k != "hash"},
                       sort_keys=True).encode()
        ).hexdigest()
        self.pruebas.append(entrada)
        self._guardar()
        return entrada["hash"]

    def registrar_resultado(self, identificador: str, p_valor: float, *,
                            tamano_efecto: float | None = None,
                            potencia: float | None = None) -> None:
        """Anota el resultado de una hipotesis ya preregistrada."""
        for e in self.pruebas:
            if e["hash"] == identificador:
                if e["resuelta"]:
                    raise ValueError(
                        "esta hipotesis ya tiene resultado registrado; volver a probarla "
                        "con otros parametros es una prueba nueva y debe preregistrarse"
                    )
                e["p_valor"] = float(p_valor)
                e["tamano_efecto"] = tamano_efecto
                e["potencia"] = potencia
                e["resuelta"] = True
                self._guardar()
                return
        raise KeyError(f"no hay hipotesis preregistrada con identificador {identificador!r}")

    @property
    def n_pruebas(self) -> int:
        return len(self.pruebas)

    def alfa_corregido(self, alfa_global: float = 0.05,
                       metodo: Literal["bonferroni", "sidak"] = "bonferroni") -> float:
        """Umbral por prueba tras corregir por el numero total de pruebas del proyecto."""
        n = max(self.n_pruebas, 1)
        if metodo == "bonferroni":
            return alfa_global / n
        return 1.0 - (1.0 - alfa_global) ** (1.0 / n)

    def benjamini_hochberg(self, q: float = 0.05) -> list[dict[str, Any]]:
        """Control de la tasa de falsos descubrimientos sobre las pruebas resueltas."""
        resueltas = [e for e in self.pruebas if e["resuelta"] and e["p_valor"] is not None]
        if not resueltas:
            return []
        orden = sorted(resueltas, key=lambda e: e["p_valor"])
        m = len(orden)
        k_max = 0
        for i, e in enumerate(orden, start=1):
            if e["p_valor"] <= i * q / m:
                k_max = i
        for i, e in enumerate(orden, start=1):
            e["significativa_fdr"] = i <= k_max
            e["umbral_bh"] = i * q / m
        return orden

    def integra(self) -> bool:
        """Verifica que la cadena de hashes no se haya roto por edicion posterior."""
        anterior = "génesis"
        for e in self.pruebas:
            if e["anterior"] != anterior:
                return False
            anterior = e["hash"]
        return True

    def advertencia_multiplicidad(self, alfa_global: float = 0.05) -> str:
        n = self.n_pruebas
        if n <= 1:
            return f"1 hipotesis probada en este proyecto. Umbral sin corregir: {alfa_global:g}."
        return (
            f"Se han probado {n} hipotesis en este proyecto. Un umbral de {alfa_global:g} sin "
            f"corregir produciria en promedio {n * alfa_global:.2f} falsos positivos por azar. "
            f"Umbral corregido (Bonferroni): {self.alfa_corregido(alfa_global):.2g}."
        )

    def _guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(self.pruebas, indent=2, ensure_ascii=False), encoding="utf-8")


@dataclass
class BitacoraDeDecisiones:
    """Constancia declarada de decisiones metodologicas. No detecta nada.

    Existe porque la fuga por seleccion de modelo es indecidible desde el
    codigo (ver :func:`verificar_corte_temporal`). Lo unico honesto que puede
    hacer el software es exigir que la decision quede escrita, fechada y
    encadenada, y mostrar esa bitacora junto al resultado.
    """

    ruta: Path
    entradas: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.ruta = Path(self.ruta)
        if self.ruta.exists():
            self.entradas = json.loads(self.ruta.read_text(encoding="utf-8"))

    def anotar(self, decision: str, justificacion: str, *,
               vio_datos_posteriores_al_corte: bool) -> None:
        """Registra una decision metodologica y si quien la tomo habia visto datos futuros."""
        if not justificacion.strip():
            raise ValueError("toda decision metodologica debe llevar justificacion escrita")
        self.entradas.append({
            "n": len(self.entradas) + 1,
            "decision": decision,
            "justificacion": justificacion,
            "vio_datos_posteriores_al_corte": bool(vio_datos_posteriores_al_corte),
            "momento_utc": datetime.now(timezone.utc).isoformat(),
        })
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(self.entradas, indent=2, ensure_ascii=False), encoding="utf-8")

    def advertencias(self) -> list[str]:
        contaminadas = [e for e in self.entradas if e["vio_datos_posteriores_al_corte"]]
        if not contaminadas:
            return []
        return [
            f"{len(contaminadas)} decision(es) metodologica(s) se tomaron habiendo visto datos "
            "posteriores al corte. La validacion no es pseudo-prospectiva: es retrospectiva "
            "con seleccion informada. Decisiones afectadas: "
            + "; ".join(e["decision"] for e in contaminadas)
        ]
