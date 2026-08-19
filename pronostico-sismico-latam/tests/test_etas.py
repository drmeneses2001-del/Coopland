"""ETAS: propiedades analiticas, simulacion y recuperacion de parametros."""
import numpy as np
import pytest

from sismolat.modelos.etas import (
    ParametrosETAS, ajustar_etas, intensidad_etas, simular_espacio_temporal, simular_etas,
)

VERDAD = ParametrosETAS(mu=0.5, K=0.015, alpha=1.5, c=0.01, p=1.15, m0=3.0)


# --- propiedades analiticas ----------------------------------------------
def test_hijos_esperados_coincide_con_la_formula_cerrada():
    esperado = VERDAD.K * VERDAD.c ** (1 - VERDAD.p) / (VERDAD.p - 1)
    assert float(VERDAD.n_hijos(VERDAD.m0)) == pytest.approx(esperado)


def test_productividad_crece_exponencialmente_con_la_magnitud():
    razon = VERDAD.n_hijos(5.0) / VERDAD.n_hijos(3.0)
    assert razon == pytest.approx(np.exp(VERDAD.alpha * 2.0))


def test_ramificacion_diverge_si_p_no_supera_uno():
    assert not np.isfinite(ParametrosETAS(0.5, 0.015, 1.5, 0.01, 0.9, 3.0).ramificacion(1.0))


def test_ramificacion_diverge_si_alpha_supera_beta_sin_truncar():
    """Con alpha >= b*ln10 la integral de productividad no converge sin Mmax."""
    p = ParametrosETAS(0.5, 0.015, 3.0, 0.01, 1.15, 3.0)
    assert not np.isfinite(p.ramificacion(b=1.0))
    assert np.isfinite(p.ramificacion(b=1.0, m_max=8.0))


def test_intensidad_sin_historial_es_la_tasa_de_fondo():
    v = intensidad_etas(np.array([5.0]), np.array([]), np.array([]), VERDAD)
    assert v[0] == pytest.approx(VERDAD.mu)


def test_intensidad_decae_tras_un_evento():
    t, m = np.array([0.0]), np.array([6.0])
    v = intensidad_etas(np.array([0.1, 1.0, 10.0]), t, m, VERDAD)
    assert v[0] > v[1] > v[2] > VERDAD.mu


# --- simulacion -----------------------------------------------------------
def test_simulacion_rechaza_procesos_sin_decaimiento_integrable():
    p = ParametrosETAS(0.5, 0.015, 1.5, 0.01, 0.9, 3.0)
    with pytest.raises(ValueError, match="p > 1"):
        simular_etas(p, b=1.0, t_fin=100.0)


def test_la_simulacion_produce_mas_eventos_que_el_fondo():
    t, _ = simular_etas(VERDAD, b=1.0, t_fin=2000.0, rng=np.random.default_rng(5))
    assert t.size > VERDAD.mu * 2000.0


def test_los_tiempos_simulados_salen_ordenados():
    t, m = simular_etas(VERDAD, b=1.0, t_fin=500.0, rng=np.random.default_rng(6))
    assert np.all(np.diff(t) >= 0) and t.size == m.size


def test_el_nucleo_espacial_requiere_truncamiento():
    """Sin truncar, q<=1.5 da distancia radial de media infinita."""
    df = simular_espacio_temporal(
        VERDAD, b=1.0, t_fin=1000.0, caja=(-100.0, -98.0, 17.0, 19.0),
        r_max_km=50.0, rng=np.random.default_rng(7),
    )
    assert df["lat"].between(-90, 90).all() and df["lon"].between(-180, 180).all()
    assert "r_max_km" in df.attrs


def test_truncar_mas_corto_concentra_la_sismicidad():
    kw = dict(b=1.0, t_fin=1500.0, caja=(-100.0, -98.0, 17.0, 19.0))
    ancho = simular_espacio_temporal(VERDAD, r_max_km=300.0,
                                     rng=np.random.default_rng(8), **kw)
    estrecho = simular_espacio_temporal(VERDAD, r_max_km=20.0,
                                        rng=np.random.default_rng(8), **kw)
    assert estrecho["lon"].std() < ancho["lon"].std()


# --- recuperacion de parametros (lento) -----------------------------------
@pytest.mark.lento
def test_etas_recupera_sus_parametros():
    """Recuperacion sobre un catalogo simulado con parametros conocidos.

    Los margenes son holgados a proposito. ETAS tiene una degeneracion conocida
    entre K y alpha: la verosimilitud es casi plana a lo largo de la direccion
    que sube uno y baja el otro, asi que las sigmas del hessiano son optimistas
    en esa combinacion. Ver docs/02-supuestos.md.
    """
    rng = np.random.default_rng(101)
    t, m = simular_etas(VERDAD, b=1.0, t_fin=3000.0, rng=rng)
    aj = ajustar_etas(t, m, m0=3.0, t_fin=3000.0, b_para_ramificacion=1.0)
    p = aj.parametros
    assert 0.3 < p.mu < 0.8, f"mu={p.mu}"
    assert 0.005 < p.K < 0.05, f"K={p.K}"
    assert 1.0 < p.alpha < 2.2, f"alpha={p.alpha}"
    assert 0.001 < p.c < 0.05, f"c={p.c}"
    assert 0.95 < p.p < 1.45, f"p={p.p}"
    assert aj.ganancia_sobre_poisson(t, m) > 0.05, "ETAS debe superar a Poisson homogeneo"


@pytest.mark.lento
def test_ajuste_avisa_si_el_proceso_sale_supercritico():
    rng = np.random.default_rng(55)
    t, m = simular_etas(VERDAD, b=1.0, t_fin=1500.0, rng=rng)
    aj = ajustar_etas(t, m, m0=3.0, t_fin=1500.0, b_para_ramificacion=1.0)
    assert any("ramificacion" in a for a in aj.advertencias)


def test_ajuste_exige_muestra_minima():
    with pytest.raises(ValueError, match="al menos"):
        ajustar_etas(np.arange(10.0), np.full(10, 3.5), m0=3.0)
