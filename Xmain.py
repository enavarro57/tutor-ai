from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"mensaje": "AI Tutor funcionando"}

@app.post("/tutor")
def tutor():
    return {"respuesta": "Tutor funcionando"}