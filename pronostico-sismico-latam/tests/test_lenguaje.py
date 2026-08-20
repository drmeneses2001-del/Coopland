"""Fase 8 -- capa de lenguaje y didactica.

La prueba central de este modulo es que la restriccion dura se impone de forma
mecanica: la capa de lenguaje no puede colar una cifra que el motor numerico no
haya calculado.
"""
import numpy as np
import pandas as pd
import pytest

from sismolat.lenguaje.cliente import (
    SISTEMA_BASE, ClienteLenguaje, ErrorDeCapaDeLenguaje, MODELO_POR_DEFECTO,
)
from sismolat.lenguaje.didactica import (
    EJERCICIOS, MODULOS_DIDACTICOS, auditar_paneles, paneles_de,
)
from sismolat.lenguaje.revisor import Gravedad, revisar
from sismolat.lenguaje.verificacion import (
    ErrorDeCifraNoTrazable, aplanar_valores, exigir_cifras_trazables, extraer_numeros,
    verificar_cifras,
)
from sismolat.procedencia import Cantidad, Procedencia
from sismolat.reproducibilidad import BitacoraDeDecisiones, RegistroDePruebas

DATOS = {
    "pga_475_g": 0.0089, "pga_2475_g": 0.0159,
    "magnitud_modal": 7.15, "distancia_modal_km": 263.5,
    "advertencias": ["la fuente se trata como puntual"],
}


class ProveedorFalso:
    """Proveedor con salida fija, para probar sin credenciales ni red."""

    def __init__(self, texto: str):
        self.texto = texto
        self.ultima_llamada = None

    def crear(self, **kw):
        self.ultima_llamada = kw
        return self.texto


# --- extraccion y verificacion de cifras -----------------------------------
def test_extrae_cifras_con_punto_y_con_coma():
    assert [v for _, v in extraer_numeros("son 0.0089 g")] == [0.0089]
    assert [v for _, v in extraer_numeros("son 0,0089 g")] == [0.0089]


def test_extrae_notacion_cientifica():
    assert [v for _, v in extraer_numeros("la tasa es 2.1e-3 por ano")] == [2.1e-3]


def test_aplanar_recorre_estructuras_anidadas():
    v = aplanar_valores({"a": [1.0, {"b": 2.5}], "c": np.array([3.5])})
    assert set(v) >= {1.0, 2.5, 3.5}


def test_un_texto_fiel_pasa_la_verificacion():
    t = ("A 475 anios el PGA es 0.0089 g; a 2475 anios, 0.0159 g. "
         "El escenario modal es M 7.15 a 263.5 km.")
    assert verificar_cifras(t, DATOS).limpio


def test_una_cifra_inventada_se_detecta():
    """El caso que la restriccion dura existe para impedir."""
    t = "El PGA es 0.0089 g, equivalente a una intensidad MMI de 6.4."
    r = verificar_cifras(t, DATOS)
    assert not r.limpio
    assert "6.4" in r.no_trazables


def test_una_conversion_de_unidades_inventada_se_detecta():
    t = "El PGA es 0.0089 g, es decir 0.087 m/s2."
    assert not verificar_cifras(t, DATOS).limpio


def test_el_redondeo_razonable_se_acepta():
    assert verificar_cifras("el PGA es 0.009 g", DATOS).limpio


def test_los_numeros_convencionales_no_se_marcan():
    t = "Para un periodo de retorno de 475 anios, equivalente a 10% en 50 anios."
    assert verificar_cifras(t, DATOS).limpio


def test_exigir_trazabilidad_lanza_en_lugar_de_devolver():
    with pytest.raises(ErrorDeCifraNoTrazable, match="no provienen del motor"):
        exigir_cifras_trazables("el PGA es 0.0089 g y la MMI 6.4", DATOS)


def test_el_informe_nombra_las_cifras_problematicas():
    r = verificar_cifras("PGA 0.0089 g, MMI 6.4, duracion 42 s", DATOS)
    assert "6.4" in r.informe() and "42" in r.informe()


# --- cliente ---------------------------------------------------------------
def test_el_modelo_por_defecto_es_opus_5():
    assert MODELO_POR_DEFECTO == "claude-opus-5"


def test_el_prompt_de_sistema_prohibe_calcular():
    assert "REGLA ABSOLUTA" in SISTEMA_BASE
    assert "no calculas nada" in SISTEMA_BASE.lower()


