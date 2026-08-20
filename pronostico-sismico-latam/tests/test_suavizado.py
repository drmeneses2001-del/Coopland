"""Sismicidad suavizada: conservacion de masa, sensatez del ancho y ausencia de fuga."""
import numpy as np
import pandas as pd
import pytest

from sismolat.evaluacion.pronostico import Rejilla
from sismolat.modelos.suavizado import (
    PISO_RELATIVO_POR_DEFECTO, anchos_adaptativos, campo_suavizado, optimizar_ancho,
    pronostico_suavizado,
)
from sismolat.procedencia import Procedencia

REJILLA = Rejilla.regular((-102.0, -96.0, 15.0, 19.5), 0.5, 3.0, 7.5, 0.5)


@pytest.fixture
def eventos():
    rng = np.random.default_rng(0)
    return rng.normal(-99.5, 0.4, 500), rng.normal(16.5, 0.4, 500)


def _df(lon, lat, t0="2012-01-01", dias=2000.0):
    rng = np.random.default_rng(1)
    return pd.DataFrame({
        "lon": lon, "lat": lat,
        "mag": 3.0 + rng.exponential(0.4, len(lon)),
        "tiempo": pd.Timestamp(t0) + pd.to_timedelta(np.sort(rng.random(len(lon)) * dias),
                                                     unit="D"),
    })


# --- nucleo ---------------------------------------------------------------
def test_la_masa_se_conserva(eventos):
    """Cada evento aporta exactamente 1, aunque su nucleo toque el borde."""
    lon, lat = eventos
    assert campo_suavizado(lon, lat, REJILLA, ancho_km=20.0).sum() == pytest.approx(len(lon))


def test_la_masa_se_conserva_tambien_en_el_borde():
    lon = np.full(50, -101.95)   # pegado al borde oeste
    lat = np.full(50, 15.05)
    assert campo_suavizado(lon, lat, REJILLA, ancho_km=50.0).sum() == pytest.approx(50)


def test_nucleo_estrecho_concentra_mas_que_ancho(eventos):
    lon, lat = eventos
    estrecho = campo_suavizado(lon, lat, REJILLA, ancho_km=5.0)
    ancho = campo_suavizado(lon, lat, REJILLA, ancho_km=80.0)
    # Mayor concentracion = mayor fraccion de la masa en la celda maxima.
    assert estrecho.max() / estrecho.sum() > ancho.max() / ancho.sum()


def test_el_campo_se_centra_donde_estan_los_eventos(eventos):
    lon, lat = eventos
    campo = campo_suavizado(lon, lat, REJILLA, ancho_km=20.0)
    i, j = np.unravel_index(np.argmax(campo), campo.shape)
    cx = 0.5 * (REJILLA.lon_bordes[i] + REJILLA.lon_bordes[i + 1])
    cy = 0.5 * (REJILLA.lat_bordes[j] + REJILLA.lat_bordes[j + 1])
    assert abs(cx - lon.mean()) < 0.6 and abs(cy - lat.mean()) < 0.6


def test_ancho_no_positivo_es_rechazado(eventos):
    lon, lat = eventos
    with pytest.raises(ValueError, match="positivos"):
        campo_suavizado(lon, lat, REJILLA, ancho_km=0.0)


# --- ancho adaptativo -----------------------------------------------------
def test_el_ancho_adaptativo_es_menor_donde_hay_mas_densidad():
    rng = np.random.default_rng(2)
    denso_lon, denso_lat = rng.normal(-99.5, 0.1, 200), rng.normal(16.5, 0.1, 200)
    disperso_lon, disperso_lat = rng.normal(-98.0, 1.2, 50), rng.normal(18.0, 1.2, 50)
    lon = np.concatenate([denso_lon, disperso_lon])
    lat = np.concatenate([denso_lat, disperso_lat])
    a = anchos_adaptativos(lon, lat, k_vecinos=5)
    assert np.median(a[:200]) < np.median(a[200:])


def test_el_ancho_minimo_se_respeta():
    lon = np.full(30, -99.5)   # todos coincidentes
    lat = np.full(30, 16.5)
    assert np.all(anchos_adaptativos(lon, lat, k_vecinos=5, ancho_min_km=3.0) >= 3.0)


