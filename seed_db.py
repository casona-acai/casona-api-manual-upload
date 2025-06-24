# seed_db.py
import psycopg2
from psycopg2 import IntegrityError
from decouple import config

# Importa a função de hash do seu módulo de autenticação.
# Isso garante que estamos usando o mesmo método de criptografia da API.
from auth import get_password_hash

# Carrega a URL do banco de dados do seu arquivo .env (para testes locais)
# ou das variáveis de ambiente (no Render).
try:
    DATABASE_URL = config("DATABASE_URL")
except Exception as e:
    print(f"ERRO: Não foi possível encontrar a variável 'DATABASE_URL'.")
    print("Certifique-se de que ela está configurada nas variáveis de ambiente do seu serviço no Render.")
    print(f"Detalhe do erro: {e}")
    exit() # Interrompe a execução se a URL não for encontrada.

# --- DADOS DAS LOJAS INICIAIS ---
# Aqui você pode adicionar todas as lojas que precisa.
# Por enquanto, apenas a loja de teste.
LOJAS_INICIAIS = [
    {
        "username": "admin",
        "senha": "admin",
        "identificador": "TESTE-01",
        "nome_loja": "Loja de Teste"
    },
    # Para adicionar mais lojas no futuro, siga este modelo:
    # {
    #     "username": "loja_centro",
    #     "senha": "uma_senha_super_forte_123",
    #     "identificador": "LOJA-CENTRO-01",
    #     "nome_loja": "Casona Açaí - Centro"
    # },
]

def seed_database():
    """Conecta ao banco de dados e insere ou atualiza as lojas iniciais."""
    conn = None
    try:
        print("Iniciando processo de seeding...")
        print("Conectando ao banco de dados...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("Conexão bem-sucedida.")

        for loja in LOJAS_INICIAIS:
            username = loja["username"]
            # Gera o hash seguro da senha
            hashed_password = get_password_hash(loja["senha"])
            identificador = loja["identificador"]
            nome_loja = loja["nome_loja"]

            try:
                print(f"Processando loja: {username}...")
                # Usamos "ON CONFLICT" para que o script possa ser executado novamente sem erros.
                # Ele insere a loja se o username não existir, ou atualiza os dados se já existir.
                # Isso é útil para corrigir ou atualizar senhas no futuro.
                cursor.execute(
                    """
                    INSERT INTO lojas (username, hashed_password, identificador, nome_loja, is_active)
                    VALUES (%s, %s, %s, %s, TRUE)
                    ON CONFLICT (username) DO UPDATE SET
                        hashed_password = EXCLUDED.hashed_password,
                        identificador = EXCLUDED.identificador,
                        nome_loja = EXCLUDED.nome_loja,
                        is_active = TRUE;
                    """,
                    (username, hashed_password, identificador, nome_loja)
                )
                print(f"-> Loja '{username}' inserida/atualizada com sucesso.")

            except IntegrityError as e:
                # Este erro pode acontecer se o 'identificador' já existir mas o 'username' não.
                print(f"AVISO: Não foi possível processar a loja '{username}'. Pode já existir com dados conflitantes. Erro: {e}")
                conn.rollback() # Desfaz a transação atual para continuar com a próxima loja
            except Exception as e:
                print(f"ERRO ao processar a loja '{username}': {e}")
                conn.rollback()

        # Confirma todas as transações bem-sucedidas no banco de dados
        conn.commit()
        cursor.close()
        print("\nProcesso de seeding concluído com sucesso!")

    except psycopg2.OperationalError as e:
        print(f"\nERRO DE CONEXÃO: Não foi possível conectar ao banco de dados.")
        print(f"Verifique se a DATABASE_URL está correta e se o banco está acessível.")
        print(f"Detalhe do erro: {e}")
    except Exception as e:
        print(f"\nERRO GERAL durante o processo de seeding: {e}")
    finally:
        if conn is not None:
            conn.close()
            print("Conexão com o banco de dados fechada.")

if __name__ == "__main__":
    seed_database()