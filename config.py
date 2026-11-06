import os
from dotenv import load_dotenv

URL= "https://www.python.org/jobs/"
OUTPUT_FILE = "data/jobs.json"



load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AI_MODEL = os.getenv("AI_MODEL", "gemini-2.5-flash")
AI_EMBEDDING_MODEL = os.getenv("AI_EMBEDDING_MODEL", "gemini-embedding-001")


def database_options():
    """Validate when DB access is needed; imports and unit tests stay offline."""
    required = {"DB_HOST": DB_HOST, "DB_NAME": DB_NAME, "DB_USER": DB_USER}
    missing = [name for name, value in required.items() if not value or not value.strip()]
    if missing:
        raise ValueError("Missing database settings: " + ", ".join(missing))
    try:
        port = int(DB_PORT or "5432")
        timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))
    except ValueError:
        raise ValueError("DB_PORT and DB_CONNECT_TIMEOUT must be integers") from None
    if not 1 <= port <= 65535 or not 1 <= timeout <= 60:
        raise ValueError("DB_PORT must be 1..65535; DB_CONNECT_TIMEOUT must be 1..60")
    sslmode = os.getenv("DB_SSLMODE", "prefer")
    if sslmode not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
        raise ValueError("DB_SSLMODE is invalid")
    return dict(host=DB_HOST, port=port, dbname=DB_NAME, user=DB_USER,
                password=DB_PASSWORD, connect_timeout=timeout, sslmode=sslmode,
                options="-c search_path=public")
