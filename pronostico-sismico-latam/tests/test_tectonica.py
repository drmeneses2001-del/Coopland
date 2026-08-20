"""Fase 6 -- dislocacion elastica, Coulomb y presupuesto geodesico de momento."""
import math

import numpy as np
import pytest

from sismolat.procedencia import Cantidad, Procedencia, supuesto
from sismolat.tectonica.coulomb import (
    ReceptorCoulomb, barrido_de_sensibilidad, cambio_de_coulomb,
    fraccion_con_signo_estable,
)
from sismolat.tectonica.elastico import (
    MedioElastico, PlanoDeFalla, desplazamiento_punto, error_de_superficie_libre,
    esfuerzo_falla_finita, esfuerzo_punto, tensor_de_momento,
)
from sismolat.tectonica.momento import (
    comparar_con_catalogo, familia_de_tasas, magnitud_desde_momento,
    momento_desde_magnitud, tasa_desde_deslizamiento, tasa_momento_geodesico,
)

MEDIO = MedioElastico()
FALLA = PlanoDeFalla(0.0, 90.0, 0.0, (0.0, 0.0, -8.0), 20.0, 12.0, 1.0)


# --- tensor de momento y solucion de Kelvin -------------------------------
def test_el_tensor_de_momento_de_cizalla_es_simetrico_y_sin_traza():
    n, d = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
    M = tensor_de_momento(n, d, 1e18)
    assert np.allclose(M, M.T)
    assert float(np.trace(M)) == pytest.approx(0.0, abs=1e-6)


def test_el_desplazamiento_de_un_doble_par_decae_como_uno_entre_r_cuadrado():
    M = tensor_de_momento(np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 1e18)
    r = np.array([10.0, 20.0, 40.0, 80.0])
    p = np.column_stack([r, np.zeros(4), np.zeros(4)])
    mag = np.linalg.norm(desplazamiento_punto(p, M, MEDIO), axis=1)
    assert np.allclose(mag[:-1] / mag[1:], 4.0, rtol=1e-9)


def test_el_desplazamiento_escala_con_el_momento():
    n, d = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    p = np.array([[20.0, 5.0, -3.0]])
    u1 = desplazamiento_punto(p, tensor_de_momento(n, d, 1e18), MEDIO)
    u2 = desplazamiento_punto(p, tensor_de_momento(n, d, 3e18), MEDIO)
    assert np.allclose(u2, 3 * u1, rtol=1e-12)


def test_observar_en_la_fuente_se_rechaza():
    M = tensor_de_momento(np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 1e18)
    with pytest.raises(ValueError, match="coincidentes"):
        desplazamiento_punto(np.array([[0.0, 0.0, 0.0]]), M, MEDIO)


def test_el_tensor_de_esfuerzos_es_simetrico():
    M = tensor_de_momento(np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 1e18)
    s = esfuerzo_punto(np.array([[15.0, 7.0, -4.0]]), M, MEDIO)
    assert np.allclose(s[0], s[0].T, rtol=1e-6)


def test_el_esfuerzo_no_depende_del_paso_de_diferencias_finitas():
    M = tensor_de_momento(np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 1e18)
    p = np.array([[15.0, 7.0, -4.0]])
    a = esfuerzo_punto(p, M, MEDIO, paso_km=0.02)
    b = esfuerzo_punto(p, M, MEDIO, paso_km=0.005)
    assert np.allclose(a, b, rtol=1e-3)


def test_la_falla_finita_converge_a_la_fuente_puntual_a_distancia():
    """Lejos, una falla de 20x12 km debe parecerse a un doble par puntual."""
    lejos = np.array([[400.0, 250.0, -8.0]])
    finita = esfuerzo_falla_finita(lejos, FALLA, MEDIO, n_largo=8, n_ancho=8)
    puntual = esfuerzo_punto(
        lejos,
        tensor_de_momento(FALLA.normal, FALLA.direccion_deslizamiento,
                          FALLA.momento_nm(MEDIO)),
        MEDIO, FALLA.centro_km,
    )
    assert np.allclose(finita, puntual, rtol=0.02)


