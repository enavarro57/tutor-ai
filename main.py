from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import os
import re
import json

from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
import models
from models import ProgresoTema, HistorialInteraccion

from openai import OpenAI

Base.metadata.create_all(bind=engine)

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class TutorRequest(BaseModel):
    alumno_id: str
    pregunta: str
    respuesta_alumno: str | None = None
    edad: int
    nivel: str
    tema: str
    historial_id: int | None = None  # 👈 ESTA LÍNEA ES LA CLAVE
    historial: list = Field(default_factory=list)
    dificultades: list = Field(default_factory=list)


@app.get("/")
@app.get("/reset-db")
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return {"status": "database reset"}
def root():
    return {"status": "ok"}


def normalizar_respuesta(texto: str) -> str:
    if not texto:
        return ""

    texto = texto.strip().lower().replace(",", ".").replace(" ", "")

    # Si es fracción tipo 3/8
    if "/" in texto:
        try:
            num, den = texto.split("/")
            return str(float(num) / float(den))
        except:
            return texto

    return texto


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

    texto = response.choices[0].message.content or ""

    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if match:
        return json.loads(match.group())
    else:
        return {
            "ejercicio": "¿Cuánto es 10 ÷ 2?",
            "respuesta_correcta": "5"
        }


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


@app.post("/tutor")
def tutor(request: TutorRequest):
    db: Session = SessionLocal()

    try:
        alumno_id = request.alumno_id
        pregunta = request.pregunta
        respuesta_alumno = request.respuesta_alumno
        nivel_inicial = request.nivel
        tema = request.tema

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

        es_correcta = None
        feedback = ""
        explicacion = ""
        siguiente_paso = ""
        ejercicio = ""
        respuesta_correcta = None

        # CASO 1: GENERAR NUEVO EJERCICIO
        if not respuesta_alumno:
            ejercicio_data = generar_ejercicio_ia(
                tema,
                nivel_detectado,
                request.edad,
                request.dificultades
            )

            ejercicio = ejercicio_data["ejercicio"]
            respuesta_correcta = ejercicio_data["respuesta_correcta"]

            explicacion = (
                f"Vamos a trabajar el tema '{tema}' en nivel '{nivel_detectado}'. "
                f"Resuelve este ejercicio: {ejercicio}"
            )
            siguiente_paso = "Envía tu respuesta en 'respuesta_alumno'."

            historial = HistorialInteraccion(
                alumno_id=alumno_id,
                mensaje_alumno=pregunta,
                respuesta_ia=explicacion,
                tema=tema,
                nivel_detectado=nivel_detectado,
                ejercicio_generado=ejercicio,
                respuesta_correcta=respuesta_correcta,
                respuesta_alumno=None,
                corregido=False
            )

            db.add(historial)
            db.commit()
            db.refresh(historial)

            return {
                "historial_id": historial.id,
                "explicacion": explicacion,
                "ejercicio": ejercicio,
                "respuesta_correcta": None,
                "es_correcta": None,
                "feedback": "",
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

        # CASO 2: CORREGIR POR historial_id
        if not request.historial_id:
            raise HTTPException(
                status_code=400,
                detail="Falta historial_id para corregir el ejercicio."
            )

        ejercicio_actual = (
            db.query(HistorialInteraccion)
            .filter_by(
                id=request.historial_id,
                alumno_id=alumno_id
            )
            .first()
        )

        if not ejercicio_actual:
            raise HTTPException(
                status_code=404,
                detail="No se encontró el ejercicio asociado a ese historial_id."
            )

        if ejercicio_actual.corregido:
            raise HTTPException(
                status_code=400,
                detail="Este ejercicio ya fue corregido."
            )

        ejercicio = ejercicio_actual.ejercicio_generado
        respuesta_correcta = ejercicio_actual.respuesta_correcta

        respuesta_normalizada = normalizar_respuesta(respuesta_alumno)
        correcta_normalizada = normalizar_respuesta(respuesta_correcta)

        es_correcta = respuesta_normalizada == correcta_normalizada

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

        if progreso.porcentaje >= 80:
            nivel_detectado = "intermedio"
        elif progreso.porcentaje >= 50:
            nivel_detectado = "básico"
        else:
            nivel_detectado = "refuerzo"

        progreso.nivel = nivel_detectado

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

        ejercicio_actual.respuesta_alumno = respuesta_alumno
        ejercicio_actual.respuesta_ia = explicacion
        ejercicio_actual.nivel_detectado = nivel_detectado
        ejercicio_actual.corregido = True

        db.commit()
        db.refresh(ejercicio_actual)

        return {
            "historial_id": ejercicio_actual.id,
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

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()