# datamanager.py (VERSÃO COM LOGS DE DEBUG)

import psycopg2
from psycopg2 import OperationalError, IntegrityError, extras
from psycopg2 import pool
import time
from datetime import datetime
import random
import threading
import logging

import email_manager
import config


class DataManager:
    """
    Classe que gerencia toda a lógica de banco de dados.
    A instância desta classe é criada e gerenciada pelo main.py.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.email_manager = email_manager.EmailManager()
        self.database_url = config.DATABASE_URL
        if not self.database_url or "postgres" not in self.database_url:
            raise Exception("URL do banco de dados não configurada corretamente.")

        try:
            self.connection_pool = pool.SimpleConnectionPool(
                minconn=2, maxconn=15, dsn=self.database_url
            )
            self.logger.info("Pool de conexões com o banco de dados criado com sucesso.")
        except OperationalError as e:
            self.logger.critical(f"Falha CRÍTICA ao criar o pool de conexões: {e}")
            raise

        self._iniciar_banco_de_dados()

    def _get_conexao(self):
        return self.connection_pool.getconn()

    def _release_conexao(self, conn):
        self.connection_pool.putconn(conn)

    def close_pool(self):
        """Fecha todas as conexões no pool."""
        if self.connection_pool:
            self.connection_pool.closeall()
            self.logger.info("Pool de conexões com o banco de dados fechado.")

    def _executar_query(self, query, params=None, fetch=None, as_dict=False):
        conn = None
        try:
            conn = self._get_conexao()
            cursor_factory = extras.RealDictCursor if as_dict else None
            with conn.cursor(cursor_factory=cursor_factory) as cursor:
                cursor.execute(query, params or ())
                if fetch == 'one':
                    return cursor.fetchone()
                if fetch == 'all':
                    return cursor.fetchall()
                conn.commit()
                return True
        except psycopg2.Error as e:
            if conn: conn.rollback()
            self.logger.error(f"ERRO DE BANCO DE DADOS na query: {query[:100]}... Erro: {e}")
            raise
        finally:
            if conn:
                self._release_conexao(conn)

    def _iniciar_banco_de_dados(self):
        comandos = [
            '''CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, identificador TEXT UNIQUE NOT NULL, hashed_password TEXT NOT NULL, nome_loja TEXT, is_active BOOLEAN NOT NULL DEFAULT TRUE)''',
            '''CREATE TABLE IF NOT EXISTS clientes (codigo TEXT PRIMARY KEY, nome TEXT NOT NULL, telefone TEXT, email TEXT, total_compras INTEGER, total_gasto REAL, contagem_brinde INTEGER, loja_origem TEXT, data_nascimento DATE, ano_ultimo_email_aniversario INTEGER, sexo TEXT)''',
            '''ALTER TABLE clientes ADD COLUMN IF NOT EXISTS data_ultimo_email_inatividade DATE;''',
            '''CREATE TABLE IF NOT EXISTS compras (id SERIAL PRIMARY KEY, codigo_cliente TEXT NOT NULL, numero_compra_geral INTEGER NOT NULL, valor REAL NOT NULL, data DATE NOT NULL, loja_compra TEXT, FOREIGN KEY (codigo_cliente) REFERENCES clientes (codigo))''',
            '''CREATE TABLE IF NOT EXISTS premios_ativos (codigo_premio TEXT PRIMARY KEY, valor_premio REAL, codigo_cliente TEXT, data_geracao DATE, FOREIGN KEY (codigo_cliente) REFERENCES clientes (codigo))''',
            '''CREATE TABLE IF NOT EXISTS premios_resgatados (id SERIAL PRIMARY KEY, codigo_premio TEXT, valor_premio REAL, codigo_cliente TEXT, data_geracao DATE, data_resgate DATE, loja_resgate TEXT)''',
            "CREATE SEQUENCE IF NOT EXISTS codigo_cliente_seq START 1;",
            "CREATE INDEX IF NOT EXISTS idx_lojas_username ON lojas (username);",
            "CREATE INDEX IF NOT EXISTS idx_clientes_telefone ON clientes (telefone);",
            "CREATE INDEX IF NOT EXISTS idx_clientes_email ON clientes (email);",
            "CREATE INDEX IF NOT EXISTS idx_compras_codigo_cliente ON compras (codigo_cliente);",
            "CREATE INDEX IF NOT EXISTS idx_premios_codigo_cliente ON premios_ativos (codigo_cliente);",
            "CREATE INDEX IF NOT EXISTS idx_clientes_nascimento_mes_dia ON clientes (EXTRACT(MONTH FROM data_nascimento), EXTRACT(DAY FROM data_nascimento));",
            "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
            "CREATE INDEX IF NOT EXISTS idx_clientes_nome_gin ON clientes USING GIN (nome gin_trgm_ops);"
        ]
        for comando in comandos:
            try:
                self._executar_query(comando)
            except Exception as e:
                self.logger.warning(
                    f"Não foi possível executar comando de inicialização: '{comando[:50]}...'. Erro: {e}.")
        self.logger.info("Tabelas e índices do banco de dados verificados/criados.")

    def obter_loja_por_username(self, username: str):
        query = "SELECT * FROM lojas WHERE username = %s"
        return self._executar_query(query, (username,), fetch='one', as_dict=True)

    def obter_loja_por_identificador(self, identificador: str):
        query = "SELECT * FROM lojas WHERE identificador = %s"
        return self._executar_query(query, (identificador,), fetch='one', as_dict=True)

    def cadastrar_cliente(self, nome, telefone, email, data_nascimento, sexo, loja_origem):
        nome_capitalizado = nome.strip().title()
        conn = None
        try:
            conn = self._get_conexao()
            with conn.cursor() as cursor:
                cursor.execute("SELECT nextval('codigo_cliente_seq')")
                novo_codigo = f"{cursor.fetchone()[0]:05d}"
                query = "INSERT INTO clientes (codigo, nome, telefone, email, total_compras, total_gasto, contagem_brinde, loja_origem, data_nascimento, sexo) VALUES (%s, %s, %s, %s, 0, 0.0, 0, %s, %s, %s)"
                cursor.execute(query,
                               (novo_codigo, nome_capitalizado, telefone, email, loja_origem, data_nascimento, sexo))
            conn.commit()

            if email:
                threading.Thread(target=self.email_manager.send_welcome_email,
                                 args=(email, nome_capitalizado, novo_codigo), daemon=True).start()
            return novo_codigo
        except IntegrityError as e:
            if conn: conn.rollback()
            self.logger.error(f"Erro de integridade ao cadastrar cliente '{nome_capitalizado}': {e}")
            raise Exception("Conflito ao cadastrar: Um cliente com dados semelhantes já pode existir.")
        except Exception as e:
            if conn: conn.rollback()
            self.logger.error(f"Erro desconhecido ao cadastrar cliente: {e}")
            raise Exception(f"Não foi possível salvar cliente: {e}")
        finally:
            if conn: self._release_conexao(conn)

    def registrar_compra(self, codigo, valor, loja_compra):
        conn = self._get_conexao()
        try:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT nome, email, total_compras, total_gasto, contagem_brinde FROM clientes WHERE codigo = %s FOR UPDATE",
                    (codigo,))
                cliente_data = cursor.fetchone()
                if not cliente_data: return None, None, None, None

                total_compras_geral = cliente_data['total_compras'] + 1
                total_gasto_geral = cliente_data['total_gasto'] + valor
                contagem_brinde_nova = cliente_data['contagem_brinde'] + 1
                data_atual = datetime.now().date()

                cursor.execute(
                    "INSERT INTO compras (codigo_cliente, numero_compra_geral, valor, data, loja_compra) VALUES (%s, %s, %s, %s, %s)",
                    (codigo, total_compras_geral, valor, data_atual, loja_compra))

                ganhou_brinde = (contagem_brinde_nova == 10)
                nova_contagem_final = 0 if ganhou_brinde else contagem_brinde_nova
                media_premio, codigo_premio_gerado = 0.0, None

                if ganhou_brinde:
                    cursor.execute(
                        "SELECT valor FROM compras WHERE codigo_cliente = %s ORDER BY numero_compra_geral DESC LIMIT 10",
                        (codigo,))
                    ultimas_compras = cursor.fetchall()
                    media_premio = sum(item['valor'] for item in ultimas_compras) / 10 if ultimas_compras else 0.0
                    codigo_premio_gerado = f"{random.randint(10000, 99999)}"
                    cursor.execute(
                        "INSERT INTO premios_ativos (codigo_premio, valor_premio, codigo_cliente, data_geracao) VALUES (%s, %s, %s, %s)",
                        (codigo_premio_gerado, media_premio, codigo, data_atual))

                cursor.execute(
                    "UPDATE clientes SET total_compras = %s, total_gasto = %s, contagem_brinde = %s WHERE codigo = %s",
                    (total_compras_geral, total_gasto_geral, nova_contagem_final, codigo))
            conn.commit()

            if cliente_data['email']:
                if ganhou_brinde:
                    threading.Thread(target=self.email_manager.send_prize_won_email, args=(
                    cliente_data['email'], cliente_data['nome'], codigo_premio_gerado, media_premio),
                                     daemon=True).start()
                else:
                    threading.Thread(target=self.email_manager.send_purchase_update_email,
                                     args=(cliente_data['email'], cliente_data['nome'], contagem_brinde_nova),
                                     daemon=True).start()
            return contagem_brinde_nova, ganhou_brinde, media_premio, codigo_premio_gerado
        except Exception as e:
            if conn: conn.rollback()
            self.logger.error(f"Falha na transação de registrar compra para o código {codigo}: {e}")
            raise Exception(f"Falha ao registrar compra: {e}")
        finally:
            if conn: self._release_conexao(conn)

    def resgatar_premio(self, codigo_premio, loja_resgate):
        conn = self._get_conexao()
        try:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT valor_premio, codigo_cliente, data_geracao FROM premios_ativos WHERE codigo_premio = %s FOR UPDATE",
                    (codigo_premio,))
                premio_ativo = cursor.fetchone()
                if not premio_ativo: return False, "Prêmio inválido ou já resgatado."

                data_resgate_atual = datetime.now().date()
                cursor.execute(
                    "INSERT INTO premios_resgatados (codigo_premio, valor_premio, codigo_cliente, data_geracao, data_resgate, loja_resgate) VALUES (%s, %s, %s, %s, %s, %s)",
                    (codigo_premio, premio_ativo['valor_premio'], premio_ativo['codigo_cliente'],
                     premio_ativo['data_geracao'], data_resgate_atual, loja_resgate))
                cursor.execute("DELETE FROM premios_ativos WHERE codigo_premio = %s", (codigo_premio,))

                cursor.execute("SELECT nome, email FROM clientes WHERE codigo = %s", (premio_ativo['codigo_cliente'],))
                cliente_info = cursor.fetchone()
            conn.commit()

            if cliente_info and cliente_info['email']:
                threading.Thread(target=self.email_manager.send_redemption_success_email,
                                 args=(cliente_info['email'], cliente_info['nome']), daemon=True).start()
            return True, "Prêmio resgatado com sucesso!"
        except Exception as e:
            if conn: conn.rollback()
            self.logger.error(f"Falha na transação de resgate de prêmio {codigo_premio}: {e}")
            raise Exception(f"Falha ao resgatar prêmio: {e}")
        finally:
            if conn: self._release_conexao(conn)

    def obter_historico_ciclo_atual(self, codigo):
        self.logger.info(f"HISTORICO: Iniciando busca de histórico para o código: {codigo}")

        resultado_cliente = self._executar_query(
            "SELECT nome, total_compras, contagem_brinde FROM clientes WHERE codigo = %s", (codigo,), fetch='one',
            as_dict=True)
        if not resultado_cliente:
            self.logger.warning(f"HISTORICO: Cliente com código {codigo} não encontrado.")
            return None

        self.logger.info(f"HISTORICO: Dados do cliente encontrados: {resultado_cliente}")

        compras_neste_ciclo = 10 if resultado_cliente.get('contagem_brinde') == 0 and resultado_cliente.get(
            'total_compras', 0) > 0 else resultado_cliente.get('contagem_brinde', 0)
        self.logger.info(f"HISTORICO: Calculado para buscar as últimas {compras_neste_ciclo} compras.")

        compras_db = self._executar_query(
            "SELECT numero_compra_geral, valor, data, loja_compra FROM compras WHERE codigo_cliente = %s ORDER BY numero_compra_geral DESC LIMIT %s",
            (codigo, compras_neste_ciclo), fetch='all', as_dict=True) or []
        self.logger.info(f"HISTORICO: Compras encontradas no ciclo: {compras_db}")

        premios_ativos = self._executar_query(
            "SELECT codigo_premio, valor_premio FROM premios_ativos WHERE codigo_cliente = %s", (codigo,), fetch='all',
            as_dict=True) or []
        self.logger.info(f"HISTORICO: Prêmios ativos encontrados: {premios_ativos}")

        resposta_final = {
            **resultado_cliente,
            "historico": list(reversed(compras_db)),
            "premios_ativos": premios_ativos
        }

        self.logger.info(f"HISTORICO: Dicionário de resposta final a ser enviado: {resposta_final}")

        return resposta_final

    def buscar_cliente_por_codigo(self, codigo):
        return self._executar_query("SELECT * FROM clientes WHERE codigo = %s", (codigo,), fetch='one', as_dict=True)

    def consultar_premio(self, codigo_premio):
        return self._executar_query("SELECT valor_premio FROM premios_ativos WHERE codigo_premio = %s",
                                    (codigo_premio,), fetch='one', as_dict=True)

    def buscar_clientes_por_termo(self, termo):
        termo_like = f"%{termo}%"
        return self._executar_query(
            "SELECT codigo, nome, telefone, email FROM clientes WHERE nome ILIKE %s OR telefone LIKE %s OR email ILIKE %s OR codigo = %s ORDER BY nome LIMIT 50",
            (termo_like, termo_like, termo_like, termo), fetch='all', as_dict=True)

    def atualizar_cliente(self, codigo, nome, telefone, email, data_nascimento, sexo):
        nome_capitalizado = nome.strip().title()
        return self._executar_query(
            "UPDATE clientes SET nome = %s, telefone = %s, email = %s, data_nascimento = %s, sexo = %s WHERE codigo = %s",
            (nome_capitalizado, telefone, email, data_nascimento, sexo, codigo))

    def enviar_emails_aniversariantes_do_dia(self):
        # Implementação completa aqui...
        pass

    def enviar_emails_clientes_inativos(self):
        # Implementação completa aqui...
        pass