"""Capa de ingesta: verificacion obligatoria, deduplicacion y homogenizacion."""
import numpy as np
import pandas as pd
import pytest

from sismolat.ingesta.dedup import CriterioDuplicado, detectar_duplicados, fusionar
from sismolat.ingesta.fdsn import ConsultaEventos, construir_url, parsear_texto_fdsn
from sismolat.ingesta.fuentes import (
    ErrorDeFuenteNoVerificada, Fuente, cargar_fuente, listar_fuentes, resumen_estado,
)
from sismolat.ingesta.homogenizacion import homogenizar, momento_a_mw


# --- registro de fuentes --------------------------------------------------
def test_ninguna_fuente_trae_url_por_defecto():
    """Escribir una URL de API de memoria es justo lo que prohibe el contrato."""
    for f in listar_fuentes():
        assert not f.url_base.strip(), f"{f.clave} trae una url_base sin verificar"
        assert not f.verificado


def test_fuente_sin_verificar_bloquea():
    with pytest.raises(ErrorDeFuenteNoVerificada, match="no esta verificada"):
        cargar_fuente("ssn_unam").exigir_verificacion()


def test_ninguna_fuente_puede_cachearse_por_defecto():
    """Hasta leer la licencia, no se persiste nada."""
    for f in listar_fuentes():
        assert not f.puede_cachearse
        with pytest.raises(ErrorDeFuenteNoVerificada, match="puede_cachearse"):
            f.exigir_permiso_de_cache()


def test_resumen_dice_que_no_hay_fuentes():
    assert "NINGUNA fuente esta verificada" in resumen_estado()


# --- cliente FDSN ---------------------------------------------------------
def test_url_usa_los_nombres_del_estandar():
    f = Fuente("x", "X", "fdsnws-event", "https://ejemplo.test/fdsnws/event/1", True,
               "doc", "lic", True)
    url = construir_url(f, ConsultaEventos("2020-01-01", "2020-12-31", mag_min=4.0,
                                           lat_min=14.0, lat_max=21.0))
    for esperado in ("starttime=", "endtime=", "minmagnitude=4.0",
                     "minlatitude=14.0", "maxlatitude=21.0", "format=text"):
        assert esperado in url


def test_url_bloqueada_si_la_fuente_no_esta_verificada():
    f = Fuente("x", "X", "fdsnws-event", "", False, "doc", "lic", False)
    with pytest.raises(ErrorDeFuenteNoVerificada):
        construir_url(f, ConsultaEventos("2020-01-01", "2020-12-31"))


def test_parseo_del_formato_de_texto_fdsn():
    texto = (
        "#EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|Contributor|"
        "ContributorID|MagType|Magnitude|MagAuthor|EventLocationName\n"
        "ev1|2017-09-19T18:14:39.00|18.55|-98.49|57.0|us|us|us|ev1|mww|7.1|us|Puebla\n"
        "ev2|2017-09-08T04:49:19.00|15.02|-93.90|47.4|us|us|us|ev2|mww|8.2|us|Chiapas\n"
    )
    d = parsear_texto_fdsn(texto, agencia="USGS")
    assert list(d["id_evento"]) == ["ev1", "ev2"]
    assert d["mag"].tolist() == [7.1, 8.2]
    assert str(d["tiempo"].dtype).startswith("datetime64")
    assert d["tiempo"].dt.tz is None, "los tiempos deben quedar naive en UTC"
    assert (d["agencia"] == "USGS").all()


def test_parseo_de_respuesta_vacia():
    assert parsear_texto_fdsn("", "X").empty


