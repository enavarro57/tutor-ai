from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
import os
import re
import json

from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
import models
from models import ProgresoTema, HistorialInteraccion, Alumno

from openai import OpenAI

Base.metadata.create_all(bind=engine)

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class TutorRequest(BaseModel):
    alumno_id: str
    pregunta: str
    respuesta_alumno: Optional[str] = None
    edad: Optional[int] = None
    nivel: str
    tema: str
    historial_id: Optional[int] = None
    historial: list = Field(default_factory=list)
    dificultades: list = Field(default_factory=list)
    fecha_nacimiento: Optional[date] = None


class AlumnoResponse(BaseModel):
    codigo: str
    nombre: Optional[str] = None
    edad: Optional[int] = None
    fecha_nacimiento: Optional[date] = None
    email: Optional[str] = None
    puntos_disponibles: int = 0
    puntos_ganados_total: int = 0
    puntos_gastados_total: int = 0

    class Config:
        from_attributes = True


class AlumnoUpdate(BaseModel):
    codigo: str
    nombre: Optional[str] = None
    edad: Optional[int] = None
    fecha_nacimiento: Optional[date] = None
    email: Optional[str] = None
    puntos_disponibles: int = 0
    puntos_ganados_total: int = 0
    puntos_gastados_total: int = 0


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/reset-db")
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return {"status": "database reset"}


def calcular_edad(fecha_nacimiento: date) -> int:
    hoy = date.today()
    return hoy.year - fecha_nacimiento.year - (
        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )


def normalizar_respuesta(texto: str) -> str:
    if not texto:
        return ""

    texto = texto.strip().lower().replace(",", ".").replace(" ", "")

    if "/" in texto:
        try:
            num, den = texto.split("/")
            return str(float(num) / float(den))
        except Exception:
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

