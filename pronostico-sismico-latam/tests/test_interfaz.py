"""Frontend minimo: informe HTML autocontenido y primitivas SVG."""
import re

import numpy as np
import pytest

from sismolat.interfaz import svg
from sismolat.interfaz.informe import AVISO_FIJO, Informe
from sismolat.procedencia import Cantidad, Procedencia, supuesto


# --- primitivas SVG --------------------------------------------------------
def test_las_marcas_log_se_ralean_al_crecer_el_rango():
    """Con seis decadas, el esquema 1-2-5 apila etiquetas ilegibles."""
    dos = svg._ticks_log(0.01, 1.0)
    seis = svg._ticks_log(1e-6, 0.2)
    doce = svg._ticks_log(1e-12, 1.0)
    for t in (dos, seis, doce):
        assert len(t) <= 9, f"demasiadas marcas: {len(t)}"
    assert len(dos) > 3


def test_las_marcas_log_caen_dentro_del_rango():
    for lo, hi in ((0.01, 1.0), (1e-6, 0.2), (3.0, 900.0)):
        for v in svg._ticks_log(lo, hi):
            assert lo <= v <= hi


def test_la_linea_log_log_produce_svg_valido():
    x = list(np.logspace(-3, 0, 20))
    y = list(np.logspace(-1, -6, 20))
    m = svg.linea_log_log([("serie", x, y, "--serie-1")],
                          etiqueta_x="PGA (g)", etiqueta_y="tasa")
    assert m.startswith("<svg") and "</svg>" in m
    assert "var(--serie-1)" in m


def test_la_linea_log_log_lleva_etiqueta_directa():
    """La regla de relieve de la paleta exige etiquetas visibles o tabla."""
    x = list(np.logspace(-3, 0, 10))
    y = list(np.logspace(-1, -5, 10))
    m = svg.linea_log_log([("media", x, y, "--serie-1")],
                          etiqueta_x="x", etiqueta_y="y")
    assert 'class="dir"' in m and ">media<" in m


def test_la_banda_se_dibuja_detras_de_la_linea():
    x = list(np.logspace(-3, 0, 10))
    y = list(np.logspace(-1, -5, 10))
    lo = [v * 0.5 for v in y]
    hi = [v * 2.0 for v in y]
    m = svg.linea_log_log([("media", x, y, "--serie-1")], etiqueta_x="x",
                          etiqueta_y="y", banda=(x, lo, hi), etiqueta_banda="16-84")
    assert m.index("polygon") < m.index('class="trazo"')
    assert "16-84" in m


def test_valores_no_positivos_no_rompen_la_escala_logaritmica():
    m = svg.linea_log_log([("s", [0.0, -1.0], [0.0, -1.0], "--serie-1")],
                          etiqueta_x="x", etiqueta_y="y")
    assert "Sin datos representables" in m


def test_el_mapa_de_calor_usa_un_solo_tono():
    """Una rampa de arcoiris inventa fronteras que el dato no tiene."""
    matriz = [[float(i * j) for j in range(6)] for i in range(6)]
    m = svg.mapa_de_calor(matriz, x_bordes=list(range(7)), y_bordes=list(range(7)),
                          etiqueta_x="lon", etiqueta_y="lat", titulo_escala="v")
    usados = set(re.findall(r'fill="(#[0-9a-f]{6})"', m))
    assert usados <= set(svg.RAMPA_SECUENCIAL)
    assert len(usados) > 2


def test_la_rampa_secuencial_es_monotona_en_luminosidad():
    def lum(h):
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    l = [lum(c) for c in svg.RAMPA_SECUENCIAL]
    assert all(a > b for a, b in zip(l, l[1:])), "la rampa debe ir de claro a oscuro"


def test_las_barras_dejan_separacion_entre_marcas():
    m = svg.barras(["a", "b", "c"], [1.0, 2.0, 3.0], etiqueta_x="x", etiqueta_y="y")
    assert 'class="barra"' in m and 'rx="4"' in m


def test_las_barras_sin_datos_lo_dicen():
    assert "Sin datos" in svg.barras([], [], etiqueta_x="x", etiqueta_y="y")
    assert "nulos" in svg.barras(["a"], [0.0], etiqueta_x="x", etiqueta_y="y")


def test_el_escapado_impide_inyeccion_de_marcado():
    m = svg.barras(["<script>x</script>"], [1.0], etiqueta_x="x", etiqueta_y="y")
    assert "<script>" not in m and "&lt;script&gt;" in m


# --- informe ---------------------------------------------------------------
@pytest.fixture
def informe():
    return Informe("Titulo de prueba", "subtitulo")


def test_el_aviso_permanente_siempre_esta(informe):
    h = informe.render()
    assert "NO es un predictor" in h
    assert "NO es un sistema de alerta" in h
    assert "no emite alertas" in h


def test_el_aviso_no_se_puede_suprimir(informe):
    """No hay parametro que lo quite: render lo escribe siempre."""
    informe.seccion("otra cosa", "texto")
    assert AVISO_FIJO.split(".")[0] in informe.render()


def test_el_informe_no_carga_recursos_externos(informe):
    """Un archivo que depende de un CDN caduca; este debe abrirse sin red."""
    informe.seccion("s").parrafo("p")
    h = informe.render()
    for patron in ("http://", "https://", "<script", "@import", "url("):
        assert patron not in h, f"recurso externo o script: {patron}"


