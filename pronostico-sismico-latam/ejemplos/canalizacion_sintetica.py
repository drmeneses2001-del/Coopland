"""Canalizacion completa de las fases 0 a 4 sobre datos sinteticos.

Por que sinteticos: el entorno de desarrollo no tiene acceso a ningun servicio
sismologico (ver docs/01-fuentes-verificadas.md), asi que no hay datos reales
que procesar. Un catalogo sintetico tiene ademas una ventaja que ninguno real
ofrece: **conocemos la respuesta**, y por tanto podemos comprobar que cada paso
recupera lo que debe.

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
    cl_test, ganancia_informacion, l_test, m_test, n_test, n_test_catalogo, s_test,
)
from sismolat.evaluacion.pronostico import PronosticoCatalogo, PronosticoRejilla, Rejilla
from sismolat.modelos.etas import ParametrosETAS, simular_espacio_temporal
from sismolat.reproducibilidad import RegistroAnalisis, verificar_corte_temporal

SEMILLA = 20260819
CAJA = (-102.0, -96.0, 15.0, 19.5)   # aprox. Guerrero-Oaxaca; rectangulo de conveniencia
M0 = 3.0
B_VERDADERO = 1.0
CORTE = pd.Timestamp("2018-01-01")


def titulo(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def main() -> None:
    rng = np.random.default_rng(SEMILLA)

    titulo("FASE 1 -- catalogo (sintetico: no hay fuentes verificadas)")
    from sismolat.ingesta.fuentes import resumen_estado
    print(resumen_estado())

    par = ParametrosETAS(mu=0.55, K=0.018, alpha=1.5, c=0.01, p=1.18, m0=M0)
    print(f"\nParametros ETAS verdaderos: {par}")
    print(f"Parametro de ramificacion n = {par.ramificacion(B_VERDADERO):.3f}")

    df = simular_espacio_temporal(par, b=B_VERDADERO, t_fin=4000.0, caja=CAJA, rng=rng)
    t0 = pd.Timestamp("2012-01-01")
    cat = Catalogo(pd.DataFrame({
        "id_evento": [f"SINT{i:06d}" for i in range(len(df))],
        "tiempo": t0 + pd.to_timedelta(df["t_dias"], unit="D"),
        "lon": df["lon"], "lat": df["lat"], "prof_km": 20.0,
        "mag": df["mag"], "mag_escala": "Mw", "agencia": "SINTETICO",
    }), origen="etas sintetico")
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
    print(f"  Corte temporal: {CORTE.date()}")
    print(f"  Entrenamiento: {entrena.n} eventos | Prueba: {prueba.n} eventos")
    fugas = verificar_corte_temporal(entrena.df, CORTE, estricto=False)
    print(f"  Comprobacion de fuga temporal: {'LIMPIA' if not fugas else fugas}")
    print("  (Solo comprueba marcas de tiempo. La fuga por seleccion de modelo no es")
    print("   detectable desde el codigo -- ver BitacoraDeDecisiones.)")

    rej = Rejilla.regular(CAJA, 0.5, M0, 7.5, 0.5)
    dias_prueba = (cat.ventana_temporal[1] - CORTE) / pd.Timedelta(days=1)
    dias_entrena = (CORTE - cat.ventana_temporal[0]) / pd.Timedelta(days=1)
    escala = dias_prueba / dias_entrena

    # Linea base obligatoria: Poisson homogeneo. Uniforme EN EL ESPACIO, pero con
    # la distribucion de magnitudes de Gutenberg-Richter.
    #
    # Repartir la tasa uniformemente tambien entre bins de magnitud seria un hombre
    # de paja: pondria la misma tasa esperada en M=3 que en M=7, y cualquier modelo
    # que solo acierte la forma de la FMD lo superaria por goleada. La ganancia
    # medida contra esa referencia no diria nada sobre destreza espacial.
    tasa_total = entrena.n * escala
    centros_mag = 0.5 * (rej.mag_bordes[:-1] + rej.mag_bordes[1:])
    ancho_mag = np.diff(rej.mag_bordes)
    beta = aj.b.valor * np.log(10.0)
    peso_mag = np.exp(-beta * (centros_mag - rej.mag_bordes[0])) * ancho_mag
    peso_mag /= peso_mag.sum()
    n_esp = rej.n_celdas_espaciales
    base = PronosticoRejilla(
        rej,
        np.ones(rej.forma) * (tasa_total / n_esp) * peso_mag[None, None, :],
        "Poisson uniforme en espacio, G-R en magnitud", dias_prueba,
    )
    # Modelo informado: sismicidad del periodo de entrenamiento, reescalada.
    conteo_entrena = rej.contar(entrena.df)
    informado = PronosticoRejilla(
        rej, conteo_entrena * escala + 1e-3, "sismicidad de entrenamiento", dias_prueba,
    )

    print(f"\n  Pronostico para {dias_prueba:.0f} dias. Total esperado: {tasa_total:.0f}; "
          f"observado: {prueba.n}")
    print("\n  Pruebas de consistencia POISSONIANAS sobre el modelo informado:")
    for prueba_fn in (n_test, l_test, cl_test, s_test, m_test):
        kw = {} if prueba_fn is n_test else {"n_sim": 2000, "semilla": SEMILLA}
        print(f"    {prueba_fn(informado, prueba.df, **kw)}")

    titulo("FASE 4a -- por que ese rechazo poissoniano no significa lo que parece")
    print("  Las cinco pruebas rechazan. Antes de concluir que el modelo falla, hay que")
    print("  comprobar si el supuesto de la PRUEBA es valido, no solo el del modelo.")
    print("\n  El catalogo lo genero un proceso ETAS: autoexcitado y por tanto")
    print("  SOBREDISPERSO. Simulamos catalogos del proceso verdadero para medirlo:")

    rng_sim = np.random.default_rng(SEMILLA + 1)
    catalogos = []
    for _ in range(400):
        d = simular_espacio_temporal(par, b=B_VERDADERO, t_fin=dias_prueba, caja=CAJA,
                                     rng=rng_sim)
        catalogos.append(d[["lon", "lat", "mag"]])
    pron_cat = PronosticoCatalogo(catalogos, rej, "ETAS simulado", dias_prueba,
                                  semilla=SEMILLA + 1)
    disp = pron_cat.dispersion_relativa()
    print(f"\n    var(N)/media(N) = {disp:.1f}   (bajo Poisson valdria 1.0)")
    print(f"    La varianza del conteo es {disp:.0f} veces la poissoniana: una sola")
    print("    secuencia grande puede dominar el total. El N-test poissoniano rechaza")
    print("    por una dispersion que el modelo predice CORRECTAMENTE.")

    r_cat = n_test_catalogo(pron_cat, prueba.df)
    print(f"\n    {r_cat}")
    for a in r_cat.advertencias:
        print(f"      {a}")
    print("\n  Leccion: aplicar la prueba poissoniana a un modelo autoexcitado produce")
    print("  rechazos espurios. Por eso PronosticoRejilla lleva 'poisson_valido' y las")
    print("  pruebas se niegan a correr cuando el supuesto no corresponde.")

    titulo("FASE 4 -- comparacion que sí distingue modelos utiles")
    g = ganancia_informacion(informado, base, prueba.df)
    print(f"\n  Referencia: {base.nombre}")
    print(f"  Ganancia del modelo informado: {g['ganancia_por_evento']:+.3f} nats/evento "
          f"(factor {g['factor_probabilidad_por_evento']:.2f}x)")
    print("\n  Esta es la comparacion que distingue un modelo util de uno vago: las")
    print("  pruebas de consistencia las pasa cualquier modelo suficientemente ancho.")
    print("\n  Lectura de este caso concreto: el fondo de la simulacion ETAS es UNIFORME")
    print("  en el espacio, asi que no existe estructura espacial persistente que")
    print("  aprender. Una ganancia cercana a cero es la respuesta CORRECTA aqui, y")
    print("  ver que el metodo no inventa destreza donde no la hay es justamente lo")
    print("  que valida el modulo de evaluacion.")

    titulo("FASE 4b -- poder discriminante (NO es una propuesta de alarmas)")
    # Umbral mas alto: con M>=3 durante 5 anios practicamente toda celda registra
    # algun evento, y un evento objetivo que ocurre en todas partes no discrimina
    # nada. El umbral es parte de la definicion del problema, no un detalle.
    umbral = 4.5
    ev = EventoObjetivo(umbral, dias_prueba, 0.5, "Guerrero-Oaxaca (sintetico)")
    print(f"  Evento objetivo: {ev}")
    obs_esp = rej.contar(prueba.filtrar(mag_min=umbral).df).sum(axis=2)
    n_con = int((obs_esp > 0).sum())
    print(f"  Celdas con evento: {n_con} de {obs_esp.size}")
    # El pronostico debe restringirse a los MISMOS bins de magnitud que el evento
    # objetivo. Comparar un campo de tasas de M>=3 contra observaciones de M>=4.5
    # mezcla dos problemas distintos y hace ilegible cualquier medida de destreza.
    bins_objetivo = rej.mag_bordes[:-1] >= umbral - 1e-9

    for nombre, pron in (("informado", informado), ("uniforme", base)):
        campo = pron.tasas[:, :, bins_objetivo].sum(axis=2)
        m = molchan(campo, obs_esp, areas_celda=rej.areas_km2, evento=ev)
        r = roc(campo, obs_esp, evento=ev)
        b_ = brier(campo, obs_esp, evento=ev)
        print(f"\n  [{nombre}]")
        print(f"    {m}")
        print(f"    {r}")
        print(f"    {b_}")

    titulo("REPRODUCIBILIDAD")
    reg = RegistroAnalisis(
        nombre="canalizacion sintetica fases 0-4",
        huella_datos=cat.huella(),
        parametros={"mc": mc, "b": aj.b.valor, "corte": str(CORTE), "caja": list(CAJA)},
        semilla=SEMILLA,
    )
    print(f"  Identificador del analisis: {reg.identificador}")
    for a in reg.advertencias():
        print(f"  AVISO: {a}")
    print("\n  Recuerda: esto es un catalogo SINTETICO. Ningun numero de arriba dice")
    print("  nada sobre la sismicidad real de Mexico.")


if __name__ == "__main__":
    main()
