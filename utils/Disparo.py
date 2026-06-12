import schedule
import time
import logging
from datetime import datetime

# Configuração de log para o agendador
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DISPARO] %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S"
)

def executar_pipeline(main_func):
    """
    Executa a função principal (main) com tratamento de erros e log de execução.
    """
    horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    logging.info(f"▶️  Iniciando execução agendada às {horario}")
    try:
        main_func()
        logging.info("✅ Execução concluída com sucesso.")
    except RuntimeError:
        print("❌ Falha crítica no FTP: A rotina será retomada no próximo disparo agendado.")
        return
    except Exception as e:
        logging.error(f"❌ Erro durante execução: {e}")
    
    logging.info("🕐 Aguardando próximo horário... (a cada 1 hora)")


def iniciar_agendador(main_func):
    """
    Configura e inicia o agendador de disparos.
    Agenda a execução de main_func a cada 1 hora.

    Args:
        main_func: A função principal a ser executada nos horários agendados.
    """
    schedule.every(1).hours.do(executar_pipeline, main_func=main_func)

    logging.info("🕐 Agendador iniciado. Disparos programados para: a cada 1 hora")
    logging.info("   Aguardando próximo horário... (pressione Ctrl+C para encerrar)")

    while True:
        schedule.run_pending()
        time.sleep(30)  # Verifica a cada 30 segundos
