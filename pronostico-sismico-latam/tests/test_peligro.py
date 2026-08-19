"""Fase 5 -- PSHA: GMM verificados, Cornell-McGuire, arbol logico y sitio."""
import math

import numpy as np
import pytest

from sismolat.procedencia import Cantidad, Procedencia, supuesto

oq = pytest.importorskip("openquake.hazardlib", reason="requiere el extra [psha]")

from sismolat.peligro.arbol import (  # noqa: E402
    ArbolLogico, NodoLogico, Rama, peligro_con_arbol,
)
from sismolat.peligro.fuentes import DistribucionMagnitudes, FuenteArea  # noqa: E402
from sismolat.peligro.gmm import (  # noqa: E402
    ErrorDeGMM, ModeloMovimiento, RegimenTectonico, gmm_disponibles,
)
from sismolat.peligro.psha import (  # noqa: E402
    Sitio, curva_de_peligro, desagregar, periodo_de_retorno, probabilidad_en_periodo,
)
from sismolat.peligro.sitio import (  # noqa: E402
    ClaseDeSitio, EstratoSobreSemiespacio, clasificar_vs30,
)

CAJA = (-101.0, -98.0, 15.5, 17.5)
SITIO = Sitio("prueba", -99.13, 19.43,
              Cantidad(760.0, "m/s", Procedencia.SUPUESTO, notas="roca de referencia"))


def _mfd(tasa=2.0, b=1.0, m_max=8.4):
    return DistribucionMagnitudes(
        Cantidad(tasa, "eventos/ano", Procedencia.DERIVADO, fuente="catalogo de prueba"),
        Cantidad(b, "adimensional", Procedencia.DERIVADO, fuente="Aki-Utsu",
                 incertidumbre=0.03),
        5.0, supuesto(m_max, "unidades de magnitud", motivo="cota superior supuesta"),
    )


def _fuente(**kw):
    return FuenteArea("interfase", CAJA, (20.0,), RegimenTectonico.SUBDUCCION_INTERFASE,
                      _mfd(**kw), paso_grados=0.5)


@pytest.fixture(scope="module")
def modelo():
    return ModeloMovimiento("ArroyoEtAl2010SInter", RegimenTectonico.SUBDUCCION_INTERFASE,
                            justificacion="calibrado con datos de la costa mexicana")


# --- GMM -------------------------------------------------------------------
def test_hay_gmm_para_cada_regimen():
    for r in RegimenTectonico:
        assert len(gmm_disponibles(r)) > 0, f"sin GMM para {r.value}"


def test_no_se_puede_usar_un_gmm_fuera_de_su_regimen():
    with pytest.raises(ErrorDeGMM, match="regimen"):
        ModeloMovimiento("ArroyoEtAl2010SInter", RegimenTectonico.SUBDUCCION_INTRAPLACA,
                         justificacion="prueba")


def test_la_justificacion_regional_es_obligatoria():
    with pytest.raises(ErrorDeGMM, match="justificacion"):
        ModeloMovimiento("ArroyoEtAl2010SInter", RegimenTectonico.SUBDUCCION_INTERFASE,
                         justificacion="   ")


def test_gmm_inexistente_se_rechaza():
    with pytest.raises(ErrorDeGMM, match="registro"):
        ModeloMovimiento("ModeloQueNoExiste2099", RegimenTectonico.CORTICAL_ACTIVA,
                         justificacion="prueba")


def test_el_movimiento_decae_con_la_distancia(modelo):
    mu, _ = modelo.media_y_sigma(8.0, np.array([25.0, 50.0, 100.0, 200.0, 400.0]))
    assert np.all(np.diff(mu) < 0)


def test_el_movimiento_crece_con_la_magnitud(modelo):
    d = np.array([100.0])
    valores = [modelo.media_y_sigma(m, d)[0][0] for m in (6.0, 7.0, 8.0)]
    assert valores[0] < valores[1] < valores[2]


