# scheduler.py

import logging
from apscheduler.schedulers.background import BackgroundScheduler

from datamanager import DataManager
from logging_config import setup_logging


def _job_wrapper(job_func_name: str):
    """
    Um invólucro (wrapper) para as tarefas agendadas do APScheduler.

    Esta função é a que o scheduler realmente chama. Sua responsabilidade é:
    1.  Configurar o logging para a thread da tarefa.
    2.  Criar uma instância fresca do `DataManager` para garantir que a tarefa
        tenha seu próprio contexto de banco de dados e não interfira com a API.
    3.  Chamar a função de negócio real (ex: `enviar_emails_aniversariantes_do_dia`).
    4.  Capturar quaisquer erros que a tarefa possa gerar, registrando-os em log.
    5.  Garantir que os recursos (como o pool de conexões) sejam limpos no final.
    """
    # Garante que o logging funcione corretamente dentro da thread da tarefa
    setup_logging()
    logger = logging.getLogger(f"scheduler.job.{job_func_name}")
    logger.info(f"Iniciando execução da tarefa agendada: {job_func_name}")

    dm = None  # Inicializa a variável para o bloco finally
    try:
        # Cria uma nova instância do DataManager especificamente para esta tarefa.
        # `run_init=False` é crucial para não tentar rodar migrações do DB novamente.
        dm = DataManager(run_init=False)

        # Usa `getattr` para obter o método do DataManager cujo nome foi passado como string.
        job_to_run = getattr(dm, job_func_name)

        # Executa a tarefa
        job_to_run()

        logger.info(f"Tarefa agendada '{job_func_name}' concluída com sucesso.")

    except Exception as e:
        logger.error(f"Erro ao executar a tarefa agendada '{job_func_name}': {e}", exc_info=True)

    finally:
        # Este bloco é sempre executado, mesmo se ocorrer um erro.
        # Ele garante que o pool de conexões criado para esta tarefa seja fechado.
        if dm and dm.connection_pool:
            dm.close_pool()
            logger.info(f"Pool de conexões para a tarefa '{job_func_name}' foi fechado.")


def start_scheduler():
    """
    Configura e inicia o agendador de tarefas (APScheduler).

    Esta função é projetada para ser chamada pelo hook `on_starting` do Gunicorn,
    garantindo que o agendador seja iniciado apenas UMA VEZ no processo mestre,
    e não em cada um dos processos trabalhadores (workers) da API.
    """
    logger = logging.getLogger("scheduler.main")

    # A verificação `if os.environ.get("GUNICORN_PID")` foi removida,
    # pois o hook do Gunicorn já garante que este código só é executado
    # no processo mestre, que é o comportamento desejado.

    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")

    # Adiciona a tarefa para enviar e-mails de aniversário.
    # Note que passamos a FUNÇÃO WRAPPER (`_job_wrapper`) e o NOME da função
    # de negócio como um argumento (`args`).
    scheduler.add_job(
        _job_wrapper,
        'cron',
        hour=8,
        minute=0,
        id="job_aniversariantes",
        args=["enviar_emails_aniversariantes_do_dia"]
    )

    # Adiciona a tarefa para enviar e-mails de inatividade.
    scheduler.add_job(
        _job_wrapper,
        'cron',
        hour=11,
        minute=0,
        id="job_clientes_inativos",
        args=["enviar_emails_clientes_inativos"]
    )

    # Inicia o agendador em uma thread de fundo.
    scheduler.start()

    logger.info("APScheduler configurado e iniciado com sucesso no processo mestre do Gunicorn.")