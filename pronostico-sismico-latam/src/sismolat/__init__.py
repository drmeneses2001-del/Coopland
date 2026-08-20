"""sismolat -- pronostico sismico probabilistico y evaluacion de peligro.

Esta biblioteca calcula **tasas de ocurrencia, probabilidades condicionales y
medidas de desempeno**. No predice sismos: la prediccion determinista (lugar,
tiempo y magnitud con precision util) no esta cientificamente demostrada, y
ningun modulo de este paquete afirma lo contrario.

Tampoco es un sistema de alerta. Los sistemas de alerta temprana operativos
(SASMEX en Mexico, SNAM/CSN en Chile, ShakeAlert en Estados Unidos) actuan sobre
ondas P **ya generadas** por un sismo en curso; esto es otra cosa.

Lee docs/00-contrato-epistemologico.md antes de usar cualquier resultado.
"""

__version__ = "0.1.0"

AVISO = (
    "sismolat calcula tasas y probabilidades, no predicciones. No emite alertas ni "
    "recomendaciones de evacuacion, y no debe usarse como si lo hiciera."
)
