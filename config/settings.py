import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    # --- Configurações de Autenticação ---
    # Pegamos do .env para segurança
    API_EMAIL = os.getenv("API_EMAIL")
    API_PASS = os.getenv("API_PASS")
    
    # Endpoints
    BASE_URL = os.getenv("BASE_URL")

    if not BASE_URL:
        raise ValueError("ERROR CRÍTICO: BASE_URL não encontrada no ambiente")
    
    LOGIN_URL = f"{BASE_URL}/api/conta/login"
    VENDAS_URL = f"{BASE_URL}/api/import/vendas"

    # --- IDs e Campos Fixos ---
    DISTRIBUIDOR_ID = os.getenv("DISTRIBUIDOR_ID")
    REPRESENTANTE_ID = os.getenv("REPRESENTANTE_ID")
    FIELD_ARQUIVO = "arquivo"
    FIELD_DISTRIBUIDOR = "distribuidorId"
    FIELD_REPRESENTANTE = "representanteId"

    # --- Caminhos ---
    IMPORTS_DIR = BASE_DIR / "imports"
    OUTPUT_DIR = BASE_DIR / "output"
    NETWORK_TIMEOUT = 60

    # --- Configurações do Banco de Dados (Views) ---
    DB_DRIVER = os.getenv("DB_DRIVER", "")
    DB_HOST = os.getenv("DB_HOST", "")
    DB_PORT = os.getenv("DB_PORT", "1433")
    DB_NAME = os.getenv("DB_NAME", "")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASS = os.getenv("DB_PASS", "")

    # --- Nomes das Views ---
    VIEW_VENDAS = os.getenv("VIEW_VENDAS", "")
    VIEW_ESTOQUE = os.getenv("VIEW_ESTOQUE", "")
    VIEW_METAS = os.getenv("VIEW_METAS", "")
    VIEW_VENDEDORES = os.getenv("VIEW_VENDEDORES", "")

    # --- Configurações de Armazenamento ---
    MAX_FILES_RETAINED = 3

    @classmethod
    def create_dirs(cls):
        cls.IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

Settings.create_dirs()
