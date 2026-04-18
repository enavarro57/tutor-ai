from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os

from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
import models
from models import ProgresoTema

from openai import OpenAI

# 🔥 Crear tablas automáticamente
Base.metadata.create_all(bind=engine)

app = FastAPI()

# 🔑 OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# --------- MODELO ---------
class TutorRequest(BaseModel):
    alumno_id: str
    pregunta: str
    respuesta_alumno: str | None = None
    edad: int
    nivel: str
    tema: str
    historial: list = []
    dificultades: list = []


# --------- ROOT ---------
@app.get("/")
def root():
    return {"status": "ok"}


# --------- NORMALIZAR RESPUESTA ---------
def normalizar_respuesta(texto: str) -> str:
    return texto.strip().lower().replace(",", ".")


# --------- IA: GENERAR EJERCICIO ---------
def generar_ejercicio_ia(tema, nivel, edad, dificultades):
    prompt = f"""
Eres un profesor de matemáticas para niños.

Genera un ejercicio de {tema} para un alumno de {edad} años.

Nivel: {nivel}

Dificultades del alumno:
{dificultades}

IMPORTANTE:
- Devuelve SOLO un JSON válido
- Incluye:
  - ejercicio
  - respuesta_correcta
- Usa números simples
- Lenguaje claro

Ejemplo:
{{
  "ejercicio": "Si tienes 12 caramelos y los repartes entre 3 amigos, ¿cuántos recibe cada uno?",
  "respuesta_correcta": "4"
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Eres un tutor educativo experto."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    texto = response.choices[0].message.content

    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if match:
        return json.loads(match.group())
    else:
        return {
            "ejercicio": "¿Cuánto es 10 ÷ 2?",
            "respuesta_correcta": "5"
        }


# --------- IA: EXPLICACIÓN (CORREGIDA) ---------
def generar_explicacion_ia(ejercicio, respuesta_alumno, respuesta_correcta, nivel):
    prompt = f"""
Eres un profesor de matemáticas para niños.

Nivel del alumno: {nivel}

EJERCICIO:
{ejercicio}

RESPUESTA DEL ALUMNO:
{respuesta_alumno}

RESPUESTA CORRECTA:
{respuesta_correcta}

IMPORTANTE:
- NO inventes otro problema
- Usa EXACTAMENTE este ejercicio
- Explica por qué está mal (si lo está)
- Explica paso a paso cómo resolver ESTE ejercicio
- Usa lenguaje claro para niños
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Eres un tutor educativo experto."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    return response.choices[0].message.content


# --------- ENDPOINT PRINCIPAL ---------
@app.post("/tutor")
def tutor(request: TutorRequest):
    db: Session = SessionLocal()

    try:
        alumno_id = request.alumno_id
        pregunta = request.pregunta
        respuesta_alumno = request.respuesta_alumno
        nivel_inicial = request.nivel
        tema = request.tema

        # --------- LEER PROGRESO ---------
        progreso = db.query(ProgresoTema).filter_by(
            alumno_id=alumno_id,
            tema=tema
        ).first()

        if progreso:
            porcentaje_actual = progreso.porcentaje or 0
            if porcentaje_actual >= 80:
                nivel_detectado = "intermedio"
            elif porcentaje_actual >= 50:
                nivel_detectado = "básico"
            else:
                nivel_detectado = "refuerzo"
        else:
            nivel_detectado = nivel_inicial

        # --------- GENERAR EJERCICIO ---------
        ejercicio_data = generar_ejercicio_ia(
            tema,
            nivel_detectado,
            request.edad,
            request.dificultades
        )

        ejercicio = ejercicio_data["ejercicio"]
        respuesta_correcta = ejercicio_data["respuesta_correcta"]

        es_correcta = None
        feedback = ""
        explicacion = ""

        # --------- SIN RESPUESTA ---------
        if not respuesta_alumno:
            explicacion = (
                f"Vamos a trabajar el tema '{tema}' en nivel '{nivel_detectado}'. "
                f"Resuelve este ejercicio: {ejercicio}"
            )
            siguiente_paso = "Envía tu respuesta en 'respuesta_alumno'."

        # --------- CON RESPUESTA ---------
        else:
            respuesta_normalizada = normalizar_respuesta(respuesta_alumno)
            correcta_normalizada = normalizar_respuesta(respuesta_correcta)

            es_correcta = respuesta_normalizada == correcta_normalizada

            # --------- ACTUALIZAR PROGRESO ---------
            if progreso:
                progreso.ejercicios_totales += 1
                if es_correcta:
                    progreso.ejercicios_correctos += 1
            else:
                progreso = ProgresoTema(
                    alumno_id=alumno_id,
                    tema=tema,
                    nivel=nivel_detectado,
                    porcentaje=0,
                    ejercicios_correctos=1 if es_correcta else 0,
                    ejercicios_totales=1
                )
                db.add(progreso)

            progreso.porcentaje = int(
                (progreso.ejercicios_correctos / progreso.ejercicios_totales) * 100
            ) if progreso.ejercicios_totales > 0 else 0

            # --------- REAJUSTAR NIVEL ---------
            if progreso.porcentaje >= 80:
                nivel_detectado = "intermedio"
            elif progreso.porcentaje >= 50:
                nivel_detectado = "básico"
            else:
                nivel_detectado = "refuerzo"

            progreso.nivel = nivel_detectado

            # --------- IA EXPLICACIÓN (CORRECTA) ---------
            explicacion = generar_explicacion_ia(
                ejercicio,
                respuesta_alumno,
                respuesta_correcta,
                nivel_detectado
            )

            if es_correcta:
                feedback = "¡Muy bien! Tu respuesta es correcta."
                siguiente_paso = "Vamos con uno más difícil."
            else:
                feedback = "Vamos a corregirlo paso a paso."
                siguiente_paso = "Intenta otro ejercicio de refuerzo."

        # --------- GUARDAR HISTORIAL ---------
        historial = HistorialInteraccion(
            alumno_id=alumno_id,
            mensaje_alumno=f"{pregunta} | respuesta_alumno: {respuesta_alumno}",
            respuesta_ia=explicacion,
            tema=tema,
            nivel_detectado=nivel_detectado
        )

        db.add(historial)
        db.commit()

        return {
            "explicacion": explicacion,
            "ejercicio": ejercicio,
            "respuesta_correcta": respuesta_correcta if es_correcta is False else None,
            "es_correcta": es_correcta,
            "feedback": feedback,
            "nivel_detectado": nivel_detectado,
            "tema": tema,
            "porcentaje_progreso": progreso.porcentaje if progreso else 0,
            "siguiente_paso": siguiente_paso,
            "recomendaciones": [
                "Practica con ejemplos pequeños.",
                "Usa dibujos para entender mejor.",
                "Repite ejercicios similares."
            ]
        }

    finally:
        db.close()