def test_la_magnitud_equivalente_de_la_falla_es_coherente():
    assert FALLA.magnitud(MEDIO) == pytest.approx(6.5, abs=0.1)


# --- limitacion declarada: no hay superficie libre -------------------------
def test_el_modulo_cuantifica_su_propio_error_de_superficie_libre():
    """La traccion residual en z=0 mide cuanto se aparta el modelo de la realidad."""
    e = error_de_superficie_libre(FALLA, MEDIO, extension_km=40.0, n=9)
    assert e["traccion_maxima_pa"] > 0, (
        "un medio infinito NO satisface la condicion de superficie libre; si esto sale "
        "cero, la comprobacion no esta midiendo lo que debe"
    )
    assert math.isfinite(e["razon_maxima"])


def test_una_falla_mas_profunda_deja_menos_traccion_en_la_superficie():
    somera = PlanoDeFalla(0.0, 90.0, 0.0, (0.0, 0.0, -4.0), 20.0, 12.0, 1.0)
    profunda = PlanoDeFalla(0.0, 90.0, 0.0, (0.0, 0.0, -30.0), 20.0, 12.0, 1.0)
    a = error_de_superficie_libre(somera, MEDIO, extension_km=40.0, n=9)
    b = error_de_superficie_libre(profunda, MEDIO, extension_km=40.0, n=9)
    assert b["traccion_maxima_pa"] < a["traccion_maxima_pa"]


# --- Coulomb ---------------------------------------------------------------
@pytest.fixture(scope="module")
def rejilla():
    g = np.linspace(-40.0, 40.0, 9)
    gx, gy = np.meshgrid(g, g, indexing="ij")
    return np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, -8.0)])


def test_el_campo_cercano_se_enmascara(rejilla):
    r = cambio_de_coulomb(rejilla, FALLA, ReceptorCoulomb(0.0, 90.0, 0.0), MEDIO)
    assert r["n_enmascarados"] > 0
    assert np.isnan(r["delta_cfs"][r["no_fiable"]]).all()


def test_el_patron_de_coulomb_tiene_simetria_de_doble_par(rejilla):
    """Un doble par produce un patron con simetria puntual respecto al centro."""
    r = cambio_de_coulomb(rejilla, FALLA, ReceptorCoulomb(0.0, 90.0, 0.0), MEDIO)
    c = r["delta_cfs"].reshape(9, 9)
    invertido = c[::-1, ::-1]
    val = np.isfinite(c) & np.isfinite(invertido)
    assert np.allclose(c[val], invertido[val], rtol=1e-6, atol=1e-3)


def test_la_friccion_desplaza_el_resultado_por_el_esfuerzo_normal(rejilla):
    rec = ReceptorCoulomb(0.0, 90.0, 0.0)
    a = cambio_de_coulomb(rejilla, FALLA, rec, MEDIO, friccion_aparente=0.0)
    b = cambio_de_coulomb(rejilla, FALLA, rec, MEDIO, friccion_aparente=0.8)
    val = np.isfinite(a["delta_cfs"]) & np.isfinite(b["delta_cfs"])
    esperado = a["delta_cfs"][val] + 0.8 * a["delta_sigma_n"][val]
    assert np.allclose(b["delta_cfs"][val], esperado, rtol=1e-9)


def test_la_friccion_fuera_de_rango_se_rechaza(rejilla):
    with pytest.raises(ValueError, match="friccion"):
        cambio_de_coulomb(rejilla, FALLA, ReceptorCoulomb(0.0, 90.0, 0.0), MEDIO,
                          friccion_aparente=1.5)


