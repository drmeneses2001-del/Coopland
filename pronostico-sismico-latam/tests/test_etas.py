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


# --- ETAS espacio-temporal: estimacion --------------------------------------
import math

from sismolat.modelos.etas import (
    ParametrosEspaciales, ajustar_etas_espacial, simular_espacio_temporal,
)

VERDAD_T = ParametrosETAS(mu=0.60, K=0.018, alpha=1.5, c=0.01, p=1.18, m0=3.0)
VERDAD_E = ParametrosEspaciales(d_km=6.0, q=1.7, gamma=0.6, r_max_km=150.0)
CAJA_FONDO = (-102.0, -96.0, 15.0, 19.5)


def _area_caja_km2(caja) -> float:
    lat_media = 0.5 * (caja[2] + caja[3])
    km_lon = 111.19 * math.cos(math.radians(lat_media))
    return (caja[1] - caja[0]) * km_lon * (caja[3] - caja[2]) * 111.19


def test_el_nucleo_espacial_truncado_integra_a_uno():
    r = np.linspace(1e-6, VERDAD_E.r_max_km, 200_000)
    m = np.full_like(r, 3.0)
    f = VERDAD_E.densidad(r, m, 3.0)
    integral = float(np.trapezoid(2 * np.pi * r * f, r))
    assert integral == pytest.approx(1.0, abs=1e-4)


def test_el_radio_mediano_crece_con_la_magnitud_del_padre():
    assert VERDAD_E.radio_mediano_km(6.0, 3.0) > VERDAD_E.radio_mediano_km(3.0, 3.0)


def test_gamma_nulo_hace_el_radio_independiente_de_la_magnitud():
    e = ParametrosEspaciales(d_km=6.0, q=1.7, gamma=0.0, r_max_km=150.0)
    assert e.radio_mediano_km(6.0, 3.0) == pytest.approx(e.radio_mediano_km(3.0, 3.0))


def test_el_ajuste_espacial_exige_muestra_grande():
    n = 50
    with pytest.raises(ValueError, match="ocho parametros"):
        ajustar_etas_espacial(np.arange(float(n)), np.full(n, 3.5), np.full(n, -99.0),
                              np.full(n, 17.0), m0=3.0, area_km2=1e5)


def test_no_se_pueden_fijar_los_ocho_parametros():
    n = 200
    fijos = dict(mu=0.5, K=0.02, alpha=1.5, c=0.01, p=1.15, d_km=5.0, q=1.6, gamma=0.5)
    with pytest.raises(ValueError, match="ocho parametros"):
        ajustar_etas_espacial(np.arange(float(n)), np.full(n, 3.5), np.full(n, -99.0),
                              np.full(n, 17.0), m0=3.0, area_km2=1e5, fijos=fijos)


def test_parametros_desconocidos_en_fijos_se_rechazan():
    n = 200
    with pytest.raises(ValueError, match="desconocidos"):
        ajustar_etas_espacial(np.arange(float(n)), np.full(n, 3.5), np.full(n, -99.0),
                              np.full(n, 17.0), m0=3.0, area_km2=1e5, fijos={"beta": 1.0})


@pytest.fixture(scope="module")
def catalogo_espacial():
    """Catalogo ETAS espacio-temporal simulado con parametros conocidos."""
    rng = np.random.default_rng(77)
    return simular_espacio_temporal(
        VERDAD_T, b=1.0, t_fin=3000.0, caja=CAJA_FONDO, d_km=VERDAD_E.d_km,
        q=VERDAD_E.q, gamma=VERDAD_E.gamma, r_max_km=VERDAD_E.r_max_km, rng=rng,
    )


@pytest.mark.lento
def test_etas_espacial_recupera_sus_ocho_parametros(catalogo_espacial):
    """Recuperacion con la region del fondo bien especificada.

    Los eventos se restringen a la caja donde vive el fondo y se usa el area de
    esa caja. Sin esa correspondencia el ajuste atribuye mal la sismicidad de
    fondo (ver la prueba siguiente).
    """
    df = catalogo_espacial
    d = df[df["lon"].between(*CAJA_FONDO[:2]) & df["lat"].between(*CAJA_FONDO[2:])]
    aj = ajustar_etas_espacial(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values,
        m0=3.0, area_km2=_area_caja_km2(CAJA_FONDO), t_fin=3000.0,
        r_max_km=VERDAD_E.r_max_km, ventana_dias=800.0,
    )
    t, e = aj.temporales, aj.espaciales
    assert 0.4 < t.mu < 0.9, f"mu={t.mu}"
    assert 0.008 < t.K < 0.035, f"K={t.K}"
    assert 1.1 < t.alpha < 1.9, f"alpha={t.alpha}"
    assert 0.003 < t.c < 0.04, f"c={t.c}"
    assert 1.05 < t.p < 1.40, f"p={t.p}"
    assert 3.5 < e.d_km < 9.0, f"d={e.d_km}"
    assert 1.3 < e.q < 2.4, f"q={e.q}"
    assert 0.3 < e.gamma < 0.95, f"gamma={e.gamma}"
    # La escala espacial derivada esta mejor determinada que d, q y gamma por
    # separado: es la cantidad que conviene reportar.
    assert e.radio_mediano_km(6.0, 3.0) == pytest.approx(
        VERDAD_E.radio_mediano_km(6.0, 3.0), rel=0.4
    )


@pytest.mark.lento
def test_una_region_de_fondo_mal_especificada_subestima_el_fondo(catalogo_espacial):
    """Documenta el modo de fallo dominante del ajuste espacio-temporal.

    Se compara el mismo catalogo ajustado de dos maneras. Si se toma como region
    la caja envolvente de TODOS los eventos -- incluidas las replicas dispersadas
    fuera de la zona donde realmente vive el fondo -- el modelo supone fondo
    uniforme sobre un area mayor de la real y **subestima mu**.

    La comparacion es pareada a proposito: la afirmacion util no es que mu caiga
    por debajo de un umbral concreto, sino que poner mal la region lo empuja
    hacia abajo respecto a ponerla bien.
    """
    df = catalogo_espacial
    dentro = df[df["lon"].between(*CAJA_FONDO[:2]) & df["lat"].between(*CAJA_FONDO[2:])]
    bien = ajustar_etas_espacial(
        dentro["t_dias"].values, dentro["mag"].values, dentro["lon"].values,
        dentro["lat"].values, m0=3.0, area_km2=_area_caja_km2(CAJA_FONDO),
        t_fin=3000.0, r_max_km=VERDAD_E.r_max_km, ventana_dias=800.0,
    )
    envolvente = (df["lon"].min(), df["lon"].max(), df["lat"].min(), df["lat"].max())
    mal = ajustar_etas_espacial(
        df["t_dias"].values, df["mag"].values, df["lon"].values, df["lat"].values,
        m0=3.0, area_km2=_area_caja_km2(envolvente), t_fin=3000.0,
        r_max_km=VERDAD_E.r_max_km, ventana_dias=800.0,
    )
    assert mal.temporales.mu < 0.8 * bien.temporales.mu, (
        f"region mal puesta dio mu={mal.temporales.mu:.4f}, region correcta "
        f"mu={bien.temporales.mu:.4f}: se esperaba una subestimacion clara"
    )
    assert any("UNIFORME" in a for a in mal.advertencias)
