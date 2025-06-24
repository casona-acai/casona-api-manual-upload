# scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os

# Importamos diretamente do datamanager, mas não instanciamos aqui.
from datamanager import DataManager
from logging_config import setup_logging


def _job_wrapper(job_func_name):
    """
    Um invólucro para as tarefas agendadas.
    Ele cria uma instância do DataManager para cada execução da tarefa,
    garantindo que a conexão com o banco de dados seja nova e segura.
    """
    setup_logging()
    logger = logging.getLogger(f"scheduler.{job_func_name}")
    logger.info(f"Iniciando a tarefa agendada: {job_func_name}")

    try:
        # Cria uma nova instância do DataManager especificamente para esta tarefa.
        # run_init=False garante que não tentaremos migrar o banco novamente.
        dm = DataManager(run_init=False)

        # Obtém a função real a ser executada a partir da instância do DataManager
        job_to_run = getattr(dm, job_func_name)
        job_to_run()

        logger.info(f"Tarefa agendada '{job_func_name}' concluída com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao executar a tarefa agendada '{job_func_name}': {e}", exc_info=True)
    finally:
        # Garante que o pool de conexões desta instância seja fechado.
        if 'dm' in locals() and dm.connection_pool:
            dm.close_pool()
            logger.info(f"Pool de conexões para a tarefa '{job_func_name}' foi fechado.")


def start_scheduler():
    """
    Configura e inicia o agendador de tarefas APScheduler.
    Esta função será chamada pelo Gunicorn no processo mestre.
    """
    logger = logging.getLogger("scheduler.main")

    # Validação para não iniciar o scheduler durante os reloads do Uvicorn em modo de dev
    if os.environ.get("GUNICORN_PID"):
        scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")

        # Passamos o NOME da função como uma string para o nosso wrapper.
        scheduler.add_job(
            _job_wrapper,
            'cron',
            hour=8,
            minute=0,
            id="job_aniversariantes",
            args=["enviar_emails_aniversariantes_do_dia"]
        )
        scheduler.add_job(
            _job_wrapper,
            'cron',
            hour=11,
            minute=0,
            id="job_clientes_inativos",
            args=["enviar_emails_clientes_inativos"]
        )

        scheduler.start()
        logger.info("APScheduler configurado e iniciado no processo mestre do Gunicorn.")
    else:
        logger.warning(
            "Não estou em um processo Gunicorn. O agendador não foi iniciado (comportamento esperado em dev local com uvicorn).")