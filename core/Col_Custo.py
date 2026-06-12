import pandas as pd

def extrair_preco_custo(df_estoque):
    """
    Seleciona e repete o preço de custo da data de entrada mais recente para cada EAN.
    
    Colunas do df_estoque (por índice posicional):
        1 → EAN
        4 → Data de Entrada
        6 → Preço de custo
    """
    INDICE_EAN    = 1
    INDICE_DATA   = 4
    INDICE_PRECO  = 6

    try:
        # Verifica se o df_estoque tem colunas suficientes
        if len(df_estoque.columns) <= max(INDICE_EAN, INDICE_DATA, INDICE_PRECO):
            return pd.DataFrame(columns=['EAN', 'Preço Custo'])

        # 1. Seleção das colunas
        df = df_estoque[[INDICE_EAN, INDICE_DATA, INDICE_PRECO]].copy()
        df.columns = ['EAN', 'Data', 'Preço Custo']

        # 2. Limpeza
        df['EAN'] = df['EAN'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        # Converte Data
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
        
        # Converte Preço Custo para numérico
        df['Preço Custo'] = (
            df['Preço Custo']
            .astype(str)
            .str.replace(',', '.', regex=False)
        )
        df['Preço Custo'] = pd.to_numeric(df['Preço Custo'], errors='coerce').fillna(0.0)

        # Remove linhas com datas inválidas (pois precisamos ordenar)
        df = df.dropna(subset=['Data'])

        # 3. Ordena por EAN e Data decrescente (mais recente primeiro)
        df = df.sort_values(by=['EAN', 'Data'], ascending=[True, False])

        # 4. Mantém apenas a primeira linha por EAN (a mais recente)
        df = df.drop_duplicates(subset=['EAN'], keep='first')

        # 5. Formatação final (2 casas decimais)
        df_agrupado = df[['EAN', 'Preço Custo']].copy()
        df_agrupado['Preço Custo'] = df_agrupado['Preço Custo'].round(2)

        # Se for <= 0, substitui por 0.001 (requisito da API)
        df_agrupado.loc[df_agrupado['Preço Custo'] <= 0, 'Preço Custo'] = 0.001

        return df_agrupado

    except Exception as e:
        print(f"❌ Erro ao capturar preço de custo: {e}")
        return None