"""Estimacion conjunta del fondo espacial y los parametros de ETAS."""
import math

import numpy as np
import pytest

from sismolat.evaluacion.pronostico import Rejilla
from sismolat.modelos.decluster_estocastico import (
    estimar_fondo_estocastico, probabilidades_de_fondo,
)
from sismolat.modelos.etas import (
    ParametrosEspaciales, ParametrosETAS, ajustar_etas_espacial, fondo_de_mezcla,
    simular_espacio_temporal,
)
from sismolat.modelos.suavizado import campo_suavizado
from sismolat.procedencia import Procedencia

VERDAD_T = ParametrosETAS(mu=0.60, K=0.018, alpha=1.5, c=0.01, p=1.18, m0=3.0)
VERDAD_E = ParametrosEspaciales(d_km=6.0, q=1.7, gamma=0.6, r_max_km=150.0)
CAJA = (-102.0, -96.0, 15.0, 19.5)
FOCOS = [(-99.5, 16.5, 0.35, 3.0), (-97.0, 16.0, 0.30, 2.0), (-100.5, 18.5, 0.45, 1.0)]


def _rejilla(paso=0.25):
    return Rejilla.regular(CAJA, paso, 3.0, 8.0, 0.5)


def _area_caja_km2():
    km_lon = 111.19 * math.cos(math.radians(0.5 * (CAJA[2] + CAJA[3])))
    return (CAJA[1] - CAJA[0]) * km_lon * (CAJA[3] - CAJA[2]) * 111.19


def _catalogo(t_fin=1500.0, semilla=77, heterogeneo=True):
    rng = np.random.default_rng(semilla)
    df = simular_espacio_temporal(
        VERDAD_T, b=1.0, t_fin=t_fin, caja=CAJA, d_km=VERDAD_E.d_km, q=VERDAD_E.q,
        gamma=VERDAD_E.gamma, r_max_km=VERDAD_E.r_max_km,
        muestrear_fondo=fondo_de_mezcla(FOCOS) if heterogeneo else None, rng=rng,
    )
    return df[df["lon"].between(*CAJA[:2]) & df["lat"].between(*CAJA[2:])]


def _fondo_verdadero(rejilla):
    cx = 0.5 * (rejilla.lon_bordes[:-1] + rejilla.lon_bordes[1:])
    cy = 0.5 * (rejilla.lat_bordes[:-1] + rejilla.lat_bordes[1:])
    gx, gy = np.meshgrid(cx, cy, indexing="ij")
    campo = np.zeros_like(gx)
    for lo, la, sig, w in FOCOS:
        campo += w * np.exp(-0.5 * (((gx - lo) / sig) ** 2 + ((gy - la) / sig) ** 2))
    return campo / campo.sum()


# --- suavizado ponderado ---------------------------------------------------
def test_el_suavizado_ponderado_conserva_la_suma_de_pesos():
    rng = np.random.default_rng(0)
    lon, lat = rng.normal(-99.5, 0.4, 300), rng.normal(16.5, 0.4, 300)
    w = rng.random(300)
    campo = campo_suavizado(lon, lat, _rejilla(0.5), ancho_km=20.0, pesos=w)
    assert campo.sum() == pytest.approx(w.sum(), rel=1e-10)


def test_pesos_negativos_se_rechazan():
    rng = np.random.default_rng(1)
    lon, lat = rng.normal(-99.5, 0.4, 50), rng.normal(16.5, 0.4, 50)
    with pytest.raises(ValueError, match="no negativos"):
        campo_suavizado(lon, lat, _rejilla(0.5), ancho_km=20.0,
                        pesos=-np.ones(50))


def test_el_numero_de_pesos_debe_coincidir():
    rng = np.random.default_rng(2)
    lon, lat = rng.normal(-99.5, 0.4, 50), rng.normal(16.5, 0.4, 50)
    with pytest.raises(ValueError, match="pesos tiene"):
        campo_suavizado(lon, lat, _rejilla(0.5), ancho_km=20.0, pesos=np.ones(10))


