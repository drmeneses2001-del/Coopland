"""Calibracion y potencia de las pruebas de evaluacion.

Una prueba de consistencia mal calibrada es peor que no tener prueba: da falsa
confianza. Estas pruebas comprueban dos cosas distintas y ambas necesarias:

* **Calibracion**: cuando el catalogo proviene del propio modelo, la tasa de
  rechazo debe aproximarse a alfa.
* **Potencia**: cuando el catalogo proviene de un modelo distinto, la prueba
  adecuada debe rechazar mas que alfa, y la prueba *inadecuada* no debe.
"""
import numpy as np
import pandas as pd
import pytest

from sismolat.evaluacion.alarma import EventoObjetivo, brier, molchan, roc
from sismolat.evaluacion.csep import (
    cl_test, ganancia_informacion, l_test, log_verosimilitud_poisson, m_test,
    n_test, n_test_catalogo, s_test,
)
from sismolat.evaluacion.pronostico import (
    ErrorDeSupuesto, PronosticoCatalogo, PronosticoRejilla, Rejilla,
)

REJILLA = Rejilla.regular((-106.0, -94.0, 14.0, 21.0), 1.0, 4.0, 7.0, 0.5)


def muestrear(tasas, rej, rng):
    c = rng.poisson(tasas)
    filas = []
    for i, j, k in np.argwhere(c > 0):
        for _ in range(int(c[i, j, k])):
            filas.append({
                "lon": 0.5 * (rej.lon_bordes[i] + rej.lon_bordes[i + 1]),
                "lat": 0.5 * (rej.lat_bordes[j] + rej.lat_bordes[j + 1]),
                "mag": 0.5 * (rej.mag_bordes[k] + rej.mag_bordes[k + 1]),
            })
    return pd.DataFrame(filas, columns=["lon", "lat", "mag"])


@pytest.fixture(scope="module")
def uniforme():
    return PronosticoRejilla(REJILLA, np.full(REJILLA.forma, 0.08), "uniforme", 365.0)


# --- calibracion ----------------------------------------------------------
@pytest.mark.parametrize("prueba", [n_test, l_test, cl_test, s_test, m_test])
def test_calibracion_con_modelo_correcto(prueba, uniforme):
    """Con el modelo verdadero, la tasa de rechazo debe rondar alfa = 0.05."""
    rng = np.random.default_rng(4)
    n, rechazos = 120, 0
    for r in range(n):
        obs = muestrear(uniforme.tasas, REJILLA, rng)
        kw = {} if prueba is n_test else {"n_sim": 300, "semilla": r}
        rechazos += prueba(uniforme, obs, **kw).rechaza
    frac = rechazos / n
    assert frac < 0.16, f"{prueba.__name__}: rechaza {frac:.3f} con el modelo correcto"


# --- potencia -------------------------------------------------------------
def test_s_test_detecta_error_espacial_y_n_test_no(uniforme):
    """Un error puramente espacial debe verlo el S-test, no el N-test."""
    rng = np.random.default_rng(11)
    grad = np.linspace(0.2, 3.0, REJILLA.forma[0])[:, None, None] * np.ones(REJILLA.forma)
    grad *= uniforme.total / grad.sum()
    n, s_rech, n_rech = 120, 0, 0
    for r in range(n):
        obs = muestrear(grad, REJILLA, rng)
        s_rech += s_test(uniforme, obs, n_sim=300, semilla=r).rechaza
        n_rech += n_test(uniforme, obs).rechaza
    assert s_rech / n > 0.15, f"S-test sin potencia: {s_rech / n:.3f}"
    assert n_rech / n < 0.16, f"N-test no deberia detectar un error espacial: {n_rech / n:.3f}"


def test_n_test_detecta_error_de_tasa(uniforme):
    rng = np.random.default_rng(12)
    obs = muestrear(uniforme.tasas * 2.5, REJILLA, rng)
    assert n_test(uniforme, obs).rechaza


def test_ganancia_es_positiva_para_el_modelo_correcto(uniforme):
    rng = np.random.default_rng(13)
    grad = np.linspace(0.2, 3.0, REJILLA.forma[0])[:, None, None] * np.ones(REJILLA.forma)
    grad *= uniforme.total / grad.sum()
    obs = muestrear(grad, REJILLA, rng)
    g = ganancia_informacion(PronosticoRejilla(REJILLA, grad, "grad", 365.0), uniforme, obs)
    assert g["ganancia_por_evento"] > 0


