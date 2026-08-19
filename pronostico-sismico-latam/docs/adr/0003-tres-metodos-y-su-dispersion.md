# ADR 0003 — Mc y decluster se reportan por triplicado, no por consenso

**Estado:** aceptado · **Fecha:** 2026-08-19

## Contexto

Tanto la magnitud de completitud como el decluster admiten varios métodos
legítimos que dan resultados distintos. La tentación es elegir uno como
"predeterminado bueno" y ofrecer los otros como opción avanzada.

## Decisión

Ninguno de los dos módulos tiene método privilegiado. `comparar_metodos_mc` y
`comparar_metodos` ejecutan los tres y **reportan su dispersión**, con
advertencia automática cuando la divergencia supera un umbral.

## Justificación empírica

Sobre un catálogo sintético con Mc verdadero = 3.5 (rampa de detección), los
tres métodos dan:

| Método | Mc |
|---|---|
| Máxima curvatura (+0.2) | 3.8 |
| Bondad de ajuste (90 %) | 3.5 |
| Estabilidad de b (MBS) | 4.1 |

Dispersión: **0.6 unidades de magnitud**. El error estadístico que cada método
declara por separado es mucho menor. Reportar uno solo transmitiría una
precisión que no existe, y la elección de Mc se propaga a b con más peso que su
propio error estadístico.

## Consecuencias

El usuario no obtiene "el" valor de Mc. Es incómodo y es correcto: la incomodidad
refleja una incertidumbre real que el consenso artificial ocultaría.
