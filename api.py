"""API de leitura dos arquivos de importação atuais."""

import os
import secrets
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Security
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.background import BackgroundTask


BASE_DIR = Path(__file__).resolve().parent
IMPORTS_DIR = BASE_DIR / "imports"
load_dotenv(BASE_DIR / ".env")

bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(
    title="NOVA Automação - Imports",
    description="Disponibiliza as quatro extrações atuais do SQL Server.",
    version="1.0.0",
)

TABELAS_EXPORTADAS = {
    "VENDA": "VW_MULTFOCO_VENDAS.csv",
    "ESTOQUE": "VW_MULTIFOCO_ESTOQUE.csv",
    "METAS": "VW_MULTIFOCO_METAS.csv",
    "VENDEDORES": "VW_MULTIFOCO_VENDEDORES.csv",
}


def validar_token_bearer(
    credenciais: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> None:
    """Valida o token Bearer estático configurado no ambiente."""
    token_esperado = os.getenv("IMPORTS_API_TOKEN", "").strip()

    if not token_esperado:
        raise HTTPException(
            status_code=503,
            detail="Token de acesso da API não configurado.",
        )

    if (
        credenciais is None
        or credenciais.scheme.lower() != "bearer"
        or not secrets.compare_digest(credenciais.credentials, token_esperado)
    ):
        raise HTTPException(
            status_code=401,
            detail="Token Bearer ausente ou inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _arquivo_atual(prefixo: str) -> Path | None:
    """Retorna a extração SQL bruta mais recente para o prefixo informado."""
    arquivos = [
        arquivo
        for arquivo in IMPORTS_DIR.glob(f"{prefixo}_*.csv")
        if arquivo.is_file() and not arquivo.name.startswith(f"{prefixo}_ATUAL_")
    ]
    return max(arquivos, key=lambda arquivo: arquivo.stat().st_mtime, default=None)


def criar_zip_imports_atuais() -> tuple[Path, list[Path]]:
    """Monta um ZIP temporário com as quatro extrações SQL mais recentes."""
    encontrados = {
        prefixo: _arquivo_atual(prefixo)
        for prefixo in TABELAS_EXPORTADAS
    }
    ausentes = [prefixo for prefixo, arquivo in encontrados.items() if arquivo is None]

    if ausentes:
        raise HTTPException(
            status_code=404,
            detail=f"Não foram encontradas as extrações atuais: {', '.join(ausentes)}.",
        )

    with NamedTemporaryFile(prefix="tabelas_multfoco_", suffix=".zip", delete=False) as temporario:
        caminho_zip = Path(temporario.name)

    with ZipFile(caminho_zip, mode="w", compression=ZIP_DEFLATED) as arquivo_zip:
        for prefixo, arquivo in encontrados.items():
            arquivo_zip.write(arquivo, arcname=TABELAS_EXPORTADAS[prefixo])

    return caminho_zip, list(encontrados.values())


@app.get("/imports/atuais", summary="Baixar os imports atuais")
def baixar_imports_atuais(
    _: None = Security(validar_token_bearer),
) -> FileResponse:
    """Baixa as quatro views SQL em um único arquivo ZIP."""
    caminho_zip, _ = criar_zip_imports_atuais()
    nome_download = f"tabelas_multfoco_{datetime.now():%Y%m%d_%H%M%S}.zip"

    return FileResponse(
        path=caminho_zip,
        media_type="application/zip",
        filename=nome_download,
        background=BackgroundTask(caminho_zip.unlink, missing_ok=True),
    )