def test_cambiar_el_receptor_cambia_el_signo_en_parte_del_dominio(rejilla):
    """La razon por la que un mapa unico de Coulomb no es un hecho."""
    a = cambio_de_coulomb(rejilla, FALLA, ReceptorCoulomb(0.0, 90.0, 0.0), MEDIO)
    b = cambio_de_coulomb(rejilla, FALLA, ReceptorCoulomb(90.0, 90.0, 0.0), MEDIO)
    val = np.isfinite(a["delta_cfs"]) & np.isfinite(b["delta_cfs"])
    cambian = np.sign(a["delta_cfs"][val]) != np.sign(b["delta_cfs"][val])
    assert cambian.mean() > 0.2, (
        f"solo el {100 * cambian.mean():.0f}% de los puntos cambia de signo al girar el "
        "receptor 90 grados; se esperaba una fraccion sustancial"
    )


@pytest.fixture(scope="module")
def barrido(rejilla):
    receptores = [ReceptorCoulomb(s, 90.0, 0.0) for s in (0.0, 45.0, 90.0)]
    return barrido_de_sensibilidad(rejilla, FALLA, receptores, MEDIO,
                                   fricciones=(0.0, 0.4, 0.8))


def test_el_barrido_cubre_todas_las_combinaciones(barrido):
    assert barrido["delta_cfs"].shape[0] == 9
    assert len(barrido["etiquetas"]) == 9


def test_solo_una_parte_del_dominio_tiene_signo_estable(barrido):
    f = fraccion_con_signo_estable(barrido)
    assert 0.0 <= f["fraccion_estable"] <= 1.0
    assert f["fraccion_estable"] < 1.0, (
        "si el signo fuera estable en todo el dominio, el barrido de sensibilidad no "
        "estaria midiendo nada"
    )
    assert f["interpretacion"]


def test_el_barrido_avisa_de_que_no_debe_presentarse_un_solo_mapa(barrido):
    assert "combinaciones" in barrido["advertencia"]


# --- presupuesto de momento ------------------------------------------------
def test_hanks_kanamori_ida_y_vuelta():
    for mw in (5.0, 6.5, 8.2):
        assert float(magnitud_desde_momento(momento_desde_magnitud(mw))) == \
            pytest.approx(mw, abs=1e-12)


def test_medio_grado_de_magnitud_multiplica_el_momento_por_cinco_y_medio():
    razon = momento_desde_magnitud(8.0) / momento_desde_magnitud(7.5)
    assert float(razon) == pytest.approx(10 ** 0.75, rel=1e-12)


def test_la_tasa_de_momento_geodesico_es_el_producto_esperado():
    A = Cantidad(60000.0, "km2", Procedencia.SUPUESTO)
    v = Cantidad(60.0, "mm/ano", Procedencia.SUPUESTO)
    m0 = tasa_momento_geodesico(A, v, mu_pa=3.0e10)
    assert m0.valor == pytest.approx(3.0e10 * 60000.0 * 1e6 * 0.060)


def test_la_tasa_de_momento_propaga_la_incertidumbre_relativa():
    A = Cantidad(60000.0, "km2", Procedencia.SUPUESTO, incertidumbre=6000.0)
    v = Cantidad(60.0, "mm/ano", Procedencia.SUPUESTO, incertidumbre=6.0)
    m0 = tasa_momento_geodesico(A, v)
    assert m0.incertidumbre / m0.valor == pytest.approx(math.sqrt(0.1 ** 2 + 0.1 ** 2))


def test_la_tasa_exige_cantidades_con_procedencia():
    with pytest.raises(TypeError, match="procedencia"):
        tasa_momento_geodesico(60000.0, Cantidad(60.0, "mm/ano", Procedencia.SUPUESTO))