def test_sigma_se_descompone_en_inter_e_intra(modelo):
    """sigma_total^2 = tau^2 + phi^2, dentro del redondeo del valor publicado.

    La tolerancia no es 1e-6 a proposito: varios GMM publican la sigma total
    redondeada a dos decimales, asi que no coincide con la raiz de la suma de
    cuadrados mas alla de ese redondeo. Exigir igualdad exacta seria exigir que
    el articulo publicara mas cifras de las que publico.
    """
    c = modelo.componentes_de_sigma(8.0, np.array([100.0]))
    tau, phi, sig = (c["tau_inter_evento"][0], c["phi_intra_evento"][0],
                     c["sigma_total"][0])
    assert sig == pytest.approx(math.sqrt(tau ** 2 + phi ** 2), abs=5e-3)


def test_la_procedencia_del_gmm_es_publicada(modelo):
    p = modelo.procedencia()
    assert p.procedencia is Procedencia.PUBLICADO
    assert "openquake" in p.fuente


# --- distribucion de magnitudes -------------------------------------------
@pytest.mark.parametrize("dm", [0.05, 0.1, 0.2, 0.5])
def test_la_discretizacion_conserva_la_tasa_total(dm):
    mfd = _mfd(tasa=3.7)
    _, tasas = mfd.tasas_por_bin(dm)
    assert tasas.sum() == pytest.approx(3.7, rel=1e-12)


def test_un_b_mayor_concentra_la_tasa_en_magnitudes_pequenas():
    c1, t1 = _mfd(b=0.8).tasas_por_bin(0.1)
    c2, t2 = _mfd(b=1.3).tasas_por_bin(0.1)
    assert (t2 * c2).sum() / t2.sum() < (t1 * c1).sum() / t1.sum()


def test_m_max_supuesto_dispara_advertencia():
    assert any("m_max" in a for a in _mfd().advertencias())


def test_la_distribucion_exige_cantidades_con_procedencia():
    with pytest.raises(TypeError, match="procedencia"):
        DistribucionMagnitudes(2.0, Cantidad(1.0, "adimensional", Procedencia.SUPUESTO),
                               5.0, supuesto(8.0, "mag", motivo="x"))


def test_los_pesos_de_la_fuente_suman_uno():
    p = _fuente().discretizar()
    assert p.peso.sum() == pytest.approx(1.0)


# --- Cornell-McGuire -------------------------------------------------------
@pytest.fixture(scope="module")
def curva(modelo):
    niveles = np.logspace(-3, np.log10(1.5), 30)
    return curva_de_peligro(SITIO, [(_fuente(), modelo)], niveles)


def test_la_curva_de_peligro_es_monotona_decreciente(curva):
    assert np.all(np.diff(curva.tasas) <= 1e-15)


def test_duplicar_la_tasa_duplica_el_peligro(modelo):
    niveles = np.array([0.01, 0.05])
    a = curva_de_peligro(SITIO, [(_fuente(tasa=2.0), modelo)], niveles)
    b = curva_de_peligro(SITIO, [(_fuente(tasa=4.0), modelo)], niveles)
    assert np.allclose(b.tasas, 2 * a.tasas, rtol=1e-10)


def test_dos_fuentes_identicas_suman_sus_tasas(modelo):
    niveles = np.array([0.01, 0.05])
    una = curva_de_peligro(SITIO, [(_fuente(), modelo)], niveles)
    dos = curva_de_peligro(SITIO, [(_fuente(), modelo), (_fuente(), modelo)], niveles)
    assert np.allclose(dos.tasas, 2 * una.tasas, rtol=1e-10)


def test_periodo_de_retorno_de_las_convenciones_normativas():
    assert periodo_de_retorno(0.10, 50.0) == pytest.approx(475.0, abs=1.0)
    assert periodo_de_retorno(0.02, 50.0) == pytest.approx(2475.0, abs=5.0)


