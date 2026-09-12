"""API de leitura das extrações atuais da automação."""

import csv
import json
import os
import secrets
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Security
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.background import BackgroundTask


BASE_DIR = Path(__file__).resolve().parent
IMPORTS_DIR = BASE_DIR / "imports"
load_dotenv(BASE_DIR / ".env")

bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(
    title="NOVA Automação - Imports",
    description="Disponibiliza em JSON as quatro extrações atuais do SQL Server.",
    version="2.0.0",
)

# A ordem abaixo também é a ordem usada no documento JSON retornado.
TABELAS_EXPORTADAS = {
    "METAS": ("METAS", "VW_MULTIFOCO_METAS.csv"),
    "VENDAS": ("VENDA", "VW_MULTFOCO_VENDAS.csv"),
    "VENDEDORES": ("VENDEDORES", "VW_MULTIFOCO_VENDEDORES.csv"),
    "ESTOQUE": ("ESTOQUE", "VW_MULTIFOCO_ESTOQUE.csv"),
}

# Arquivos gerados antes da criação dos metadados ainda podem ser publicados.
# Nas novas extrações, os nomes reais retornados pelo SQL têm prioridade.
COLUNAS_LEGADAS = {
    "VENDA": [
        "CFOP",
        "Saida_Data_Venda",
        "Saida_Numero_Nota",
        "Saida_Filial_Cnpj",
        "Saida_Quantidade",
        "Saida_Valor_Unitario_Item",
        "Produto_Ean",
        "Vendedor_Codigo",
        "Vendedor_Nome",
        "Vendedor_Ativo",
        "Cliente_Codigo",
    ],
    "ESTOQUE": [
        "Filial_Cnpj",
        "Produto_Ean",
        "Estoque_Quantidade",
        "Lote",
        "Data_Entrada",
        "Data_Validade",
        "Preco_Custo",
    ],
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


def _encontrar_extracoes_atuais() -> dict[str, tuple[Path, str]]:
    """Localiza as quatro extrações ou responde 404 com a lista das ausentes."""
    encontrados = {
        categoria: (_arquivo_atual(prefixo), prefixo)
        for categoria, (prefixo, _) in TABELAS_EXPORTADAS.items()
    }
    ausentes = [
        categoria
        for categoria, (arquivo, _) in encontrados.items()
        if arquivo is None
    ]

    if ausentes:
        raise HTTPException(
            status_code=404,
            detail=f"Não foram encontradas as extrações atuais: {', '.join(ausentes)}.",
        )

    return {
        categoria: (arquivo, prefixo)
        for categoria, (arquivo, prefixo) in encontrados.items()
        if arquivo is not None
    }


def _normalizar_colunas(colunas: list[str], quantidade: int) -> list[str]:
    """Garante nomes preenchidos e únicos para todas as colunas do CSV."""
    resultado: list[str] = []
    ocorrencias: dict[str, int] = {}

    for indice in range(quantidade):
        nome = str(colunas[indice]).strip() if indice < len(colunas) else ""
        nome = nome or f"coluna_{indice + 1}"
        ocorrencias[nome] = ocorrencias.get(nome, 0) + 1
        if ocorrencias[nome] > 1:
            nome = f"{nome}_{ocorrencias[nome]}"
        resultado.append(nome)

    return resultado


def _obter_colunas(arquivo: Path, prefixo: str) -> list[str]:
    """Lê o esquema salvo na extração e usa nomes compatíveis para CSVs antigos."""
    caminho_esquema = arquivo.with_suffix(".columns.json")
    colunas: list[str] = []

    if caminho_esquema.is_file():
        try:
            conteudo = json.loads(caminho_esquema.read_text(encoding="utf-8"))
            if isinstance(conteudo, list):
                colunas = [str(item) for item in conteudo]
        except (OSError, UnicodeError, json.JSONDecodeError):
            colunas = []

    with arquivo.open("r", encoding="latin-1", newline="") as csv_file:
        primeira_linha = next(csv.reader(csv_file, delimiter=";"), [])

    if not colunas:
        colunas = COLUNAS_LEGADAS.get(prefixo, [])

    return _normalizar_colunas(colunas, len(primeira_linha))


def _gerar_json(
    tabelas: dict[str, tuple[Path, list[str]]],
) -> Iterator[str]:
    """Gera o documento aos poucos para não carregar todas as vendas na memória."""
    partes = ["{"]
    tamanho_buffer = 1

    def adicionar(parte: str) -> None:
        nonlocal tamanho_buffer
        partes.append(parte)
        tamanho_buffer += len(parte)

    for indice_tabela, (categoria, (arquivo, colunas)) in enumerate(tabelas.items()):
        if indice_tabela:
            adicionar(",")
        adicionar(f"{json.dumps(categoria)}:[")

        with arquivo.open("r", encoding="latin-1", newline="") as csv_file:
            leitor = csv.reader(csv_file, delimiter=";")
            for indice_linha, linha in enumerate(leitor):
                if indice_linha:
                    adicionar(",")
                registro = {
                    coluna: (
                        linha[indice]
                        if indice < len(linha) and linha[indice] != ""
                        else None
                    )
                    for indice, coluna in enumerate(colunas)
                }
                adicionar(
                    json.dumps(
                        registro,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )

                # Evita dezenas de milhares de pequenos envios pelo servidor ASGI.
                if tamanho_buffer >= 64 * 1024:
                    yield "".join(partes)
                    partes.clear()
                    tamanho_buffer = 0

        adicionar("]")

    adicionar("}")
    if partes:
        yield "".join(partes)


def criar_zip_imports_atuais() -> Path:
    """Monta um ZIP temporário com as quatro extrações SQL mais recentes."""
    encontrados = _encontrar_extracoes_atuais()

    with NamedTemporaryFile(
        prefix="tabelas_multfoco_",
        suffix=".zip",
        delete=False,
    ) as temporario:
        caminho_zip = Path(temporario.name)

    with ZipFile(caminho_zip, mode="w", compression=ZIP_DEFLATED) as arquivo_zip:
        for categoria, (arquivo, _) in encontrados.items():
            nome_no_zip = TABELAS_EXPORTADAS[categoria][1]
            arquivo_zip.write(arquivo, arcname=nome_no_zip)

    return caminho_zip


@app.get(
    "/imports/atuais",
    summary="Consultar os imports atuais em JSON",
    response_class=StreamingResponse,
)
def consultar_imports_atuais(
    _: None = Security(validar_token_bearer),
) -> StreamingResponse:
    """Retorna METAS, VENDAS, VENDEDORES e ESTOQUE como listas de objetos."""
    encontrados = _encontrar_extracoes_atuais()
    tabelas = {
        categoria: (arquivo, _obter_colunas(arquivo, prefixo))
        for categoria, (arquivo, prefixo) in encontrados.items()
    }

    return StreamingResponse(
        _gerar_json(tabelas),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/imports/atuais.zip", summary="Baixar os imports atuais em CSV")
def baixar_imports_atuais(
    _: None = Security(validar_token_bearer),
) -> FileResponse:
    """Mantém disponível o download legado das quatro views em um ZIP."""
    caminho_zip = criar_zip_imports_atuais()
    nome_download = f"tabelas_multfoco_{datetime.now():%Y%m%d_%H%M%S}.zip"

    return FileResponse(
        path=caminho_zip,
        media_type="application/zip",
        filename=nome_download,
        background=BackgroundTask(caminho_zip.unlink, missing_ok=True),
    )
