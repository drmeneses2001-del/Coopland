"""Identificador reproducible, deteccion de fuga temporal y registro de pruebas."""
import pandas as pd
import pytest

from sismolat.reproducibilidad import (
    BitacoraDeDecisiones, ErrorDeFugaTemporal, RegistroAnalisis, RegistroDePruebas,
    verificar_corte_temporal,
)


def test_identificador_es_determinista():
    a = RegistroAnalisis("x", "hash", {"b": 1.0, "mc": 3.5}, semilla=1, version="v1")
    b = RegistroAnalisis("x", "hash", {"mc": 3.5, "b": 1.0}, semilla=1, version="v1")
    assert a.identificador == b.identificador


def test_identificador_cambia_con_los_parametros():
    a = RegistroAnalisis("x", "h", {"mc": 3.5}, semilla=1, version="v1")
    b = RegistroAnalisis("x", "h", {"mc": 3.6}, semilla=1, version="v1")
    assert a.identificador != b.identificador


def test_sin_control_de_versiones_no_es_reproducible():
    r = RegistroAnalisis("x", "h", {}, semilla=1, version="sin-control-de-versiones")
    assert not r.reproducible
    assert any("reproducible" in a for a in r.advertencias())


def test_sin_semilla_avisa():
    r = RegistroAnalisis("x", "h", {}, semilla=None, version="v1")
    assert any("semilla" in a for a in r.advertencias())


def test_fuga_temporal_detectada():
    s = pd.Series(pd.to_datetime(["2019-01-01", "2021-01-01"]))
    with pytest.raises(ErrorDeFugaTemporal):
        verificar_corte_temporal(s, "2020-01-01")


def test_sin_fuga_no_lanza():
    s = pd.Series(pd.to_datetime(["2018-01-01", "2019-01-01"]))
    assert verificar_corte_temporal(s, "2020-01-01") == []


def test_modo_no_estricto_devuelve_problemas():
    s = pd.Series(pd.to_datetime(["2021-01-01"]))
    assert len(verificar_corte_temporal(s, "2020-01-01", estricto=False)) == 1


def test_registro_de_pruebas_encadena_y_corrige(tmp_path):
    r = RegistroDePruebas(tmp_path / "p.json")
    h = r.preregistrar("hipotesis A", "schuster")
    r.registrar_resultado(h, 0.01)
    for i in range(9):
        r.preregistrar(f"hip {i}", "x")
    assert r.n_pruebas == 10
    assert r.alfa_corregido(0.05) == pytest.approx(0.005)
    assert r.integra()


def test_no_se_puede_registrar_dos_veces_el_mismo_resultado(tmp_path):
    r = RegistroDePruebas(tmp_path / "p.json")
    h = r.preregistrar("h", "m")
    r.registrar_resultado(h, 0.2)
    with pytest.raises(ValueError, match="ya tiene resultado"):
        r.registrar_resultado(h, 0.01)


def test_registro_persiste_entre_sesiones(tmp_path):
    ruta = tmp_path / "p.json"
    RegistroDePruebas(ruta).preregistrar("h1", "m")
    assert RegistroDePruebas(ruta).n_pruebas == 1, "el conteo debe ser de proyecto, no de sesion"


def test_cadena_rota_se_detecta(tmp_path):
    import json
    ruta = tmp_path / "p.json"
    r = RegistroDePruebas(ruta)
    r.preregistrar("a", "m")
    r.preregistrar("b", "m")
    datos = json.loads(ruta.read_text())
    datos[1]["anterior"] = "manipulado"
    ruta.write_text(json.dumps(datos))
    assert not RegistroDePruebas(ruta).integra()


def test_benjamini_hochberg(tmp_path):
    r = RegistroDePruebas(tmp_path / "p.json")
    for p in (0.001, 0.02, 0.3, 0.6):
        r.registrar_resultado(r.preregistrar(f"h{p}", "m"), p)
    orden = r.benjamini_hochberg(q=0.05)
    assert orden[0]["significativa_fdr"] is True
    assert orden[-1]["significativa_fdr"] is False


def test_bitacora_marca_decisiones_contaminadas(tmp_path):
    b = BitacoraDeDecisiones(tmp_path / "b.json")
    b.anotar("elegir Mc=3.5", "por el diagrama", vio_datos_posteriores_al_corte=True)
    assert any("no es pseudo-prospectiva" in a for a in b.advertencias())


def test_bitacora_exige_justificacion(tmp_path):
    b = BitacoraDeDecisiones(tmp_path / "b.json")
    with pytest.raises(ValueError):
        b.anotar("algo", "", vio_datos_posteriores_al_corte=False)
