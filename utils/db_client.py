import os
import pandas as pd
import pyodbc
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

load_dotenv()

# --- Configurações do Banco de Dados (via .env) ---
DB_DRIVER = os.getenv("DB_DRIVER", "mssql")
DB_HOST   = os.getenv("DB_HOST")
DB_PORT   = os.getenv("DB_PORT", "1433")
DB_NAME   = os.getenv("DB_NAME")
DB_USER   = os.getenv("DB_USER")
DB_PASS   = os.getenv("DB_PASS")

# --- Nomes das Views (via .env) ---
VIEW_VENDAS  = os.getenv("VIEW_VENDAS",  "dbo.VW_MULTFOCO_VENDAS")
VIEW_ESTOQUE = os.getenv("VIEW_ESTOQUE", "dbo.VW_MULTIFOCO_ESTOQUE")
VIEW_METAS = os.getenv("VIEW_METAS", "dbo.VW_MULTIFOCO_METAS")
VIEW_VENDEDORES = os.getenv("VIEW_VENDEDORES", "dbo.VW_MULTIFOCO_VENDEDORES")

# --- Configurações de Filtros ---
CNPJS_PERMITIDOS_ENV = os.getenv("CNPJS_PERMITIDOS")
CNPJS_PERMITIDOS_LIST = [c.strip() for c in CNPJS_PERMITIDOS_ENV.split(",") if c.strip()]

# --- Pasta de destino dos arquivos baixados ---
DIRETORIO_IMPORTS = "imports"

# --- Nome dos arquivos CSV gerados (sem extensão) ---
NOME_ARQUIVO_VENDAS  = "VENDA"
NOME_ARQUIVO_ESTOQUE = "ESTOQUE"
NOME_ARQUIVO_METAS = "METAS"
NOME_ARQUIVO_VENDEDORES = "VENDEDORES"

# --- Query segura para a view de VENDAS ---
# A coluna Saida_Valor_Unitario_Item causa erro 8114 (varchar→numeric) dentro
# da definição criptografada da view. Usando TRY_CONVERT, o SQL Server retorna
# NULL em vez de abortar a query, e o valor correto aparece para os registros válidos.
QUERY_VENDAS = """
    SELECT
        CFOP,
        Saida_Data_Venda,
        Saida_Numero_Nota,
        Saida_Filial_Cnpj,
        Saida_Quantidade,
        TRY_CONVERT(NUMERIC(18,4), Saida_Valor_Unitario_Item) AS Saida_Valor_Unitario_Item,
        CAST(Produto_Ean AS VARCHAR(MAX)) AS Produto_Ean,
        Vendedor_Codigo,
        Vendedor_Nome,
        Vendedor_Ativo,
        Cliente_Codigo
    FROM {view}
"""


def _get_connection():
    """
    Cria e retorna uma conexão pyodbc com o SQL Server.
    Tenta múltiplas variações de string de conexão para garantir compatibilidade
    com servidores SQL Server externos/legados que podem ter configurações TLS restritas.
    Lança RuntimeError se todas as tentativas falharem.
    """
    drivers_preferidos = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "FreeTDS",
    ]

    driver_disponivel = None
    drivers_instalados = list(pyodbc.drivers())
    print(f"   Drivers instalados: {drivers_instalados}")

    for driver in drivers_preferidos:
        if driver in drivers_instalados:
            driver_disponivel = driver
            break

    if not driver_disponivel:
        raise RuntimeError(
            f"Nenhum driver ODBC compatível encontrado. "
            f"Drivers instalados: {drivers_instalados}"
        )

    print(f"   Driver selecionado: {driver_disponivel}")

    # Variações de string de conexão tentadas em ordem de compatibilidade.
    # Encrypt=no é o mais compatível com SQL Servers externos sem TLS moderno.
    base = (
        f"DRIVER={{{driver_disponivel}}};"
        f"SERVER={DB_HOST},{DB_PORT};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASS};"
        f"LoginTimeout=60;"
    )

    variacoes = [
        ("Encrypt=no",                               base + "Encrypt=no;"),
        ("TrustServerCertificate=yes + Encrypt=no",  base + "TrustServerCertificate=yes;Encrypt=no;"),
        ("Sem parâmetros TLS (padrão do driver)",     base),
        ("TrustServerCertificate=yes + Encrypt=yes",  base + "TrustServerCertificate=yes;Encrypt=yes;"),
    ]

    ultimo_erro = None
    for descricao, conn_str in variacoes:
        try:
            print(f"   🔄 Tentando ({descricao})...")
            conn = pyodbc.connect(conn_str, timeout=65)
            print(f"✅ Conectado ao banco '{DB_NAME}' em '{DB_HOST}' [{descricao}].")
            return conn
        except pyodbc.Error as e:
            print(f"   ↪ Falhou: {e}")
            ultimo_erro = e

    raise RuntimeError(f"Falha ao conectar ao banco de dados: {ultimo_erro}") from ultimo_erro


