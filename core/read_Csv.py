import pandas as pd
import os

def ler_csv_sem_header(caminho_arquivo):
    """
    Lê um arquivo CSV sem cabeçalho com delimitador ';'
    """
    if not os.path.exists(caminho_arquivo):
        # ERRO: Sempre verifique se o arquivo existe antes de tentar ler
        # para evitar que o programa pare abruptamente (crash).
        print(f"ERRO CRÍTICO: Arquivo não encontrado em: {caminho_arquivo}")
        return None

    try:
        # PONTO DE ATENÇÃO: dtype=str é obrigatório para EANs
        # Se não usar, o Pandas converterá EANs longos para notação científica.
        df = pd.read_csv(
            caminho_arquivo,
            sep=';',
            header=None,
            dtype=str,
            encoding='latin-1' # Se houver erro de acento, mude para 'latin-1'
        )
        return df
    except pd.errors.EmptyDataError:
        print(f"Aviso: O arquivo está vazio ou não possui colunas para ler: {caminho_arquivo}")
        return None
    except Exception as e:
        print(f"Falha em latin-1, tentando encoding alternativo para {caminho_arquivo}")
        try:
            return pd.read_csv(caminho_arquivo, sep=';', header=None, dtype=str, encoding='ISO-8859-1')
        except pd.errors.EmptyDataError:
            print(f"Aviso: O arquivo está vazio ou não possui colunas para ler: {caminho_arquivo}")
            return None
        except Exception as fallback_e:
            print(f"Erro ao ler arquivo {caminho_arquivo} com encoding alternativo: {fallback_e}")
            return None