def test_probabilidad_poisson_es_consistente_con_la_tasa(curva):
    p = curva.probabilidad_en(50.0)
    assert np.allclose(p, 1 - np.exp(-curva.tasas * 50.0))
    assert np.all((p >= 0) & (p <= 1))


def test_el_nivel_de_2475_supera_al_de_475(curva):
    assert curva.nivel_para_periodo(2475.0) > curva.nivel_para_periodo(475.0)


def test_no_extrapola_fuera_del_rango_calculado(curva):
    """Un periodo de retorno de 1 ano exige una tasa mayor que cualquiera calculada."""
    with pytest.raises(ValueError, match="fuera del rango"):
        curva.nivel_para_periodo(1.0)


def test_la_curva_avisa_de_lo_que_no_incluye(curva):
    texto = " ".join(curva.advertencias)
    assert "EPISTEMICA" in texto and "PUNTUAL" in texto


def test_fuente_y_modelo_deben_compartir_regimen(modelo):
    cortical = FuenteArea("c", CAJA, (10.0,), RegimenTectonico.CORTICAL_ACTIVA,
                          _mfd(), paso_grados=1.0)
    with pytest.raises(ValueError, match="regimen"):
        curva_de_peligro(SITIO, [(cortical, modelo)], np.array([0.01]))


# --- caso analitico exacto -------------------------------------------------
def test_caso_de_una_sola_magnitud_y_distancia_coincide_con_la_formula(modelo):
    """Con una fuente puntual y un solo bin de magnitud, lambda = nu * P exacto."""
    from scipy import stats

    from sismolat.peligro.psha import EPSILON_MAXIMO_POR_DEFECTO
    fuente = FuenteArea("puntual", (-99.5, -99.0, 16.0, 16.5), (20.0,),
                        RegimenTectonico.SUBDUCCION_INTERFASE,
                        DistribucionMagnitudes(
                            Cantidad(1.0, "eventos/ano", Procedencia.SUPUESTO),
                            Cantidad(1.0, "adimensional", Procedencia.SUPUESTO),
                            7.0, supuesto(7.2, "mag", motivo="bin unico")),
                        paso_grados=0.5)
    z = 0.02
    c = curva_de_peligro(SITIO, [(fuente, modelo)], np.array([z]), dm=0.2)

    puntos = fuente.discretizar()
    dist = puntos.distancias_km(SITIO.lon, SITIO.lat)
    centros, tasas = fuente.magnitudes.tasas_por_bin(0.2)
    e_max = EPSILON_MAXIMO_POR_DEFECTO.valor
    norm = stats.norm.cdf(e_max) - stats.norm.cdf(-e_max)
    esperado = 0.0
    for m, nu in zip(centros, tasas):
        mu, sig = modelo.media_y_sigma(float(m), dist, vs30=SITIO.vs30.valor)
        eps = (math.log(z) - mu) / sig
        p = (stats.norm.cdf(e_max) - stats.norm.cdf(np.clip(eps, -e_max, e_max))) / norm
        p = np.where(eps > e_max, 0.0, np.where(eps < -e_max, 1.0, p))
        esperado += nu * float((p * puntos.peso).sum())
    assert c.tasas[0] == pytest.approx(esperado, rel=1e-12)


# --- desagregacion ---------------------------------------------------------
@pytest.mark.parametrize("dm", [0.2, 0.1])
def test_la_desagregacion_suma_la_tasa_total(modelo, dm):
    z = 0.01
    c = curva_de_peligro(SITIO, [(_fuente(), modelo)], np.array([z]), dm=dm)
    d = desagregar(SITIO, [(_fuente(), modelo)], z, dm=dm,
                   bordes_r=np.arange(0.0, 801.0, 10.0))
    assert d.tasa_total == pytest.approx(c.tasas[0], rel=1e-9)


