"""Informe HTML autocontenido: un solo archivo, sin red y sin dependencias.

Que es y que no es
------------------
Es un **frontend minimo**: un generador de informes estaticos que produce un
unico archivo HTML abrible en cualquier navegador, sin servidor, sin conexion y
sin instalar nada. No es una aplicacion interactiva ni un visor de mapas.

Esa eleccion es deliberada. Para revisar un resultado --que es lo que hace falta
aqui-- un archivo que se abre con doble clic y sigue siendo legible dentro de
cinco anios vale mas que una aplicacion que depende de un servidor encendido y de
recursos externos que caducan.

Que impone el informe
---------------------
El informe no es un envoltorio neutro: hace cumplir el contrato epistemologico
en la presentacion, que es donde suele romperse.

* **Encabezado fijo** que niega prediccion y alerta. No es opcional ni
  suprimible: :meth:`Informe.render` lo escribe siempre.
* **Toda cifra lleva su procedencia visible.** :meth:`Informe.cantidad` no puede
  renderizar un numero sin etiqueta, porque recibe :class:`Cantidad`, no float.
* **Las advertencias van arriba de su seccion, no al pie.** Una advertencia al
  final de la pagina es una advertencia que nadie lee.
* **El resultado nulo ocupa el mismo espacio que el positivo.**
* **Vista de tabla junto a cada grafico.** Ademas de accesibilidad, es la
  respuesta a la regla de relieve de la paleta: una de sus tintas queda por
  debajo de 3:1 sobre fondo claro.

Lo que este modulo NO puede hacer
---------------------------------
* No dibuja mapas geograficos con costas ni fallas: la rejilla se representa
  como mapa de calor en coordenadas, sin fondo cartografico.
* No es interactivo mas alla de los tooltips nativos de SVG.
* No valida que los resultados que se le pasan sean correctos: presenta lo que
  recibe, con su procedencia.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..procedencia import Cantidad, Procedencia
from . import svg

__all__ = ["Informe", "AVISO_FIJO"]

AVISO_FIJO = (
    "Esto NO es un predictor de sismos. La prediccion determinista --lugar, tiempo y "
    "magnitud con precision util-- no esta cientificamente demostrada. "
    "Esto NO es un sistema de alerta: SASMEX, SNAM/CSN y ShakeAlert detectan ondas de "
    "sismos que YA ocurrieron, que es otra cosa. "
    "Este informe no emite alertas ni recomendaciones de evacuacion."
)

_CSS = """
:root{color-scheme:light dark}
.raiz{
  --plano:#f9f9f7; --superficie:#fcfcfb;
  --tinta:#0b0b0b; --tinta-2:#52514e; --tinta-muted:#898781;
  --rejilla:#e1e0d9; --eje:#c3c2b7; --borde:rgba(11,11,11,.10);
  --serie-1:#2a78d6; --serie-2:#eb6834; --serie-3:#1baf7a;
  --critico:#d03b3b; --aviso:#fab219; --bien:#0ca30c; --serio:#ec835a;
}
@media (prefers-color-scheme:dark){
  :root:where(:not([data-theme="light"])) .raiz{
    --plano:#0d0d0d; --superficie:#1a1a19;
    --tinta:#fff; --tinta-2:#c3c2b7; --tinta-muted:#898781;
    --rejilla:#2c2c2a; --eje:#383835; --borde:rgba(255,255,255,.10);
    --serie-1:#3987e5; --serie-2:#d95926; --serie-3:#199e70;
  }
}
:root[data-theme="dark"] .raiz{
  --plano:#0d0d0d; --superficie:#1a1a19;
  --tinta:#fff; --tinta-2:#c3c2b7; --tinta-muted:#898781;
  --rejilla:#2c2c2a; --eje:#383835; --borde:rgba(255,255,255,.10);
  --serie-1:#3987e5; --serie-2:#d95926; --serie-3:#199e70;
}
*{box-sizing:border-box}
body{margin:0;background:var(--plano)}
.raiz{
  background:var(--plano);color:var(--tinta);
  font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;
  padding:32px 20px 72px;
}
.caja{max-width:920px;margin:0 auto}
h1{font-size:26px;line-height:1.25;margin:0 0 4px}
h2{font-size:19px;margin:40px 0 10px;padding-top:20px;border-top:1px solid var(--borde)}
h3{font-size:15px;margin:22px 0 8px;color:var(--tinta-2)}
p{margin:10px 0}
.sub{color:var(--tinta-2);margin:0 0 20px}
.aviso-fijo{
  border:2px solid var(--critico);border-radius:10px;padding:14px 16px;margin:18px 0 28px;
  background:color-mix(in srgb,var(--critico) 7%,var(--superficie));
}
.aviso-fijo strong{color:var(--critico)}
.tarjeta{
  background:var(--superficie);border:1px solid var(--borde);border-radius:10px;
  padding:16px 18px;margin:14px 0;
}
.avisos{border-left:3px solid var(--aviso);padding:2px 0 2px 14px;margin:12px 0}
.avisos li{margin:6px 0;color:var(--tinta-2);font-size:14px}
.grave{border-left-color:var(--critico)}
.grave li{color:var(--tinta)}
.cant{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;margin:8px 0}
.cant .v{font-size:17px;font-variant-numeric:tabular-nums}
.cant .u{color:var(--tinta-2);font-size:14px}
.badge{
  font-size:11px;letter-spacing:.04em;text-transform:uppercase;
  border:1px solid var(--borde);border-radius:999px;padding:2px 8px;color:var(--tinta-2);
}
.badge.debil{border-color:var(--aviso);color:var(--aviso)}
.badge.nover{border-color:var(--critico);color:var(--critico)}
.gr{width:100%;height:auto;display:block;background:var(--superficie);
    border:1px solid var(--borde);border-radius:8px;margin:8px 0}