def test_el_prompt_de_sistema_niega_prediccion_y_alerta():
    bajo = SISTEMA_BASE.lower()
    assert "no esta cientificamente demostrada" in bajo
    assert "alerta temprana" in bajo
    assert "evacuacion" in bajo


def test_la_respuesta_fiel_queda_verificada():
    p = ProveedorFalso("El PGA a 475 anios es 0.0089 g.")
    r = ClienteLenguaje(proveedor=p).preguntar("explica", DATOS)
    assert r.verificado and not r.cifras_no_trazables


def test_la_respuesta_con_cifra_inventada_queda_marcada():
    p = ProveedorFalso("El PGA es 0.0089 g, con intensidad MMI 5.8.")
    r = ClienteLenguaje(proveedor=p).preguntar("explica", DATOS)
    assert not r.verificado and "5.8" in r.cifras_no_trazables
    assert "NO MOSTRAR" in str(r)


def test_no_se_le_pueden_pasar_datos_crudos():
    """La capa no calcula porque no recibe con que calcular."""
    p = ProveedorFalso("texto")
    with pytest.raises(TypeError, match="no calcula"):
        ClienteLenguaje(proveedor=p).preguntar("explica", [1.0, 2.0, 3.0])


@pytest.mark.parametrize("nivel", ["estudiante", "posgrado", "especialista"])
def test_los_tres_niveles_producen_prompts_distintos(nivel):
    p = ProveedorFalso("texto sin cifras")
    ClienteLenguaje(proveedor=p).preguntar("explica", DATOS, nivel=nivel)
    assert nivel in p.ultima_llamada["system"].lower()


def test_un_nivel_desconocido_se_rechaza():
    with pytest.raises(ValueError, match="nivel desconocido"):
        ClienteLenguaje(proveedor=ProveedorFalso("x")).preguntar("e", DATOS, nivel="experto")


def test_los_datos_calculados_llegan_en_el_mensaje():
    p = ProveedorFalso("texto sin cifras")
    ClienteLenguaje(proveedor=p).preguntar("explica", DATOS)
    contenido = p.ultima_llamada["mensajes"][0]["content"]
    assert "0.0089" in contenido and "puntual" in contenido


def test_se_usa_pensamiento_adaptativo_y_esfuerzo():
    class Espia(ProveedorFalso):
        pass
    p = Espia("texto")
    ClienteLenguaje(proveedor=p).preguntar("explica", DATOS, esfuerzo="high")
    assert p.ultima_llamada["esfuerzo"] == "high"


# --- revisor ---------------------------------------------------------------
def test_el_revisor_detecta_fuga_temporal():
    ent = pd.DataFrame({"tiempo": pd.to_datetime(["2019-01-01", "2021-06-01"])})
    inf = revisar(entrenamiento=ent, corte_temporal="2020-01-01")
    assert not inf.utilizable
    assert any(h.categoria == "fuga temporal" for h in inf.invalidantes)


def test_el_revisor_detecta_seleccion_informada(tmp_path):
    b = BitacoraDeDecisiones(tmp_path / "b.json")
    b.anotar("elegir Mc", "mirando todo", vio_datos_posteriores_al_corte=True)
    inf = revisar(bitacora=b)
    assert any(h.categoria == "seleccion informada" for h in inf.invalidantes)


def test_el_revisor_detecta_pruebas_multiples(tmp_path):
    reg = RegistroDePruebas(tmp_path / "p.json")
    for p in (0.001, 0.03, 0.04, 0.6):
        reg.registrar_resultado(reg.preregistrar(f"h{p}", "m"), p)
    for i in range(10):
        reg.preregistrar(f"e{i}", "m")
    inf = revisar(registro_pruebas=reg)
    assert any(h.categoria == "pruebas multiples" for h in inf.hallazgos)


def test_el_revisor_detecta_un_registro_manipulado(tmp_path):
    import json
    ruta = tmp_path / "p.json"
    reg = RegistroDePruebas(ruta)
    reg.preregistrar("a", "m")
    reg.preregistrar("b", "m")
    datos = json.loads(ruta.read_text())
    datos[1]["anterior"] = "manipulado"
    ruta.write_text(json.dumps(datos))
    inf = revisar(registro_pruebas=RegistroDePruebas(ruta))
    assert any(h.categoria == "registro manipulado" for h in inf.invalidantes)


