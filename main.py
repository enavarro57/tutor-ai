from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
import os
import re
import json

from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
from models import ProgresoTema, HistorialInteraccion, Alumno

from openai import OpenAI

Base.metadata.create_all(bind=engine)

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# SCHEMAS
# =========================

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


class AlumnoUpdate(BaseModel):
    codigo: str
    nombre: Optional[str] = None
    edad: Optional[int] = None
    fecha_nacimiento: Optional[date] = None
    email: Optional[str] = None
    puntos_disponibles: int = 0
    puntos_ganados_total: int = 0
    puntos_gastados_total: int = 0


# =========================
# UTILIDADES
# =========================

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


# =========================
# IA
# =========================

def generar_ejercicio_ia(tema, nivel, edad, dificultades):
    prompt = f"""
Eres un profesor de matemáticas para niños.

Genera un ejercicio de {tema} para un alumno de {edad} años.

Nivel: {nivel}

Dificultades del alumno:
{dificultades}

Devuelve SOLO JSON con:
- ejercicio
- respuesta_correcta
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
Eres un profesor para niños.

Explica paso a paso:

Ejercicio: {ejercicio}
Respuesta alumno: {respuesta_alumno}
Correcta: {respuesta_correcta}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Tutor experto."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    return response.choices[0].message.content


# =========================
# ROOT
# =========================

@app.get("/")
def root():
    return {"status": "ok"}


# =========================
# TUTOR
# =========================

@app.post("/tutor")
def tutor(request: TutorRequest):
    db: Session = SessionLocal()

    try:
        alumno_id = request.alumno_id

        # Edad
        if request.fecha_nacimiento:
            edad = calcular_edad(request.fecha_nacimiento)
        elif request.edad:
            edad = request.edad
        else:
            raise HTTPException(400, "Falta edad")

        # Alumno
        alumno = db.query(Alumno).filter_by(codigo=alumno_id).first()

        if not alumno:
            alumno = Alumno(
                codigo=alumno_id,
                edad=edad,
                fecha_nacimiento=request.fecha_nacimiento
            )
            db.add(alumno)
            db.flush()

        # Generar ejercicio
        if not request.respuesta_alumno:
            data = generar_ejercicio_ia(
                request.tema,
                request.nivel,
                edad,
                request.dificultades
            )

            historial = HistorialInteraccion(
                alumno_id=alumno_id,
                mensaje_alumno=request.pregunta,
                respuesta_ia=data["ejercicio"],
                ejercicio_generado=data["ejercicio"],
                respuesta_correcta=data["respuesta_correcta"]
            )

            db.add(historial)
            db.commit()
            db.refresh(historial)

            return {
                "historial_id": historial.id,
                "ejercicio": data["ejercicio"],
                "es_correcta": None
            }

        # Corregir
        hist = db.query(HistorialInteraccion).filter_by(
            id=request.historial_id
        ).first()

        correcta = normalizar_respuesta(request.respuesta_alumno) == \
                   normalizar_respuesta(hist.respuesta_correcta)

        explicacion = generar_explicacion_ia(
            hist.ejercicio_generado,
            request.respuesta_alumno,
            hist.respuesta_correcta,
            request.nivel
        )

        hist.corregido = True
        hist.respuesta_alumno = request.respuesta_alumno
        hist.respuesta_ia = explicacion

        db.commit()

        return {
            "es_correcta": correcta,
            "explicacion": explicacion
        }

    finally:
        db.close()


# =========================
# ALUMNOS (CLAVE)
# =========================

@app.get("/alumnos")
def listar_alumnos():
    db: Session = SessionLocal()
    try:
        alumnos = db.query(Alumno).order_by(Alumno.codigo.asc()).all()

        return [
            {
                "codigo": a.codigo,
                "nombre": a.nombre,
                "edad": a.edad,
                "fecha_nacimiento": str(a.fecha_nacimiento) if a.fecha_nacimiento else None,
                "email": a.email,
                "puntos_disponibles": a.puntos_disponibles or 0,
                "puntos_ganados_total": a.puntos_ganados_total or 0,
                "puntos_gastados_total": a.puntos_gastados_total or 0,
            }
            for a in alumnos
        ]
    finally:
        db.close()


@app.get("/alumnos/{codigo}")
def obtener_alumno(codigo: str):
    db: Session = SessionLocal()
    try:
        a = db.query(Alumno).filter_by(codigo=codigo).first()

        if not a:
            raise HTTPException(404, "No encontrado")

        return {
            "codigo": a.codigo,
            "nombre": a.nombre,
            "edad": a.edad,
            "fecha_nacimiento": str(a.fecha_nacimiento) if a.fecha_nacimiento else None,
            "email": a.email,
            "puntos_disponibles": a.puntos_disponibles or 0,
            "puntos_ganados_total": a.puntos_ganados_total or 0,
            "puntos_gastados_total": a.puntos_gastados_total or 0,
        }
    finally:
        db.close()


@app.post("/alumnos")
def crear_alumno(request: AlumnoUpdate):
    db: Session = SessionLocal()
    try:
        if db.query(Alumno).filter_by(codigo=request.codigo).first():
            raise HTTPException(400, "Ya existe")

        edad = request.edad
        if request.fecha_nacimiento:
            edad = calcular_edad(request.fecha_nacimiento)

        alumno = Alumno(
            codigo=request.codigo,
            nombre=request.nombre,
            edad=edad,
            fecha_nacimiento=request.fecha_nacimiento,
            email=request.email,
            puntos_disponibles=request.puntos_disponibles,
            puntos_ganados_total=request.puntos_ganados_total,
            puntos_gastados_total=request.puntos_gastados_total,
        )

        db.add(alumno)
        db.commit()
        db.refresh(alumno)

        return {"ok": True}

    finally:
        db.close()


@app.put("/alumnos/{codigo}")
def actualizar_alumno(codigo: str, request: AlumnoUpdate):
    db: Session = SessionLocal()
    try:
        alumno = db.query(Alumno).filter_by(codigo=codigo).first()

        if not alumno:
            raise HTTPException(404, "No existe")

        alumno.nombre = request.nombre
        alumno.edad = request.edad
        alumno.fecha_nacimiento = request.fecha_nacimiento
        alumno.email = request.email
        alumno.puntos_disponibles = request.puntos_disponibles
        alumno.puntos_ganados_total = request.puntos_ganados_total
        alumno.puntos_gastados_total = request.puntos_gastados_total

        db.commit()

        return {"ok": True}

    finally:
        db.close()