Explica paso a paso usando lenguaje claro para niños.
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
        respuesta_alumno = request.respuesta_alumno
        nivel_inicial = request.nivel
        tema = request.tema

        if request.fecha_nacimiento is not None:
            edad_alumno = calcular_edad(request.fecha_nacimiento)
        elif request.edad is not None:
            edad_alumno = request.edad
        else:
            raise HTTPException(
                status_code=400,
                detail="Debes enviar fecha_nacimiento o edad."
            )

        if edad_alumno < 0 or edad_alumno > 120:
            raise HTTPException(
                status_code=400,
                detail="La edad calculada no es válida."
            )

        alumno = db.query(Alumno).filter_by(codigo=alumno_id).first()

        if alumno:
            alumno.edad = edad_alumno
            if request.fecha_nacimiento is not None:
                alumno.fecha_nacimiento = request.fecha_nacimiento
        else:
            alumno = Alumno(
                codigo=alumno_id,
                edad=edad_alumno,
                fecha_nacimiento=request.fecha_nacimiento
            )
            db.add(alumno)
            db.flush()

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

        if not respuesta_alumno:
            ejercicio_data = generar_ejercicio_ia(
                tema,
                nivel_detectado,
                edad_alumno,
                request.dificultades
            )

            ejercicio = ejercicio_data["ejercicio"]
            respuesta_correcta = ejercicio_data["respuesta_correcta"]

            historial = HistorialInteraccion(
                alumno_id=alumno_id,
                mensaje_alumno=request.pregunta,
                respuesta_ia=ejercicio,
                tema=tema,
                nivel_detectado=nivel_detectado,
                ejercicio_generado=ejercicio,
                respuesta_correcta=respuesta_correcta,
                corregido=False
            )

            db.add(historial)
            db.commit()
            db.refresh(historial)

            return {
                "historial_id": historial.id,
                "ejercicio": ejercicio,
                "explicacion": ejercicio,
                "es_correcta": None,
                "respuesta_correcta": None,
                "porcentaje_progreso": progreso.porcentaje if progreso else 0,
                "edad_calculada": edad_alumno
            }

        if not request.historial_id:
            raise HTTPException(status_code=400, detail="Falta historial_id")

        ejercicio_actual = db.query(HistorialInteraccion).filter_by(
            id=request.historial_id,
            alumno_id=alumno_id
        ).first()

        if not ejercicio_actual:
            raise HTTPException(status_code=404, detail="Ejercicio no encontrado")

        if ejercicio_actual.corregido:
            raise HTTPException(status_code=400, detail="Ya corregido")

        respuesta_correcta = ejercicio_actual.respuesta_correcta

        es_correcta = (
            normalizar_respuesta(respuesta_alumno)
            == normalizar_respuesta(respuesta_correcta)
        )

        if progreso:
            progreso.ejercicios_totales += 1
            if es_correcta:
                progreso.ejercicios_correctos += 1
        else:
            progreso = ProgresoTema(
                alumno_id=alumno_id,
                tema=tema,
                ejercicios_totales=1,
                ejercicios_correctos=1 if es_correcta else 0
            )
            db.add(progreso)

        progreso.porcentaje = int(
            (progreso.ejercicios_correctos / progreso.ejercicios_totales) * 100
        )

        explicacion = generar_explicacion_ia(
            ejercicio_actual.ejercicio_generado,
            respuesta_alumno,
            respuesta_correcta,
            nivel_detectado
        )

        ejercicio_actual.respuesta_alumno = respuesta_alumno
        ejercicio_actual.respuesta_ia = explicacion
        ejercicio_actual.corregido = True

        db.commit()

        return {
            "historial_id": ejercicio_actual.id,
            "es_correcta": es_correcta,
            "explicacion": explicacion,
            "respuesta_correcta": None if es_correcta else respuesta_correcta,
            "porcentaje_progreso": progreso.porcentaje,
            "edad_calculada": edad_alumno
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/alumnos", response_model=List[AlumnoResponse])
def listar_alumnos():
    db: Session = SessionLocal()
    try:
        alumnos = db.query(Alumno).order_by(Alumno.codigo.asc()).all()
        return alumnos
    finally:
        db.close()


@app.get("/alumnos/{codigo}", response_model=AlumnoResponse)
def obtener_alumno(codigo: str):
    db: Session = SessionLocal()
    try:
        alumno = db.query(Alumno).filter_by(codigo=codigo).first()

        if not alumno:
            raise HTTPException(status_code=404, detail="Alumno no encontrado")

        return alumno
    finally:
        db.close()


@app.post("/alumnos", response_model=AlumnoResponse)
def crear_alumno(request: AlumnoUpdate):
    db: Session = SessionLocal()
    try:
        existente = db.query(Alumno).filter_by(codigo=request.codigo).first()
        if existente:
            raise HTTPException(
                status_code=400,
                detail="Ya existe un alumno con ese código"
            )

        edad_final = request.edad
        if request.fecha_nacimiento is not None:
            edad_final = calcular_edad(request.fecha_nacimiento)

        alumno = Alumno(
            codigo=request.codigo,
            nombre=request.nombre,
            edad=edad_final,
            fecha_nacimiento=request.fecha_nacimiento,
            email=request.email,
            puntos_disponibles=request.puntos_disponibles,
            puntos_ganados_total=request.puntos_ganados_total,
            puntos_gastados_total=request.puntos_gastados_total,
        )

        db.add(alumno)
        db.commit()
        db.refresh(alumno)

        return alumno

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.put("/alumnos/{codigo}", response_model=AlumnoResponse)
def actualizar_alumno(codigo: str, request: AlumnoUpdate):
    db: Session = SessionLocal()
    try:
        alumno = db.query(Alumno).filter_by(codigo=codigo).first()

        if not alumno:
            raise HTTPException(status_code=404, detail="Alumno no encontrado")

        if request.codigo != codigo:
            raise HTTPException(
                status_code=400,
                detail="El código del alumno en la URL y en el body no coincide"
            )

        edad_final = request.edad
        if request.fecha_nacimiento is not None:
            edad_final = calcular_edad(request.fecha_nacimiento)

        alumno.nombre = request.nombre
        alumno.edad = edad_final
        alumno.fecha_nacimiento = request.fecha_nacimiento
        alumno.email = request.email
        alumno.puntos_disponibles = request.puntos_disponibles
        alumno.puntos_ganados_total = request.puntos_ganados_total
        alumno.puntos_gastados_total = request.puntos_gastados_total

        db.commit()
        db.refresh(alumno)

        return alumno

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
