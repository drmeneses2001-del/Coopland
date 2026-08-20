"""Instantaneas versionadas del catalogo y modo sin conexion.

Es el modulo que sostiene la reproducibilidad frente a la revision retroactiva
de los catalogos: una agencia puede recalcular la magnitud de un evento de hace
cinco anios, y un analisis que no declare con que estado del catalogo corrio no
es reproducible aunque el codigo y la semilla sean los mismos.
"""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from sismolat.catalogo import Catalogo
from sismolat.ingesta.instantanea import (
    Instantanea, cargar, guardar, listar, mensaje_de_antiguedad,
)


def _catalogo(n=20, semilla=0, origen="prueba"):
    rng = np.random.default_rng(semilla)
    return Catalogo(pd.DataFrame({
        "id_evento": [f"e{i:04d}" for i in range(n)],
        "tiempo": pd.Timestamp("2020-01-01") + pd.to_timedelta(np.sort(rng.random(n) * 365),
                                                               unit="D"),
        "lon": rng.uniform(-102, -96, n),
        "lat": rng.uniform(15, 19.5, n),
        "prof_km": rng.uniform(5, 60, n),
        "mag": 3.0 + rng.exponential(0.5, n),
        "mag_escala": "Mw",
        "agencia": "SINTETICO",
    }), origen=origen)


# --- ida y vuelta ----------------------------------------------------------
def test_guardar_y_cargar_devuelve_el_mismo_catalogo(tmp_path):
    cat = _catalogo()
    ruta = guardar(cat, tmp_path, fuente="prueba")
    inst = cargar(ruta)
    assert inst.catalogo.n == cat.n
    assert inst.huella == cat.huella()
    pd.testing.assert_frame_equal(
        inst.catalogo.df.reset_index(drop=True), cat.df.reset_index(drop=True)
    )


def test_el_nombre_del_fichero_lleva_la_huella(tmp_path):
    cat = _catalogo()
    ruta = guardar(cat, tmp_path, fuente="ssn")
    assert cat.huella()[:12] in ruta.name
    assert ruta.name.startswith("ssn_")


def test_se_escribe_el_json_de_metadatos(tmp_path):
    cat = _catalogo()
    ruta = guardar(cat, tmp_path, fuente="usgs", consulta={"mag_min": 4.0})
    meta = json.loads(ruta.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["fuente"] == "usgs"
    assert meta["n_eventos"] == cat.n
    assert meta["consulta"] == {"mag_min": 4.0}
    assert meta["huella"] == cat.huella()


def test_la_consulta_se_conserva_en_la_instantanea(tmp_path):
    consulta = {"t_inicio": "2020-01-01", "mag_min": 3.5}
    ruta = guardar(_catalogo(), tmp_path, fuente="ssn", consulta=consulta)
    assert cargar(ruta).consulta == consulta


def test_el_origen_del_catalogo_sobrevive(tmp_path):
    ruta = guardar(_catalogo(origen="ssn|filtrado"), tmp_path, fuente="ssn")
    assert cargar(ruta).catalogo.origen == "ssn|filtrado"


# --- integridad ------------------------------------------------------------
def test_una_instantanea_modificada_se_detecta(tmp_path):
    """Si el parquet cambia despues de guardarse, la huella deja de cuadrar."""
    cat = _catalogo()
    ruta = guardar(cat, tmp_path, fuente="ssn")
    d = pd.read_parquet(ruta)
    d.loc[0, "mag"] = 9.9
    d.to_parquet(ruta, index=False)
    with pytest.raises(ValueError, match="no coincide con la registrada"):
        cargar(ruta)


def test_dos_catalogos_distintos_dan_huellas_distintas(tmp_path):
    a = guardar(_catalogo(semilla=1), tmp_path, fuente="x")
    b = guardar(_catalogo(semilla=2), tmp_path, fuente="x")
    assert cargar(a).huella != cargar(b).huella


def test_el_mismo_catalogo_guardado_dos_veces_da_la_misma_huella(tmp_path):
    cat = _catalogo()
    a = guardar(cat, tmp_path / "uno", fuente="x")
    b = guardar(cat, tmp_path / "dos", fuente="x")
    assert cargar(a).huella == cargar(b).huella


# --- listado ---------------------------------------------------------------
def test_listar_devuelve_vacio_si_no_hay_directorio(tmp_path):
    assert listar(tmp_path / "no_existe") == []


def test_listar_ordena_de_la_mas_reciente_a_la_mas_antigua(tmp_path):
    for i in range(3):
        guardar(_catalogo(semilla=i), tmp_path, fuente=f"f{i}")
    metas = listar(tmp_path)
    assert len(metas) == 3
    momentos = [m["momento_utc"] for m in metas]
    assert momentos == sorted(momentos, reverse=True)


def test_listar_incluye_la_ruta_del_parquet(tmp_path):
    guardar(_catalogo(), tmp_path, fuente="ssn")
    meta = listar(tmp_path)[0]
    assert meta["ruta"].endswith(".parquet")
    assert cargar(meta["ruta"]).huella == meta["huella"]


# --- antiguedad y modo sin conexion ----------------------------------------
def _instantanea_con_edad(dias: float, n: int = 20) -> Instantanea:
    cat = _catalogo(n=n)
    momento = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    return Instantanea(catalogo=cat, fuente="ssn", momento_utc=momento,
                       huella=cat.huella(), consulta={})


def test_la_edad_se_calcula_en_dias():
    assert _instantanea_con_edad(10.0).edad_dias == pytest.approx(10.0, abs=0.01)


@pytest.mark.parametrize("dias,unidad", [(0.5, "horas"), (10.0, "dias"), (120.0, "meses")])
def test_el_mensaje_usa_la_unidad_adecuada(dias, unidad):
    assert unidad in mensaje_de_antiguedad(_instantanea_con_edad(dias))


def test_el_mensaje_declara_fuente_tamano_y_huella():
    inst = _instantanea_con_edad(1.0, n=42)
    m = mensaje_de_antiguedad(inst)
    assert "ssn" in m and "42 eventos" in m and inst.huella[:12] in m
    assert "MODO SIN CONEXION" in m


def test_datos_viejos_disparan_la_advertencia_fuerte():
    """Leer actividad reciente con datos de meses es incorrecto y debe decirse."""
    m = mensaje_de_antiguedad(_instantanea_con_edad(90.0))
    assert "ATENCION" in m and "actividad reciente" in m


def test_datos_frescos_no_disparan_la_advertencia():
    assert "ATENCION" not in mensaje_de_antiguedad(_instantanea_con_edad(2.0))