def test_la_desagregacion_apunta_a_la_fuente_real(modelo):
    """La distancia modal debe caer en el rango real fuente-sitio."""
    d = desagregar(SITIO, [(_fuente(), modelo)], 0.01, dm=0.2)
    dist = _fuente().discretizar().distancias_km(SITIO.lon, SITIO.lat)
    assert dist.min() - 30 <= d.modal()["distancia_km"] <= dist.max() + 30


def test_niveles_altos_desagregan_en_epsilon_mayor(modelo):
    bajo = desagregar(SITIO, [(_fuente(), modelo)], 0.005, dm=0.2)
    alto = desagregar(SITIO, [(_fuente(), modelo)], 0.05, dm=0.2)
    assert alto.media()["epsilon"] > bajo.media()["epsilon"]


def test_la_fraccion_de_la_desagregacion_suma_uno(modelo):
    d = desagregar(SITIO, [(_fuente(), modelo)], 0.01, dm=0.2)
    assert d.fraccion.sum() == pytest.approx(1.0)


# --- arbol logico ----------------------------------------------------------
def _arbol():
    return ArbolLogico((
        NodoLogico("b", (Rama("bajo", 0.3, 0.9), Rama("central", 0.4, 1.0),
                         Rama("alto", 0.3, 1.1)),
                   justificacion="rango del intervalo de confianza de b en el catalogo"),
        NodoLogico("m_max", (Rama("8.0", 0.5, 8.0), Rama("8.6", 0.5, 8.6)),
                   justificacion="cotas superior e inferior de la magnitud maxima creible"),
    ))


def test_los_pesos_de_un_nodo_deben_sumar_uno():
    with pytest.raises(ValueError, match="suman"):
        NodoLogico("x", (Rama("a", 0.5, 1), Rama("b", 0.6, 2)), justificacion="prueba")


def test_un_nodo_exige_justificacion():
    with pytest.raises(ValueError, match="justificacion"):
        NodoLogico("x", (Rama("a", 1.0, 1),), justificacion="")


def test_el_numero_de_hojas_es_el_producto():
    assert _arbol().n_combinaciones == 6


def test_los_pesos_de_las_hojas_suman_uno():
    assert sum(p for _, p, _ in _arbol().combinaciones()) == pytest.approx(1.0)


@pytest.fixture(scope="module")
def resultado_arbol(modelo):
    niveles = np.logspace(-3, np.log10(0.5), 20)
    return peligro_con_arbol(
        SITIO, _arbol(),
        lambda a: [(_fuente(b=a["b"], m_max=a["m_max"]), modelo)],
        niveles, dm=0.2,
    )


def test_la_media_del_arbol_es_la_media_ponderada(resultado_arbol):
    esperado = np.average(resultado_arbol.tasas, axis=0, weights=resultado_arbol.pesos)
    assert np.allclose(resultado_arbol.media, esperado)


def test_los_fractiles_estan_ordenados(resultado_arbol):
    f16, f50, f84 = (resultado_arbol.fractil(q) for q in (0.16, 0.5, 0.84))
    assert np.all(f16 <= f50 + 1e-15) and np.all(f50 <= f84 + 1e-15)


def test_la_dispersion_epistemica_es_positiva(resultado_arbol):
    d = resultado_arbol.dispersion_epistemica(475.0)
    assert d["fractil_84"] >= d["fractil_16"]
    assert d["razon_84_16"] >= 1.0


def test_un_arbol_de_una_sola_hoja_reproduce_la_curva_simple(modelo):
    niveles = np.array([0.01, 0.03])
    arbol = ArbolLogico((NodoLogico("b", (Rama("unico", 1.0, 1.0),),
                                    justificacion="rama unica de control"),))
    r = peligro_con_arbol(SITIO, arbol, lambda a: [(_fuente(b=a["b"]), modelo)],
                          niveles, dm=0.2)
    simple = curva_de_peligro(SITIO, [(_fuente(b=1.0), modelo)], niveles, dm=0.2)
    assert np.allclose(r.media, simple.tasas, rtol=1e-12)


