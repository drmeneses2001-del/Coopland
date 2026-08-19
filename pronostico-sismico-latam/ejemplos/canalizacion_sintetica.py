"""Canalizacion completa de las fases 0 a 4 sobre datos sinteticos.

Por que sinteticos: el entorno de desarrollo no tiene acceso a ningun servicio
sismologico (ver docs/01-fuentes-verificadas.md), asi que no hay datos reales
que procesar. Un catalogo sintetico tiene ademas una ventaja que ninguno real
ofrece: **conocemos la respuesta**, y por tanto podemos comprobar que cada paso
recupera lo que debe -- y, no menos importante, que no encuentra lo que no hay.

Se corren dos escenarios en paralelo:

* **Fondo uniforme**: no existe estructura espacial persistente que aprender.
  La respuesta correcta es ganancia nula.
* **Fondo heterogeneo**: sí existe. La respuesta correcta es encontrarla.

Un modulo de evaluacion que solo acertara en uno de los dos seria inutil.

Ejecutar con:  python ejemplos/canalizacion_sintetica.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sismolat.catalogo import Catalogo
from sismolat.estadistica.decluster import advertir_uso, comparar_metodos
from sismolat.estadistica.gutenberg_richter import ajustar
from sismolat.estadistica.mc import comparar_metodos_mc
from sismolat.evaluacion.alarma import EventoObjetivo, brier, molchan, roc
from sismolat.evaluacion.csep import (
    cl_test, ganancia_informacion, l_test, m_test, m_test_catalogo, n_test,
    n_test_catalogo, s_test, s_test_catalogo,
)
from sismolat.evaluacion.pronostico import PronosticoCatalogo, PronosticoRejilla, Rejilla
from sismolat.modelos.etas import (
    ParametrosETAS, fondo_de_mezcla, simular_espacio_temporal,
)
from sismolat.modelos.suavizado import optimizar_ancho, pronostico_suavizado
from sismolat.reproducibilidad import RegistroAnalisis, verificar_corte_temporal

SEMILLA = 20260819
CAJA = (-102.0, -96.0, 15.0, 19.5)   # aprox. Guerrero-Oaxaca; rectangulo de conveniencia
M0 = 3.0
B_VERDADERO = 1.0
INICIO = pd.Timestamp("2012-01-01")
CORTE = pd.Timestamp("2018-01-01")
UMBRAL_OBJETIVO = 4.5

PAR = ParametrosETAS(mu=0.55, K=0.018, alpha=1.5, c=0.01, p=1.18, m0=M0)
FONDO_HETEROGENEO = fondo_de_mezcla([
    (-99.5, 16.5, 0.35, 3.0), (-97.0, 16.0, 0.30, 2.0), (-100.5, 18.5, 0.45, 1.0),
])


def titulo(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def simular_catalogo(fondo, semilla: int, t_fin: float = 4000.0) -> Catalogo:
    df = simular_espacio_temporal(PAR, b=B_VERDADERO, t_fin=t_fin, caja=CAJA,
                                  muestrear_fondo=fondo,
                                  rng=np.random.default_rng(semilla))
    d = pd.DataFrame({
        "id_evento": [f"SINT{i:06d}" for i in range(len(df))],
        "tiempo": INICIO + pd.to_timedelta(df["t_dias"], unit="D"),
        "lon": df["lon"], "lat": df["lat"], "prof_km": 20.0,
        "mag": df["mag"], "mag_escala": "Mw", "agencia": "SINTETICO",
    })
    d = d[d["lon"].between(CAJA[0], CAJA[1]) & d["lat"].between(CAJA[2], CAJA[3])]
    return Catalogo(d.reset_index(drop=True), origen="etas sintetico")


def referencia_uniforme(rej: Rejilla, n: int, b: float, dias: float) -> PronosticoRejilla:
    """Poisson uniforme EN EL ESPACIO pero con magnitudes G-R.

    Repartir la tasa uniformemente tambien entre bins de magnitud seria un hombre
    de paja: pondria la misma tasa esperada en M=3 que en M=7, y cualquier modelo
    que solo acierte la forma de la FMD lo superaria sin destreza espacial alguna.
    """
    centros = 0.5 * (rej.mag_bordes[:-1] + rej.mag_bordes[1:])
    peso = np.exp(-b * np.log(10.0) * (centros - rej.mag_bordes[0])) * np.diff(rej.mag_bordes)
    peso /= peso.sum()
    return PronosticoRejilla(
        rej, np.ones(rej.forma) * (n / rej.n_celdas_espaciales) * peso[None, None, :],
        "Poisson uniforme en espacio, G-R en magnitud", dias,
    )


def main() -> None:
    titulo("FASE 1 -- catalogo (sintetico: no hay fuentes verificadas)")
    from sismolat.ingesta.fuentes import resumen_estado
    print(resumen_estado())

    cat = simular_catalogo(FONDO_HETEROGENEO, SEMILLA)
    print(f"\nParametros ETAS verdaderos: {PAR}")
    print(f"Parametro de ramificacion n = {PAR.ramificacion(B_VERDADERO):.3f}")
    print(f"\nCatalogo: {cat.n} eventos, {cat.duracion_anios:.1f} anios, "
          f"huella {cat.huella()[:12]}")
    for a in cat.advertencias():
        print(f"  AVISO: {a}")

    titulo("FASE 2 -- magnitud de completitud y valor b")
    r_mc = comparar_metodos_mc(cat.magnitudes(), 0.1)
    for res in r_mc["resultados"].values():
        print(f"  {res}")
    print(f"  dispersion entre metodos: {r_mc['dispersion']:.2f} unidades "
          f"(Mc verdadero = {M0})")
    if r_mc["advertencia"]:
        print(f"  AVISO: {r_mc['advertencia']}")

    mc = r_mc["mc_mediana"]
    aj = ajustar(cat.magnitudes(), mc=mc, dm=0.1)
    print(f"\n  {aj}")
    z = (aj.b.valor - B_VERDADERO) / aj.b.incertidumbre
    print(f"  b verdadero = {B_VERDADERO} -> desviacion {z:+.1f} sigma")
    print("  Nota: b estimado sobre catalogo CON replicas; el declusterizado dara otro valor.")

    titulo("FASE 2b -- decluster (tres metodos, sin metodo privilegiado)")
    for a in advertir_uso("valor_b"):
        print(f"  {a}")
    r_dec = comparar_metodos(cat, b=aj.b.valor, permitir_no_verificado=True)
    print()
    for res in r_dec["resultados"].values():
        print(f"  {res}")
    if r_dec["advertencia"]:
        print(f"\n  AVISO: {r_dec['advertencia']}")
    print("\n  " + "\n  ".join(advertir_uso("etas")))

    titulo("FASE 3/4 -- pronostico y evaluacion pseudo-prospectiva")
    entrena = cat.filtrar(t_fin=CORTE)
    prueba = cat.filtrar(t_inicio=CORTE)
    dias_entrena = (CORTE - cat.ventana_temporal[0]) / pd.Timedelta(days=1)
    dias_prueba = (cat.ventana_temporal[1] - CORTE) / pd.Timedelta(days=1)
    print(f"  Corte temporal: {CORTE.date()}")
    print(f"  Entrenamiento: {entrena.n} eventos | Prueba: {prueba.n} eventos")
    fugas = verificar_corte_temporal(entrena.df, CORTE, estricto=False)
    print(f"  Comprobacion de fuga temporal: {'LIMPIA' if not fugas else fugas}")
    print("  (Solo comprueba marcas de tiempo. La fuga por seleccion de modelo no es")
    print("   detectable desde el codigo -- ver BitacoraDeDecisiones.)")

    rej = Rejilla.regular(CAJA, 0.5, M0, 7.5, 0.5)

    # El ancho del nucleo se elige por verosimilitud DENTRO del entrenamiento.
    # optimizar_ancho no recibe el periodo de prueba: la salvaguarda es estructural.
    opt = optimizar_ancho(entrena.df, rej, b=aj.b.valor,
                          candidatos=np.array([2, 3, 5, 8, 12, 20, 30, 50, 80]))
    print(f"\n  Seleccion de ancho de nucleo (sin ver el periodo de prueba): {opt}")
    for a in opt.advertencias:
        print(f"    AVISO: {a}")

    suave = pronostico_suavizado(entrena.df, rej, b=aj.b.valor,
                                 dias_entrenamiento=dias_entrena,
                                 dias_pronostico=dias_prueba, k_vecinos=int(opt.mejor))
    base = referencia_uniforme(rej, entrena.n * dias_prueba / dias_entrena,
                               aj.b.valor, dias_prueba)
    print(f"\n  Modelo    : {suave.nombre}")
    print(f"  Referencia: {base.nombre}")
    print(f"  Total esperado: {suave.total:.0f}; observado: {prueba.n}")

    print("\n  Pruebas de consistencia POISSONIANAS:")
    for fn in (n_test, l_test, cl_test, s_test, m_test):
        kw = {} if fn is n_test else {"n_sim": 2000, "semilla": SEMILLA}
        print(f"    {fn(suave, prueba.df, **kw)}")

    titulo("FASE 4a -- por que ese rechazo poissoniano no significa lo que parece")
    print("  Antes de concluir que el modelo falla, hay que comprobar si el supuesto")
    print("  de la PRUEBA es valido, no solo el del modelo.")
    print("\n  El catalogo lo genero un proceso ETAS: autoexcitado y por tanto")
    print("  SOBREDISPERSO y agrupado. Simulamos catalogos del proceso para medirlo:")

    rng_sim = np.random.default_rng(SEMILLA + 1)
    catalogos = [
        simular_espacio_temporal(PAR, b=B_VERDADERO, t_fin=dias_prueba, caja=CAJA,
                                 muestrear_fondo=FONDO_HETEROGENEO,
                                 rng=rng_sim)[["lon", "lat", "mag"]]
        for _ in range(400)
    ]
    pron_cat = PronosticoCatalogo(catalogos, rej, "ETAS simulado", dias_prueba,
                                  semilla=SEMILLA + 1)
    disp = pron_cat.dispersion_relativa()
    print(f"\n    var(N)/media(N) = {disp:.1f}   (bajo Poisson valdria 1.0)")
    print(f"    La varianza del conteo es {disp:.0f} veces la poissoniana: una sola")
    print("    secuencia grande puede dominar el total.")

    print("\n  Las mismas pruebas, en su version basada en catalogo:")
    for fn in (n_test_catalogo, s_test_catalogo, m_test_catalogo):
        kw = {} if fn is n_test_catalogo else {"semilla": SEMILLA}
        print(f"    {fn(pron_cat, prueba.df, **kw)}")
    print("\n  Leccion: las pruebas poissonianas castigan al modelo por una")
    print("  sobredispersion y un agrupamiento que el modelo predice CORRECTAMENTE.")
    print("  Por eso PronosticoRejilla lleva 'poisson_valido' y las pruebas lanzan")
    print("  ErrorDeSupuesto cuando no corresponde.")

    titulo("FASE 4b -- destreza: detectarla cuando existe y no inventarla cuando no")
    print("  Se repite todo el analisis con un fondo UNIFORME, donde por construccion")
    print("  no hay estructura espacial persistente que aprender.\n")
    print(f"  {'escenario':<16}{'ganancia':>11}{'Molchan ASS':>14}{'ROC AUC':>10}"
          f"{'Brier':>10}")
    print(f"  {'-' * 61}")

    ev = EventoObjetivo(UMBRAL_OBJETIVO, dias_prueba, 0.5, "Guerrero-Oaxaca (sintetico)")
    bins = rej.mag_bordes[:-1] >= UMBRAL_OBJETIVO - 1e-9
    for etiqueta, fondo in (("heterogeneo", FONDO_HETEROGENEO), ("uniforme", None)):
        c = cat if fondo is FONDO_HETEROGENEO else simular_catalogo(fondo, SEMILLA)
        tr, te = c.filtrar(t_fin=CORTE), c.filtrar(t_inicio=CORTE)
        dtr = (CORTE - c.ventana_temporal[0]) / pd.Timedelta(days=1)
        dte = (c.ventana_temporal[1] - CORTE) / pd.Timedelta(days=1)
        o = optimizar_ancho(tr.df, rej, b=B_VERDADERO,
                            candidatos=np.array([2, 3, 5, 8, 12, 20, 30, 50, 80]))
        s = pronostico_suavizado(tr.df, rej, b=B_VERDADERO, dias_entrenamiento=dtr,
                                 dias_pronostico=dte, k_vecinos=int(o.mejor))
        r = referencia_uniforme(rej, tr.n * dte / dtr, B_VERDADERO, dte)
        obs = rej.contar(te.filtrar(mag_min=UMBRAL_OBJETIVO).df).sum(axis=2)
        campo = s.tasas[:, :, bins].sum(axis=2)
        g = ganancia_informacion(s, r, te.df)["ganancia_por_evento"]
        m = molchan(campo, obs, areas_celda=rej.areas_km2, evento=ev).ganancia_area
        a_ = roc(campo, obs, evento=ev).area_bajo_curva
        b_ = brier(campo, obs, evento=ev).destreza
        print(f"  {etiqueta:<16}{g:>+11.3f}{m:>+14.3f}{a_:>10.3f}{b_:>+10.3f}")

    print(f"\n  Evento objetivo: {ev}")
    print("\n  Con fondo heterogeneo el modelo encuentra la estructura que existe.")
    print("  Con fondo uniforme la ganancia es nula o negativa: es la respuesta")
    print("  CORRECTA, y ver que el metodo no inventa destreza donde no la hay es")
    print("  tan importante como verlo detectarla donde sí la hay.")

    titulo("REPRODUCIBILIDAD")
    reg = RegistroAnalisis(
        nombre="canalizacion sintetica fases 0-4",
        huella_datos=cat.huella(),
        parametros={"mc": mc, "b": aj.b.valor, "corte": str(CORTE),
                    "caja": list(CAJA), "k_vecinos": int(opt.mejor)},
        semilla=SEMILLA,
    )
    print(f"  Identificador del analisis: {reg.identificador}")
    for a in reg.advertencias():
        print(f"  AVISO: {a}")
    print("\n  Recuerda: esto es un catalogo SINTETICO. Ningun numero de arriba dice")
    print("  nada sobre la sismicidad real de Mexico.")


if __name__ == "__main__":
    main()