.rejilla{stroke:var(--rejilla);stroke-width:1}
.eje{stroke:var(--eje);stroke-width:1}
.tick{fill:var(--tinta-muted);font-size:11px;font-variant-numeric:tabular-nums}
.eje-tit{fill:var(--tinta-2);font-size:12px}
.trazo{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.dir{font-size:12px;font-weight:600}
.banda{fill:var(--serie-1);opacity:.16}
.marco-mapa{stroke:var(--eje);stroke-width:1}
.barra{stroke:var(--superficie);stroke-width:2}
.pt,.marca{cursor:crosshair}
.leyenda{font-size:13px;color:var(--tinta-2);margin:2px 0 0;display:flex;
         align-items:center;gap:8px}
.muestra{width:14px;height:10px;border-radius:2px;display:inline-block}
.banda-m{background:var(--serie-1);opacity:.3}
details{margin:6px 0 18px}
summary{cursor:pointer;color:var(--tinta-2);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th,td{text-align:right;padding:4px 8px;border-bottom:1px solid var(--borde);
      font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left;font-variant-numeric:normal}
th{color:var(--tinta-2);font-weight:600}
.nulo{border:2px solid var(--eje);border-radius:10px;padding:18px;margin:16px 0}
.nulo h3{margin-top:0;font-size:16px;color:var(--tinta)}
.dato{display:grid;grid-template-columns:minmax(0,190px) 1fr;gap:4px 16px;
      font-size:14px;margin:10px 0}
.dato dt{color:var(--tinta-2)}
.dato dd{margin:0;font-variant-numeric:tabular-nums}
.pie{margin-top:48px;padding-top:16px;border-top:1px solid var(--borde);
     color:var(--tinta-muted);font-size:12px}
.vacio{color:var(--tinta-muted);font-style:italic}
@media (max-width:560px){.dato{grid-template-columns:1fr}}
"""


def _e(t: object) -> str:
    return html.escape(str(t), quote=True)


@dataclass
class Informe:
    """Acumula secciones y las vuelca a un HTML autocontenido."""

    titulo: str
    subtitulo: str = ""
    partes: list[str] = field(default_factory=list)

    # -- bloques de texto -------------------------------------------------
    def seccion(self, titulo: str, texto: str = "") -> "Informe":
        self.partes.append(f"<h2>{_e(titulo)}</h2>")
        if texto:
            self.partes.append(f"<p>{_e(texto)}</p>")
        return self

    def parrafo(self, texto: str) -> "Informe":
        self.partes.append(f"<p>{_e(texto)}</p>")
        return self

    def nota(self, texto: str) -> "Informe":
        self.partes.append(f'<div class="tarjeta"><p>{_e(texto)}</p></div>')
        return self

    def advertencias(self, avisos: Iterable[str], *, graves: bool = False) -> "Informe":
        avisos = [a for a in avisos if str(a).strip()]
        if not avisos:
            return self
        clase = "avisos grave" if graves else "avisos"
        items = "".join(f"<li>{_e(a)}</li>" for a in avisos)
        self.partes.append(f'<ul class="{clase}">{items}</ul>')
        return self

    # -- cantidades con procedencia ---------------------------------------
    def cantidad(self, etiqueta: str, c: Cantidad) -> "Informe":
        """Renderiza una cantidad. **Exige** :class:`Cantidad`, no un float."""
        if not isinstance(c, Cantidad):
            raise TypeError(
                f"'{etiqueta}' debe ser una Cantidad con procedencia declarada, no "
                f"{type(c).__name__}. El informe no muestra numeros desnudos."
            )
        val = f"{c.valor:.4g}"
        if c.incertidumbre is not None:
            val += f" ± {c.incertidumbre:.2g}"
        clase = "badge"
        if not c.verificado:
            clase += " nover"
        elif c.procedencia.es_debil:
            clase += " debil"
        etq = c.procedencia.value + ("/NO VERIFICADO" if not c.verificado else "")
        fuente = f'<span class="u">{_e(c.fuente)}</span>' if c.fuente else ""
        self.partes.append(
            f'<div class="cant"><strong>{_e(etiqueta)}</strong>'
            f'<span class="v">{_e(val)}</span>'
            f'<span class="u">{_e(c.unidad)}</span>'
            f'<span class="{clase}">{_e(etq)}</span>{fuente}</div>'
        )
        if c.notas:
            self.partes.append(f'<p class="sub" style="margin:0 0 8px">{_e(c.notas)}</p>')
        return self

    def datos(self, pares: dict[str, Any]) -> "Informe":
        filas = "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in pares.items())
        self.partes.append(f'<dl class="dato">{filas}</dl>')
        return self

    def tabla(self, cabecera: list[str], filas: list[list[Any]], *,
              resumen: str = "Ver los datos en tabla") -> "Informe":
        """Vista de tabla. Acompaña a cada grafico: accesibilidad y regla de relieve."""
        th = "".join(f"<th>{_e(c)}</th>" for c in cabecera)
        tr = "".join("<tr>" + "".join(f"<td>{_e(v)}</td>" for v in f) + "</tr>"
                     for f in filas)
        self.partes.append(
            f"<details><summary>{_e(resumen)}</summary>"
            f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></details>"
        )
        return self

    def grafico(self, marcado: str) -> "Informe":
        self.partes.append(marcado)
        return self

    # -- bloques especializados -------------------------------------------
    def curva_de_peligro(self, curva, *, resultado_arbol=None,
                         periodos=(475.0, 2475.0)) -> "Informe":
        """Curva de peligro en escala doble logaritmica, con banda de fractiles."""
        niveles = list(map(float, curva.niveles))
        tasas = list(map(float, curva.tasas))
        series = [("media" if resultado_arbol is not None else "tasa anual",
                   niveles, tasas, "--serie-1")]
        banda = None
        etiqueta_banda = ""
        if resultado_arbol is not None:
            banda = (niveles, list(map(float, resultado_arbol.fractil(0.16))),
                     list(map(float, resultado_arbol.fractil(0.84))))
            etiqueta_banda = ("fractiles 16-84 del arbol logico (incertidumbre "
                              "epistemica; NO es un intervalo de confianza)")
        self.grafico(svg.linea_log_log(
            series, etiqueta_x=f"{curva.medida} (g)",
            etiqueta_y="tasa anual de excedencia", banda=banda,
            etiqueta_banda=etiqueta_banda,
        ))
        filas = []
        for T in periodos:
            try:
                filas.append([f"{T:.0f}", f"{curva.nivel_para_periodo(T):.5f}"])
            except ValueError:
                filas.append([f"{T:.0f}", "fuera del rango calculado"])
        self.tabla(["periodo de retorno (anios)", f"{curva.medida} (g)"], filas,
                   resumen="Niveles por periodo de retorno")
        self.tabla(["nivel (g)", "tasa anual"],
                   [[f"{n:.5g}", f"{t:.4g}"] for n, t in zip(niveles, tasas)],
                   resumen="Ver la curva completa en tabla")
        self.advertencias(curva.advertencias)
        return self

    def mapa_de_fondo(self, ajuste, *, dias: float = 365.0) -> "Informe":
        """Mapa de calor del fondo estimado por decluster estocastico."""
        rej = ajuste.rejilla
        tasa = ajuste.tasa_fondo_por_celda(dias)
        self.grafico(svg.mapa_de_calor(
            [list(map(float, fila)) for fila in tasa],
            x_bordes=list(map(float, rej.lon_bordes)),
            y_bordes=list(map(float, rej.lat_bordes)),
            etiqueta_x="longitud (grados)", etiqueta_y="latitud (grados)",
            titulo_escala=f"eventos/celda en {dias:.0f} d",
            unidad="eventos",
        ))
        self.datos({
            "eventos de fondo esperados": f"{ajuste.n_fondo_esperado:.0f} "
                                          f"de {ajuste.probabilidad_fondo.size}",
            "fraccion atribuida a disparo": f"{100 * ajuste.fraccion_disparada:.0f}%",
            "iteraciones": f"{ajuste.n_iteraciones}"
                           f"{'' if ajuste.convergio else ' (NO convergio)'}",
            "ancho del nucleo": str(ajuste.ancho_suavizado_km),
        })
        self.cantidad("tasa total de fondo", ajuste.mu_total)
        self.advertencias(ajuste.advertencias)
        return self

    def convergencia(self, historia) -> "Informe":
        """Traza de mu a lo largo de las iteraciones del esquema EM."""
        it = [float(h["iteracion"]) for h in historia]
        mu = [float(h["mu"]) for h in historia]
        self.grafico(svg.linea_simple(
            it, mu, etiqueta_x="iteracion", etiqueta_y="mu (eventos/dia)",
            nombre="convergencia de la tasa de fondo",
        ))
        self.tabla(["iteracion", "mu", "eventos de fondo", "cambio relativo"],
                   [[h["iteracion"], f"{h['mu']:.5g}", f"{h['n_fondo']:.0f}",
                     f"{h['cambio_relativo_mu']:.3g}"] for h in historia],
                   resumen="Ver la traza de convergencia en tabla")
        return self

    def desagregacion(self, desag) -> "Informe":
        """Contribucion al peligro por bin de magnitud."""
        f = desag.fraccion.sum(axis=(1, 2))
        centros = 0.5 * (desag.bordes_m[:-1] + desag.bordes_m[1:])
        paso = max(1, len(centros) // 10)
        self.grafico(svg.barras(
            [f"{c:.1f}" for c in centros], [float(v) for v in f],
            etiqueta_x="magnitud", etiqueta_y="fraccion de la contribucion",
            paso_etiqueta=paso,
        ))
        self.datos({
            "nivel objetivo": f"{desag.nivel_objetivo:.5g} g",
            "escenario modal": ", ".join(f"{k}={v:.2f}" for k, v in desag.modal().items()),
            "escenario medio": ", ".join(f"{k}={v:.2f}" for k, v in desag.media().items()),
        })
        self.nota(
            "El escenario modal NO es 'el sismo que producira esa aceleracion': es el bin "
            "que mas aporta a una suma sobre muchos escenarios. Con distribuciones anchas "
            "o multimodales puede no representar nada."
        )
        return self

    def panel_nulo(self, resultado) -> "Informe":
        """Resultado exploratorio, con la misma prominencia rechace o no."""
        rechaza = resultado.rechaza_nulo
        veredicto = ("SE RECHAZA LA HIPOTESIS NULA" if rechaza
                     else "NO SE RECHAZA LA HIPOTESIS NULA")
        pot = ("no calculada" if resultado.potencia is None
               else f"{resultado.potencia:.3f}")
        bloque = [
            f'<div class="nulo"><h3>{_e(veredicto)}</h3>',
            f"<p>{_e(resultado.hipotesis)}</p>",
        ]
        bloque.append(
            '<dl class="dato">'
            f"<dt>metodo</dt><dd>{_e(resultado.metodo)}</dd>"
            f"<dt>eventos</dt><dd>{resultado.n}</dd>"
            f"<dt>tamano de efecto</dt><dd>{resultado.tamano_efecto:+.5f} "
            f"{_e(resultado.unidad_efecto)}</dd>"
            f"<dt>potencia</dt><dd>{_e(pot)}</dd>"
            f"<dt>p-valor</dt><dd>{resultado.p_valor:.5g}</dd>"
            f"<dt>umbral corregido</dt><dd>{resultado.alfa_corregido:.5g}</dd>"
            f"<dt>pruebas en el proyecto</dt><dd>{resultado.n_pruebas_proyecto}</dd>"
            "</dl>"
        )
        if rechaza:
            lectura = (
                "Los datos son incompatibles con la hipotesis nula al umbral corregido. "
                "Eso NO establece causalidad, ni que el mecanismo propuesto sea correcto, "
                "ni que el efecto sirva para pronosticar."
            )
        elif resultado.potencia is not None and resultado.potencia >= 0.8:
            lectura = (
                "Los datos son compatibles con la hipotesis nula. Eso NO demuestra que el "
                f"efecto no exista. Con potencia {resultado.potencia:.2f}, un efecto del "
                "tamano supuesto se habria detectado con alta probabilidad: eso SI acota "
                "el tamano de un posible efecto real."
            )
        else:
            lectura = (
                "Los datos son compatibles con la hipotesis nula, pero la potencia no "
                "permite acotar el tamano de un posible efecto. No rechazar aqui NO es "
                "evidencia de ausencia: es falta de datos."
            )
        bloque.append(f"<p>{_e(lectura)}</p>")
        if resultado.n_pruebas_proyecto > 1:
            bloque.append(
                f'<p class="sub">Con {resultado.n_pruebas_proyecto} hipotesis probadas y '
                f"umbral 0.05 sin corregir se esperarian "
                f"{resultado.n_pruebas_proyecto * 0.05:.1f} falsos positivos solo por azar.</p>"
            )
        bloque.append("</div>")
        self.partes.append("".join(bloque))
        self.advertencias(resultado.advertencias)
        return self

    def revision(self, informe) -> "Informe":
        """Hallazgos del revisor metodologico determinista."""
        if not informe.hallazgos:
            self.nota("Sin hallazgos en las comprobaciones automatizables.")
        else:
            graves = [str(h) for h in informe.invalidantes]
            otros = [str(h) for h in informe.hallazgos if h not in informe.invalidantes]
            self.advertencias(graves, graves=True)
            self.advertencias(otros)
        self.partes.append("<h3>Lo que esta revision NO cubre</h3>")
        self.advertencias(informe.no_cubierto)
        return self

    # -- salida ------------------------------------------------------------
    def render(self) -> str:
        momento = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        cuerpo = "".join(self.partes)
        return (
            "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{_e(self.titulo)}</title><style>{_CSS}</style></head><body>"
            f'<div class="raiz"><div class="caja">'
            f"<h1>{_e(self.titulo)}</h1>"
            + (f'<p class="sub">{_e(self.subtitulo)}</p>' if self.subtitulo else "")
            + f'<div class="aviso-fijo"><strong>Aviso permanente.</strong> {_e(AVISO_FIJO)}</div>'
            + cuerpo
            + f'<p class="pie">Generado por sismolat el {momento}. '
              "Informe autocontenido: no carga recursos externos. "
              "Proyecto de uso personal y de aprendizaje. Las cifras llevan su procedencia; las limitaciones de cada modulo estan declaradas.</p>"
            "</div></div></body></html>"
        )

    def guardar(self, ruta: str | Path) -> Path:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(self.render(), encoding="utf-8")
        return ruta
