"""Genera un informe HTML autocontenido a partir de un analisis completo.

Datos SINTETICOS y fuentes de EJEMPLO. Los GMM son reales y verificados; las
tasas, magnitudes maximas y geometrias no provienen de ningun modelo publicado.
Ningun numero del informe describe el peligro sismico real de ningun sitio.

Ejecutar con:  python ejemplos/informe_completo.py [ruta_de_salida.html]
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from sismolat.estadistica.gutenberg_richter import ajustar
from sismolat.estadistica.mc import comparar_metodos_mc
from sismolat.evaluacion.pronostico import Rejilla
from sismolat.exploratorio.circular import (
    fase_por_periodo, n_minimo_para_detectar, prueba_de_schuster,
)
from sismolat.exploratorio.panel import ejecutar_preregistrada
from sismolat.interfaz.informe import Informe
from sismolat.lenguaje.revisor import revisar
from sismolat.modelos.decluster_estocastico import estimar_fondo_estocastico
from sismolat.modelos.etas import (
    ParametrosETAS, fondo_de_mezcla, simular_espacio_temporal,
)
from sismolat.peligro.arbol import ArbolLogico, NodoLogico, Rama, peligro_con_arbol
from sismolat.peligro.fuentes import DistribucionMagnitudes, FuenteArea
from sismolat.peligro.gmm import ModeloMovimiento, RegimenTectonico
from sismolat.peligro.psha import Sitio, curva_de_peligro, desagregar
from sismolat.procedencia import Cantidad, Procedencia, supuesto
from sismolat.reproducibilidad import RegistroAnalisis, RegistroDePruebas

SEMILLA = 20260820
CAJA = (-102.0, -96.0, 15.0, 19.5)
FOCOS = [(-99.5, 16.5, 0.35, 3.0), (-97.0, 16.0, 0.30, 2.0), (-100.5, 18.5, 0.45, 1.0)]
PAR = ParametrosETAS(mu=0.60, K=0.018, alpha=1.5, c=0.01, p=1.18, m0=3.0)


def _fuente(b=1.0, m_max=8.4, tasa=2.0):
    mfd = DistribucionMagnitudes(
        Cantidad(tasa, "eventos/ano", Procedencia.SUPUESTO, notas="valor de ejemplo"),
        Cantidad(b, "adimensional", Procedencia.SUPUESTO, notas="valor de ejemplo"),
        5.0, supuesto(m_max, "unidades de magnitud", motivo="cota de ejemplo"),
    )
    return FuenteArea("interfase (ejemplo)", (-101.0, -97.5, 15.0, 17.5), (20.0,),
                      RegimenTectonico.SUBDUCCION_INTERFASE, mfd, paso_grados=0.5)


def main(salida: str | None = None) -> Path:
    rng = np.random.default_rng(SEMILLA)
    inf = Informe(
        "Informe de analisis sismico",
        "Datos sinteticos y fuentes de ejemplo. Ningun numero describe una region real.",
    )

    # ---------------------------------------------------------------- datos
    print("simulando catalogo...")
    df = simular_espacio_temporal(
        PAR, b=1.0, t_fin=1500.0, caja=CAJA, d_km=6.0, q=1.7, gamma=0.6,
        r_max_km=150.0, muestrear_fondo=fondo_de_mezcla(FOCOS), rng=rng,
    )
    d = df[df["lon"].between(*CAJA[:2]) & df["lat"].between(*CAJA[2:])]
    inf.seccion("El catalogo",
                f"Catalogo sintetico ETAS con fondo heterogeneo conocido: {len(d)} eventos "
                f"en {1500.0 / 365.25:.1f} anios sobre la caja {CAJA}.")

    r_mc = comparar_metodos_mc(d["mag"].to_numpy(), 0.1)
    inf.parrafo("Magnitud de completitud por tres metodos. La dispersion entre ellos es "
                "la incertidumbre honesta de Mc, y suele superar el error estadistico "
                "que cada metodo declara por separado.")
    inf.tabla(["metodo", "Mc", "n sobre Mc", "criterio alcanzado"],
              [[res.metodo, f"{res.mc.valor:.2f}", res.n_sobre_mc,
                "si" if res.criterio_alcanzado else "NO"]
               for res in r_mc["resultados"].values()],
              resumen="Ver los tres metodos de Mc")
    inf.datos({"dispersion entre metodos": f"{r_mc['dispersion']:.2f} unidades de magnitud",
               "Mc mediana usada": f"{r_mc['mc_mediana']:.2f}"})
    if r_mc["advertencia"]:
        inf.advertencias([r_mc["advertencia"]])

    aj_b = ajustar(d["mag"].to_numpy(), mc=r_mc["mc_mediana"], dm=0.1)
    inf.cantidad("valor b (Aki-Utsu)", aj_b.b)

    # ------------------------------------------------- fondo estimado
    print("estimando el fondo por decluster estocastico (puede tardar)...")
    rej = Rejilla.regular(CAJA, 0.25, 3.0, 8.0, 0.5)
    fondo = estimar_fondo_estocastico(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values,
        m0=3.0, rejilla=rej, t_fin=1500.0, r_max_km=150.0, ventana_dias=600.0,
        k_vecinos=10, max_iteraciones=6,
    )
    inf.seccion(
        "Fondo sismico estimado conjuntamente",
        "Cada evento contribuye al mapa de fondo en proporcion a su probabilidad de ser "
        "de fondo, en lugar de contarse entero o descartarse entero. Frente al supuesto "
        "de fondo uniforme, esto evita que la estructura espacial del fondo se atribuya "
        "al disparo.",
    )
    inf.mapa_de_fondo(fondo, dias=365.0)
    inf.parrafo("Traza de convergencia del esquema iterativo. Es un metodo tipo EM: "
                "converge a un optimo local, y por eso conviene repetir desde varios "
                "puntos de partida.")
    inf.convergencia(fondo.historia)

    # ------------------------------------------------------------- peligro
    print("calculando el peligro...")
    modelo = ModeloMovimiento(
        "ArroyoEtAl2010SInter", RegimenTectonico.SUBDUCCION_INTERFASE,
        justificacion="calibrado con registros de la costa mexicana del Pacifico",
    )
    sitio = Sitio("sitio de referencia en roca", -99.13, 19.43,
                  Cantidad(760.0, "m/s", Procedencia.SUPUESTO,
                           notas="roca de referencia; NO representa la zona lacustre"))
    niveles = np.logspace(-3, np.log10(1.0), 36)
    arbol = ArbolLogico((
        NodoLogico("b", (Rama("0.9", 0.3, 0.9), Rama("1.0", 0.4, 1.0), Rama("1.1", 0.3, 1.1)),
                   justificacion="rango del intervalo de confianza de b"),
        NodoLogico("m_max", (Rama("8.0", 0.4, 8.0), Rama("8.4", 0.4, 8.4),
                             Rama("8.8", 0.2, 8.8)),
                   justificacion="cotas creibles de la magnitud maxima"),
    ))
    r_arbol = peligro_con_arbol(
        sitio, arbol, lambda a: [(_fuente(b=a["b"], m_max=a["m_max"]), modelo)],
        niveles, dm=0.2,
    )
    curva = r_arbol.curva_media()
    inf.seccion(
        "Peligro sismico probabilistico",
        f"Modelo de movimiento del terreno: {modelo.nombre}, implementacion verificada "
        "de openquake.hazardlib. Las fuentes, en cambio, son de ejemplo.",
    )
    inf.curva_de_peligro(curva, resultado_arbol=r_arbol)
    disp = r_arbol.dispersion_epistemica(475.0)
    inf.parrafo("Dispersion epistemica: cuanto se mueve el nivel de diseno entre las "
                "ramas del arbol logico. Es la medida de cuanto del resultado es "
                "ignorancia y no azar.")
    inf.datos({
        "media a 475 anios": f"{disp['media']:.5f} g",
        "fractil 16": f"{disp['fractil_16']:.5f} g",
        "fractil 84": f"{disp['fractil_84']:.5f} g",
        "razon 84/16": f"{disp['razon_84_16']:.2f}",
    })

    inf.seccion("Desagregacion", "Que combinacion de magnitud, distancia y epsilon "
                                 "produce el peligro al nivel de 475 anios.")
    inf.desagregacion(desagregar(sitio, [(_fuente(), modelo)],
                                 curva.nivel_para_periodo(475.0), dm=0.2))

    # ------------------------------------------------------- exploratorio
    print("hipotesis exploratoria...")
    registro = RegistroDePruebas(Path(tempfile.mkdtemp()) / "pruebas.json")
    resultado = ejecutar_preregistrada(
        registro,
        "La marea semidiurna modula la tasa de sismicidad de la region",
        "prueba de Schuster sobre la fase del ciclo de 12.42 h",
        lambda: prueba_de_schuster(
            fase_por_periodo(d["t_dias"].to_numpy(), 12.4206 / 24.0),
            calcular_potencia_para=0.05),
        extraer_efecto=lambda s: s.R_medio, extraer_p=lambda s: s.p_valor,
        extraer_potencia=lambda s: s.potencia, extraer_n=lambda s: s.n,
        unidad_efecto="longitud resultante media",
    )
    inf.seccion(
        "Hipotesis exploratoria preregistrada",
        f"Antes de mirar los datos: detectar una modulacion del 2% --el orden del efecto "
        f"de marea publicado-- exige del orden de {n_minimo_para_detectar(0.02):,} eventos "
        "con potencia 0.8. El panel siguiente ocupa el mismo espacio rechace o no.",
    )
    inf.panel_nulo(resultado)

    # ------------------------------------------------------------ revision
    inf.seccion("Revision metodologica",
                "Comprobaciones deterministas: las hace el codigo, no un modelo de "
                "lenguaje. El informe declara ademas lo que la revision no cubre.")
    entrenamiento = pd.DataFrame({"tiempo": pd.to_datetime(["2015-01-01", "2019-12-31"])})
    inf.revision(revisar(
        registro_pruebas=registro, entrenamiento=entrenamiento,
        corte_temporal="2020-01-01", resultados_nulos=[resultado],
        cantidades=[aj_b.b, fondo.mu_total],
        curva_de_peligro=curva, periodos_solicitados=(475.0, 2475.0),
    ))

    reg = RegistroAnalisis(
        nombre="informe completo sintetico",
        huella_datos=f"{len(d)}-eventos-semilla-{SEMILLA}",
        parametros={"mc": r_mc["mc_mediana"], "b": aj_b.b.valor, "caja": list(CAJA)},
        semilla=SEMILLA,
    )
    inf.seccion("Reproducibilidad")
    inf.datos({"identificador del analisis": reg.identificador[:32] + "...",
               "version del codigo": reg.version[:16],
               "semilla": str(reg.semilla)})
    inf.advertencias(reg.advertencias())

    ruta = Path(salida or "informe.html")
    inf.guardar(ruta)
    print(f"\nInforme escrito en {ruta.resolve()}  ({ruta.stat().st_size / 1024:.0f} kB)")
    return ruta


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
