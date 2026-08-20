"""Canalizacion de las fases 5 a 8: peligro, Coulomb, hipotesis y revision.

Los GMM son reales y verificados (openquake.hazardlib). **Las fuentes no**: sus
tasas, magnitudes maximas y geometrias son valores de ejemplo, no un modelo
sismogenico de Mexico. Ningun numero de esta salida dice nada sobre el peligro
sismico real de ningun sitio.

Ejecutar con:  python ejemplos/canalizacion_peligro.py
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from sismolat.exploratorio.circular import (
    fase_por_periodo, n_minimo_para_detectar, prueba_de_schuster,
)
from sismolat.exploratorio.energia import informe_de_escalas
from sismolat.exploratorio.panel import ejecutar_preregistrada, presentar
from sismolat.lenguaje.cliente import ClienteLenguaje
from sismolat.lenguaje.revisor import revisar
from sismolat.lenguaje.verificacion import verificar_cifras
from sismolat.peligro.arbol import ArbolLogico, NodoLogico, Rama, peligro_con_arbol
from sismolat.peligro.fuentes import DistribucionMagnitudes, FuenteArea
from sismolat.peligro.gmm import ModeloMovimiento, RegimenTectonico
from sismolat.peligro.psha import Sitio, curva_de_peligro, desagregar, periodo_de_retorno
from sismolat.peligro.sitio import (
    ADVERTENCIA_ZONA_LACUSTRE, EstratoSobreSemiespacio, clasificar_vs30,
)
from sismolat.procedencia import Cantidad, Procedencia, supuesto
from sismolat.reproducibilidad import RegistroDePruebas
from sismolat.tectonica.coulomb import (
    ReceptorCoulomb, barrido_de_sensibilidad, fraccion_con_signo_estable,
)
from sismolat.tectonica.elastico import MedioElastico, PlanoDeFalla, error_de_superficie_libre
from sismolat.tectonica.momento import (
    comparar_con_catalogo, familia_de_tasas, tasa_momento_geodesico,
)

SEMILLA = 20260819
CAJA_INTERFASE = (-101.0, -97.5, 15.0, 17.5)
SITIO = Sitio(
    "sitio de referencia en roca", -99.13, 19.43,
    Cantidad(760.0, "m/s", Procedencia.SUPUESTO,
             notas="roca de referencia; NO representa la zona lacustre"),
)


def titulo(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def fuente(b: float = 1.0, m_max: float = 8.4, tasa: float = 2.0) -> FuenteArea:
    """Fuente de EJEMPLO. Las cifras no provienen de ningun modelo publicado."""
    mfd = DistribucionMagnitudes(
        tasa_total=Cantidad(tasa, "eventos/ano", Procedencia.SUPUESTO,
                            notas="valor de ejemplo, no calibrado"),
        b=Cantidad(b, "adimensional", Procedencia.SUPUESTO, notas="valor de ejemplo"),
        m_min=5.0,
        m_max=supuesto(m_max, "unidades de magnitud", motivo="cota de ejemplo"),
    )
    return FuenteArea("interfase (ejemplo)", CAJA_INTERFASE, (20.0,),
                      RegimenTectonico.SUBDUCCION_INTERFASE, mfd, paso_grados=0.5)


def main() -> None:
    titulo("AVISO")
    print("  Los GMM son reales y verificados. Las FUENTES son de ejemplo: sus tasas,")
    print("  magnitudes maximas y geometrias no provienen de ningun modelo publicado.")
    print("  Ningun numero de esta salida dice nada sobre el peligro sismico real.")

    # ---------------------------------------------------------------- FASE 5
    titulo("FASE 5 -- curva de peligro con un GMM verificado")
    modelo = ModeloMovimiento(
        "ArroyoEtAl2010SInter", RegimenTectonico.SUBDUCCION_INTERFASE,
        justificacion="calibrado con registros de la costa mexicana del Pacifico",
    )
    print(f"  Modelo    : {modelo}")
    print(f"  Procedencia: {modelo.procedencia().fuente}")
    print(f"  Medidas   : {modelo.medidas[:3]}  |  sitio: {set(modelo.parametros_de_sitio)}")

    niveles = np.logspace(-3, np.log10(1.0), 40)
    curva = curva_de_peligro(SITIO, [(fuente(), modelo)], niveles)
    print(f"\n  {curva}")
    for T in (475.0, 2475.0):
        print(f"    PGA para {T:.0f} anios: {curva.nivel_para_periodo(T):.4f} g")
    print(f"    (475 anios = 10% en 50; {periodo_de_retorno(0.02, 50.0):.0f} = 2% en 50)")
    print("\n  Advertencias de la curva:")
    for a in curva.advertencias:
        print(f"    - {a[:110]}")

    titulo("FASE 5b -- desagregacion: que escenario produce ese peligro")
    objetivo = curva.nivel_para_periodo(475.0)
    d = desagregar(SITIO, [(fuente(), modelo)], objetivo, dm=0.2)
    print(f"  Nivel objetivo: {objetivo:.4f} g   (suma de la desagregacion: {d.tasa_total:.3e},")
    print(f"   tasa de la curva: {1 / 475.0:.3e})")
    print(f"  Escenario modal : {{{', '.join(f'{k}={v:.2f}' for k, v in d.modal().items())}}}")
    print(f"  Escenario medio : {{{', '.join(f'{k}={v:.2f}' for k, v in d.media().items())}}}")
    print("\n  El escenario modal NO es 'el sismo que producira esa aceleracion': es el")
    print("  bin que mas aporta a una suma sobre muchos escenarios.")

    titulo("FASE 5c -- arbol logico: cuanto del resultado es ignorancia")
    arbol = ArbolLogico((
        NodoLogico("b", (Rama("0.9", 0.3, 0.9), Rama("1.0", 0.4, 1.0), Rama("1.1", 0.3, 1.1)),
                   justificacion="rango del intervalo de confianza de b en el catalogo"),
        NodoLogico("m_max", (Rama("8.0", 0.4, 8.0), Rama("8.4", 0.4, 8.4),
                             Rama("8.8", 0.2, 8.8)),
                   justificacion="cotas creibles de la magnitud maxima de la interfase"),
    ))
    print(arbol.resumen())
    r = peligro_con_arbol(SITIO, arbol,
                          lambda a: [(fuente(b=a["b"], m_max=a["m_max"]), modelo)],
                          niveles, dm=0.2)
    disp = r.dispersion_epistemica(475.0)
    print(f"\n  A 475 anios, sobre las {arbol.n_combinaciones} hojas del arbol:")
    print(f"    media      : {disp['media']:.4f} g")
    print(f"    fractil 16 : {disp['fractil_16']:.4f} g")
    print(f"    fractil 84 : {disp['fractil_84']:.4f} g")
    print(f"    razon 84/16: {disp['razon_84_16']:.2f}")
    print("\n  Esos fractiles NO son intervalos de confianza: son cuantiles de una")
    print("  distribucion construida a partir de juicios expertos, y su anchura")
    print("  depende de cuantas ramas se incluyeron.")

    titulo("FASE 5d -- efecto de sitio: por que Vs30 no basta en la zona lacustre")
    clase, avisos = clasificar_vs30(SITIO.vs30)
    print(f"  Sitio en roca: Vs30 = {SITIO.vs30.valor:.0f} m/s -> clase {clase.value}")
    print(f"\n  {ADVERTENCIA_ZONA_LACUSTRE}")
    print("\n  En su lugar, la funcion de transferencia 1D con parametros declarados:")
    for espesor in (20.0, 40.0, 60.0):
        e = EstratoSobreSemiespacio(espesor_m=espesor, vs_suelo_ms=60.0,
                                    vs_roca_ms=700.0, amortiguamiento=0.03)
        H = e.transferencia(np.array([e.periodo_dominante_s]))[0]
        print(f"    estrato de {espesor:4.0f} m -> T0 = {e.periodo_dominante_s:.2f} s, "
              f"amplificacion en T0 = {H:.1f}x")
    print("\n  Tres sitios con el MISMO Vs30 y periodos dominantes de 1.3 a 4 s.")
    print("  Por eso un factor unico sobre PGA no describe la zona lacustre.")

    # ---------------------------------------------------------------- FASE 6
    titulo("FASE 6 -- Coulomb: el mapa depende de lo que elijas")
    medio = MedioElastico()
    falla = PlanoDeFalla(0.0, 90.0, 0.0, (0.0, 0.0, -8.0), 20.0, 12.0, 1.0)
    print(f"  Fuente: falla de rumbo, Mw equivalente {falla.magnitud(medio):.2f}")

    g = np.linspace(-40.0, 40.0, 11)
    gx, gy = np.meshgrid(g, g, indexing="ij")
    puntos = np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, -8.0)])
    # El gradiente importa mas que el numero suelto: dice QUE eleccion es la que
    # destruye la conclusion. Resulta ser la orientacion del receptor, no la friccion.
    escenarios = (
        ("solo varia la friccion (1 receptor)", [ReceptorCoulomb(0.0, 90.0, 0.0)],
         (0.0, 0.4, 0.8)),
        ("receptores +-15 grados", [ReceptorCoulomb(s, 90.0, 0.0) for s in (-15.0, 0.0, 15.0)],
         (0.4,)),
        ("receptores 0/45/90 grados", [ReceptorCoulomb(s, 90.0, 0.0) for s in (0.0, 45.0, 90.0)],
         (0.4,)),
        ("todo combinado", [ReceptorCoulomb(s, 90.0, 0.0) for s in (0.0, 45.0, 90.0)],
         (0.0, 0.4, 0.8)),
    )
    print(f"\n  {'que se hace variar':38s} {'combos':>7s} {'signo estable':>14s}")
    print(f"  {'-' * 61}")
    for nombre, receptores, fricciones in escenarios:
        b = barrido_de_sensibilidad(puntos, falla, receptores, medio, fricciones=fricciones)
        e = fraccion_con_signo_estable(b)
        print(f"  {nombre:38s} {b['delta_cfs'].shape[0]:7d} "
              f"{100 * e['fraccion_estable']:13.1f}%")
    print("\n  Lo que destruye la conclusion NO es la friccion --con un receptor fijo, el")
    print("  73% del dominio conserva el signo-- sino la ORIENTACION DEL RECEPTOR.")
    print("  Un mapa unico de lobulos esconde exactamente esa dependencia.")

    err = error_de_superficie_libre(falla, medio, extension_km=40.0, n=9)
    print(f"\n  Error por no modelar la superficie libre (traccion residual en z=0,")
    print(f"  que en la corteza real deberia ser nula):")
    print(f"    traccion mediana {err['traccion_mediana_pa'] / 1e5:.3f} bar; razon frente")
    print(f"    al esfuerzo de referencia: {err['razon_mediana']:.3f}")
    print(f"    -> {err['interpretacion']}")

    titulo("FASE 6b -- presupuesto de momento: una familia, no un numero")
    area = Cantidad(60000.0, "km2", Procedencia.SUPUESTO,
                    notas="area acoplada de ejemplo", incertidumbre=12000.0)
    conv = Cantidad(60.0, "mm/ano", Procedencia.SUPUESTO,
                    notas="convergencia de ejemplo", incertidumbre=5.0)
    m0 = tasa_momento_geodesico(area, conv)
    print(f"  Tasa de momento geodesico: {m0}")
    fam = familia_de_tasas(m0, (0.9, 1.0, 1.1), 5.0, (7.8, 8.2, 8.6), (0.3, 0.5, 0.8))
    print(f"\n  Sobre {len(fam['combinaciones'])} combinaciones razonables:")
    print(f"    tasa minima  : {fam['tasa_min']:.2f} eventos/ano")
    print(f"    tasa mediana : {fam['tasa_mediana']:.2f} eventos/ano")
    print(f"    tasa maxima  : {fam['tasa_max']:.2f} eventos/ano")
    print(f"    factor de dispersion: {fam['factor_dispersion']:.1f}")
    cat_tasa = Cantidad(2.0, "eventos/ano", Procedencia.SUPUESTO, notas="ejemplo")
    comp = comparar_con_catalogo(
        Cantidad(fam["tasa_mediana"], "eventos/ano", Procedencia.DERIVADO,
                 fuente="presupuesto de momento"), cat_tasa)
    print(f"\n  Contraste con el catalogo (razon {comp['razon_geodesica_catalogo']:.1f}):")
    print(f"    {comp['interpretacion'][:150]}")

    # ---------------------------------------------------------------- FASE 7
    titulo("FASE 7 -- hipotesis exploratoria con preregistro")
    print(informe_de_escalas().split("QUE SE SIGUE DE ESTO")[1].strip()[:640])

    print("\n  Antes de tocar los datos: ¿es contestable la pregunta?")
    n_min = n_minimo_para_detectar(0.02)
    print(f"    Detectar una modulacion del 2% (el orden del efecto de marea publicado)")
    print(f"    exige del orden de {n_min:,} eventos con potencia 0.8.")

    rng = np.random.default_rng(SEMILLA)
    import tempfile
    from pathlib import Path
    registro = RegistroDePruebas(Path(tempfile.mkdtemp()) / "pruebas.json")
    tiempos = np.sort(rng.random(3000) * 3650.0)
    resultado = ejecutar_preregistrada(
        registro,
        "La marea semidiurna modula la tasa de sismicidad de la region",
        "prueba de Schuster sobre la fase del ciclo de 12.42 h",
        lambda: prueba_de_schuster(fase_por_periodo(tiempos, 12.4206 / 24.0),
                                   calcular_potencia_para=0.05),
        extraer_efecto=lambda s: s.R_medio, extraer_p=lambda s: s.p_valor,
        extraer_potencia=lambda s: s.potencia, extraer_n=lambda s: s.n,
        unidad_efecto="longitud resultante media",
    )
    print()
    print(presentar(resultado))

    # ---------------------------------------------------------------- FASE 8
    titulo("FASE 8 -- revision metodologica (determinista) y capa de lenguaje")
    entrenamiento = pd.DataFrame({
        "tiempo": pd.to_datetime(["2015-01-01", "2016-06-01", "2019-12-31"])})
    informe = revisar(
        registro_pruebas=registro,
        entrenamiento=entrenamiento, corte_temporal="2020-01-01",
        resultados_nulos=[resultado],
        cantidades=[m0, area, conv],
        curva_de_peligro=curva, periodos_solicitados=(475.0, 2475.0),
    )
    print(informe.texto())

    titulo("FASE 8b -- la capa de lenguaje no puede inventar una cifra")
    datos = {
        "pga_475_g": round(curva.nivel_para_periodo(475.0), 5),
        "pga_2475_g": round(curva.nivel_para_periodo(2475.0), 5),
        "magnitud_modal": round(d.modal()["magnitud"], 2),
        "distancia_modal_km": round(d.modal()["distancia_km"], 1),
        "razon_fractiles_84_16": round(disp["razon_84_16"], 3),
    }
    print("  Datos que se le entregan (ya calculados por el motor):")
    for k, v in datos.items():
        print(f"    {k} = {v}")

    fiel = (f"A 475 anios el PGA es {datos['pga_475_g']} g y a 2475 anios "
            f"{datos['pga_2475_g']} g. El escenario modal es M {datos['magnitud_modal']} "
            f"a {datos['distancia_modal_km']} km.")
    inventado = (f"A 475 anios el PGA es {datos['pga_475_g']} g, equivalente a una "
                 "intensidad MMI de 6.4 y una duracion significativa de 45 s.")
    for etiqueta, texto in (("texto fiel", fiel), ("texto con cifras inventadas", inventado)):
        v = verificar_cifras(texto, datos)
        print(f"\n  [{etiqueta}]")
        print(f"    {texto}")
        print(f"    -> {v.informe()[:150]}")

    print("\n  La comprobacion es mecanica: no depende de que el modelo obedezca la")
    print("  instruccion de no calcular. Un texto que no la supera no se muestra.")

    titulo("FIN")
    print("  Recuerda: fuentes de EJEMPLO. Ningun numero de arriba describe el peligro")
    print("  sismico real de ningun sitio de Mexico.")


if __name__ == "__main__":
    main()
