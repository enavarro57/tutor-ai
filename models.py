from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Boolean, Date
from sqlalchemy.sql import func
from database import Base


class HistorialInteraccion(Base):
    __tablename__ = "historial_interacciones"

    id = Column(Integer, primary_key=True, index=True)
    alumno_id = Column(String(100), nullable=False)
    mensaje_alumno = Column(Text, nullable=False)
    respuesta_ia = Column(Text, nullable=False)
    tema = Column(String(255))
    nivel_detectado = Column(String(100))
    ejercicio_generado = Column(Text)
    respuesta_correcta = Column(String(255))
    respuesta_alumno = Column(String(255))
    corregido = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())


class ProgresoTema(Base):
    __tablename__ = "progreso_tema"

    id = Column(Integer, primary_key=True, index=True)
    alumno_id = Column(String(100), nullable=False)
    tema = Column(String(255), nullable=False)
    nivel = Column(String(100))
    porcentaje = Column(Integer, default=0)
    ejercicios_correctos = Column(Integer, default=0)
    ejercicios_totales = Column(Integer, default=0)
    updated_at = Column(TIMESTAMP, server_default=func.now())


class Alumno(Base):
    __tablename__ = "alumnos"

    id = Column(Integer, primary_key=True, index=True)

    # 🔥 CORREGIDO: ahora coincide con la BD
    codigo = Column(String(100), unique=True, nullable=False)

    nombre = Column(String(255))
    nivel_actual = Column(String(100))
    edad = Column(Integer)
    tfno_whats = Column(String(20))
    email = Column(String(150))
    nombre_tutor = Column(String(255))
    tfno_whats_tutor = Column(String(20))
    email_tutor = Column(String(150))
    fecha_alta = Column(Date)
    datos_bancarios_cargo = Column(Text)

    # 🔥 CORREGIDO: nombres reales de la BD
    puntos_disponibles = Column(Integer, default=0)
    puntos_ganados_total = Column(Integer, default=0)
    puntos_gastados_total = Column(Integer, default=0)

    fecha_nacimiento = Column(Date, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Subgrupo(Base):
    __tablename__ = "subgrupos"

    id = Column(Integer, primary_key=True, index=True)
    grupo = Column(String(100))
    subgrupo = Column(String(100))
    descripcion = Column(String(255))


class ProgresoAlumnoSubgrupo(Base):
    __tablename__ = "progreso_alumno_subgrupo"

    id = Column(Integer, primary_key=True, index=True)
    alumno_id = Column(String(100), nullable=False)
    grupo = Column(String(100))
    subgrupo = Column(String(100))
    nivel_actual = Column(String(50))
    puntos_acumulados = Column(Integer, default=0)
    aciertos = Column(Integer, default=0)
    errores = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())


class SesionPractica(Base):
    __tablename__ = "sesiones_practica"

    id = Column(Integer, primary_key=True, index=True)
    alumno_id = Column(String(100))
    grupo = Column(String(100))
    subgrupo = Column(String(100))
    nivel_inicial = Column(String(50))
    nivel_actual = Column(String(50))
    created_at = Column(TIMESTAMP, server_default=func.now())


class EjercicioSesion(Base):
    __tablename__ = "ejercicios_sesion"

    id = Column(Integer, primary_key=True, index=True)
    sesion_id = Column(Integer)
    alumno_id = Column(String(100))

    grupo = Column(String(100))
    subgrupo = Column(String(100))
    nivel = Column(String(50))

    descripcion_ejercicio = Column(Text)
    respuesta_correcta = Column(Text)
    respuesta_alumno = Column(Text)

    es_correcta = Column(Boolean, nullable=True)
    feedback = Column(Text)

    puntos_obtenidos = Column(Integer, default=0)
    corregido = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())