"""El esquema de catalogo rechaza lo mal formado y avisa de lo peligroso."""
import numpy as np
import pandas as pd
import pytest

from sismolat.catalogo import Catalogo, ErrorDeCatalogo


def _df(n=5, **kw):
    base = {
        "id_evento": [f"e{i}" for i in range(n)],
        "tiempo": pd.to_datetime(["2020-01-0%d" % (i + 1) for i in range(n)]),
        "lon": np.linspace(-100, -99, n),
        "lat": np.linspace(18, 19, n),
        "prof_km": np.full(n, 20.0),
        "mag": np.linspace(4.0, 5.0, n),
        "mag_escala": ["Mw"] * n,
        "agencia": ["SSN"] * n,
    }
    base.update(kw)
    return pd.DataFrame(base)


def test_faltan_columnas():
    with pytest.raises(ErrorDeCatalogo, match="faltan columnas"):
        Catalogo(_df().drop(columns=["prof_km"]))


def test_tiempo_debe_ser_datetime():
    d = _df()
    d["tiempo"] = d["tiempo"].astype(str)
    with pytest.raises(ErrorDeCatalogo, match="datetime64"):
        Catalogo(d)


def test_tiempo_con_zona_es_rechazado():
    d = _df()
    d["tiempo"] = d["tiempo"].dt.tz_localize("UTC")
    with pytest.raises(ErrorDeCatalogo, match="naive"):
        Catalogo(d)


def test_coordenadas_fuera_de_rango():
    with pytest.raises(ErrorDeCatalogo, match="lat"):
        Catalogo(_df(lat=np.full(5, 95.0)))


def test_ids_duplicados_son_rechazados():
    with pytest.raises(ErrorDeCatalogo, match="duplicados"):
        Catalogo(_df(id_evento=["a"] * 5))


def test_avisa_de_escalas_mezcladas():
    c = Catalogo(_df(mag_escala=["Mw", "mb", "Mw", "Ms", "Mw"]))
    assert any("mezcla" in a for a in c.advertencias())


def test_avisa_de_agencias_sin_deduplicar():
    c = Catalogo(_df(agencia=["SSN", "USGS", "SSN", "SSN", "SSN"]))
    assert any("id_fusion" in a for a in c.advertencias())


def test_catalogo_limpio_no_dispara_avisos():
    assert Catalogo(_df()).advertencias() == []


def test_huella_es_estable_ante_reordenamiento():
    d = _df()
    h1 = Catalogo(d).huella()
    h2 = Catalogo(d.iloc[::-1].reset_index(drop=True)).huella()
    assert h1 == h2


def test_huella_cambia_si_cambia_un_dato():
    d = _df()
    h1 = Catalogo(d).huella()
    d2 = d.copy()
    d2.loc[0, "mag"] = 9.9
    assert Catalogo(d2).huella() != h1


def test_filtrar_conserva_el_esquema():
    c = Catalogo(_df(n=5)).filtrar(mag_min=4.5)
    assert c.n == 3 and isinstance(c, Catalogo)
