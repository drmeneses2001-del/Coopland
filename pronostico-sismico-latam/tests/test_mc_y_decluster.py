"""Magnitud de completitud y decluster: comportamiento y salvaguardas."""
import numpy as np
import pytest

from sismolat.estadistica.decluster import (
    ErrorDeParametrosNoVerificados, advertir_uso, cargar_parametros, comparar_metodos,
    gardner_knopoff, reasenberg, zaliapin_ben_zion,
)
from sismolat.estadistica.mc import (
    comparar_metodos_mc, mc_bondad_ajuste, mc_espacial, mc_estabilidad_b,
    mc_maxima_curvatura, mc_por_ventanas,
)
from sismolat.sintetico import catalogo_poisson_gr, magnitudes_gr


def catalogo_incompleto(mc_verdadero=3.5, n=400_000, semilla=11):
    """Catalogo con una rampa de deteccion centrada en mc_verdadero."""
    rng = np.random.default_rng(semilla)
    m = magnitudes_gr(n, 1.0, mc=2.0, dm=0.1, rng=rng)
    p_det = 1.0 / (1.0 + np.exp(-(m - mc_verdadero) / 0.15))
    return m[rng.random(m.size) < p_det]


# --- Mc -------------------------------------------------------------------
@pytest.mark.parametrize("metodo", [mc_maxima_curvatura, mc_bondad_ajuste, mc_estabilidad_b])
def test_mc_queda_cerca_del_verdadero(metodo):
    m = catalogo_incompleto(3.5)
    mc = metodo(m, 0.1).mc.valor
    assert 3.2 <= mc <= 4.3, f"{metodo.__name__} dio Mc={mc}"


def test_los_metodos_discrepan_y_se_reporta():
    """La dispersion entre metodos es el resultado honesto, no un estorbo."""
    r = comparar_metodos_mc(catalogo_incompleto(3.5), 0.1)
    assert r["dispersion"] > 0
    assert len(r["resultados"]) == 3
    if r["dispersion"] > 0.3:
        assert r["advertencia"], "una dispersion grande debe producir advertencia"


def test_correccion_maxc_es_una_convencion_declarada():
    from sismolat.estadistica.mc import CORRECCION_MAXC_POR_DEFECTO
    from sismolat.procedencia import Procedencia
    assert CORRECCION_MAXC_POR_DEFECTO.procedencia is Procedencia.CONVENCION
    assert CORRECCION_MAXC_POR_DEFECTO.notas.strip(), "una convencion debe declarar su motivo"


def test_bondad_de_ajuste_declara_no_haber_convergido():
    """Con una FMD que no es G-R, el metodo no debe fingir que convergio."""
    rng = np.random.default_rng(3)
    m = np.round(rng.normal(5.0, 0.3, 20_000), 1)  # gaussiana, no exponencial
    r = mc_bondad_ajuste(m, 0.1)
    if not r.criterio_alcanzado:
        assert r.advertencia and not r.mc.verificado


def test_mc_espacial_deja_nan_donde_no_hay_datos():
    import pandas as pd
    cat = catalogo_poisson_gr(400, 10, 1.0, 3.0, rng=np.random.default_rng(2))
    d = cat.df.copy()
    rejilla = mc_espacial(d, paso_grados=1.0, radio_grados=1.0, n_minimo=10_000)
    assert rejilla["mc"].isna().all(), "sin datos suficientes, Mc debe ser NaN, no interpolado"
    assert not rejilla["suficiente"].any()


def test_mc_por_ventanas_devuelve_una_fila_por_ventana():
    cat = catalogo_poisson_gr(2000, 5, 1.0, 3.0, rng=np.random.default_rng(6))
    r = mc_por_ventanas(cat.df, ventana="365D", n_minimo=50)
    assert len(r) >= 4 and {"inicio", "n", "mc", "suficiente"} <= set(r.columns)


# --- decluster ------------------------------------------------------------
@pytest.mark.parametrize("metodo", ["gardner_knopoff", "zaliapin_ben_zion", "reasenberg"])
def test_parametros_no_verificados_bloquean_por_defecto(metodo):
    with pytest.raises(ErrorDeParametrosNoVerificados, match="NO VERIFICADOS"):
        cargar_parametros(metodo)