def test_el_revisor_detecta_parametros_no_verificados():
    c = Cantidad(1.0, "adimensional", Procedencia.PUBLICADO, fuente="X 1974",
                 verificado=False)
    inf = revisar(cantidades=[c])
    assert any(h.categoria == "parametros no verificados" for h in inf.hallazgos)


def test_el_revisor_detecta_un_nulo_sin_potencia():
    class R:
        hipotesis = "h"
        rechaza_nulo = False
        potencia = None
    assert any(h.categoria == "nulo sin potencia" for h in revisar(resultados_nulos=[R()]).hallazgos)


def test_el_revisor_detecta_potencia_insuficiente():
    class R:
        hipotesis = "h"
        rechaza_nulo = False
        potencia = 0.2
    assert any(h.categoria == "potencia insuficiente"
               for h in revisar(resultados_nulos=[R()]).hallazgos)


def test_el_revisor_detecta_supuesto_de_poisson_incorrecto():
    class P:
        nombre = "etas"
        poisson_valido = False
    assert any(h.categoria == "supuesto de Poisson" for h in revisar(pronosticos=[P()]).hallazgos)


def test_un_analisis_limpio_no_produce_hallazgos():
    ent = pd.DataFrame({"tiempo": pd.to_datetime(["2018-01-01", "2019-01-01"])})
    inf = revisar(entrenamiento=ent, corte_temporal="2020-01-01")
    assert inf.utilizable and not inf.hallazgos


def test_el_revisor_declara_lo_que_no_cubre():
    inf = revisar()
    texto = " ".join(inf.no_cubierto)
    assert "SELECCION" in texto and "indecidible" in texto


def test_el_informe_es_serializable_para_la_capa_de_lenguaje():
    ent = pd.DataFrame({"tiempo": pd.to_datetime(["2021-01-01"])})
    d = revisar(entrenamiento=ent, corte_temporal="2020-01-01").a_dict()
    assert d["utilizable"] is False and d["n_invalidantes"] >= 1
    assert isinstance(d["hallazgos"], list)


def test_el_informe_del_revisor_pasa_la_verificacion_de_cifras():
    """El revisor alimenta a la capa de lenguaje: sus cifras deben ser trazables."""
    class R:
        hipotesis = "h"
        rechaza_nulo = False
        potencia = 0.2
    d = revisar(resultados_nulos=[R()]).a_dict()
    p = ProveedorFalso("La potencia es 0.20, insuficiente para interpretar el no rechazo.")
    assert ClienteLenguaje(proveedor=p).preguntar("resume", d).verificado


# --- didactica -------------------------------------------------------------
def test_todos_los_modulos_declaran_sus_limitaciones():
    """Guardia de regresion: un modulo nuevo sin limitaciones declaradas falla aqui.

    Un modulo que no declara lo que no puede hacer se presenta como si no tuviera
    limites, que es exactamente lo contrario de lo que este proyecto pretende.
    """
    a = auditar_paneles()
    assert a["sin_limitaciones_declaradas"] == (), (
        "modulos sin panel de limitaciones: " + ", ".join(a["sin_limitaciones_declaradas"])
    )
    assert a["n_modulos"] >= 25


@pytest.mark.parametrize("modulo", MODULOS_DIDACTICOS)
def test_cada_modulo_tiene_resumen_y_limitaciones(modulo):
    p = paneles_de(modulo)
    assert p.resumen.strip()
    assert p.limitaciones.strip()


def test_el_panel_se_renderiza_con_las_tres_secciones():
    t = paneles_de("sismolat.modelos.omori").texto()
    assert "1. LA MATEMATICA" in t
    assert "2. LOS DATOS Y SUS SUPUESTOS" in t
    assert "3. LO QUE ESTE MODULO NO PUEDE HACER" in t


def test_los_ejercicios_declaran_su_trampa():
    assert len(EJERCICIOS) >= 5
    for e in EJERCICIOS:
        assert e.trampa.strip() and e.que_deberia_salir.strip()
        assert e.texto().count("=") > 10


def test_los_ejercicios_apuntan_a_metodos_existentes():
    import sismolat.estadistica.mc  # noqa: F401
    import sismolat.exploratorio.circular  # noqa: F401
    import sismolat.tectonica.momento  # noqa: F401
    nombres = " ".join(e.metodo_sugerido for e in EJERCICIOS)
    for fn in ("comparar_metodos_mc", "n_test_catalogo", "familia_de_tasas",
               "n_minimo_para_detectar", "barrido_de_sensibilidad"):
        assert fn in nombres