def test_el_presupuesto_de_momento_se_conserva():
    """La tasa deducida, integrada sobre G-R, devuelve el momento disponible."""
    from sismolat.peligro.fuentes import DistribucionMagnitudes
    m0 = Cantidad(1.0e20, "N m/ano", Procedencia.DERIVADO, fuente="prueba")
    b = Cantidad(1.0, "adimensional", Procedencia.DERIVADO, fuente="prueba")
    chi = supuesto(0.6, "adimensional", motivo="acoplamiento de prueba")
    m_max = supuesto(8.4, "unidades de magnitud", motivo="cota de prueba")
    tasa = tasa_desde_deslizamiento(m0, b, 5.0, m_max, chi)

    mfd = DistribucionMagnitudes(
        Cantidad(tasa.valor, "eventos/ano", Procedencia.DERIVADO, fuente="prueba"),
        b, 5.0, m_max)
    assert mfd.momento_anual_nm(dm=0.01) == pytest.approx(chi.valor * m0.valor, rel=1e-3)


def test_un_acoplamiento_mayor_da_mas_sismos():
    m0 = Cantidad(1.0e20, "N m/ano", Procedencia.DERIVADO, fuente="p")
    b = Cantidad(1.0, "adimensional", Procedencia.DERIVADO, fuente="p")
    m_max = supuesto(8.4, "mag", motivo="p")
    baja = tasa_desde_deslizamiento(m0, b, 5.0, m_max,
                                    supuesto(0.3, "adimensional", motivo="p"))
    alta = tasa_desde_deslizamiento(m0, b, 5.0, m_max,
                                    supuesto(0.9, "adimensional", motivo="p"))
    assert alta.valor == pytest.approx(3 * baja.valor, rel=1e-9)


def test_subir_m_max_reduce_la_tasa_de_eventos_pequenos():
    """El mismo momento repartido hasta magnitudes mayores da menos sismos."""
    m0 = Cantidad(1.0e20, "N m/ano", Procedencia.DERIVADO, fuente="p")
    b = Cantidad(1.0, "adimensional", Procedencia.DERIVADO, fuente="p")
    chi = supuesto(0.5, "adimensional", motivo="p")
    baja = tasa_desde_deslizamiento(m0, b, 5.0, supuesto(7.5, "mag", motivo="p"), chi)
    alta = tasa_desde_deslizamiento(m0, b, 5.0, supuesto(8.5, "mag", motivo="p"), chi)
    assert alta.valor < baja.valor


def test_el_acoplamiento_fuera_de_rango_se_rechaza():
    m0 = Cantidad(1.0e20, "N m/ano", Procedencia.DERIVADO, fuente="p")
    b = Cantidad(1.0, "adimensional", Procedencia.DERIVADO, fuente="p")
    with pytest.raises(ValueError, match="acoplamiento"):
        tasa_desde_deslizamiento(m0, b, 5.0, supuesto(8.0, "mag", motivo="p"),
                                 supuesto(1.5, "adimensional", motivo="p"))


def test_la_familia_de_tasas_expone_una_dispersion_grande():
    """El punto de C.13: un numero unico esconde una ignorancia de casi un orden."""
    m0 = Cantidad(1.0e20, "N m/ano", Procedencia.DERIVADO, fuente="p")
    fam = familia_de_tasas(m0, (0.9, 1.0, 1.1), 5.0, (7.8, 8.2, 8.6), (0.3, 0.5, 0.8))
    assert len(fam["combinaciones"]) == 27
    assert fam["factor_dispersion"] > 5.0
    assert "m_max" in fam["advertencia"]


def test_la_comparacion_con_el_catalogo_no_decide_por_el_usuario():
    geo = Cantidad(10.0, "eventos/ano", Procedencia.DERIVADO, fuente="geodesia")
    cat = Cantidad(2.0, "eventos/ano", Procedencia.DERIVADO, fuente="catalogo")
    r = comparar_con_catalogo(geo, cat)
    assert r["razon_geodesica_catalogo"] == pytest.approx(5.0)
    assert "no puede distinguirlas" in r["interpretacion"]


def test_tasas_compatibles_se_reportan_como_tales():
    geo = Cantidad(2.4, "eventos/ano", Procedencia.DERIVADO, fuente="geodesia")
    cat = Cantidad(2.0, "eventos/ano", Procedencia.DERIVADO, fuente="catalogo")
    assert "Compatibles" in comparar_con_catalogo(geo, cat)["interpretacion"]