def test_una_cantidad_se_muestra_con_su_procedencia(informe):
    informe.cantidad("valor b", Cantidad(1.02, "adimensional", Procedencia.DERIVADO,
                                         fuente="Aki-Utsu", incertidumbre=0.03))
    h = informe.render()
    assert "1.02" in h and "0.03" in h and "DERIVADO" in h and "Aki-Utsu" in h


def test_una_procedencia_debil_se_marca_visualmente(informe):
    informe.cantidad("m_max", supuesto(8.4, "unidades de magnitud", motivo="cota"))
    h = informe.render()
    assert "badge debil" in h and "SUPUESTO" in h


def test_una_cantidad_no_verificada_se_marca_como_tal(informe):
    informe.cantidad("coef", Cantidad(1.0, "adimensional", Procedencia.PUBLICADO,
                                      fuente="X 1974", verificado=False))
    h = informe.render()
    assert "badge nover" in h and "NO VERIFICADO" in h


def test_el_informe_rechaza_numeros_desnudos(informe):
    """La regla del contrato, impuesta por el tipo del argumento."""
    with pytest.raises(TypeError, match="no muestra numeros desnudos"):
        informe.cantidad("crudo", 3.14)


def test_las_advertencias_graves_se_distinguen(informe):
    informe.advertencias(["algo grave"], graves=True)
    informe.advertencias(["algo menor"])
    h = informe.render()
    assert "avisos grave" in h and "algo grave" in h and "algo menor" in h


def test_las_advertencias_vacias_no_generan_lista(informe):
    informe.advertencias([])
    informe.advertencias(["", "   "])
    assert "<ul" not in informe.render()


def test_el_texto_del_usuario_se_escapa(informe):
    informe.seccion("<img src=x onerror=alert(1)>", "<b>negrita</b>")
    h = informe.render()
    assert "<img" not in h and "<b>negrita</b>" not in h
    assert "&lt;img" in h


def test_la_tabla_acompana_al_grafico(informe):
    informe.tabla(["a", "b"], [[1, 2], [3, 4]])
    h = informe.render()
    assert "<details>" in h and "<table>" in h and "<td>1</td>" in h


def test_el_tema_oscuro_se_declara_en_los_dos_ambitos(informe):
    """Media query para el ajuste del sistema; data-theme para el conmutador."""
    h = informe.render()
    assert "prefers-color-scheme:dark" in h
    assert ':root[data-theme="dark"]' in h
    assert ':root:where(:not([data-theme="light"]))' in h


def test_el_informe_se_guarda_en_disco(tmp_path, informe):
    ruta = informe.guardar(tmp_path / "sub" / "informe.html")
    assert ruta.exists()
    assert ruta.read_text(encoding="utf-8").startswith("<!doctype html>")


# --- panel de resultado nulo ----------------------------------------------
class _Resultado:
    hipotesis = "una hipotesis"
    metodo = "Schuster"
    n = 3000
    tamano_efecto = 0.021
    unidad_efecto = "longitud resultante media"
    p_valor = 0.26
    alfa_corregido = 0.05
    n_pruebas_proyecto = 1
    advertencias = ()

    def __init__(self, potencia=0.94, rechaza=False):
        self.potencia = potencia
        self.rechaza_nulo = rechaza


def test_el_panel_nulo_tiene_la_misma_estructura_que_el_positivo(informe):
    a = Informe("x").panel_nulo(_Resultado(rechaza=False)).render()
    b = Informe("x").panel_nulo(_Resultado(rechaza=True)).render()
    for campo in ("tamano de efecto", "potencia", "p-valor", "umbral corregido"):
        assert campo in a and campo in b
    assert len(a) > 0.6 * len(b), "el panel nulo no puede ser marginal"


def test_el_panel_nulo_no_afirma_ausencia_de_efecto(informe):
    h = Informe("x").panel_nulo(_Resultado(potencia=0.94)).render()
    assert "NO demuestra que el efecto no exista" in h
    assert "SI acota" in h or "acota el tamano" in h


def test_potencia_baja_invalida_el_no_rechazo(informe):
    h = Informe("x").panel_nulo(_Resultado(potencia=0.2)).render()
    assert "NO es evidencia de ausencia" in h


def test_el_panel_avisa_de_las_pruebas_multiples():
    r = _Resultado()
    r.n_pruebas_proyecto = 20
    assert "falsos positivos" in Informe("x").panel_nulo(r).render()


# --- avisos colapsados del arbol logico ------------------------------------
def test_los_avisos_del_arbol_se_colapsan_por_familia():
    """Nueve hojas emitiendo el mismo aviso con distinto valor son ruido."""
    from sismolat.peligro.arbol import _colapsar_avisos
    avisos = [f"m_max = {v} tiene procedencia SUPUESTO." for v in (8.0, 8.4, 8.8)]
    avisos.append("otra cosa distinta")
    salida = _colapsar_avisos(avisos)
    assert len(salida) == 2
    assert any("3 ramas" in a for a in salida)
    assert "otra cosa distinta" in salida


def test_un_aviso_unico_no_se_altera():
    from sismolat.peligro.arbol import _colapsar_avisos
    assert _colapsar_avisos(["solo uno con 3 valores"]) == ("solo uno con 3 valores",)
