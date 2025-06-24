# gunicorn_config.py
import os
import multiprocessing
from scheduler import start_scheduler

# --- Configurações do Servidor ---

# O Gunicorn vai escutar nesta porta. O Render irá mapeá-la para as portas 80/443.
# O valor '10000' é o padrão do Render, mas podemos pegar da variável de ambiente se disponível.
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Número de workers. 4 é um bom padrão para um plano free.
# Ele se baseia na fórmula: (2 * número de CPUs) + 1
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)

# Define o tipo de worker para ser compatível com FastAPI (asyncio).
worker_class = "uvicorn.workers.UvicornWorker"

# Tempo em segundos que um worker pode ficar inativo antes de ser reiniciado.
timeout = 120

# Arquivos de log (útil para debug, o Render captura a saída padrão de qualquer forma)
accesslog = "-"
errorlog = "-"

# --- Hooks (Ganchos de Execução) ---

def on_starting(server):
    """
    Hook do Gunicorn que executa no processo MESTRE antes de criar os workers.
    É o lugar perfeito para iniciar tarefas que devem rodar apenas UMA VEZ.
    """
    server.log.info("Processo Mestre do Gunicorn iniciando...")
    start_scheduler()