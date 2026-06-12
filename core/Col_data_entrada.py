import pandas as pd
from datetime import datetime

def preencher_data_entrada(df_final, df_estoque):
    """
    Atualiza a 'Data Entrada' pegando a data mais recente na coluna 5 (índice 4) 
    do dataframe ESTOQUE, agrupado por EAN.
    Formato na base: aaaa/mm/dd
    Formato de saída: dd/mm/aa
    """
    try:
        data_hoje = datetime.now().strftime('%d/%m/%y')
        mapa_datas = {}
        
        if df_estoque is not None and not df_estoque.empty and len(df_estoque.columns) > 4:
            df_validos = df_estoque.dropna(subset=[1, 4]).copy()
            
            # EAN está no índice 1
            df_validos[1] = df_validos[1].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            
            # A data está no índice 4 (aaaa/mm/dd)
            df_validos['data_dt'] = pd.to_datetime(df_validos[4], errors='coerce')
            
            df_validos = df_validos.dropna(subset=['data_dt'])
            
            if not df_validos.empty:
                # Pegar a data máxima por EAN
                max_dates = df_validos.groupby(1)['data_dt'].max()
                
                # Formatar para dd/mm/aa (%d/%m/%y)
                for ean, max_date in max_dates.items():
                    mapa_datas[ean] = max_date.strftime('%d/%m/%y')

        datas_entrada = []
        for idx, row in df_final.iterrows():
            ean = str(row['EAN']).replace('.0', '').strip()
            data_decidida = mapa_datas.get(ean, data_hoje)
            datas_entrada.append(data_decidida)
            
        df_final['Data Entrada'] = datas_entrada
        return df_final

    except Exception as e:
        print(f"❌ Erro ao buscar Data de Entrada no ESTOQUE: {e}")
        df_final['Data Entrada'] = datetime.now().strftime('%d/%m/%y')
        return df_final