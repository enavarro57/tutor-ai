from fastapi import APIRouter

router = APIRouter()


@router.get("/retos")
def listar_retos():
    return []


@router.post("/retos")
def crear_reto():
    return {"ok": True}