# --- pronostico -----------------------------------------------------------
def test_ninguna_celda_tiene_probabilidad_cero(eventos):
    lon, lat = eventos
    p = pronostico_suavizado(_df(lon, lat), REJILLA, b=1.0,
                             dias_entrenamiento=2000.0, dias_pronostico=500.0)
    assert (p.tasas > 0).all(), (
        "una celda de tasa cero produce log-verosimilitud -inf si ocurre alli un evento"
    )


def test_el_total_escala_con_el_tiempo(eventos):
    lon, lat = eventos
    corto = pronostico_suavizado(_df(lon, lat), REJILLA, b=1.0,
                                 dias_entrenamiento=2000.0, dias_pronostico=500.0)
    largo = pronostico_suavizado(_df(lon, lat), REJILLA, b=1.0,
                                 dias_entrenamiento=2000.0, dias_pronostico=1000.0)
    assert largo.total == pytest.approx(2 * corto.total)


def test_la_distribucion_de_magnitudes_sigue_gutenberg_richter(eventos):
    lon, lat = eventos
    p = pronostico_suavizado(_df(lon, lat), REJILLA, b=1.0,
                             dias_entrenamiento=2000.0, dias_pronostico=500.0)
    marg = p.magnitud
    # Con b=1 y bins de 0.5, la razon entre bins consecutivos debe ser 10^-0.5.
    razones = marg[1:] / marg[:-1]
    assert np.allclose(razones, 10 ** -0.5, rtol=1e-6)


def test_exige_exactamente_un_criterio_de_ancho(eventos):
    lon, lat = eventos
    kw = dict(b=1.0, dias_entrenamiento=2000.0, dias_pronostico=500.0)
    with pytest.raises(ValueError, match="exactamente uno"):
        pronostico_suavizado(_df(lon, lat), REJILLA, ancho_km=20.0, k_vecinos=5, **kw)
    with pytest.raises(ValueError, match="exactamente uno"):
        pronostico_suavizado(_df(lon, lat), REJILLA, ancho_km=None, k_vecinos=None, **kw)


def test_el_piso_es_un_supuesto_declarado():
    assert PISO_RELATIVO_POR_DEFECTO.procedencia is Procedencia.SUPUESTO
    assert PISO_RELATIVO_POR_DEFECTO.notas.strip()


def test_el_piso_acerca_el_pronostico_al_uniforme(eventos):
    from sismolat.procedencia import supuesto
    lon, lat = eventos
    kw = dict(b=1.0, dias_entrenamiento=2000.0, dias_pronostico=500.0, k_vecinos=5)
    bajo = pronostico_suavizado(_df(lon, lat), REJILLA,
                                piso_relativo=supuesto(0.001, "adimensional", motivo="prueba"),
                                **kw)
    alto = pronostico_suavizado(_df(lon, lat), REJILLA,
                                piso_relativo=supuesto(0.5, "adimensional", motivo="prueba"),
                                **kw)
    assert alto.espacial.std() < bajo.espacial.std()


# --- optimizacion del ancho ----------------------------------------------
def test_la_optimizacion_no_ve_el_periodo_de_prueba(eventos):
    """La salvaguarda es estructural: la funcion no recibe el periodo de prueba."""
    import inspect
    firma = inspect.signature(optimizar_ancho).parameters
    assert "df_entrenamiento" in firma
    assert not any("prueba" in n or "test" in n for n in firma)


def test_la_optimizacion_devuelve_un_candidato_del_rango(eventos):
    lon, lat = eventos
    cand = np.array([2, 5, 10, 20])
    r = optimizar_ancho(_df(lon, lat), REJILLA, b=1.0, candidatos=cand)
    assert r.mejor in cand
    assert r.log_verosimilitudes.size == cand.size


def test_avisa_si_el_optimo_cae_en_un_extremo(eventos):
    lon, lat = eventos
    r = optimizar_ancho(_df(lon, lat), REJILLA, b=1.0, candidatos=np.array([2, 3, 4]))
    if r.mejor in (2, 4):
        assert any("extremo" in a for a in r.advertencias)


def test_la_optimizacion_exige_muestra_suficiente():
    lon = np.full(20, -99.5)
    lat = np.full(20, 16.5)
    with pytest.raises(ValueError):
        optimizar_ancho(_df(lon, lat), REJILLA, b=1.0, candidatos=np.array([5, 10]))