def _salvar_csv(df: pd.DataFrame, nome_base: str) -> str:
    """
    Salva o DataFrame como CSV na pasta /imports seguindo as regras de negócio:
      - Separador: ';'
      - Encoding:  'latin-1'
      - Sem cabeçalho (header=False) — padrão do projeto
      - Nome do arquivo: <NOME_BASE>_<DD-MM-AAAA>.csv

    Retorna o caminho completo do arquivo salvo.
    """
    os.makedirs(DIRETORIO_IMPORTS, exist_ok=True)

    data_str = datetime.now().strftime("%d-%m-%Y")
    nome_arquivo = f"{nome_base}_{data_str}.csv"
    caminho = os.path.join(DIRETORIO_IMPORTS, nome_arquivo)
    caminho_temporario = f"{caminho}.tmp"

    df.to_csv(
        caminho_temporario,
        sep=";",
        index=False,
        header=False,
        encoding="latin-1",
    )
    # A troca atômica impede que a API entregue um arquivo parcialmente escrito.
    os.replace(caminho_temporario, caminho)
    print(f"📥 Arquivo salvo: {caminho}  ({len(df)} linhas)")
    return caminho


def _executar_query(conn, query: str) -> pd.DataFrame:
    """
    Executa uma query via cursor pyodbc e retorna um DataFrame.
    Usa cursor direto (evita o UserWarning do pd.read_sql com pyodbc).
    """
    cursor = conn.cursor()
    cursor.execute(query)
    colunas = [desc[0] for desc in cursor.description]
    linhas  = cursor.fetchall()
    cursor.close()
    return pd.DataFrame.from_records(linhas, columns=colunas)


