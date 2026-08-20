# Contrato epistemológico

Estas reglas gobiernan todo el código de este repositorio. No son una
declaración de intenciones: están implementadas, y hay pruebas que fallan si se
violan.

## 1. Esto no es un predictor

La predicción determinista de sismos —lugar, tiempo y magnitud con precisión
útil— **no está científicamente demostrada**. Ningún módulo, mensaje de
interfaz ni texto generado por esta aplicación afirmará lo contrario.

Lo que sí es defendible y es lo que aquí se implementa:

- tasas de ocurrencia,
- probabilidades condicionales en ventanas espacio-temporales,
- pronóstico de réplicas,
- evaluación estadística formal del desempeño.

## 2. Esto no es un sistema de alerta

Los sistemas de alerta temprana operativos —SASMEX en México, SNAM/CSN en
Chile, ShakeAlert en Estados Unidos— detectan ondas P de un sismo **que ya
ocurrió** y avisan antes de que lleguen las ondas S. Eso no es pronóstico y no
tiene relación con lo que hace este software.

Esta aplicación **no emite alertas ni recomendaciones de evacuación**.

El diagrama de Molchan, que sí está implementado, es un instrumento para medir
poder discriminante. Su presencia no implica que se propongan alarmas; el
módulo `sismolat.evaluacion.alarma` lo dice en su propia documentación.

## 3. Prohibido inventar

Ningún dato, cifra, coeficiente, ruta de API ni referencia bibliográfica puede
fabricarse. Un valor que no se obtuvo de una fuente comprobada se marca como
`SUPUESTO`, `CONVENCION` o `ESTIMACION`, y esa marca es visible en el código,
en los datos y en la interfaz.

**Cómo está implementado.** Es imposible construir una cantidad sin declarar su
procedencia:

```python
Cantidad(1.0, "adimensional", Procedencia.PUBLICADO)
# ErrorDeProcedencia: procedencia PUBLICADO exige una fuente citable
```

Los coeficientes tomados de la literatura viven en archivos `parametros/*.toml`
con un campo `verificado`. Mientras sea `false`, el código exige autorización
explícita para usarlos y marca **todo** lo derivado como no verificado. La
contaminación se propaga hacia adelante a propósito
(`Cantidad.derivar` hereda el estado de verificación).

Ninguna URL base de servicio aparece en el código. Ver
[`01-fuentes-verificadas.md`](01-fuentes-verificadas.md).

## 4. Un valor sin procedencia es un bug

La regla se impone por tipos, no por convención. El vocabulario de procedencia
es cerrado (`MEDIDO`, `DERIVADO`, `PUBLICADO`, `SUPUESTO`, `CONVENCION`,
`ESTIMACION`) y las procedencias que afirman respaldo externo exigen una fuente
citable en el constructor.

Toda cantidad lleva unidad e incertidumbre. Una incertidumbre `None` significa
*no cuantificada* y se muestra así — no es lo mismo que cero, y el número
desnudo no existe.

## 5. Las decisiones metodológicas se declaran, no se esconden

Varias cosas que suelen presentarse como pasos de limpieza son en realidad
hipótesis:

- **El decluster** produce la partición entre sismicidad de fondo y racimos; no
  la descubre. Tres métodos dan resultados distintos y `comparar_metodos` está
  hecho para mostrarlo.
- **Mc** no es una medición sino el resultado de un criterio. `comparar_metodos_mc`
  reporta la dispersión entre métodos, que suele superar el error estadístico de
  cada uno.
- **La homogenización de magnitudes** es una regresión con error, no un cambio
  de unidad, y ese error se propaga.

## 6. Lo que el software no puede garantizar

La detección automática de fuga de información **solo alcanza a las marcas de
tiempo**. La fuga real —elegir modelo, región de prueba o hiperparámetros
después de haber visto el catálogo completo— es indecidible desde el código.
Para eso existe `BitacoraDeDecisiones`, que no detecta nada: obliga a dejar
constancia fechada.

Prometer "detección automática de fuga" sin esta distinción sería una garantía
falsa, y una garantía falsa en un módulo de validación es peor que no tener el
módulo.

## 7. L'Aquila y la comunicación del riesgo

En 2009, un sismo de M6.3 en L'Aquila (Italia) causó más de 300 muertes. Seis
científicos y un funcionario fueron condenados en primera instancia por
homicidio culposo; las condenas de los científicos fueron posteriormente
anuladas en apelación, y la del funcionario se mantuvo reducida.

El caso no se trató, como a veces se dice, de "no haber predicho el sismo".
Se trató de **cómo se comunicó** el riesgo: de una reunión cuyo mensaje público
resultante llevó a parte de la población a concluir que no había peligro.

La lección que este proyecto toma de ahí es concreta:

- una probabilidad baja no es "no va a pasar";
- comunicar un resultado sin su incertidumbre es una forma de desinformar;
- el modo en que se presenta un número tiene consecuencias materiales.

De ahí vienen las decisiones de diseño de este repositorio: el panel de
resultado nulo con la misma prominencia que el positivo, la incertidumbre
obligatoria junto a cada valor, y las advertencias que ningún módulo permite
silenciar.
