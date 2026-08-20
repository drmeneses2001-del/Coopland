"""Primitivas SVG en linea para el informe. Sin bibliotecas externas.

Por que SVG en linea y no una biblioteca de graficos
----------------------------------------------------
El informe debe ser un **unico archivo** que se abra sin servidor, sin red y sin
instalar nada: es lo que hace falta para revisar un resultado en una maquina
cualquiera, y lo que hace que el archivo siga siendo legible dentro de cinco
anios. Cualquier dependencia de CDN convierte el informe en algo que caduca.

Convenciones de color
---------------------
Los colores no se escriben aqui: se referencian como variables CSS
(``var(--serie-1)``, ``var(--tinta-muted)``...) que el informe define para el
tema claro y el oscuro. Asi el mismo SVG sirve en ambos temas y los valores
viven en un solo sitio.

Lo que este modulo NO puede hacer
---------------------------------
* No decide que grafico corresponde a que dato. Eso lo hace quien construye el
  informe; aqui solo estan las primitivas.
* No hace ajuste automatico de etiquetas: si hay demasiadas se solapan, y por eso
  las funciones aceptan un paso de etiquetado explicito.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass

__all__ = ["Marco", "linea_log_log", "banda_log_log", "mapa_de_calor", "barras",
           "linea_simple", "escapar"]


def escapar(t: object) -> str:
    return html.escape(str(t), quote=True)


@dataclass(frozen=True)
class Marco:
    """Geometria de un panel de grafico, en pixeles."""

    ancho: int = 640
    alto: int = 360
    izq: int = 68
    der: int = 24
    arriba: int = 20
    abajo: int = 48

    @property
    def x0(self) -> int:
        return self.izq

    @property
    def x1(self) -> int:
        return self.ancho - self.der

    @property
    def y0(self) -> int:
        return self.alto - self.abajo

    @property
    def y1(self) -> int:
        return self.arriba


def _ticks_log(vmin: float, vmax: float, max_marcas: int = 9) -> list[float]:
    """Marcas de un eje logaritmico, ralas cuando el rango abarca muchas decadas.

    El esquema 1-2-5 funciona en dos o tres decadas; sobre seis apila etiquetas
    hasta hacerlas ilegibles. Al pasar del limite se cae a potencias de diez y,
    si aun sobran, a una de cada dos o tres.
    """
    lo, hi = math.floor(math.log10(vmin)), math.ceil(math.log10(vmax))
    finas = [m * 10.0 ** e for e in range(int(lo), int(hi) + 1) for m in (1, 2, 5)
             if vmin <= m * 10.0 ** e <= vmax]
    if len(finas) <= max_marcas:
        return finas or [vmin, vmax]
    decadas = [10.0 ** e for e in range(int(lo), int(hi) + 1) if vmin <= 10.0 ** e <= vmax]
    if len(decadas) <= max_marcas:
        return decadas or [vmin, vmax]
    paso = math.ceil(len(decadas) / max_marcas)
    return decadas[::paso] or [vmin, vmax]


def _fmt(v: float) -> str:
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 1e4 or a < 1e-3:
        e = int(math.floor(math.log10(a)))
        return f"{v / 10 ** e:.0f}e{e}"
    if a >= 100:
        return f"{v:.0f}"
    if a >= 1:
        return f"{v:.3g}"
    return f"{v:.3g}"


def _ejes(m: Marco, xt, yt, fx, fy, etiqueta_x: str, etiqueta_y: str) -> list[str]:
    p = []
    for v in yt:
        y = fy(v)
        p.append(f'<line class="rejilla" x1="{m.x0}" y1="{y:.1f}" x2="{m.x1}" y2="{y:.1f}"/>')
        p.append(f'<text class="tick" x="{m.x0 - 8}" y="{y + 4:.1f}" '
                 f'text-anchor="end">{escapar(_fmt(v))}</text>')
    for v in xt:
        x = fx(v)
        p.append(f'<line class="rejilla" x1="{x:.1f}" y1="{m.y0}" x2="{x:.1f}" y2="{m.y1}"/>')
        p.append(f'<text class="tick" x="{x:.1f}" y="{m.y0 + 18}" '
                 f'text-anchor="middle">{escapar(_fmt(v))}</text>')
    p.append(f'<line class="eje" x1="{m.x0}" y1="{m.y0}" x2="{m.x1}" y2="{m.y0}"/>')
    p.append(f'<line class="eje" x1="{m.x0}" y1="{m.y0}" x2="{m.x0}" y2="{m.y1}"/>')
    p.append(f'<text class="eje-tit" x="{(m.x0 + m.x1) / 2:.0f}" y="{m.alto - 6}" '
             f'text-anchor="middle">{escapar(etiqueta_x)}</text>')
    p.append(f'<text class="eje-tit" transform="translate(14,{(m.y0 + m.y1) / 2:.0f}) '
             f'rotate(-90)" text-anchor="middle">{escapar(etiqueta_y)}</text>')
    return p


def linea_log_log(
    series: list[tuple[str, list[float], list[float], str]],
    *, etiqueta_x: str, etiqueta_y: str, marco: Marco | None = None,
    banda: tuple[list[float], list[float], list[float]] | None = None,
    etiqueta_banda: str = "",
) -> str:
    """Grafico de lineas en escala doble logaritmica.

    ``series`` son tuplas ``(nombre, x, y, variable_css_de_color)``. ``banda`` es
    ``(x, y_inferior, y_superior)`` y se dibuja detras, en el color de la serie 1.

    Cada serie lleva **etiqueta directa** al final del trazo: la paleta de
    referencia deja una de sus tintas por debajo de 3:1 sobre la superficie
    clara, y la regla de relieve exige entonces etiquetas visibles o vista de
    tabla. El informe ofrece las dos.
    """
    m = marco or Marco()
    xs = [v for _, x, _, _ in series for v in x if v > 0]
    ys = [v for _, _, y, _ in series for v in y if v > 0]
    if banda:
        xs += [v for v in banda[0] if v > 0]
        ys += [v for v in banda[1] + banda[2] if v > 0]
    if not xs or not ys:
        return '<p class="vacio">Sin datos representables (se requieren valores positivos).</p>'
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    lx0, lx1 = math.log10(xmin), math.log10(xmax)
    ly0, ly1 = math.log10(ymin), math.log10(ymax)
    if lx1 == lx0:
        lx1 = lx0 + 1
    if ly1 == ly0:
        ly1 = ly0 + 1

    def fx(v):
        return m.x0 + (math.log10(v) - lx0) / (lx1 - lx0) * (m.x1 - m.x0)

    def fy(v):
        return m.y0 - (math.log10(v) - ly0) / (ly1 - ly0) * (m.y0 - m.y1)

    p = _ejes(m, _ticks_log(xmin, xmax), _ticks_log(ymin, ymax), fx, fy,
              etiqueta_x, etiqueta_y)

    if banda:
        bx, blo, bhi = banda
        pares = [(x, lo, hi) for x, lo, hi in zip(bx, blo, bhi) if x > 0 and lo > 0 and hi > 0]
        if pares:
            arriba = " ".join(f"{fx(x):.1f},{fy(hi):.1f}" for x, _, hi in pares)
            abajo = " ".join(f"{fx(x):.1f},{fy(lo):.1f}" for x, lo, _ in reversed(pares))
            p.append(f'<polygon class="banda" points="{arriba} {abajo}"/>')

    for nombre, x, y, color in series:
        pts = [(fx(a), fy(b)) for a, b in zip(x, y) if a > 0 and b > 0]
        if not pts:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{a:.1f},{b:.1f}" for i, (a, b) in enumerate(pts))
        p.append(f'<path class="trazo" d="{d}" style="stroke:var({color})"/>')
        # La etiqueta directa se ancla al ultimo punto que sigue dentro del marco,
        # no al ultimo del trazo: si la curva sale por abajo, la etiqueta se
        # quedaba pegada al eje y se solapaba con sus marcas.
        dentro = [(a, b) for a, b in pts if m.y1 <= b <= m.y0 - 14]
        ax, ay = (dentro[-1] if dentro else pts[-1])
        p.append(f'<text class="dir" x="{min(ax + 4, m.x1 - 4):.1f}" y="{ay - 8:.1f}" '
                 f'text-anchor="end" style="fill:var({color})">{escapar(nombre)}</text>')
        for a, b in pts:
            p.append(f'<circle class="pt" cx="{a:.1f}" cy="{b:.1f}" r="9" '
                     f'style="fill:transparent"><title>{escapar(nombre)}</title></circle>')

    leyenda = ""
    if banda and etiqueta_banda:
        leyenda = (f'<p class="leyenda"><span class="muestra banda-m"></span>'
                   f'{escapar(etiqueta_banda)}</p>')
    return (f'<svg class="gr" viewBox="0 0 {m.ancho} {m.alto}" role="img" '
            f'aria-label="{escapar(etiqueta_y)} frente a {escapar(etiqueta_x)}">'
            + "".join(p) + "</svg>" + leyenda)


def linea_simple(
    x: list[float], y: list[float], *, etiqueta_x: str, etiqueta_y: str,
    nombre: str = "", color: str = "--serie-1", marco: Marco | None = None,
) -> str:
    """Linea en escala lineal, una sola serie (sin caja de leyenda: el titulo la nombra)."""
    m = marco or Marco(alto=260)
    if not x or not y:
        return '<p class="vacio">Sin datos.</p>'
    xmin, xmax = min(x), max(x)
    ymin, ymax = min(y), max(y)
    if xmax == xmin:
        xmax = xmin + 1
    if ymax == ymin:
        ymax = ymin + max(abs(ymin) * 0.1, 1e-9)
    ymin = min(ymin, 0.0)

    def fx(v):
        return m.x0 + (v - xmin) / (xmax - xmin) * (m.x1 - m.x0)

    def fy(v):
        return m.y0 - (v - ymin) / (ymax - ymin) * (m.y0 - m.y1)

    xt = [xmin + (xmax - xmin) * k / 4 for k in range(5)]
    yt = [ymin + (ymax - ymin) * k / 4 for k in range(5)]
    p = _ejes(m, xt, yt, fx, fy, etiqueta_x, etiqueta_y)
    pts = [(fx(a), fy(b)) for a, b in zip(x, y)]
    d = " ".join(f"{'M' if i == 0 else 'L'}{a:.1f},{b:.1f}" for i, (a, b) in enumerate(pts))
    p.append(f'<path class="trazo" d="{d}" style="stroke:var({color})"/>')
    for (a, b), vx, vy in zip(pts, x, y):
        p.append(f'<circle class="marca" cx="{a:.1f}" cy="{b:.1f}" r="4" '
                 f'style="fill:var({color})"><title>{escapar(_fmt(vx))}: '
                 f'{escapar(_fmt(vy))}</title></circle>')
    return (f'<svg class="gr" viewBox="0 0 {m.ancho} {m.alto}" role="img" '
            f'aria-label="{escapar(nombre or etiqueta_y)}">' + "".join(p) + "</svg>")


#: Rampa secuencial de un solo tono, clara a oscura. Nunca un arcoiris.
RAMPA_SECUENCIAL = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
                    "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab",
                    "#184f95", "#104281", "#0d366b"]


def mapa_de_calor(
    matriz, *, x_bordes, y_bordes, etiqueta_x: str, etiqueta_y: str,
    titulo_escala: str, marco: Marco | None = None, unidad: str = "",
) -> str:
    """Mapa de calor con rampa secuencial de **un solo tono**, claro a oscuro.

    Una rampa de arcoiris introduce fronteras que el dato no tiene: el ojo lee un
    salto donde solo hay un cambio de tono. Un solo tono con luminosidad creciente
    conserva el orden de magnitud sin inventar estructura.
    """
    m = marco or Marco(ancho=700, alto=420, izq=60, abajo=64, der=132)
    n_x, n_y = len(matriz), len(matriz[0])
    vmax = max(max(f) for f in matriz)
    vmin = min(min(f) for f in matriz)
    if vmax <= vmin:
        vmax = vmin + 1e-12
    ancho = (m.x1 - m.x0) / n_x
    alto = (m.y0 - m.y1) / n_y

    p = []
    for i in range(n_x):
        for j in range(n_y):
            v = matriz[i][j]
            k = int(round((v - vmin) / (vmax - vmin) * (len(RAMPA_SECUENCIAL) - 1)))
            x = m.x0 + i * ancho
            y = m.y0 - (j + 1) * alto
            centro_x = 0.5 * (x_bordes[i] + x_bordes[i + 1])
            centro_y = 0.5 * (y_bordes[j] + y_bordes[j + 1])
            p.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{ancho + 0.6:.2f}" '
                f'height="{alto + 0.6:.2f}" fill="{RAMPA_SECUENCIAL[k]}">'
                f'<title>{centro_x:.2f}, {centro_y:.2f}: {_fmt(v)} {escapar(unidad)}</title>'
                f"</rect>"
            )
    # Ejes con pocas etiquetas, para que no se solapen.
    for k in range(5):
        vx = x_bordes[0] + (x_bordes[-1] - x_bordes[0]) * k / 4
        x = m.x0 + (vx - x_bordes[0]) / (x_bordes[-1] - x_bordes[0]) * (m.x1 - m.x0)
        p.append(f'<text class="tick" x="{x:.0f}" y="{m.y0 + 18}" '
                 f'text-anchor="middle">{escapar(f"{vx:.1f}")}</text>')
        vy = y_bordes[0] + (y_bordes[-1] - y_bordes[0]) * k / 4
        y = m.y0 - (vy - y_bordes[0]) / (y_bordes[-1] - y_bordes[0]) * (m.y0 - m.y1)
        p.append(f'<text class="tick" x="{m.x0 - 8}" y="{y + 4:.0f}" '
                 f'text-anchor="end">{escapar(f"{vy:.1f}")}</text>')
    p.append(f'<rect class="marco-mapa" x="{m.x0}" y="{m.y1}" width="{m.x1 - m.x0}" '
             f'height="{m.y0 - m.y1}" fill="none"/>')
    p.append(f'<text class="eje-tit" x="{(m.x0 + m.x1) / 2:.0f}" y="{m.alto - 20}" '
             f'text-anchor="middle">{escapar(etiqueta_x)}</text>')
    p.append(f'<text class="eje-tit" transform="translate(14,{(m.y0 + m.y1) / 2:.0f}) '
             f'rotate(-90)" text-anchor="middle">{escapar(etiqueta_y)}</text>')

    # Barra de escala.
    bx = m.x1 + 16
    balto = (m.y0 - m.y1)
    paso = balto / len(RAMPA_SECUENCIAL)
    for k, c in enumerate(RAMPA_SECUENCIAL):
        p.append(f'<rect x="{bx}" y="{m.y0 - (k + 1) * paso:.2f}" width="14" '
                 f'height="{paso + 0.5:.2f}" fill="{c}"/>')
    p.append(f'<text class="tick" x="{bx + 18}" y="{m.y1 + 8}">{escapar(_fmt(vmax))}</text>')
    p.append(f'<text class="tick" x="{bx + 18}" y="{m.y0}">{escapar(_fmt(vmin))}</text>')
    p.append(f'<text class="eje-tit" transform="translate({bx + 52},'
             f'{(m.y0 + m.y1) / 2:.0f}) rotate(-90)" text-anchor="middle">'
             f'{escapar(titulo_escala)}</text>')
    return (f'<svg class="gr" viewBox="0 0 {m.ancho} {m.alto}" role="img" '
            f'aria-label="{escapar(titulo_escala)}">' + "".join(p) + "</svg>")


def barras(
    etiquetas: list[str], valores: list[float], *, etiqueta_x: str, etiqueta_y: str,
    color: str = "--serie-1", marco: Marco | None = None, paso_etiqueta: int = 1,
) -> str:
    """Barras verticales con extremo redondeado y separacion de 2 px entre marcas."""
    m = marco or Marco(alto=300)
    if not valores:
        return '<p class="vacio">Sin datos.</p>'
    vmax = max(valores)
    if vmax <= 0:
        return '<p class="vacio">Todos los valores son nulos.</p>'
    n = len(valores)
    paso = (m.x1 - m.x0) / n
    ancho = max(paso - 2.0, 1.0)

    p = []
    for k in range(5):
        v = vmax * k / 4
        y = m.y0 - v / vmax * (m.y0 - m.y1)
        p.append(f'<line class="rejilla" x1="{m.x0}" y1="{y:.1f}" x2="{m.x1}" y2="{y:.1f}"/>')
        p.append(f'<text class="tick" x="{m.x0 - 8}" y="{y + 4:.1f}" '
                 f'text-anchor="end">{escapar(_fmt(v))}</text>')
    for i, (et, v) in enumerate(zip(etiquetas, valores)):
        h = max(v / vmax * (m.y0 - m.y1), 0.0)
        x = m.x0 + i * paso + 1.0
        p.append(f'<rect class="barra" x="{x:.1f}" y="{m.y0 - h:.1f}" width="{ancho:.1f}" '
                 f'height="{h:.1f}" rx="4" style="fill:var({color})">'
                 f'<title>{escapar(et)}: {escapar(_fmt(v))}</title></rect>')
        if i % paso_etiqueta == 0:
            p.append(f'<text class="tick" x="{x + ancho / 2:.1f}" y="{m.y0 + 18}" '
                     f'text-anchor="middle">{escapar(et)}</text>')
    p.append(f'<line class="eje" x1="{m.x0}" y1="{m.y0}" x2="{m.x1}" y2="{m.y0}"/>')
    p.append(f'<text class="eje-tit" x="{(m.x0 + m.x1) / 2:.0f}" y="{m.alto - 6}" '
             f'text-anchor="middle">{escapar(etiqueta_x)}</text>')
    p.append(f'<text class="eje-tit" transform="translate(14,{(m.y0 + m.y1) / 2:.0f}) '
             f'rotate(-90)" text-anchor="middle">{escapar(etiqueta_y)}</text>')
    return (f'<svg class="gr" viewBox="0 0 {m.ancho} {m.alto}" role="img" '
            f'aria-label="{escapar(etiqueta_y)} por {escapar(etiqueta_x)}">'
            + "".join(p) + "</svg>")
