"""Fase 7 -- hipotesis exploratorias: estadistica circular, covariables y panel nulo."""
import math

import numpy as np
import pytest

from sismolat.exploratorio.circular import (
    fase_entre_eventos, fase_por_periodo, n_minimo_para_detectar, potencia_schuster,
    prueba_de_schuster,
)
from sismolat.exploratorio.covariable import potencia_covariable, prueba_de_covariable
from sismolat.exploratorio.energia import (
    comparar_con_caida_de_esfuerzo, escalas_tipicas, informe_de_escalas,
    tiempo_de_recarga_tectonica,
)
from sismolat.exploratorio.panel import ejecutar_preregistrada, presentar
from sismolat.procedencia import Procedencia
from sismolat.reproducibilidad import RegistroDePruebas


# --- estadistica circular --------------------------------------------------
def test_schuster_esta_calibrado_bajo_el_nulo():
    """Con fases uniformes, la tasa de rechazo debe rondar alfa."""
    rng = np.random.default_rng(0)
    n, rech = 400, 0
    for _ in range(n):
        rech += prueba_de_schuster(rng.random(500) * 2 * math.pi).p_valor < 0.05
    assert 0.02 < rech / n < 0.09, f"rechaza {rech / n:.3f}, esperado ~0.05"


def test_schuster_detecta_una_modulacion_real():
    rng = np.random.default_rng(1)
    th = rng.vonmises(1.0, 0.3, size=3000)
    r = prueba_de_schuster(th)
    assert r.p_valor < 0.01
    assert r.R_medio > 0.1
    assert r.fase_media_rad == pytest.approx(1.0, abs=0.2)


def test_el_p_exacto_por_simulacion_concuerda_con_el_asintotico():
    rng = np.random.default_rng(2)
    r = prueba_de_schuster(rng.random(300) * 2 * math.pi, n_simulaciones=4000)
    assert r.p_exacto is not None
    assert abs(r.p_exacto - r.p_valor) < 0.12


def test_avisa_cuando_el_efecto_es_significativo_pero_diminuto():
    rng = np.random.default_rng(3)
    th = rng.vonmises(0.0, 0.06, size=30000)
    r = prueba_de_schuster(th)
    if r.p_valor < 0.05 and r.R_medio < 0.05:
        assert any("diminuto" in a for a in r.advertencias)


def test_avisa_con_muestra_pequena():
    rng = np.random.default_rng(4)
    r = prueba_de_schuster(rng.random(20) * 2 * math.pi)
    assert any("N pequeno" in a or "asintotica" in a for a in r.advertencias)


def test_muestra_insuficiente_se_rechaza():
    with pytest.raises(ValueError, match="al menos 3"):
        prueba_de_schuster(np.array([0.1, 0.2]))


def test_la_potencia_crece_con_el_tamano_del_efecto():
    p1 = potencia_schuster(500, 0.03, semilla=0)
    p2 = potencia_schuster(500, 0.15, semilla=0)
    assert p2 > p1


def test_la_potencia_crece_con_el_numero_de_eventos():
    assert potencia_schuster(2000, 0.06, semilla=0) > potencia_schuster(200, 0.06, semilla=0)


def test_n_minimo_es_mayor_para_efectos_menores():
    """El numero didactico: detectar una modulacion del 2% exige decenas de miles."""
    n_pequeno = n_minimo_para_detectar(0.02)
    n_grande = n_minimo_para_detectar(0.10)
    assert n_pequeno > n_grande
    assert n_pequeno > 5000, (
        f"detectar r=0.02 deberia exigir muchos eventos, salio {n_pequeno}"
    )


def test_fase_por_periodo_cubre_el_ciclo_completo():
    t = np.linspace(0, 100, 5000)
    f = fase_por_periodo(t, periodo_dias=1.0)
    assert f.min() >= 0 and f.max() < 2 * math.pi + 1e-9
    # Con muestreo uniforme en el tiempo, las fases deben salir uniformes.
    assert prueba_de_schuster(f).p_valor > 0.01


def test_periodo_no_positivo_se_rechaza():
    with pytest.raises(ValueError, match="periodo"):
        fase_por_periodo(np.array([1.0, 2.0]), periodo_dias=0.0)


