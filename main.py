from ai_tutor_crud import router as crud_router
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date
from fractions import Fraction
import os
import re
import json

from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
from models import ProgresoTema, HistorialInteraccion, Alumno

from openai import OpenAI

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(crud_router)
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
    wp_user_id: Optional[int] = None
    nombre: Optional[str] = None
    apellidos: Optional[str] = None
    estado: Optional[str] = None
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
        "wp_user_id": getattr(a, "wp_user_id", None),
        "nombre": a.nombre,
        "apellidos": getattr(a, "apellidos", None),
        "estado": getattr(a, "estado", None),
        "edad": getattr(a, "edad", None),
        "fecha_nacimiento": str(a.fecha_nacimiento) if a.fecha_nacimiento else None,
        "tfno_whats": getattr(a, "tfno_whats", None),
        "email": a.email,
        "nombre_tutor": getattr(a, "nombre_tutor", None),
        "tfno_whats_tutor": getattr(a, "tfno_whats_tutor", None),
        "email_tutor": getattr(a, "email_tutor", None),
        "fecha_alta": str(a.fecha_alta) if getattr(a, "fecha_alta", None) else None,
        "datos_bancarios_cargo": getattr(a, "datos_bancarios_cargo", None),
        "contrasena": getattr(a, "contrasena", None),
        "comentarios": getattr(a, "comentarios", None),
        "puntos_disponibles": a.puntos_disponibles or 0,
        "puntos_ganados_total": a.puntos_ganados_total or 0,
        "puntos_gastados_total": a.puntos_gastados_total or 0,
    }


def normalizar_respuesta(texto: str):
    if not texto:
        return None

    texto = texto.strip().lower().replace(",", ".")

    fraccion = re.search(r"(\d+)\s*/\s*(\d+)", texto)
    if fraccion:
        try:
            return float(Fraction(int(fraccion.group(1)), int(fraccion.group(2))))
        except Exception:
            return texto

    numero = re.search(r"\d+(\.\d+)?", texto)
    if numero:
        try:
            return float(numero.group())
        except Exception:
            return texto

    return texto.replace(" ", "")


def comparar_respuestas(respuesta_alumno: str, respuesta_correcta: str) -> bool:
    r1 = normalizar_respuesta(respuesta_alumno)
    r2 = normalizar_respuesta(respuesta_correcta)

    if isinstance(r1, float) and isinstance(r2, float):
        return abs(r1 - r2) < 0.0001

    return r1 == r2


def generar_ejercicio_ia(tema, nivel, edad, dificultades):
    prompt = f"""
Eres un profesor de matemáticas para niños.

Genera un ejercicio de {tema} para un alumno de {edad} años.

Nivel: {nivel}

Dificultades del alumno:
{dificultades}

IMPORTANTE:
- Devuelve SOLO JSON válido
- Incluye:
  - ejercicio
  - respuesta_correcta
- respuesta_correcta debe ser SOLO el resultado final, sin explicación
- Si es fracción, usa formato como "3/8"
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
Nivel: {nivel}
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
            raise HTTPException(status_code=400, detail="Falta edad")

        alumno = db.query(Alumno).filter_by(codigo=alumno_id).first()

        if not alumno:
            alumno = Alumno(
                codigo=alumno_id,
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

        if not request.historial_id:
            raise HTTPException(status_code=400, detail="Falta historial_id")

        hist = db.query(HistorialInteraccion).filter_by(
            id=request.historial_id,
            alumno_id=alumno_id
        ).first()

        if not hist:
            raise HTTPException(status_code=404, detail="Historial no encontrado")

        correcta = comparar_respuestas(
            request.respuesta_alumno,
            hist.respuesta_correcta
        )

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
            "explicacion": explicacion,
            "respuesta_correcta": None if correcta else hist.respuesta_correcta
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
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


@app.get("/alumnos/by-wp-user/{wp_user_id}")
def obtener_alumno_por_wp_user(wp_user_id: int):
    db: Session = SessionLocal()
    try:
        alumno = db.query(Alumno).filter_by(wp_user_id=wp_user_id).first()

        if not alumno:
            raise HTTPException(status_code=404, detail="Alumno no encontrado")

        return alumno_to_dict(alumno)

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

        alumno = Alumno(
            codigo=nuevo_codigo,
            wp_user_id=request.wp_user_id,
            nombre=request.nombre,
            apellidos=request.apellidos,
            estado=request.estado,
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

        alumno.wp_user_id = request.wp_user_id
        alumno.nombre = request.nombre
        alumno.apellidos = request.apellidos
        alumno.estado = request.estado
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