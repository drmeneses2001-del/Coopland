"""Capa didactica: los tres paneles fijos, extraidos del propio codigo.

El principio
------------
Cada modulo de esta biblioteca documenta en su docstring tres cosas: **la
matematica** (derivacion, supuestos, condiciones de validez), **los datos**
(procedencia, cobertura, sesgos conocidos) y **lo que ese modulo NO puede
hacer**. Este modulo las extrae y las presenta.

Que la documentacion didactica salga del codigo y no de un texto aparte no es
comodidad: es la unica forma de que no se desincronice. Un panel escrito a mano
envejece en cuanto alguien cambia el modulo; uno extraido del docstring
envejece solo si alguien cambia el docstring, que es donde debe estar.

:func:`auditar_paneles` recorre el paquete y **lista los modulos que no declaran
sus limitaciones**. Un modulo sin panel de "lo que no puede hacer" es un modulo
que se presenta como si no tuviera limites.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from dataclasses import dataclass

__all__ = ["Paneles", "paneles_de", "auditar_paneles", "MODULOS_DIDACTICOS", "Ejercicio",
           "EJERCICIOS"]

#: Encabezados que se reconocen como cada uno de los tres paneles.
_MATEMATICA = ("la matematica", "el calculo explicito", "por que hay varios metodos",
               "por que hace falta", "por que existe este modulo", "reparto de trabajo",
               "el principio", "el vinculo cuantitativo entre tectonica y pronostico")
_DATOS = ("supuestos y condiciones de validez", "supuestos que afectan al resultado",
          "sobre los pesos", "que esta verificado y que no", "fallos visibles",
          "coeficientes", "que se considera trazable", "magnitud maxima",
          "truncamiento de epsilon", "alcance de esta implementacion")
_LIMITES = ("lo que este modulo no puede hacer", "lo que este modulo no puede garantizar",
            "la limitacion que esto impone, y como se declara")

_SECCION = re.compile(r"^(?P<titulo>[^\n]{3,90})\n-{3,}\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Paneles:
    """Los tres paneles didacticos de un modulo."""

    modulo: str
    resumen: str
    matematica: str
    datos: str
    limitaciones: str

    @property
    def completo(self) -> bool:
        """Un modulo esta completo si declara al menos sus limitaciones."""
        return bool(self.limitaciones.strip())

    def texto(self, ancho: int = 74) -> str:
        linea = "=" * ancho
        out = [linea, f"MODULO: {self.modulo}", linea, "", self.resumen.strip(), ""]
        for titulo, cuerpo in (("1. LA MATEMATICA", self.matematica),
                               ("2. LOS DATOS Y SUS SUPUESTOS", self.datos),
                               ("3. LO QUE ESTE MODULO NO PUEDE HACER", self.limitaciones)):
            out += ["-" * ancho, titulo, "-" * ancho, ""]
            out.append(cuerpo.strip() if cuerpo.strip()
                       else "  (no declarado en el docstring del modulo)")
            out.append("")
        return "\n".join(out)


def _secciones(doc: str) -> tuple[str, dict[str, str]]:
    """Parte un docstring en resumen inicial y secciones con subrayado."""
    marcas = list(_SECCION.finditer(doc))
    if not marcas:
        return doc, {}
    resumen = doc[: marcas[0].start()]
    secciones: dict[str, str] = {}
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(doc)
        secciones[m.group("titulo").strip().lower()] = doc[m.end(): fin]
    return resumen, secciones


def _juntar(secciones: dict[str, str], claves: tuple[str, ...]) -> str:
    partes = [cuerpo for titulo, cuerpo in secciones.items()
              if any(k in titulo for k in claves)]
    return "\n".join(p.strip() for p in partes)


def paneles_de(nombre_modulo: str) -> Paneles:
    """Extrae los tres paneles del docstring de un modulo."""
    mod = importlib.import_module(nombre_modulo)
    doc = inspect.getdoc(mod) or ""
    resumen, secciones = _secciones(doc)
    return Paneles(
        modulo=nombre_modulo, resumen=resumen,
        matematica=_juntar(secciones, _MATEMATICA),
        datos=_juntar(secciones, _DATOS),
        limitaciones=_juntar(secciones, _LIMITES),
    )


#: Modulos de los que se espera panel didactico completo.
MODULOS_DIDACTICOS: tuple[str, ...] = (
    "sismolat.procedencia", "sismolat.catalogo", "sismolat.reproducibilidad",
    "sismolat.sintetico",
    "sismolat.estadistica.gutenberg_richter", "sismolat.estadistica.mc",
    "sismolat.estadistica.decluster",
    "sismolat.modelos.omori", "sismolat.modelos.etas", "sismolat.modelos.suavizado",
    "sismolat.evaluacion.pronostico", "sismolat.evaluacion.csep",
    "sismolat.evaluacion.alarma",
    "sismolat.peligro.gmm", "sismolat.peligro.fuentes", "sismolat.peligro.psha",
    "sismolat.peligro.arbol", "sismolat.peligro.sitio",
    "sismolat.tectonica.elastico", "sismolat.tectonica.coulomb",
    "sismolat.tectonica.momento",
    "sismolat.exploratorio.circular", "sismolat.exploratorio.covariable",
    "sismolat.exploratorio.energia", "sismolat.exploratorio.panel",
    "sismolat.lenguaje.verificacion", "sismolat.lenguaje.cliente",
    "sismolat.lenguaje.revisor",
)


def auditar_paneles(modulos: tuple[str, ...] = MODULOS_DIDACTICOS) -> dict:
    """Comprueba que cada modulo declare sus limitaciones.

    Un modulo sin panel de "lo que no puede hacer" se presenta como si no
    tuviera limites, que es justo lo contrario de lo que este proyecto pretende.
    """
    completos, incompletos = [], []
    for nombre in modulos:
        try:
            p = paneles_de(nombre)
        except ImportError:
            continue
        (completos if p.completo else incompletos).append(nombre)
    return {
        "n_modulos": len(completos) + len(incompletos),
        "completos": tuple(completos),
        "sin_limitaciones_declaradas": tuple(incompletos),
        "fraccion_completa": (len(completos) / (len(completos) + len(incompletos))
                              if (completos or incompletos) else 0.0),
    }


@dataclass(frozen=True)
class Ejercicio:
    """Un ejercicio guiado: hipotesis, metodo y la confrontacion con la evaluacion."""

    titulo: str
    contexto: str
    hipotesis: str
    metodo_sugerido: str
    que_deberia_salir: str
    trampa: str

    def texto(self, ancho: int = 74) -> str:
        return "\n".join([
            "=" * ancho, f"EJERCICIO: {self.titulo}", "=" * ancho, "",
            f"  Contexto  : {self.contexto}", "",
            f"  Hipotesis : {self.hipotesis}", "",
            f"  Metodo    : {self.metodo_sugerido}", "",
            "  QUE DEBERIA SALIR (no lo mires hasta haberlo hecho)",
            f"    {self.que_deberia_salir}", "",
            "  LA TRAMPA",
            f"    {self.trampa}", "",
        ])


#: Ejercicios guiados. Cada uno enfrenta al usuario con un error frecuente y
#: **medido en este repositorio**, no con un caso inventado.
EJERCICIOS: tuple[Ejercicio, ...] = (
    Ejercicio(
        titulo="El valor de b depende de Mc mas que de su propio error",
        contexto="Catalogo sintetico con Mc verdadero conocido.",
        hipotesis="El valor de b es robusto frente a la eleccion del metodo de Mc.",
        metodo_sugerido="comparar_metodos_mc y luego ajustar b en cada uno de los tres Mc.",
        que_deberia_salir=(
            "Los tres metodos difieren en ~0.6 unidades de magnitud, y b cambia entre "
            "ellos mucho mas que su error estadistico. La hipotesis es falsa."
        ),
        trampa=(
            "Reportar b con su sigma de Shi-Bolt sugiere una precision que la eleccion de "
            "Mc destruye. El error dominante no es el que se reporta."
        ),
    ),
    Ejercicio(
        titulo="El decluster no es un paso de limpieza",
        contexto="El mismo catalogo, tres algoritmos de decluster.",
        hipotesis="Los tres metodos identifican aproximadamente el mismo fondo.",
        metodo_sugerido="comparar_metodos con permitir_no_verificado=True.",
        que_deberia_salir=(
            "Las fracciones eliminadas difieren en unos 19 puntos porcentuales. La "
            "particion la produce el algoritmo, no la descubre."
        ),
        trampa=(
            "Elegir el metodo que da el resultado esperado y no declararlo. Cualquier "
            "conclusion posterior hereda esa eleccion."
        ),
    ),
    Ejercicio(
        titulo="Una prueba poissoniana rechaza un modelo correcto",
        contexto="Catalogo generado por ETAS; pronostico de sismicidad suavizada.",
        hipotesis="Si el N-test rechaza, el modelo es malo.",
        metodo_sugerido="n_test frente a n_test_catalogo sobre el mismo pronostico.",
        que_deberia_salir=(
            "El N-test poissoniano rechaza con p del orden de 1e-35; el basado en catalogo "
            "no rechaza. La dispersion var(N)/media(N) ronda 36 en las simulaciones."
        ),
        trampa=(
            "Concluir que el modelo falla cuando lo que falla es el supuesto de la prueba. "
            "Comprueba siempre el supuesto de la PRUEBA, no solo el del modelo."
        ),
    ),
    Ejercicio(
        titulo="El presupuesto de momento no da un numero",
        contexto="Tasa de convergencia y area acoplada de un segmento de subduccion.",
        hipotesis="Con la geodesia se puede fijar la tasa sismica de la zona.",
        metodo_sugerido="familia_de_tasas sobre rangos razonables de b, m_max y acoplamiento.",
        que_deberia_salir=(
            "La tasa varia en un factor cercano a 17 entre combinaciones igualmente "
            "defendibles. El parametro dominante es m_max."
        ),
        trampa=(
            "Publicar la mediana como si fuera la respuesta. La dispersion no es ruido: "
            "es ignorancia sobre parametros que nadie conoce bien."
        ),
    ),
    Ejercicio(
        titulo="Un mapa de Coulomb depende de lo que elijas",
        contexto="Falla de rumbo, receptores y friccion aparente variables.",
        hipotesis="El mapa de lobulos muestra donde aumento el esfuerzo.",
        metodo_sugerido="barrido_de_sensibilidad y fraccion_con_signo_estable.",
        que_deberia_salir=(
            "Girar el receptor 90 grados cambia el signo en mas del 20% del dominio. Solo "
            "la fraccion con signo estable es defendible."
        ),
        trampa=(
            "Presentar un mapa unico. Se lee como un hecho y es una eleccion entre muchas."
        ),
    ),
    Ejercicio(
        titulo="Cuantos sismos hacen falta para ver una modulacion de marea",
        contexto="Efecto de marea publicado: del orden del 2% de exceso.",
        hipotesis="Con unos cientos de eventos se puede contrastar la hipotesis.",
        metodo_sugerido="n_minimo_para_detectar(0.02) antes de tocar los datos.",
        que_deberia_salir=(
            "Hacen falta del orden de 14 000 eventos para tener potencia 0.8. Con unos "
            "cientos, no rechazar el nulo era el resultado garantizado."
        ),
        trampa=(
            "Hacer la prueba, no rechazar, y presentarlo como evidencia de que no hay "
            "efecto. Sin potencia, un no rechazo no dice nada."
        ),
    ),
)