def test_fase_entre_eventos_usa_ciclos_de_duracion_variable():
    marcas = np.array([0.0, 10.0, 25.0, 30.0])
    eventos = np.array([5.0, 17.5, 27.5])
    f = fase_entre_eventos(eventos, marcas)
    assert np.allclose(f, [math.pi, math.pi, math.pi], atol=1e-9)


def test_fase_entre_eventos_exige_marcas_suficientes():
    with pytest.raises(ValueError, match="dos marcas"):
        fase_entre_eventos(np.array([1.0]), np.array([0.0]))


# --- covariables -----------------------------------------------------------
def _serie(n=4000, amplitud=0.0, semilla=0):
    rng = np.random.default_rng(semilla)
    ts = np.arange(float(n))
    vs = np.sin(2 * math.pi * ts / 365.25) * amplitud + rng.standard_normal(n)
    return ts, vs


def test_covariable_calibrada_cuando_no_hay_relacion():
    """Eventos en tiempos aleatorios: la covariable en ellos no debe diferir."""
    ts, vs = _serie(amplitud=0.0, semilla=5)
    rng = np.random.default_rng(6)
    rech = 0
    for k in range(60):
        eventos = np.sort(rng.random(300) * ts[-1])
        r = prueba_de_covariable(eventos, ts, vs, n_permutaciones=300, semilla=k)
        rech += r.p_valor < 0.05
    assert rech / 60 < 0.20, f"rechaza {rech / 60:.3f} sin relacion real"


def test_covariable_detecta_una_relacion_impuesta():
    """Si los eventos se concentran donde la covariable es alta, debe verse."""
    ts, vs = _serie(amplitud=0.0, semilla=7)
    prob = (vs - vs.min()) ** 3
    prob /= prob.sum()
    rng = np.random.default_rng(8)
    eventos = np.sort(rng.choice(ts, size=600, p=prob, replace=True))
    r = prueba_de_covariable(eventos, ts, vs, n_permutaciones=500)
    assert r.tamano_efecto > 0.3
    assert r.p_valor < 0.01


def test_la_covariable_constante_se_rechaza():
    ts = np.arange(1000.0)
    with pytest.raises(ValueError, match="constante"):
        prueba_de_covariable(np.sort(np.random.default_rng(0).random(50) * 999),
                             ts, np.ones_like(ts))


def test_eventos_fuera_del_periodo_se_excluyen_y_se_avisa():
    ts, vs = _serie(semilla=9)
    eventos = np.concatenate([np.linspace(10, 3000, 100), np.array([99999.0])])
    r = prueba_de_covariable(eventos, ts, vs, n_permutaciones=200)
    assert any("fuera del periodo" in a for a in r.advertencias)


def test_avisa_de_estacionalidad_marcada():
    ts, vs = _serie(n=3000, amplitud=3.0, semilla=10)
    eventos = np.sort(np.random.default_rng(11).random(400) * ts[-1])
    r = prueba_de_covariable(eventos, ts, vs, n_permutaciones=200)
    assert any("anual" in a for a in r.advertencias)


def test_muestra_insuficiente_se_rechaza_en_covariable():
    ts, vs = _serie(semilla=12)
    with pytest.raises(ValueError, match="se requieren 20"):
        prueba_de_covariable(np.array([1.0, 2.0, 3.0]), ts, vs)


def test_la_potencia_de_covariable_crece_con_el_efecto():
    assert (potencia_covariable(200, 0.5, n_simulaciones=300) >
            potencia_covariable(200, 0.05, n_simulaciones=300))


# --- escalas de esfuerzo ---------------------------------------------------
def test_la_recarga_tectonica_da_el_orden_de_los_intervalos_de_recurrencia():
    """Comprobacion de que las escalas son las correctas: ~1000 anios."""
    t = tiempo_de_recarga_tectonica(3.0e6, 3.0e10, 1.0e-7)
    assert 100 < t < 10000


def test_todas_las_escalas_son_estimaciones_declaradas():
    for e in escalas_tipicas():
        assert e.esfuerzo_pa.procedencia is Procedencia.ESTIMACION
        assert e.esfuerzo_pa.notas.strip()