# --- probabilidades de fondo ----------------------------------------------
def test_las_probabilidades_estan_en_cero_uno():
    d = _catalogo(t_fin=600.0)
    area = _area_caja_km2()
    phi = probabilidades_de_fondo(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values, 3.0,
        VERDAD_T, VERDAD_E, np.full(len(d), 1.0 / area),
    )
    assert phi.shape == (len(d),)
    assert np.all((phi >= 0.0) & (phi <= 1.0))


def test_sin_disparo_todo_es_fondo():
    """Con K = 0 no hay eventos disparados: toda probabilidad de fondo vale 1."""
    d = _catalogo(t_fin=600.0)
    sin_disparo = ParametrosETAS(mu=0.6, K=0.0, alpha=1.5, c=0.01, p=1.18, m0=3.0)
    phi = probabilidades_de_fondo(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values, 3.0,
        sin_disparo, VERDAD_E, np.full(len(d), 1.0 / _area_caja_km2()),
    )
    assert np.allclose(phi, 1.0)


def test_mas_disparo_baja_la_probabilidad_media_de_fondo():
    d = _catalogo(t_fin=600.0)
    area = np.full(len(d), 1.0 / _area_caja_km2())
    args = (d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values, 3.0)
    poco = ParametrosETAS(0.6, 0.005, 1.5, 0.01, 1.18, 3.0)
    mucho = ParametrosETAS(0.6, 0.05, 1.5, 0.01, 1.18, 3.0)
    assert (probabilidades_de_fondo(*args, mucho, VERDAD_E, area).mean() <
            probabilidades_de_fondo(*args, poco, VERDAD_E, area).mean())


# --- salvaguardas ----------------------------------------------------------
def test_catalogo_pequeno_se_rechaza():
    rng = np.random.default_rng(3)
    n = 50
    with pytest.raises(ValueError, match="bastantes mas"):
        estimar_fondo_estocastico(
            np.sort(rng.random(n) * 100), np.full(n, 3.5),
            rng.uniform(-100, -99, n), rng.uniform(16, 17, n),
            m0=3.0, rejilla=_rejilla(0.5),
        )


def test_los_eventos_fuera_de_la_rejilla_se_descartan_y_se_avisa():
    d = _catalogo(t_fin=800.0)
    rejilla_pequena = Rejilla.regular((-100.5, -98.5, 16.0, 17.5), 0.25, 3.0, 8.0, 0.5)
    a = estimar_fondo_estocastico(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values,
        m0=3.0, rejilla=rejilla_pequena, t_fin=800.0, r_max_km=VERDAD_E.r_max_km,
        ventana_dias=400.0, max_iteraciones=2,
    )
    assert any("fuera de la rejilla" in x for x in a.advertencias)


def test_el_resultado_declara_sus_supuestos():
    d = _catalogo(t_fin=800.0)
    a = estimar_fondo_estocastico(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values,
        m0=3.0, rejilla=_rejilla(0.5), t_fin=800.0, r_max_km=VERDAD_E.r_max_km,
        ventana_dias=400.0, max_iteraciones=2,
    )
    texto = " ".join(a.advertencias)
    assert "SUPUESTO" in texto and "LOCAL" in texto
    assert a.mu_total.procedencia is Procedencia.DERIVADO


def test_la_densidad_de_fondo_esta_normalizada():
    d = _catalogo(t_fin=800.0)
    rej = _rejilla(0.5)
    a = estimar_fondo_estocastico(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values,
        m0=3.0, rejilla=rej, t_fin=800.0, r_max_km=VERDAD_E.r_max_km,
        ventana_dias=400.0, max_iteraciones=2,
    )
    assert float((a.densidad_fondo * rej.areas_km2).sum()) == pytest.approx(1.0, rel=1e-6)
    assert np.all(a.densidad_fondo > 0)


