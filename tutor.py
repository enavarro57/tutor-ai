
from openai import OpenAI, RateLimitError
import json

client = OpenAI()


def generar_respuesta(pregunta, edad, nivel, tema, historial, dificultades):
    historial_texto = "\n".join(historial) if isinstance(historial, list) else str(historial)
    dificultades_texto = ", ".join(dificultades) if isinstance(dificultades, list) else str(dificultades)

    prompt = f"""
Eres un tutor educativo claro, amable y adaptado a la edad del alumno.

Datos del alumno:
- Edad: {edad}
- Nivel: {nivel}
- Tema: {tema}
- Dificultades: {dificultades_texto}

Historial reciente:
{historial_texto}

Pregunta actual del alumno:
{pregunta}

Tu tarea:
1. Explica el concepto de forma sencilla y adaptada a su nivel.
2. Propón un siguiente paso práctico.
3. Mantén el nivel detectado.
4. Mantén el tema.
5. Añade recomendaciones simples si procede.

Debes responder SIEMPRE con JSON válido.
No escribas texto fuera del JSON.
Usa exactamente esta estructura:

{{
  "explicacion": "explicación clara para el alumno",
  "siguiente_paso": "acción concreta que debe hacer ahora",
  "nivel_detectado": "{nivel}",
  "tema": "{tema}",
  "recomendaciones": ["recomendación 1", "recomendación 2"]
}}
"""

    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un tutor educativo que responde siempre en JSON válido."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=700,
        )

        contenido = respuesta.choices[0].message.content.strip()

        try:
            return json.loads(contenido)
        except json.JSONDecodeError:
            return {
                "explicacion": contenido,
                "siguiente_paso": "Practica un ejemplo similar.",
                "nivel_detectado": nivel,
                "tema": tema,
                "recomendaciones": []
            }

    except RateLimitError:
        return {
            "explicacion": "Ahora mismo hay muchas peticiones. Inténtalo de nuevo en un momento.",
            "siguiente_paso": "Vuelve a enviar la pregunta dentro de un rato.",
            "nivel_detectado": nivel,
            "tema": tema,
            "recomendaciones": []
        }
    except Exception as e:
        return {
            "explicacion": f"Ha ocurrido un error: {str(e)}",
            "siguiente_paso": "Revisa la configuración e inténtalo otra vez.",
            "nivel_detectado": nivel,
            "tema": tema,
            "recomendaciones": []
        }