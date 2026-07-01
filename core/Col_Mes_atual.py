import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

def agrupar_vendas(df_vendas):
    """
    Soma as vendas da Coluna 5 (índice 4) por EAN (índice 6).
    Força a limpeza de strings para garantir que '5' vire 5 antes da soma.
    Separa em 'Mês Atual' e 'Mês -1' usando a coluna Data da Venda (índice 1).
    """
    INDICE_CFOP = 0
    INDICE_DATA = 1
    INDICE_VALOR = 4   
    INDICE_EAN = 6     

    try:
        # 0. Filtrar CFOPs indesejados
        df_vendas[INDICE_CFOP] = df_vendas[INDICE_CFOP].astype(str).str.strip()
        df_vendas = df_vendas[~df_vendas[INDICE_CFOP].isin(['6202', '5202','5949','1949'])]

        # 1. Limpeza do EAN (Essencial para o groupby encontrar os pares)
        df_vendas[INDICE_EAN] = df_vendas[INDICE_EAN].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        # 2. Limpeza e Conversão do Valor
        df_vendas[INDICE_VALOR] = (
            df_vendas[INDICE_VALOR]
            .astype(str)            # Força virar string para limpar
            .str.strip()            # Remove espaços " 5 " -> "5"
            .replace('', '0')       # Se estiver vazio, vira "0"
        )
        
        # Converte para numérico e garante que é int64
        df_vendas[INDICE_VALOR] = pd.to_numeric(df_vendas[INDICE_VALOR], errors='coerce').fillna(0).astype('int64')

        # Converte Data
        df_vendas['data_venda'] = pd.to_datetime(df_vendas[INDICE_DATA], format='%d/%m/%Y', errors='coerce')
        
        hoje = datetime.now()
        mes_atual = hoje.month
        ano_atual = hoje.year

        mes_passado_dt = hoje - relativedelta(months=1)
        mes_passado = mes_passado_dt.month
        ano_passado = mes_passado_dt.year

        mask_atual = (df_vendas['data_venda'].dt.month == mes_atual) & (df_vendas['data_venda'].dt.year == ano_atual)
        mask_passado = (df_vendas['data_venda'].dt.month == mes_passado) & (df_vendas['data_venda'].dt.year == ano_passado)
        
        # 3. Agrupamento e Soma
        df_atual = df_vendas[mask_atual].groupby(INDICE_EAN)[INDICE_VALOR].sum().reset_index()
        df_atual.columns = ['EAN', 'Mês Atual']
        
        df_passado = df_vendas[mask_passado].groupby(INDICE_EAN)[INDICE_VALOR].sum().reset_index()
        df_passado.columns = ['EAN', 'Mês -1']

        # 4. Renomeação e Garantia Final de Tipo
        df_agrupado = pd.merge(df_atual, df_passado, on='EAN', how='outer')
        df_agrupado['Mês Atual'] = df_agrupado['Mês Atual'].fillna(0).astype('int64')
        df_agrupado['Mês -1'] = df_agrupado['Mês -1'].astype('Int64')

        return df_agrupado

    except Exception as e:
        print(f"❌ Erro crítico ao agrupar vendas: {e}")
        return None