def filtrar_vendas_periodo_atual(caminho_venda_bruto: str) -> str:
    """
    Filtra o CSV bruto de vendas para manter apenas as linhas do mês atual
    e do mês anterior, baseado na coluna de data (índice 1, formato YYYY-MM-DD).

    Salva o resultado filtrado como VENDA_ATUAL_DD-MM-AAAA.csv na pasta /imports.
    A data é convertida para o formato dd/mm/YYYY (padrão dos scripts de processamento).

    Args:
        caminho_venda_bruto: caminho do arquivo CSV bruto de vendas.

    Retorna:
        caminho do arquivo CSV filtrado, ou None se falhar.
    """
    INDICE_DATA = 1  # Coluna 2 (índice 1) = Saida_Data_Venda

    try:
        df = pd.read_csv(
            caminho_venda_bruto,
            sep=';',
            header=None,
            encoding='latin-1',
            dtype=str,
        )

        total_original = len(df)

        # Converter a coluna de data para datetime (formato YYYY-MM-DD do banco)
        df['_data_parsed'] = pd.to_datetime(df[INDICE_DATA], format='%Y-%m-%d', errors='coerce')

        # Definir o período: mês atual e mês anterior
        hoje = datetime.now()
        primeiro_dia_mes_anterior = (hoje - relativedelta(months=1)).replace(day=1)

        # Filtrar: data >= primeiro dia do mês anterior
        mask = df['_data_parsed'] >= primeiro_dia_mes_anterior
        df_filtrado = df[mask].copy()

        # Filtrar por CNPJ específico (Coluna 4, Índice 3)
        INDICE_CNPJ = 3
        cnpjs_permitidos = CNPJS_PERMITIDOS_LIST
        
        # Garantir que a coluna de CNPJ não tenha espaços invisíveis ou nulos
        df_filtrado[INDICE_CNPJ] = df_filtrado[INDICE_CNPJ].astype(str).str.strip()
        df_filtrado = df_filtrado[df_filtrado[INDICE_CNPJ].isin(cnpjs_permitidos)]

        # Converter a data para o formato dd/mm/YYYY (esperado pelos processamentos)
        df_filtrado[INDICE_DATA] = df_filtrado['_data_parsed'].dt.strftime('%d/%m/%Y')

        # Formatar colunas numéricas do banco (NUMERIC(18,4) → formato correto)
        # Col 4 (Quantidade): "12.0000" → "12" (inteiro)
        INDICE_QTD = 4
        df_filtrado[INDICE_QTD] = pd.to_numeric(df_filtrado[INDICE_QTD], errors='coerce').fillna(0).astype(int).astype(str)

        # Col 5 (Preço Unitário): "40.4400" → "40,44" (formato BR com vírgula)
        INDICE_PRECO = 5
        df_filtrado[INDICE_PRECO] = (
            pd.to_numeric(df_filtrado[INDICE_PRECO], errors='coerce')
            .fillna(0.0)
            .apply(lambda x: f"{x:.2f}".replace('.', ','))
        )

        # Col 10 (Cliente Código): "3245.0" → "3245" (inteiro)
        INDICE_CLIENTE = 10
        df_filtrado[INDICE_CLIENTE] = pd.to_numeric(df_filtrado[INDICE_CLIENTE], errors='coerce').fillna(0).astype(int).astype(str)

        # Remover coluna auxiliar
        df_filtrado = df_filtrado.drop(columns=['_data_parsed'])

        # Salvar como VENDA_ATUAL_DD-MM-AAAA.csv
        data_str = hoje.strftime("%d-%m-%Y")
        nome_arquivo = f"VENDA_ATUAL_{data_str}.csv"
        caminho_saida = os.path.join(DIRETORIO_IMPORTS, nome_arquivo)

        df_filtrado.to_csv(
            caminho_saida,
            sep=';',
            index=False,
            header=False,
            encoding='latin-1',
        )

        print(f"🔍 Filtro aplicado: {total_original} → {len(df_filtrado)} registros (mês atual + mês anterior)")
        print(f"📥 Arquivo filtrado salvo: {caminho_saida}  ({len(df_filtrado)} linhas)")
        return caminho_saida

    except Exception as e:
        print(f"❌ Erro ao filtrar vendas por período: {e}")
        return None

def filtrar_estoque_atual(caminho_estoque_bruto: str) -> str:
    """
    Filtra o CSV bruto de estoque para manter apenas as linhas onde o estoque (índice 2)
    é maior que zero. Salva o resultado filtrado como ESTOQUE_ATUAL_DD-MM-AAAA.csv.

    Args:
        caminho_estoque_bruto: caminho do arquivo CSV bruto de estoque.

    Retorna:
        caminho do arquivo CSV filtrado, ou None se falhar.
    """
    INDICE_ESTOQUE = 2

    try:
        df = pd.read_csv(
            caminho_estoque_bruto,
            sep=';',
            header=None,
            encoding='latin-1',
            dtype=str,
        )

        total_original = len(df)

        # Converter a coluna de estoque para numérico para aplicar o filtro
        df[INDICE_ESTOQUE] = pd.to_numeric(df[INDICE_ESTOQUE], errors='coerce').fillna(0)

        # Filtrar as linhas onde o estoque é > 0
        df_filtrado = df[df[INDICE_ESTOQUE] > 0].copy()

        # # Filtrar por CNPJ específico (Coluna 1, Índice 0)
        INDICE_CNPJ = 0
        cnpjs_permitidos = CNPJS_PERMITIDOS_LIST
        
        # Garantir que a coluna de CNPJ não tenha espaços invisíveis ou nulos
        df_filtrado[INDICE_CNPJ] = df_filtrado[INDICE_CNPJ].astype(str).str.strip()
        df_filtrado = df_filtrado[df_filtrado[INDICE_CNPJ].isin(cnpjs_permitidos)]

        # Opcional: Converter de volta para inteiro/string se necessário, 
        # mas como é salvo em CSV o pandas lidará com o numérico corretamente.
        # Caso precise manter o formato original exato (ex. string sem ".0"):
        df_filtrado[INDICE_ESTOQUE] = df_filtrado[INDICE_ESTOQUE].astype(int).astype(str)

        # Salvar como ESTOQUE_ATUAL_DD-MM-AAAA.csv
        hoje = datetime.now()
        data_str = hoje.strftime("%d-%m-%Y")
        nome_arquivo = f"ESTOQUE_ATUAL_{data_str}.csv"
        caminho_saida = os.path.join(DIRETORIO_IMPORTS, nome_arquivo)

        df_filtrado.to_csv(
            caminho_saida,
            sep=';',
            index=False,
            header=False,
            encoding='latin-1',
        )

        print(f"🔍 Filtro de estoque aplicado: {total_original} → {len(df_filtrado)} registros (estoque > 0)")
        print(f"📥 Arquivo de estoque atual salvo: {caminho_saida}  ({len(df_filtrado)} linhas)")
        return caminho_saida

    except Exception as e:
        print(f"❌ Erro ao filtrar estoque: {e}")
        return None


