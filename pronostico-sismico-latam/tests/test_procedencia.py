"""La regla 'un valor sin procedencia es un bug' se impone por el constructor."""
import pytest

from sismolat.procedencia import (
    Cantidad, ErrorDeProcedencia, Procedencia, convencion, supuesto, adimensional,
)


def test_unidad_es_obligatoria():
    with pytest.raises(ErrorDeProcedencia, match="unidad"):
        Cantidad(1.0, "", Procedencia.SUPUESTO)


def test_procedencias_empiricas_exigen_fuente():
    for p in (Procedencia.MEDIDO, Procedencia.PUBLICADO, Procedencia.DERIVADO):
        with pytest.raises(ErrorDeProcedencia, match="fuente"):
            Cantidad(1.0, "adimensional", p)


def test_procedencias_debiles_no_exigen_fuente():
    for p in (Procedencia.SUPUESTO, Procedencia.CONVENCION, Procedencia.ESTIMACION):
        assert Cantidad(1.0, "adimensional", p).procedencia is p


def test_convencion_y_supuesto_exigen_motivo():
    with pytest.raises(ErrorDeProcedencia):
        convencion(1.0, "adimensional", motivo="  ")
    with pytest.raises(ErrorDeProcedencia):
        supuesto(1.0, "adimensional", motivo="")


def test_valor_no_finito_es_rechazado():
    for malo in (float("nan"), float("inf")):
        with pytest.raises(ErrorDeProcedencia):
            Cantidad(malo, "adimensional", Procedencia.SUPUESTO)


def test_incertidumbre_negativa_es_rechazada():
    with pytest.raises(ErrorDeProcedencia):
        Cantidad(1.0, "adimensional", Procedencia.SUPUESTO, incertidumbre=-0.1)


def test_no_verificado_se_propaga_a_lo_derivado():
    base = Cantidad(1.0, "adimensional", Procedencia.PUBLICADO, fuente="x",
                    verificado=False)
    assert base.derivar(2.0, unidad="adimensional", fuente="calculo").verificado is False


def test_verificado_se_conserva_cuando_el_insumo_lo_esta():
    base = Cantidad(1.0, "adimensional", Procedencia.PUBLICADO, fuente="x")
    assert base.derivar(2.0, unidad="adimensional", fuente="calculo").verificado is True


def test_etiqueta_ui_marca_lo_no_verificado():
    c = adimensional(1.0, Procedencia.SUPUESTO).marcar_no_verificado("prueba")
    assert "NO-VERIFICADO" in c.etiqueta_ui


def test_ida_y_vuelta_por_diccionario():
    c = Cantidad(1.02, "adimensional", Procedencia.PUBLICADO, fuente="Aki 1965",
                 incertidumbre=0.05, notas="nota")
    assert Cantidad.de_dict(c.a_dict()) == c


def test_sigma_no_cuantificada_no_es_cero():
    c = Cantidad(1.0, "adimensional", Procedencia.SUPUESTO)
    assert c.incertidumbre is None
    assert "no cuantificada" in str(c)
