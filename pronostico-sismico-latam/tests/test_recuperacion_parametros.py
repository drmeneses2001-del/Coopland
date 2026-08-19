"""Pruebas de recuperacion de parametros: el criterio de correccion de los estimadores.

Si un estimador no recupera los valores con los que se simulo el catalogo, el
estimador esta mal. Es el unico criterio disponible cuando no hay implementacion
de referencia contra la que cotejar.

Estas pruebas usan semillas fijas para ser deterministas. Los margenes en sigmas
son deliberadamente holgados: no son un umbral de calidad cientifica, sino una
barrera contra regresiones que rompan el estimador.
"""
import numpy as np
import pytest

from sismolat.estadistica.gutenberg_richter import ajustar, b_aki_utsu, fmd
from sismolat.modelos.omori import ajustar_omori
from sismolat.sintetico import magnitudes_gr, tiempos_omori


# --- Gutenberg-Richter ----------------------------------------------------
@pytest.mark.parametrize("b_verdadero", [0.70, 0.90, 1.00, 1.30])
def test_b_se_recupera_en_catalogo_grande(b_verdadero):
    rng = np.random.default_rng(20250819)
    m = magnitudes_gr(200_000, b_verdadero, mc=3.0, dm=0.1, rng=rng)
    aj = ajustar(m, mc=3.0, dm=0.1)
    z = (aj.b.valor - b_verdadero) / aj.b.incertidumbre
    assert abs(z) < 4.0, f"b={aj.b.valor:.4f} frente a {b_verdadero} (z={z:.2f})"


def test_cobertura_del_intervalo_de_shi_bolt():
    """El intervalo de 1 sigma debe cubrir el valor verdadero ~68% de las veces."""
    rng = np.random.default_rng(4242)
    dentro = 0
    n = 300
    for _ in range(n):
        m = magnitudes_gr(2000, 1.0, 3.0, 0.1, rng=rng)
        aj = ajustar(m, 3.0, 0.1)
        dentro += abs(aj.b.valor - 1.0) <= aj.b.incertidumbre
    frac = dentro / n
    assert 0.60 < frac < 0.76, f"cobertura {frac:.3f}, esperada ~0.683"


def test_binning_a_media_unidad_no_sesga():
    """El umbral efectivo Mc - dM/2 es lo que hace insesgado al estimador."""
    rng = np.random.default_rng(7)
    m = magnitudes_gr(100_000, 1.0, mc=3.0, dm=0.1, rng=rng)
    b = b_aki_utsu(m, 3.0, dm=0.1).valor
    b_sin_correccion = np.log10(np.e) / (m[m >= 3.0].mean() - 3.0)
    assert abs(b - 1.0) < 0.02
    # Sin restar dM/2, el umbral efectivo queda demasiado alto y b sale sesgado
    # HACIA ARRIBA (el denominador de Aki-Utsu se acorta en dM/2).
    assert b_sin_correccion > 1.04, "sin la correccion de binning el sesgo debe ser visible"


def test_b_exige_muestra_minima():
    rng = np.random.default_rng(1)
    with pytest.raises(ValueError, match="al menos"):
        b_aki_utsu(magnitudes_gr(10, 1.0, 3.0, 0.1, rng=rng), 3.0)


def test_fmd_acumulada_es_monotona():
    rng = np.random.default_rng(2)
    _, _, acum = fmd(magnitudes_gr(5000, 1.0, 3.0, 0.1, rng=rng), 0.1)
    assert np.all(np.diff(acum) <= 0)


# --- Omori-Utsu -----------------------------------------------------------
@pytest.mark.parametrize("K,c,p", [(300.0, 0.02, 1.10), (800.0, 0.05, 0.90), (500.0, 0.01, 1.35)])
def test_omori_recupera_sus_parametros(K, c, p):
    rng = np.random.default_rng(23)
    t = tiempos_omori(K, c, p, 0.01, 100.0, rng=rng)
    aj = ajustar_omori(t, t0=0.01, t1=100.0)
    for nombre, estimado, verdadero in (
        ("p", aj.p, p), ("c", aj.c, c), ("K", aj.K, K),
    ):
        z = (estimado.valor - verdadero) / estimado.incertidumbre
        assert abs(z) < 4.0, f"{nombre}={estimado.valor:.5g} frente a {verdadero} (z={z:.2f})"


def test_omori_exige_muestra_minima():
    with pytest.raises(ValueError, match="al menos 10"):
        ajustar_omori(np.array([1.0, 2.0, 3.0]))


def test_omori_avisa_si_la_ventana_empieza_en_cero():
    rng = np.random.default_rng(5)
    t = tiempos_omori(500.0, 0.01, 1.1, 1e-4, 50.0, rng=rng)
    aj = ajustar_omori(t, t0=1e-4, t1=50.0)
    assert any("incompletitud" in a for a in aj.advertencias)


def test_integral_omori_caso_p_igual_a_uno():
    from sismolat.modelos.omori import integral_omori
    directo = integral_omori(0.1, 1.0, 0.0, 10.0)
    limite = integral_omori(0.1, 1.0 + 1e-9, 0.0, 10.0)
    assert abs(directo - limite) < 1e-6
