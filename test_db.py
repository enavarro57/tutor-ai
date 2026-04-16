from sqlalchemy import create_engine, text

DB_USER = "postgres"
DB_PASSWORD = "Ena12345="
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "tutor_db"

DATABASE_URL = (
    f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
    print("Conexion OK:", result.scalar())