# --- efecto de sitio -------------------------------------------------------
@pytest.mark.parametrize("vs30,clase", [
    (1800.0, ClaseDeSitio.ROCA_DURA), (900.0, ClaseDeSitio.ROCA),
    (500.0, ClaseDeSitio.SUELO_MUY_DENSO), (250.0, ClaseDeSitio.SUELO_RIGIDO),
    (120.0, ClaseDeSitio.SUELO_BLANDO),
])
def test_clasificacion_por_vs30(vs30, clase):
    c, _ = clasificar_vs30(Cantidad(vs30, "m/s", Procedencia.MEDIDO, fuente="sondeo"))
    assert c is clase


def test_suelo_muy_blando_remite_a_la_funcion_de_transferencia():
    _, avisos = clasificar_vs30(Cantidad(90.0, "m/s", Procedencia.MEDIDO, fuente="sondeo"))
    assert any("lacustre" in a.lower() or "EstratoSobreSemiespacio" in a for a in avisos)


def test_la_transferencia_1d_tiene_su_maximo_en_el_periodo_dominante():
    e = EstratoSobreSemiespacio(espesor_m=40.0, vs_suelo_ms=60.0, vs_roca_ms=700.0,
                                amortiguamiento=0.03)
    T = np.logspace(-1, 1, 20000)
    H = e.transferencia(T)
    assert T[int(np.argmax(H))] == pytest.approx(e.periodo_dominante_s, rel=0.01)


def test_la_transferencia_1d_tiene_armonicos_en_t0_tercios_y_quintos():
    e = EstratoSobreSemiespacio(espesor_m=40.0, vs_suelo_ms=60.0, vs_roca_ms=700.0,
                                amortiguamiento=0.03)
    T = np.logspace(-1, 1, 40000)
    H = e.transferencia(T)
    picos = sorted(T[k] for k in range(1, H.size - 1)
                   if H[k] > H[k - 1] and H[k] > H[k + 1])[-3:][::-1]
    T0 = e.periodo_dominante_s
    for obtenido, esperado in zip(picos, (T0, T0 / 3, T0 / 5)):
        assert obtenido == pytest.approx(esperado, rel=0.02)


def test_sin_amortiguamiento_la_amplificacion_es_el_inverso_de_la_impedancia():
    e = EstratoSobreSemiespacio(espesor_m=40.0, vs_suelo_ms=60.0, vs_roca_ms=700.0,
                                amortiguamiento=0.0)
    H = e.transferencia(np.array([e.periodo_dominante_s]))
    assert H[0] == pytest.approx(e.amplificacion_maxima_teorica, rel=1e-3)


def test_el_amortiguamiento_reduce_el_pico():
    kw = dict(espesor_m=40.0, vs_suelo_ms=60.0, vs_roca_ms=700.0)
    T = np.array([EstratoSobreSemiespacio(**kw).periodo_dominante_s])
    sin_amort = EstratoSobreSemiespacio(**kw, amortiguamiento=0.0).transferencia(T)[0]
    con_amort = EstratoSobreSemiespacio(**kw, amortiguamiento=0.05).transferencia(T)[0]
    assert con_amort < sin_amort


def test_un_estrato_mas_grueso_alarga_el_periodo_dominante():
    a = EstratoSobreSemiespacio(espesor_m=20.0, vs_suelo_ms=60.0, vs_roca_ms=700.0)
    b = EstratoSobreSemiespacio(espesor_m=60.0, vs_suelo_ms=60.0, vs_roca_ms=700.0)
    assert b.periodo_dominante_s == pytest.approx(3 * a.periodo_dominante_s)


def test_sin_contraste_de_impedancia_se_rechaza():
    with pytest.raises(ValueError, match="contraste"):
        EstratoSobreSemiespacio(espesor_m=40.0, vs_suelo_ms=800.0, vs_roca_ms=700.0)