def test_el_embalse_esta_al_nivel_de_la_caida_de_esfuerzo():
    """Por eso la sismicidad inducida por embalses sí tiene mecanismo."""
    embalse = next(e for e in escalas_tipicas() if "embalse" in e.nombre.lower())
    c = comparar_con_caida_de_esfuerzo(embalse)
    assert c["razon"] < 10
    assert "INDUCIR" in c["interpretacion"]


def test_la_atmosfera_esta_tres_ordenes_por_debajo():
    atm = next(e for e in escalas_tipicas() if "atmosferica" in e.nombre.lower())
    c = comparar_con_caida_de_esfuerzo(atm)
    assert 2.5 < c["ordenes_de_magnitud"] < 4.0
    assert "modular" in c["interpretacion"]


def test_la_atmosfera_es_comparable_a_la_acumulacion_anual():
    """El matiz que suele perderse: no es despreciable frente a un ano de tectonica."""
    atm = next(e for e in escalas_tipicas() if "atmosferica" in e.nombre.lower())
    tect = next(e for e in escalas_tipicas() if "tectonica" in e.nombre.lower())
    assert 0.2 < atm.esfuerzo_pa.valor / tect.esfuerzo_pa.valor < 5.0


def test_el_informe_distingue_modulacion_de_causacion():
    texto = informe_de_escalas()
    assert "modulacion" in texto.lower() and "causacion" in texto.lower()
    assert "ESTIMACIONES" in texto


# --- panel y preregistro ---------------------------------------------------
@pytest.fixture
def registro(tmp_path):
    return RegistroDePruebas(tmp_path / "pruebas.json")


def _resultado(registro, semilla=3, n=800, kappa=None):
    rng = np.random.default_rng(semilla)
    fases = (rng.random(n) * 2 * math.pi if kappa is None
             else rng.vonmises(0.5, kappa, size=n))
    return ejecutar_preregistrada(
        registro, "hipotesis de prueba", "Schuster",
        lambda: prueba_de_schuster(fases, calcular_potencia_para=0.10),
        extraer_efecto=lambda s: s.R_medio, extraer_p=lambda s: s.p_valor,
        extraer_potencia=lambda s: s.potencia, extraer_n=lambda s: s.n,
    )


def test_la_hipotesis_queda_preregistrada_antes_del_resultado(registro):
    r = _resultado(registro)
    assert registro.n_pruebas == 1
    assert registro.pruebas[0]["resuelta"] is True
    assert registro.integra()


def test_el_panel_tiene_la_misma_estructura_rechace_o_no(registro):
    nulo = presentar(_resultado(registro, semilla=3))
    positivo = presentar(_resultado(registro, semilla=4, kappa=1.0))
    for seccion in ("TAMANO DE EFECTO", "POTENCIA", "SIGNIFICANCIA",
                    "QUE PERMITE AFIRMAR ESTE RESULTADO"):
        assert seccion in nulo and seccion in positivo
    # La longitud del panel nulo no debe ser marginal frente a la del positivo.
    assert len(nulo) > 0.6 * len(positivo)


def test_el_panel_nulo_no_afirma_ausencia_de_efecto(registro):
    texto = presentar(_resultado(registro, semilla=3))
    assert "NO demuestra que" in texto


def test_el_umbral_se_corrige_al_acumular_pruebas(registro):
    for _ in range(10):
        _resultado(registro)
    assert registro.n_pruebas == 10
    r = _resultado(registro)
    assert r.n_pruebas_proyecto == 11
    assert r.alfa_corregido == pytest.approx(0.05 / 11)


def test_el_panel_muestra_los_falsos_positivos_esperados(registro):
    for _ in range(19):
        _resultado(registro)
    texto = presentar(_resultado(registro))
    assert "falsos positivos" in texto
    assert "20" in texto


def test_potencia_baja_invalida_el_no_rechazo(registro):
    r = ejecutar_preregistrada(
        registro, "hipotesis con pocos datos", "Schuster",
        lambda: prueba_de_schuster(
            np.random.default_rng(0).random(30) * 2 * math.pi,
            calcular_potencia_para=0.03),
        extraer_efecto=lambda s: s.R_medio, extraer_p=lambda s: s.p_valor,
        extraer_potencia=lambda s: s.potencia, extraer_n=lambda s: s.n,
    )
    texto = presentar(r)
    if not r.rechaza_nulo and r.potencia < 0.5:
        assert "NO es evidencia de ausencia" in texto
