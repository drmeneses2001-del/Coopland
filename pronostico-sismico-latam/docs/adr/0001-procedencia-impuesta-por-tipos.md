# ADR 0001 — La procedencia se impone por tipos, no por convención

**Estado:** aceptado · **Fecha:** 2026-08-19

## Contexto

El contrato epistemológico exige que todo valor declare su origen. La forma
habitual de hacerlo —un comentario, o un campo de texto libre en la base de
datos— se degrada: a las dos semanas la mitad está vacía y nadie lo nota.

## Decisión

`Cantidad` valida en el constructor:

- La unidad es obligatoria; para cantidades sin dimensión hay que escribir
  `"adimensional"` explícitamente.
- La procedencia es un enum cerrado, no una cadena.
- `MEDIDO`, `PUBLICADO` y `DERIVADO` **exigen** una fuente citable.
- `CONVENCION` y `SUPUESTO` exigen un motivo escrito.
- La incertidumbre `None` significa *no cuantificada* y se muestra así.
- `verificado=False` se **propaga** a todo lo derivado (`Cantidad.derivar`).

## Consecuencias

**A favor:** es imposible construir un valor sin procedencia; la contaminación
por parámetros no verificados es visible aguas abajo; la interfaz puede marcar
cada número sin lógica adicional.

**En contra:** más verboso que un `float`; hay que decidir la procedencia en
cada sitio (que es el objetivo); `Cantidad` no soporta aritmética directa a
propósito — sumar dos cantidades sin decidir qué pasa con la procedencia sería
justo el agujero que esto cierra.

## Alternativas descartadas

- *Campo de texto libre*: se degrada.
- *Unidades con `pint`*: resuelve unidades, no procedencia; podría añadirse
  encima más adelante.