@pytest.mark.parametrize("metodo", ["gardner_knopoff", "zaliapin_ben_zion", "reasenberg"])
def test_se_puede_autorizar_explicitamente(metodo):
    p = cargar_parametros(metodo, permitir_no_verificado=True)
    assert p["verificado"] is False
    assert p["fuente"], "todo bloque debe declarar la fuente a verificar"


@pytest.mark.parametrize("fn", [gardner_knopoff, reasenberg])
def test_decluster_bloquea_sin_autorizacion(fn):
    cat = catalogo_poisson_gr(200, 5, 1.0, 3.0, rng=np.random.default_rng(3))
    with pytest.raises(ErrorDeParametrosNoVerificados):
        fn(cat)


def test_resultado_hereda_la_marca_de_no_verificado():
    cat = catalogo_poisson_gr(300, 5, 1.0, 3.0, rng=np.random.default_rng(3))
    r = gardner_knopoff(cat, permitir_no_verificado=True)
    assert r.verificado is False
    assert "NO-VERIFICADO" in r.aplicar(cat).origen


def test_catalogo_poissoniano_apenas_se_declusteriza():
    """Sin racimos reales, un decluster no deberia eliminar casi nada."""
    cat = catalogo_poisson_gr(300, 20, 1.0, 3.0, rng=np.random.default_rng(9))
    r = gardner_knopoff(cat, permitir_no_verificado=True)
    assert r.fraccion_eliminada < 0.35, (
        f"elimino {r.fraccion_eliminada:.2f} de un catalogo sin racimos"
    )


def test_decluster_elimina_mas_en_catalogo_con_racimos():
    """Un catalogo ETAS debe perder mas eventos que uno poissoniano equivalente."""
    import pandas as pd
    from sismolat.catalogo import Catalogo
    from sismolat.modelos.etas import ParametrosETAS, simular_espacio_temporal
    par = ParametrosETAS(mu=0.15, K=0.02, alpha=1.5, c=0.01, p=1.2, m0=3.0)
    df = simular_espacio_temporal(par, b=1.0, t_fin=1500.0,
                                  caja=(-100.0, -98.0, 17.0, 19.0),
                                  rng=np.random.default_rng(31))
    cat = Catalogo(pd.DataFrame({
        "id_evento": [f"s{i}" for i in range(len(df))],
        "tiempo": pd.Timestamp("2010-01-01") + pd.to_timedelta(df["t_dias"], unit="D"),
        "lon": df["lon"], "lat": df["lat"], "prof_km": 20.0,
        "mag": df["mag"], "mag_escala": "Mw", "agencia": "SINTETICO",
    }), origen="etas")
    poiss = catalogo_poisson_gr(len(df) / 4.1, 4.1, 1.0, 3.0,
                                caja=(-100.0, -98.0, 17.0, 19.0),
                                rng=np.random.default_rng(32))
    f_etas = gardner_knopoff(cat, permitir_no_verificado=True).fraccion_eliminada
    f_poiss = gardner_knopoff(poiss, permitir_no_verificado=True).fraccion_eliminada
    assert f_etas > f_poiss, f"ETAS {f_etas:.3f} deberia perder mas que Poisson {f_poiss:.3f}"


def test_comparar_metodos_reporta_divergencia():
    cat = catalogo_poisson_gr(400, 8, 1.0, 3.0, rng=np.random.default_rng(15))
    r = comparar_metodos(cat, b=1.0, permitir_no_verificado=True)
    assert set(r["resultados"]) == {"gardner_knopoff", "zaliapin_ben_zion", "reasenberg"}
    assert r["rango_fracciones"] >= 0


def test_advertencia_de_uso_prohibe_decluster_antes_de_etas():
    avisos = advertir_uso("etas")
    assert any("ERROR DE METODO" in a for a in avisos)


def test_advertencia_de_uso_para_psha_es_distinta():
    assert not any("ERROR DE METODO" in a for a in advertir_uso("psha"))
