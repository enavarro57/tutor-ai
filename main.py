from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
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
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    nivel_actual: Optional[str] = None
    edad: Optional[int] = None
    fecha_nacimiento: Optional[date] = None
    tfno_whats: Optional[str] = None
    email: Optional[str] = None
    nombre_tutor: Optional[str] = None
    tfno_whats_tutor: Optional[str] = None
    email_tutor: Optional[str] = None
    fecha_alta: Optional[date] = None
    datos_bancarios_cargo: Optional[str] = None
    contrasena: Optional[str] = None
    comentarios: Optional[str] = None
    puntos_disponibles: int = 0
    puntos_ganados_total: int = 0
    puntos_gastados_total: int = 0


def calcular_edad(fecha_nacimiento: date) -> int:
    hoy = date.today()
    return hoy.year - fecha_nacimiento.year - (
        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )


def generar_codigo_alumno(db: Session) -> str:
    codigos_existentes = {
        str(c[0])
        for c in db.query(Alumno.codigo).all()
        if c[0] and re.fullmatch(r"\d{6}", str(c[0]))
    }

    for numero in range(100000, 1000000):
        codigo = str(numero)
        if codigo not in codigos_existentes:
            return codigo

    raise HTTPException(
        status_code=400,
        detail="No hay códigos disponibles de 6 dígitos."
    )


def alumno_to_dict(a: Alumno):
    return {
        "codigo": a.codigo,
        "nombre": a.nombre,
        "nivel_actual": a.nivel_actual,
        "edad": a.edad,
        "fecha_nacimiento": str(a.fecha_nacimiento) if a.fecha_nacimiento else None,
        "tfno_whats": a.tfno_whats,
        "email": a.email,
        "nombre_tutor": a.nombre_tutor,
        "tfno_whats_tutor": a.tfno_whats_tutor,
        "email_tutor": a.email_tutor,
        "fecha_alta": str(a.fecha_alta) if a.fecha_alta else None,
        "datos_bancarios_cargo": a.datos_bancarios_cargo,
        "contrasena": a.contrasena,
        "comentarios": a.comentarios,
        "puntos_disponibles": a.puntos_disponibles or 0,
        "puntos_ganados_total": a.puntos_ganados_total or 0,
        "puntos_gastados_total": a.puntos_gastados_total or 0,
    }


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


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/tutor")
def tutor(request: TutorRequest):
    db: Session = SessionLocal()

    try:
        alumno_id = request.alumno_id

        if request.fecha_nacimiento:
            edad = calcular_edad(request.fecha_nacimiento)
        elif request.edad:
            edad = request.edad
        else:
            raise HTTPException(400, "Falta edad")

        alumno = db.query(Alumno).filter_by(codigo=alumno_id).first()

        if not alumno:
            alumno = Alumno(
                codigo=alumno_id,
                edad=edad,
                fecha_nacimiento=request.fecha_nacimiento
            )
            db.add(alumno)
            db.flush()

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

        hist = db.query(HistorialInteraccion).filter_by(
            id=request.historial_id
        ).first()

        correcta = normalizar_respuesta(request.respuesta_alumno) == normalizar_respuesta(hist.respuesta_correcta)

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


@app.get("/alumnos")
def listar_alumnos():
    db: Session = SessionLocal()
    try:
        alumnos = db.query(Alumno).order_by(Alumno.codigo.asc()).all()
        return [alumno_to_dict(a) for a in alumnos]
    finally:
        db.close()


@app.get("/alumnos/{codigo}")
def obtener_alumno(codigo: str):
    db: Session = SessionLocal()
    try:
        alumno = db.query(Alumno).filter_by(codigo=codigo).first()

        if not alumno:
            raise HTTPException(status_code=404, detail="Alumno no encontrado")

        return alumno_to_dict(alumno)
    finally:
        db.close()


@app.post("/alumnos")
def crear_alumno(request: AlumnoUpdate):
    db: Session = SessionLocal()
    try:
        nuevo_codigo = generar_codigo_alumno(db)

        edad = request.edad
        if request.fecha_nacimiento:
            edad = calcular_edad(request.fecha_nacimiento)

        alumno = Alumno(
            codigo=nuevo_codigo,
            nombre=request.nombre,
            nivel_actual=request.nivel_actual,
            edad=edad,
            fecha_nacimiento=request.fecha_nacimiento,
            tfno_whats=request.tfno_whats,
            email=request.email,
            nombre_tutor=request.nombre_tutor,
            tfno_whats_tutor=request.tfno_whats_tutor,
            email_tutor=request.email_tutor,
            fecha_alta=request.fecha_alta or date.today(),
            datos_bancarios_cargo=request.datos_bancarios_cargo,
            contrasena=request.contrasena,
            comentarios=request.comentarios,
            puntos_disponibles=0,
            puntos_ganados_total=0,
            puntos_gastados_total=0,
        )

        db.add(alumno)
        db.commit()
        db.refresh(alumno)

        return {
            "ok": True,
            "codigo": alumno.codigo,
            "alumno": alumno_to_dict(alumno)
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.put("/alumnos/{codigo}")
def actualizar_alumno(codigo: str, request: AlumnoUpdate):
    db: Session = SessionLocal()
    try:
        alumno = db.query(Alumno).filter_by(codigo=codigo).first()

        if not alumno:
            raise HTTPException(status_code=404, detail="Alumno no encontrado")

        edad = request.edad
        if request.fecha_nacimiento:
            edad = calcular_edad(request.fecha_nacimiento)

        alumno.nombre = request.nombre
        alumno.nivel_actual = request.nivel_actual
        alumno.edad = edad
        alumno.fecha_nacimiento = request.fecha_nacimiento
        alumno.tfno_whats = request.tfno_whats
        alumno.email = request.email
        alumno.nombre_tutor = request.nombre_tutor
        alumno.tfno_whats_tutor = request.tfno_whats_tutor
        alumno.email_tutor = request.email_tutor
        alumno.fecha_alta = request.fecha_alta
        alumno.datos_bancarios_cargo = request.datos_bancarios_cargo
        alumno.contrasena = request.contrasena
        alumno.comentarios = request.comentarios
        alumno.puntos_disponibles = request.puntos_disponibles
        alumno.puntos_ganados_total = request.puntos_ganados_total
        alumno.puntos_gastados_total = request.puntos_gastados_total

        db.commit()
        db.refresh(alumno)

        return {
            "ok": True,
            "alumno": alumno_to_dict(alumno)
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.delete("/alumnos/{codigo}")
def eliminar_alumno(codigo: str):
    db: Session = SessionLocal()
    try:
        alumno = db.query(Alumno).filter_by(codigo=codigo).first()

        if not alumno:
            raise HTTPException(status_code=404, detail="Alumno no encontrado")

        db.delete(alumno)
        db.commit()

        return {
            "ok": True,
            "mensaje": "Alumno eliminado correctamente"
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()