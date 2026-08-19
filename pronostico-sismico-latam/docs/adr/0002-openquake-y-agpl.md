# ADR 0002 — Reutilizar OpenQuake implica AGPL-3.0

**Estado:** decisión tomada (reutilizar), implicación pendiente de resolver
**Fecha:** 2026-08-19

## Contexto

Recodificar a mano los modelos de movimiento del terreno (GMM) y los tests CSEP
es la principal fuente de errores silenciosos posible en este proyecto: un
signo, un término de saturación o una unidad (cm/s² frente a g frente a ln g)
producen un número plausible y equivocado. "Verificar los coeficientes en la
literatura" **no es verificación**: verificación es reproducir valores de
referencia publicados, que rara vez acompañan a los artículos.

## Decisión

Reutilizar implementaciones ya cotejadas por sus autores:

- **pyCSEP** para las pruebas de evaluación — licencia **BSD 3-Clause**
  (verificado). Sin restricción.
- **OpenQuake hazardlib** para los GMM — licencia **AGPL-3.0** (verificado
  literalmente en el archivo `LICENSE` de `gem/oq-engine`).

Implementar desde cero solo el núcleo donde el valor didáctico está en leer el
código: Mc, b de Aki-Utsu, decluster, Omori-Utsu, ETAS.

## Implicación pendiente

La AGPL-3.0 se activa **al servir el software por red**, no solo al
distribuirlo. Si la plataforma se expone como servicio web y enlaza OpenQuake
en el mismo proceso, la AGPL alcanza a todo el servicio.

Opciones, para decidir antes de empezar la fase 5:

1. **Aceptar la AGPL** para todo el proyecto. Es lo más simple y coherente.
2. **Aislar OpenQuake** en un proceso o servicio separado que se comunique por
   una interfaz definida. Más complejidad de despliegue.
3. **Prescindir de OpenQuake**: entonces los GMM quedan sin implementación
   verificable y la fase 5 no puede prometer lo que promete.

## Actualización: uso personal (2026-08-19)

El autor ha declarado que el proyecto es de **uso exclusivo y personal** por
ahora. Eso desactiva el problema temporalmente:

- La AGPL-3.0 obliga a ofrecer el código fuente **a quien use el software**. Si
  el único usuario es quien ya lo tiene, no hay obligación que cumplir.
- Tampoco hay distribución ni servicio en red, que son los otros dos
  disparadores.

**La decisión sigue pendiente**, y hay que retomarla antes de: publicar el
repositorio, desplegarlo como servicio, compartirlo con terceros, o usarlo en
docencia. En cualquiera de esos casos, la elección entre las tres opciones de
arriba vuelve a ser bloqueante.

Mientras tanto, `openquake-engine` está en el extra opcional `psha` de
`pyproject.toml`, con la advertencia en el propio archivo. **Las fases 0–4 no lo
usan**.

El repositorio no lleva archivo `LICENSE`, lo que en la práctica significa
"todos los derechos reservados". Para un repositorio privado de uso personal es
lo correcto: no concede permisos que el autor no ha decidido conceder.