def buscar_dados_views() -> list[str]:
    """
    Conecta ao SQL Server e extrai dados das quatro views da integração,
    salvando cada uma como arquivo .csv na pasta /imports.

    Regras de negócio aplicadas:
      - Gera arquivos de VENDA, ESTOQUE, METAS e VENDEDORES
      - Separador ';', encoding 'latin-1', sem cabeçalho
      - A pasta /imports é criada automaticamente se não existir
      - Em caso de view vazia, o arquivo NÃO é gerado e um aviso é exibido

    Retorna:
        lista com os caminhos dos arquivos gerados (pode estar vazia em caso de falha).

    Lança:
        RuntimeError — se a conexão com o banco falhar.
    """
    arquivos_gerados = []

    print("\n🔌 Iniciando conexão com o banco de dados...")
    conn = _get_connection()

    # Mapeamento: (nome do arquivo, nome da view, query a executar)
    views = [
        (NOME_ARQUIVO_VENDAS, VIEW_VENDAS, QUERY_VENDAS.format(view=VIEW_VENDAS)),
        (NOME_ARQUIVO_ESTOQUE, VIEW_ESTOQUE, f"SELECT * FROM {VIEW_ESTOQUE}"),
        (NOME_ARQUIVO_METAS, VIEW_METAS, f"SELECT * FROM {VIEW_METAS}"),
        (NOME_ARQUIVO_VENDEDORES, VIEW_VENDEDORES, f"SELECT * FROM {VIEW_VENDEDORES}"),
    ]

    try:
        for nome_base, nome_view, query in views:
            print(f"\n📊 Extraindo '{nome_base}' de '{nome_view}'...")
            try:
                df = _executar_query(conn, query)

                if df.empty:
                    print(f"⚠️  Query retornou 0 registros — arquivo não será gerado.")
                    continue

                # --- LIMPEZA DE EAN (Garante que códigos de 14 dígitos não virem floats) ---
                # Vendas: EAN está no índice 6. Estoque: EAN está no índice 1.
                idx_ean = {
                    NOME_ARQUIVO_VENDAS: 6,
                    NOME_ARQUIVO_ESTOQUE: 1,
                }.get(nome_base)
                if idx_ean is not None and len(df.columns) > idx_ean:
                    col_ean = df.columns[idx_ean]
                    # Converte para string e remove o ".0" que o pandas/sql pode inserir em números grandes
                    df[col_ean] = df[col_ean].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

                print(f"   ✔ {len(df)} registros encontrados.")
                caminho = _salvar_csv(df, nome_base)
                arquivos_gerados.append(caminho)

            except Exception as e:
                print(f"❌ Erro ao extrair '{nome_base}': {e}")

    finally:
        conn.close()
        print("\n🔒 Conexão com o banco encerrada.")

    return arquivos_gerados
