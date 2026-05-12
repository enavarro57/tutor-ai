from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Reto, Grupo


router = APIRouter()


class RetoRequest(BaseModel):
    codigo: str
    descripcion: str | None = None


class GrupoRequest(BaseModel):
    codigo: str
    descripcion: str | None = None
    reto_codigo: str


def reto_to_dict(r: Reto):
    return {
        "codigo": r.codigo,
        "descripcion": r.descripcion,
    }


def grupo_to_dict(g: Grupo):
    return {
        "codigo": g.codigo,
        "descripcion": g.descripcion,
        "reto_codigo": g.reto_codigo,
        "reto_descripcion": g.reto_descripcion,
    }


# =========================
# RETOS
# =========================

@router.get("/retos")
def listar_retos():
    db: Session = SessionLocal()
    try:
        retos = db.query(Reto).order_by(Reto.codigo.asc()).all()
        return [reto_to_dict(r) for r in retos]
    finally:
        db.close()


@router.get("/retos/{codigo}")
def obtener_reto(codigo: str):
    db: Session = SessionLocal()
    try:
        reto = db.query(Reto).filter_by(codigo=codigo).first()
        if not reto:
            raise HTTPException(status_code=404, detail="Reto no encontrado")
        return reto_to_dict(reto)
    finally:
        db.close()


@router.post("/retos")
def crear_reto(request: RetoRequest):
    db: Session = SessionLocal()
    try:
        existe = db.query(Reto).filter_by(codigo=request.codigo).first()
        if existe:
            raise HTTPException(status_code=400, detail="Ya existe un reto con ese código")

        reto = Reto(codigo=request.codigo, descripcion=request.descripcion)

        db.add(reto)
        db.commit()
        db.refresh(reto)

        return {"ok": True, "reto": reto_to_dict(reto)}

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

        return {"ok": True, "reto": reto_to_dict(reto)}

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

        return {"ok": True, "mensaje": "Reto eliminado correctamente"}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# =========================
# GRUPOS
# =========================

@router.get("/grupos")
def listar_grupos():
    db: Session = SessionLocal()
    try:
        grupos = db.query(Grupo).order_by(Grupo.codigo.asc()).all()
        return [grupo_to_dict(g) for g in grupos]
    finally:
        db.close()


@router.get("/grupos/{codigo}")
def obtener_grupo(codigo: str):
    db: Session = SessionLocal()
    try:
        grupo = db.query(Grupo).filter_by(codigo=codigo).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")
        return grupo_to_dict(grupo)
    finally:
        db.close()


@router.post("/grupos")
def crear_grupo(request: GrupoRequest):
    db: Session = SessionLocal()
    try:
        existe = db.query(Grupo).filter_by(codigo=request.codigo).first()
        if existe:
            raise HTTPException(status_code=400, detail="Ya existe un grupo con ese código")

        reto = db.query(Reto).filter_by(codigo=request.reto_codigo).first()
        if not reto:
            raise HTTPException(status_code=400, detail="El reto indicado no existe")

        grupo = Grupo(
            codigo=request.codigo,
            descripcion=request.descripcion,
            reto_codigo=reto.codigo,
            reto_descripcion=reto.descripcion,
        )

        db.add(grupo)
        db.commit()
        db.refresh(grupo)

        return {"ok": True, "grupo": grupo_to_dict(grupo)}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.put("/grupos/{codigo}")
def actualizar_grupo(codigo: str, request: GrupoRequest):
    db: Session = SessionLocal()
    try:
        grupo = db.query(Grupo).filter_by(codigo=codigo).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")

        reto = db.query(Reto).filter_by(codigo=request.reto_codigo).first()
        if not reto:
            raise HTTPException(status_code=400, detail="El reto indicado no existe")

        grupo.codigo = request.codigo
        grupo.descripcion = request.descripcion
        grupo.reto_codigo = reto.codigo
        grupo.reto_descripcion = reto.descripcion

        db.commit()
        db.refresh(grupo)

        return {"ok": True, "grupo": grupo_to_dict(grupo)}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.delete("/grupos/{codigo}")
def eliminar_grupo(codigo: str):
    db: Session = SessionLocal()
    try:
        grupo = db.query(Grupo).filter_by(codigo=codigo).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")

        db.delete(grupo)
        db.commit()

        return {"ok": True, "mensaje": "Grupo eliminado correctamente"}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()