
import os
import sys
import pandas as pd
from core.read_Csv import ler_csv_sem_header
from core.Col_estoque import processar_estoque_agrupado
from core.Col_data_validade import processar_validade_estoque
from core.Col_Custo import extrair_preco_custo
from core.Col_Mes_atual import agrupar_vendas
from core.Col_faturamento_total import calcular_faturamento_atual
from core.Col_data_entrada import preencher_data_entrada
from utils.exporter_excel import gerar_relatorio_vendas
from utils.controler_import import arquivar_arquivos_importacao
from utils.api_client import enviar_ultimo_relatorio
from utils.db_client import buscar_dados_views, filtrar_vendas_periodo_atual, filtrar_estoque_atual
from utils.Disparo import iniciar_agendador

def main():
    diretorio_imports = 'imports'
    usar_arquivos_ja_filtrados = False  # flag: True quando os _ATUAL_ já estão prontos

    # =========================================================
    # FLAG: USE_BANCO
    #   True  → busca dados do banco de dados (comportamento normal)
    #   False → usa os arquivos CSV já existentes na pasta /imports
    # =========================================================
    USE_BANCO = True

    if USE_BANCO:
        print("\n--- Extração de dados das Views ---")
        try:
            arquivos_baixados = buscar_dados_views()
            if not arquivos_baixados:
                print("⚠️ Aviso: Nenhum dado retornado das Views. A rotina será encerrada.")
                return
        except RuntimeError as e:
            print(f"❌ Erro crítico na conexão: {e}")
            print("A rotina será retomada no próximo disparo agendado.")
            return
        except Exception as e:
            print(f"❌ Erro inesperado na extração: {e}")
            return

        venda_bruta_path = next((f for f in arquivos_baixados if 'VENDA' in os.path.basename(f).upper()), None)
        estoque_path     = next((f for f in arquivos_baixados if 'ESTOQUE' in os.path.basename(f).upper()), None)

        if not venda_bruta_path or not estoque_path:
            print("❌ Erro: Arquivos de VENDA ou ESTOQUE não encontrados na extração.")
            return

    else:
        # --- MODO OFFLINE: lê os arquivos existentes em /imports ---
        print("\n⚠️  [MODO OFFLINE] Banco de dados desativado. Usando arquivos da pasta /imports.")

        arquivos_imports = [
            os.path.join(diretorio_imports, f)
            for f in os.listdir(diretorio_imports)
            if f.endswith('.csv')
        ]

        # Tenta primeiro arquivos brutos (sem _ATUAL_)
        vendas_brutas = sorted(
            [f for f in arquivos_imports if 'VENDA' in os.path.basename(f).upper() and 'ATUAL' not in os.path.basename(f).upper()],
            key=os.path.getmtime, reverse=True,
        )
        estoques_brutos = sorted(
            [f for f in arquivos_imports if 'ESTOQUE' in os.path.basename(f).upper() and 'ATUAL' not in os.path.basename(f).upper()],
            key=os.path.getmtime, reverse=True,
        )

        # Fallback: usa arquivos _ATUAL_ quando não há brutos (já filtrados, pula etapa de filtro)
        vendas_atuais = sorted(
            [f for f in arquivos_imports if 'VENDA' in os.path.basename(f).upper() and 'ATUAL' in os.path.basename(f).upper()],
            key=os.path.getmtime, reverse=True,
        )
        estoques_atuais = sorted(
            [f for f in arquivos_imports if 'ESTOQUE' in os.path.basename(f).upper() and 'ATUAL' in os.path.basename(f).upper()],
            key=os.path.getmtime, reverse=True,
        )

        usar_arquivos_ja_filtrados = False

        if vendas_brutas and estoques_brutos:
            venda_bruta_path = vendas_brutas[0]
            estoque_path     = estoques_brutos[0]
            print(f"📂 VENDA (bruto)  : {venda_bruta_path}")
            print(f"📂 ESTOQUE (bruto): {estoque_path}")

        elif vendas_atuais and estoques_atuais:
            # Já filtrados — usa diretamente sem passar pelo filtro
            venda_bruta_path     = vendas_atuais[0]
            estoque_path         = estoques_atuais[0]
            usar_arquivos_ja_filtrados = True
            print(f"📂 VENDA (já filtrado)  : {venda_bruta_path}")
            print(f"📂 ESTOQUE (já filtrado): {estoque_path}")

        else:
            if not vendas_brutas and not vendas_atuais:
                print("❌ Nenhum arquivo VENDA encontrado na pasta /imports.")
            if not estoques_brutos and not estoques_atuais:
                print("❌ Nenhum arquivo ESTOQUE encontrado na pasta /imports.")
            return


    # 3. Filtrar vendas e estoque (pula se já são arquivos _ATUAL_)
    if usar_arquivos_ja_filtrados:
        venda_path         = venda_bruta_path
        estoque_atual_path = estoque_path
        print("ℹ️  Arquivos já filtrados — etapa de filtro ignorada.")
    else:
        # Filtrar vendas — manter apenas mês atual e mês anterior
        venda_path = filtrar_vendas_periodo_atual(venda_bruta_path)
        if not venda_path:
            print("❌ Erro: Falha ao filtrar vendas por período.")
            return

        # Filtrar estoque — manter apenas produtos com estoque > 0
        estoque_atual_path = filtrar_estoque_atual(estoque_path)
        if not estoque_atual_path:
            print("❌ Erro: Falha ao filtrar estoque atual.")
            return

    # --- BACKUP DIÁRIO DE IMPORTAÇÕES (Raw + Atual) ---
    print("Iniciando rotina de backup dos arquivos importados do dia...")
    arquivar_arquivos_importacao(diretorio_imports)

    # Remover os arquivos brutos apenas quando veio do banco
    # (em modo offline, preservamos os arquivos originais da pasta)
    if USE_BANCO:
        try:
            os.remove(venda_bruta_path)
            print(f"🗑️  Arquivo bruto removido: {venda_bruta_path}")
            os.remove(estoque_path)
            print(f"🗑️  Arquivo bruto removido: {estoque_path}")
        except OSError:
            pass

    df_vendas_bruto = ler_csv_sem_header(venda_path)
    df_estoque_bruto = ler_csv_sem_header(estoque_atual_path)

    if df_vendas_bruto is not None and df_estoque_bruto is not None:
        print(f"✅ Arquivos carregados com sucesso: {venda_path} ({len(df_vendas_bruto)} linhas) e {estoque_atual_path} ({len(df_estoque_bruto)} linhas).")

        # --- PROCESSAMENTOS INDIVIDUAIS ---
        estoque_final = processar_estoque_agrupado(df_estoque_bruto.copy())
        custo_final = extrair_preco_custo(df_estoque_bruto.copy())
        validade_final = processar_validade_estoque(df_estoque_bruto.copy())
        
        vendas_final = agrupar_vendas(df_vendas_bruto.copy())
        faturamento_final = calcular_faturamento_atual(df_vendas_bruto.copy())

        # --- CONSOLIDAÇÃO FINAL ---
        try:
            # 1. União dos dados pelo EAN
            # Utilizamos how='outer' para preservar EANs que só aparecem em vendas.csv
            df_final = pd.merge(estoque_final, custo_final, on='EAN', how='outer')
            df_final = pd.merge(df_final, validade_final, on='EAN', how='outer')
            df_final = pd.merge(df_final, vendas_final, on='EAN', how='outer')
            df_final = pd.merge(df_final, faturamento_final, on='EAN', how='outer')

            # 2. Adicionar Data de Entrada (dd/mm/aa)
            df_final = preencher_data_entrada(df_final, df_estoque_bruto.copy())

            # 3. Limpeza de Nulos e Tipagem
            colunas_numericas = ['Estoque', 'Mês Atual', 'Faturamento Atual', 'Faturamento M-1']
            df_final[colunas_numericas] = df_final[colunas_numericas].fillna(0)
        
            # Garantir formato inteiro para colunas de contagem
            df_final['Estoque'] = df_final['Estoque'].astype(int)
            df_final['Mês Atual'] = df_final['Mês Atual'].astype(int)
            df_final['Mês -1'] = df_final['Mês -1'].astype('Int64')

            # Para todo item cujo estoque for 0, o preço de custo passa a ser 0.001
            estoque_zero = df_final['Estoque'] == 0
            df_final.loc[estoque_zero, 'Preço Custo'] = 0.001
            
            # Itens restantes sem preço recebem valor numérico 0.001
            df_final['Preço Custo'] = df_final['Preço Custo'].fillna(0.001)
            
            # Garantia extra contra zeros inteiros salvos do processo
            df_final.loc[df_final['Preço Custo'] == 0, 'Preço Custo'] = 0.001

            # --- EXPORTAÇÃO E GESTÃO DE ARQUIVOS (Output) ---
            # Esta função cria as colunas vazias, salva na pasta /output 
            # e remove os arquivos mais antigos mantendo apenas os 4 últimos.
            gerar_relatorio_vendas(df_final)
            
            print("\n--- Fluxo finalizado: Relatório gerado e pasta /output organizada ---")
            
           # --- ENVIO PARA API ---
            sucesso_envio = enviar_ultimo_relatorio()
            if not sucesso_envio:
                print("❌ Falha ao enviar o relatório para a API.")


        except Exception as e:
            print(f"❌ Erro crítico no processamento final: {e}")
    else:
        print("❌ Erro fatal: Verifique se os arquivos VENDA.csv e ESTOQUE.csv estão na pasta /imports.")

if __name__ == "__main__":
    # Executa uma vez imediatamente ao iniciar
    main()
    
    # Inicia o agendador para rodar a cada 1 hora
    iniciar_agendador(main)