# --- deduplicacion --------------------------------------------------------
@pytest.fixture
def multiagencia():
    return pd.DataFrame({
        "id_evento": ["ssn1", "usgs1", "ssn2", "usgs2", "ssn3"],
        "tiempo": pd.to_datetime([
            "2020-06-23T15:29:03", "2020-06-23T15:29:05",
            "2020-06-23T15:31:00", "2020-06-23T15:31:02", "2020-06-23T16:00:00"]),
        "lon": [-96.12, -95.90, -96.30, -96.25, -99.0],
        "lat": [15.78, 15.85, 15.90, 15.88, 19.0],
        "prof_km": [20.0, 22.0, 15.0, 16.0, 10.0],
        "mag": [7.4, 7.4, 4.5, 4.6, 3.2],
        "mag_escala": ["Mw", "Mww", "Mw", "mb", "Mw"],
        "agencia": ["SSN", "USGS", "SSN", "USGS", "SSN"],
    })


def test_empareja_reportes_de_agencias_distintas(multiagencia):
    r = detectar_duplicados(multiagencia)
    assert r.n_entrada == 5 and r.n_grupos == 3


def test_no_empareja_eventos_de_la_misma_agencia(multiagencia):
    r = detectar_duplicados(multiagencia)
    assert (r.parejas["agencia_i"] != r.parejas["agencia_j"]).all()


def test_umbrales_estrechos_impiden_emparejar(multiagencia):
    r = detectar_duplicados(multiagencia, CriterioDuplicado(delta_t_s=0.5, delta_r_km=1.0))
    assert r.n_grupos == 5
    assert any("UTC" in a for a in r.advertencias), (
        "no encontrar ningun duplicado entre agencias debe hacer sospechar de la zona horaria"
    )


def test_fusion_registra_procedencia_por_campo(multiagencia):
    r = detectar_duplicados(multiagencia, CriterioDuplicado(prioridad=("SSN", "USGS")))
    f = fusionar(r)
    assert len(f) == 3
    assert (f["origen_mag"] == "SSN").all()
    assert f.loc[f["n_reportes"] == 2, "agencias_del_grupo"].iloc[0] == "SSN,USGS"


def test_fusion_exige_prioridad_declarada(multiagencia):
    with pytest.raises(ValueError, match="prioridad"):
        fusionar(detectar_duplicados(multiagencia))


def test_dispersion_entre_agencias_se_conserva(multiagencia):
    r = detectar_duplicados(multiagencia, CriterioDuplicado(prioridad=("SSN", "USGS")))
    f = fusionar(r)
    assert f["dispersion_mag_entre_agencias"].max() == pytest.approx(0.1)


# --- homogenizacion -------------------------------------------------------
def test_no_convierte_sin_regresion_verificada():
    d = pd.DataFrame({"mag": [4.5, 3.2], "mag_escala": ["mb", "ML"]})
    h, avisos = homogenizar(d)
    assert h["mag_homog"].isna().all(), "sin regresion verificada debe quedar NaN, no copiarse"
    assert any("SIN homogenizar" in a for a in avisos)


def test_escalas_equivalentes_pasan_sin_conversion():
    d = pd.DataFrame({"mag": [7.4, 5.1], "mag_escala": ["Mww", "Mw"]})
    h, _ = homogenizar(d)
    assert h["mag_homog"].tolist() == [7.4, 5.1]


def test_nunca_sobrescribe_la_magnitud_original():
    d = pd.DataFrame({"mag": [7.4, 4.5], "mag_escala": ["Mww", "mb"]})
    h, _ = homogenizar(d)
    assert h["mag"].tolist() == [7.4, 4.5]
    assert h["mag_escala"].tolist() == ["Mww", "mb"]


def test_hanks_kanamori():
    # Mw = (2/3)(log10 M0 - 9.1) con M0 en N m
    assert float(momento_a_mw(10 ** (1.5 * 7.0 + 9.1))) == pytest.approx(7.0, abs=1e-9)
    with pytest.raises(ValueError):
        momento_a_mw(np.array([-1.0]))


def test_conversion_de_plantilla_esta_desactivada():
    from sismolat.ingesta.homogenizacion import cargar_conversiones
    for c in cargar_conversiones().values():
        assert not c.activo, f"la conversion '{c.clave}' no deberia estar activa"
