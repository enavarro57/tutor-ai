from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Boolean
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