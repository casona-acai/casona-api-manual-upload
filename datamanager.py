# datamanager.py

import psycopg2
from psycopg2 import OperationalError, IntegrityError, extras
from psycopg2 import pool
from datetime import datetime, timedelta
import random
import threading
import logging

import email_manager
import config


class DataManager:
    """
    Classe que gerencia toda a lógica de banco de dados para o sistema de fidelidade por pontos.
    """

    def __init__(self, run_init=True):
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

        if run_init:
            self._iniciar_banco_de_dados()

    def _get_conexao(self):
        return self.connection_pool.getconn()

    def _release_conexao(self, conn):
        self.connection_pool.putconn(conn)

    def close_pool(self):
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
        comandos_migracao = [
            '''ALTER TABLE clientes ADD COLUMN IF NOT EXISTS pontos_acumulados INTEGER NOT NULL DEFAULT 0;''',
            '''ALTER TABLE clientes ADD COLUMN IF NOT EXISTS compras_ciclo_atual INTEGER NOT NULL DEFAULT 0;''',
            '''ALTER TABLE compras ADD COLUMN IF NOT EXISTS pontos_gerados INTEGER NOT NULL DEFAULT 0;''',
            '''ALTER TABLE clientes DROP COLUMN IF EXISTS contagem_brinde;''',
            '''DROP TABLE IF EXISTS premios_ativos;''',
            '''CREATE TABLE IF NOT EXISTS premios_ativos (
                codigo_premio TEXT PRIMARY KEY,
                codigo_cliente TEXT NOT NULL UNIQUE,
                pontos_premio INTEGER NOT NULL,
                data_geracao DATE NOT NULL,
                data_ultima_atualizacao DATE NOT NULL,
                FOREIGN KEY (codigo_cliente) REFERENCES clientes (codigo) ON DELETE CASCADE
            );''',
            '''DROP TABLE IF EXISTS premios_resgatados;''',
            '''CREATE TABLE IF NOT EXISTS premios_resgatados (
                id SERIAL PRIMARY KEY,
                codigo_premio TEXT,
                codigo_cliente TEXT NOT NULL,
                pontos_resgatados INTEGER NOT NULL,
                valor_resgatado REAL NOT NULL,
                data_geracao DATE,
                data_resgate DATE NOT NULL,
                loja_resgate TEXT
            );'''
        ]

        comandos_estrutura = [
            '''CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, identificador TEXT UNIQUE NOT NULL, hashed_password TEXT NOT NULL, nome_loja TEXT, is_active BOOLEAN NOT NULL DEFAULT TRUE)''',
            '''CREATE TABLE IF NOT EXISTS clientes (
                codigo TEXT PRIMARY KEY, nome TEXT NOT NULL, telefone TEXT, email TEXT, cep TEXT, 
                total_compras INTEGER NOT NULL DEFAULT 0, total_gasto REAL NOT NULL DEFAULT 0.0,
                pontos_acumulados INTEGER NOT NULL DEFAULT 0, compras_ciclo_atual INTEGER NOT NULL DEFAULT 0,
                loja_origem TEXT, data_nascimento DATE, ano_ultimo_email_aniversario INTEGER, sexo TEXT,
                data_ultimo_email_inatividade DATE
            )''',
            '''CREATE TABLE IF NOT EXISTS compras (
                id SERIAL PRIMARY KEY, codigo_cliente TEXT NOT NULL, numero_compra_geral INTEGER NOT NULL,
                valor REAL NOT NULL, pontos_gerados INTEGER NOT NULL, data DATE NOT NULL, loja_compra TEXT,
                FOREIGN KEY (codigo_cliente) REFERENCES clientes (codigo) ON DELETE CASCADE
            )''',
            "CREATE SEQUENCE IF NOT EXISTS codigo_cliente_seq START 1;",
            "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
            "CREATE INDEX IF NOT EXISTS idx_clientes_nome_gin ON clientes USING GIN (nome gin_trgm_ops);"
        ]

        self.logger.info("Iniciando verificação e migração do banco de dados...")
        for comando in comandos_migracao:
            try:
                self._executar_query(comando)
            except Exception as e:
                self.logger.warning(f"Comando de migração falhou (pode ser normal): '{comando[:50]}...'. Erro: {e}")

        self.logger.info("Verificando estrutura principal do banco de dados...")
        for comando in comandos_estrutura:
            try:
                self._executar_query(comando)
            except Exception as e:
                self.logger.warning(f"Comando de inicialização falhou: '{comando[:50]}...'. Erro: {e}.")

        self.logger.info("Banco de dados pronto para operar com o sistema de pontos.")

    def _calcular_pontos_validos(self, codigo_cliente: str, cursor) -> int:
        data_limite = datetime.now().date() - timedelta(days=180)
        query = "SELECT COALESCE(SUM(pontos_gerados), 0) as total_pontos FROM compras WHERE codigo_cliente = %s AND data >= %s"
        cursor.execute(query, (codigo_cliente, data_limite))
        resultado = cursor.fetchone()
        pontos_validos = resultado['total_pontos'] if resultado else 0
        cursor.execute("UPDATE clientes SET pontos_acumulados = %s WHERE codigo = %s", (pontos_validos, codigo_cliente))
        return pontos_validos

    def obter_loja_por_username(self, username: str):
        query = "SELECT * FROM lojas WHERE username = %s"
        return self._executar_query(query, (username,), fetch='one', as_dict=True)

    def obter_loja_por_identificador(self, identificador: str):
        query = "SELECT * FROM lojas WHERE identificador = %s"
        return self._executar_query(query, (identificador,), fetch='one', as_dict=True)

    def cadastrar_cliente(self, nome, telefone, email, data_nascimento, sexo, cep, loja_origem):
        nome_capitalizado = nome.strip().title()
        conn = None
        try:
            conn = self._get_conexao()
            with conn.cursor() as cursor:
                cursor.execute("SELECT nextval('codigo_cliente_seq')")
                novo_codigo = f"{cursor.fetchone()[0]:05d}"
                query = """
                    INSERT INTO clientes (codigo, nome, telefone, email, cep, loja_origem, data_nascimento, sexo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    novo_codigo, nome_capitalizado, telefone, email, cep, loja_origem, data_nascimento, sexo))
            conn.commit()

            if email:
                threading.Thread(target=self.email_manager.send_welcome_email,
                                 args=(email, nome_capitalizado, novo_codigo), daemon=True).start()
            return novo_codigo
        except IntegrityError as e:
            if conn: conn.rollback()
            raise Exception("Conflito ao cadastrar: Um cliente com dados semelhantes já pode existir.")
        except Exception as e:
            if conn: conn.rollback()
            raise Exception(f"Não foi possível salvar cliente: {e}")
        finally:
            if conn: self._release_conexao(conn)

    def registrar_compra(self, codigo, valor, loja_compra):
        conn = self._get_conexao()
        try:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT nome, email, COALESCE(total_compras, 0) as total_compras, COALESCE(compras_ciclo_atual, 0) as compras_ciclo_atual FROM clientes WHERE codigo = %s FOR UPDATE",
                    (codigo,))
                cliente_data = cursor.fetchone()
                if not cliente_data: return None

                pontos_gerados = int(valor * 100)
                data_atual = datetime.now().date()

                compras_ciclo_atual_novo = cliente_data['compras_ciclo_atual'] + 1
                total_compras_geral = cliente_data['total_compras'] + 1

                cursor.execute(
                    "INSERT INTO compras (codigo_cliente, numero_compra_geral, valor, pontos_gerados, data, loja_compra) VALUES (%s, %s, %s, %s, %s, %s)",
                    (codigo, total_compras_geral, valor, pontos_gerados, data_atual, loja_compra))

                cursor.execute(
                    "UPDATE clientes SET total_compras = COALESCE(total_compras, 0) + 1, total_gasto = COALESCE(total_gasto, 0.0) + %s, compras_ciclo_atual = %s WHERE codigo = %s",
                    (valor, compras_ciclo_atual_novo, codigo))

                pontos_totais_validos = self._calcular_pontos_validos(codigo, cursor)

                codigo_premio_ativo = None
                premio_gerado_agora = False
                cursor.execute("SELECT codigo_premio FROM premios_ativos WHERE codigo_cliente = %s", (codigo,))
                premio_ativo = cursor.fetchone()

                if premio_ativo:
                    codigo_premio_ativo = premio_ativo['codigo_premio']
                    cursor.execute(
                        "UPDATE premios_ativos SET pontos_premio = pontos_premio + %s, data_ultima_atualizacao = %s WHERE codigo_cliente = %s",
                        (pontos_gerados, data_atual, codigo))
                elif compras_ciclo_atual_novo >= 5 and pontos_totais_validos > 0:
                    codigo_premio_ativo = f"{random.randint(10000, 99999)}"
                    cursor.execute(
                        "INSERT INTO premios_ativos (codigo_premio, codigo_cliente, pontos_premio, data_geracao, data_ultima_atualizacao) VALUES (%s, %s, %s, %s, %s)",
                        (codigo_premio_ativo, codigo, pontos_totais_validos, data_atual, data_atual))
                    premio_gerado_agora = True

            conn.commit()

            # Adicionamos os pontos gerados nesta compra ao resultado que será enviado por e-mail
            resultado_compra = {
                "pontos_nesta_compra": pontos_gerados,
                "compras_no_ciclo": compras_ciclo_atual_novo,
                "pontos_acumulados": pontos_totais_validos,
                "codigo_premio_ativo": codigo_premio_ativo,
                "premio_gerado_nesta_compra": premio_gerado_agora
            }

            if cliente_data.get('email'):
                threading.Thread(
                    target=self.email_manager.send_purchase_update_email,
                    args=(cliente_data['email'], cliente_data['nome'], resultado_compra),
                    daemon=True
                ).start()

            return resultado_compra
        except Exception as e:
            if conn: conn.rollback()
            self.logger.error(f"Falha na transação de registrar compra para o código {codigo}: {e}", exc_info=True)
            raise Exception(f"Falha ao registrar compra: {e}")
        finally:
            if conn: self._release_conexao(conn)

    def obter_status_fidelidade(self, codigo):
        conn = self._get_conexao()
        try:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM clientes WHERE codigo = %s", (codigo,))
                cliente_data = cursor.fetchone()
                if not cliente_data: return None

                pontos_validos = self._calcular_pontos_validos(codigo, cursor)
                cliente_data['pontos_acumulados'] = pontos_validos

                cursor.execute("SELECT codigo_premio, pontos_premio FROM premios_ativos WHERE codigo_cliente = %s",
                               (codigo,))
                premio_ativo = cursor.fetchone()

                data_limite = datetime.now().date() - timedelta(days=180)
                cursor.execute(
                    "SELECT valor, pontos_gerados, data, loja_compra FROM compras WHERE codigo_cliente = %s AND data >= %s ORDER BY data DESC",
                    (codigo, data_limite))
                historico_compras_validas = cursor.fetchall()

            conn.commit()

            return {
                "cliente": cliente_data,
                "resumo_fidelidade": {
                    "pontos_acumulados": pontos_validos,
                    "compras_no_ciclo_atual": cliente_data.get('compras_ciclo_atual', 0),
                    "habilitado_para_gerar_premio": cliente_data.get('compras_ciclo_atual', 0) >= 5,
                    "premio_ativo": {
                        "codigo_premio": premio_ativo['codigo_premio'] if premio_ativo else None,
                        "pontos_premio": premio_ativo['pontos_premio'] if premio_ativo else 0,
                        "valor_resgate": round(premio_ativo['pontos_premio'] / 100, 2) if premio_ativo else 0.0,
                    }
                },
                "historico_compras_validas": historico_compras_validas
            }
        except Exception as e:
            if conn: conn.rollback()
            raise
        finally:
            if conn: self._release_conexao(conn)

    def consultar_premio(self, codigo_premio):
        query = """
            SELECT pa.codigo_premio, pa.pontos_premio, pa.codigo_cliente, c.nome as nome_cliente
            FROM premios_ativos pa JOIN clientes c ON pa.codigo_cliente = c.codigo
            WHERE pa.codigo_premio = %s
        """
        premio = self._executar_query(query, (codigo_premio,), fetch='one', as_dict=True)
        if premio:
            premio['valor_resgate'] = round(premio['pontos_premio'] / 100, 2)
        return premio

    def resgatar_premio(self, codigo_premio, loja_resgate):
        conn = self._get_conexao()
        try:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM premios_ativos WHERE codigo_premio = %s FOR UPDATE", (codigo_premio,))
                premio_ativo = cursor.fetchone()
                if not premio_ativo: return False, "Prêmio inválido ou já resgatado."

                codigo_cliente = premio_ativo['codigo_cliente']
                pontos_resgatados = premio_ativo['pontos_premio']
                valor_resgatado = round(pontos_resgatados / 100, 2)
                data_resgate_atual = datetime.now().date()

                cursor.execute(
                    "INSERT INTO premios_resgatados (codigo_premio, codigo_cliente, pontos_resgatados, valor_resgatado, data_geracao, data_resgate, loja_resgate) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (codigo_premio, codigo_cliente, pontos_resgatados, valor_resgatado, premio_ativo['data_geracao'],
                     data_resgate_atual, loja_resgate))

                cursor.execute("DELETE FROM premios_ativos WHERE codigo_premio = %s", (codigo_premio,))

                cursor.execute("UPDATE clientes SET compras_ciclo_atual = 0 WHERE codigo = %s", (codigo_cliente,))

                self._calcular_pontos_validos(codigo_cliente, cursor)

            conn.commit()
            return True, f"Prêmio de R$ {valor_resgatado:.2f} resgatado com sucesso!"
        except Exception as e:
            if conn: conn.rollback()
            raise Exception(f"Falha ao resgatar prêmio: {e}")
        finally:
            if conn: self._release_conexao(conn)

    def buscar_clientes_por_termo(self, termo):
        termo_like = f"%{termo}%"
        return self._executar_query(
            "SELECT codigo, nome, telefone, email FROM clientes WHERE nome ILIKE %s OR telefone LIKE %s OR email ILIKE %s OR codigo = %s ORDER BY nome LIMIT 50",
            (termo_like, termo_like, termo_like, termo), fetch='all', as_dict=True)

    def buscar_cliente_por_codigo(self, codigo):
        return self._executar_query("SELECT * FROM clientes WHERE codigo = %s", (codigo,), fetch='one', as_dict=True)

    def atualizar_cliente(self, codigo, nome, telefone, email, data_nascimento, sexo, cep):
        nome_capitalizado = nome.strip().title()
        query = "UPDATE clientes SET nome = %s, telefone = %s, email = %s, data_nascimento = %s, sexo = %s, cep = %s WHERE codigo = %s"
        return self._executar_query(query, (nome_capitalizado, telefone, email, data_nascimento, sexo, cep, codigo))

    def enviar_emails_aniversariantes_do_dia(self):
        self.logger.info("(TAREFA AGENDADA) Verificando aniversariantes do dia...")
        pass

    def enviar_emails_clientes_inativos(self):
        self.logger.info("(TAREFA AGENDADA) Verificando clientes inativos...")
        pass

    def get_all_dashboard_data(self):
        conn = self._get_conexao()
        try:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM clientes ORDER BY nome")
                clientes = cursor.fetchall()
                cursor.execute("SELECT * FROM compras")
                compras = cursor.fetchall()
                cursor.execute("SELECT * FROM premios_resgatados")
                premios_resgatados = cursor.fetchall()
            return {"clientes": clientes, "compras": compras, "premios_resgatados": premios_resgatados}
        finally:
            if conn: self._release_conexao(conn)

    def get_all_lojas_from_db(self):
        query = """
            SELECT DISTINCT loja FROM (
                SELECT loja_origem as loja FROM clientes WHERE loja_origem IS NOT NULL AND loja_origem != ''
                UNION
                SELECT loja_compra as loja FROM compras WHERE loja_compra IS NOT NULL AND loja_compra != ''
                UNION
                SELECT loja_resgate as loja FROM premios_resgatados WHERE loja_resgate IS NOT NULL AND loja_resgate != ''
            ) as lojas_unicas WHERE loja IS NOT NULL ORDER BY loja;
        """
        rows = self._executar_query(query, fetch='all')
        return [row[0] for row in rows] if rows else []