def test_ganancia_es_negativa_para_el_modelo_equivocado(uniforme):
    rng = np.random.default_rng(14)
    grad = np.linspace(0.2, 3.0, REJILLA.forma[0])[:, None, None] * np.ones(REJILLA.forma)
    grad *= uniforme.total / grad.sum()
    obs = muestrear(uniforme.tasas, REJILLA, rng)
    g = ganancia_informacion(PronosticoRejilla(REJILLA, grad, "grad", 365.0), uniforme, obs)
    assert g["ganancia_por_evento"] < 0


# --- salvaguardas ---------------------------------------------------------
def test_prueba_poissoniana_rechazada_sobre_pronostico_no_poissoniano():
    pron = PronosticoRejilla(REJILLA, np.full(REJILLA.forma, 0.08), "etas", 365.0,
                             poisson_valido=False)
    rng = np.random.default_rng(1)
    obs = muestrear(pron.tasas, REJILLA, rng)
    with pytest.raises(ErrorDeSupuesto, match="autoexcitado"):
        n_test(pron, obs)


def test_verosimilitud_infinita_si_ocurre_lo_declarado_imposible():
    tasas = np.array([1.0, 0.0])
    assert log_verosimilitud_poisson(tasas, np.array([1.0, 1.0])) == -np.inf
    assert np.isfinite(log_verosimilitud_poisson(tasas, np.array([1.0, 0.0])))


def test_pronostico_catalogo_exige_suficientes_simulaciones():
    with pytest.raises(ValueError, match="al menos"):
        PronosticoCatalogo([pd.DataFrame({"lon": [], "lat": [], "mag": []})] * 10,
                           REJILLA, "x", 365.0)


def test_n_test_catalogo_mide_sobredispersion():
    """Con catalogos sobredispersos, la version basada en catalogo debe notarlo."""
    rng = np.random.default_rng(21)
    cats = []
    for _ in range(400):
        # Mezcla: la mitad de las realizaciones tienen tasa alta -> sobredispersion.
        factor = 0.3 if rng.random() < 0.5 else 2.0
        cats.append(muestrear(np.full(REJILLA.forma, 0.08 * factor), REJILLA, rng))
    pron = PronosticoCatalogo(cats, REJILLA, "sobredisperso", 365.0)
    assert pron.dispersion_relativa() > 3.0
    obs = muestrear(np.full(REJILLA.forma, 0.08 * 2.0), REJILLA, rng)
    r = n_test_catalogo(pron, obs)
    assert not r.rechaza, "la version basada en catalogo debe tolerar la sobredispersion"


# --- Molchan / ROC / Brier ------------------------------------------------
@pytest.fixture(scope="module")
def campo():
    rng = np.random.default_rng(1)
    nl, na, _ = REJILLA.forma
    verdad = np.exp(rng.normal(0, 1.2, size=(nl, na)))
    verdad *= 300 / verdad.sum()
    return verdad, rng.poisson(verdad)


def test_molchan_exige_medida_de_referencia(campo):
    verdad, obs = campo
    with pytest.raises(ValueError, match="areas_celda"):
        molchan(verdad, obs)


def test_molchan_distingue_modelo_util_de_azar(campo):
    verdad, obs = campo
    areas = REJILLA.areas_km2
    bueno = molchan(verdad, obs, areas_celda=areas)
    azar = molchan(np.full_like(verdad, verdad.mean()), obs, medida_referencia="celdas")
    assert bueno.ganancia_area > 0.3
    assert azar.ganancia_area == pytest.approx(0.0, abs=1e-12), \
        "con todas las celdas empatadas el ASS debe ser 0 exacto"


def test_roc_del_modelo_sin_informacion_es_exactamente_media(campo):
    """Con todas las celdas empatadas, el AUC debe ser 0.5 exacto, no aproximado.

    Si los empates se desempatan por indice de arreglo, sale un AUC distinto de
    0.5 y el pronostico uniforme aparenta destreza que no tiene.
    """
    verdad, obs = campo
    plano = roc(np.full_like(verdad, verdad.mean()), obs)
    assert plano.area_bajo_curva == pytest.approx(0.5, abs=1e-12)
    assert roc(verdad, obs).area_bajo_curva > 0.65


def test_brier_resolucion_nula_para_pronostico_constante(campo):
    verdad, obs = campo
    r = brier(np.full_like(verdad, verdad.mean()), obs)
    assert r.resolucion == pytest.approx(0.0, abs=1e-12)
    assert brier(verdad, obs).destreza > 0


def test_evento_objetivo_se_arrastra_al_resultado(campo):
    verdad, obs = campo
    ev = EventoObjetivo(4.0, 365.0, 1.0, "region de prueba")
    assert molchan(verdad, obs, areas_celda=REJILLA.areas_km2, evento=ev).evento is ev
    assert brier(verdad, obs, evento=ev).evento is ev