def test_la_fraccion_disparada_es_coherente_con_las_probabilidades():
    d = _catalogo(t_fin=800.0)
    a = estimar_fondo_estocastico(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values,
        m0=3.0, rejilla=_rejilla(0.5), t_fin=800.0, r_max_km=VERDAD_E.r_max_km,
        ventana_dias=400.0, max_iteraciones=2,
    )
    n = a.probabilidad_fondo.size
    assert a.n_fondo_esperado == pytest.approx(a.probabilidad_fondo.sum())
    assert a.fraccion_disparada == pytest.approx(1.0 - a.n_fondo_esperado / n)
    assert 0.0 <= a.fraccion_disparada <= 1.0


# --- validacion central (lenta) --------------------------------------------
@pytest.mark.lento
def test_el_fondo_estimado_recupera_lo_que_el_uniforme_destruye():
    """La razon de ser del modulo, medida sobre un catalogo con fondo conocido.

    Con fondo verdadero heterogeneo, suponerlo uniforme no sesga mu: lo COLAPSA.
    El modelo no puede representar la estructura espacial del fondo y se la
    atribuye entera al disparo.
    """
    d = _catalogo(t_fin=2000.0)
    rej = _rejilla(0.25)

    uniforme = ajustar_etas_espacial(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values,
        m0=3.0, area_km2=_area_caja_km2(), t_fin=2000.0,
        r_max_km=VERDAD_E.r_max_km, ventana_dias=800.0,
    )
    conjunto = estimar_fondo_estocastico(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values,
        m0=3.0, rejilla=rej, t_fin=2000.0, r_max_km=VERDAD_E.r_max_km,
        ventana_dias=800.0, k_vecinos=10, max_iteraciones=8,
    )

    error_uniforme = abs(uniforme.temporales.mu - VERDAD_T.mu) / VERDAD_T.mu
    error_conjunto = abs(conjunto.temporales.mu - VERDAD_T.mu) / VERDAD_T.mu
    assert error_conjunto < error_uniforme, (
        f"mu uniforme={uniforme.temporales.mu:.4f}, conjunto="
        f"{conjunto.temporales.mu:.4f}, verdadero={VERDAD_T.mu}"
    )
    assert error_conjunto < 0.5, f"mu={conjunto.temporales.mu:.4f}"

    # El mapa estimado debe parecerse al fondo verdadero.
    verdadero = _fondo_verdadero(rej)
    est = conjunto.densidad_fondo / conjunto.densidad_fondo.sum()
    r = float(np.corrcoef(est.ravel(), verdadero.ravel())[0, 1])
    assert r > 0.7, f"correlacion del mapa de fondo con el verdadero: {r:.3f}"


@pytest.mark.lento
def test_el_ajuste_conjunto_recupera_los_parametros_de_disparo():
    d = _catalogo(t_fin=2000.0)
    a = estimar_fondo_estocastico(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values,
        m0=3.0, rejilla=_rejilla(0.25), t_fin=2000.0, r_max_km=VERDAD_E.r_max_km,
        ventana_dias=800.0, k_vecinos=10, max_iteraciones=8,
    )
    t, e = a.temporales, a.espaciales
    assert 0.006 < t.K < 0.045, f"K={t.K}"
    assert 1.0 < t.alpha < 2.0, f"alpha={t.alpha}"
    assert 1.0 < t.p < 1.5, f"p={t.p}"
    assert 3.0 < e.d_km < 11.0, f"d={e.d_km}"
    assert 1.2 < e.q < 2.5, f"q={e.q}"


@pytest.mark.lento
def test_la_historia_muestra_la_convergencia():
    d = _catalogo(t_fin=1500.0)
    a = estimar_fondo_estocastico(
        d["t_dias"].values, d["mag"].values, d["lon"].values, d["lat"].values,
        m0=3.0, rejilla=_rejilla(0.5), t_fin=1500.0, r_max_km=VERDAD_E.r_max_km,
        ventana_dias=600.0, max_iteraciones=8,
    )
    assert len(a.historia) >= 2
    cambios = [h["cambio_relativo_mu"] for h in a.historia]
    assert cambios[-1] < cambios[0], "el cambio relativo de mu deberia decrecer"
