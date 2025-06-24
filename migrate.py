# migrate.py
import os
import sys
import logging
from datamanager import DataManager
from logging_config import setup_logging

# Este bloco tenta carregar variáveis de ambiente de um arquivo .env,
# o que é útil para rodar o script localmente. No Render, as variáveis
# são injetadas diretamente, então o arquivo não será encontrado, o que é normal.
try:
    from dotenv import load_dotenv

    if os.path.exists('.env'):
        load_dotenv()
        logging.info("Arquivo .env carregado para migração local.")
except ImportError:
    pass  # Se python-dotenv não estiver instalado, apenas ignora.


def run_migrations():
    """
    Executa as migrações do banco de dados de forma segura.
    Esta função deve ser chamada antes de a aplicação principal iniciar.
    """
    setup_logging()
    logger = logging.getLogger("migration")
    logger.info("=============================================")
    logger.info("INICIANDO PROCESSO DE MIGRAÇÃO DO BANCO DE DADOS")
    logger.info("=============================================")

    try:
        # A instância do DataManager aqui é usada apenas para a migração.
        # Note que não passamos nenhum parâmetro, pois vamos alterar o DataManager
        # para que ele mesmo chame a função de inicialização do banco.
        dm = DataManager()
        dm._iniciar_banco_de_dados()
        logger.info("MIGRAÇÃO CONCLUÍDA COM SUCESSO!")
    except Exception as e:
        logger.critical(f"FALHA CRÍTICA DURANTE A MIGRAÇÃO: {e}", exc_info=True)
        sys.exit(1)  # Sai com um código de erro para falhar o build


if __name__ == "__main__":
    run_migrations()