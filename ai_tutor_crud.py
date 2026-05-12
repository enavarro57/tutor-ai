from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Reto


router = APIRouter()


class RetoRequest(BaseModel):
    codigo: str
    descripcion: str | None = None


def reto_to_dict(r: Reto):
    return {
        "codigo": r.codigo,
        "descripcion": r.descripcion,
    }


@router.get("/retos")
def listar_retos():
    db: Session = SessionLocal()
    try:
        retos = db.query(Reto).order_by(Reto.codigo.asc()).all()
        return [reto_to_dict(r) for r in retos]
    finally:
        db.close()


@router.post("/retos")
def crear_reto(request: RetoRequest):
    db: Session = SessionLocal()
    try:
        existe = db.query(Reto).filter_by(codigo=request.codigo).first()
        if existe:
            raise HTTPException(
                status_code=400,
                detail="Ya existe un reto con ese código"
            )

        reto = Reto(
            codigo=request.codigo,
            descripcion=request.descripcion,
        )

        db.add(reto)
        db.commit()
        db.refresh(reto)

        return {
            "ok": True,
            "reto": reto_to_dict(reto),
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.put("/retos/{codigo}")
def actualizar_reto(codigo: str, request: RetoRequest):
    db: Session = SessionLocal()
    try:
        reto = db.query(Reto).filter_by(codigo=codigo).first()
        if not reto:
            raise HTTPException(status_code=404, detail="Reto no encontrado")

        reto.codigo = request.codigo
        reto.descripcion = request.descripcion

        db.commit()
        db.refresh(reto)

        return {
            "ok": True,
            "reto": reto_to_dict(reto),
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.delete("/retos/{codigo}")
def eliminar_reto(codigo: str):
    db: Session = SessionLocal()
    try:
        reto = db.query(Reto).filter_by(codigo=codigo).first()
        if not reto:
            raise HTTPException(status_code=404, detail="Reto no encontrado")

        db.delete(reto)
        db.commit()

        return {
            "ok": True,
            "mensaje": "Reto eliminado correctamente",
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()