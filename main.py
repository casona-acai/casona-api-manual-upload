# main.py (VERSÃO 4.0.2 - CORREÇÃO FINAL NO ENDPOINT DE HISTÓRICO)

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.background import BackgroundScheduler
import logging

import auth
import models
from datamanager import DataManager
from logging_config import setup_logging

# --- CONFIGURAÇÃO INICIAL ---
setup_logging()
logger = logging.getLogger(__name__)


# --- GERENCIADOR DE CICLO DE VIDA (LIFESPAN) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando a aplicação...")
    data_manager_instance = DataManager()
    auth.set_data_manager(data_manager_instance)
    app.state.data_manager = data_manager_instance

    scheduler.add_job(data_manager_instance.enviar_emails_aniversariantes_do_dia, 'cron', hour=8, minute=0,
                      id="job_aniversariantes")
    scheduler.add_job(data_manager_instance.enviar_emails_clientes_inativos, 'cron', hour=11, minute=0,
                      id="job_clientes_inativos")

    scheduler.start()
    logger.info("Agendador de tarefas iniciado.")

    yield

    logger.info("Encerrando a aplicação...")
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Agendador de tarefas encerrado.")
    app.state.data_manager.close_pool()


# --- CRIAÇÃO DA APLICAÇÃO FASTAPI COM O LIFESPAN ---
app = FastAPI(title="Casona Fidelidade API", version="4.0.2-hotfix", lifespan=lifespan)


# --- DEPENDÊNCIA PARA OBTER O DATA MANAGER ---
def get_data_manager(request: Request) -> DataManager:
    return request.app.state.data_manager


# --- CONFIGURAÇÃO DE MIDDLEWARES E SEGURANÇA ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
origins = ["https://monumental-chaja-fb2a91.netlify.app", "http://127.0.0.1:5500", "http://localhost:8000", "null"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
    return response


# --- INSTÂNCIA DO AGENDADOR DE TAREFAS ---
scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")


# --- ENDPOINTS ---
# --- NOVA DEPENDÊNCIA DE SEGURANÇA PARA O DASHBOARD ---
def get_admin_user(current_store: dict = Depends(auth.get_current_store)):
    """Verifica se o usuário logado é o administrador."""
    if current_store.get("identificador") != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado: Requer privilégios de administrador.")
    return current_store

@app.get("/debug-historico/{codigo}", tags=["Debug"])
def debug_obter_historico(
    codigo: str,
    current_store: dict = Depends(auth.get_current_store),
    dm: DataManager = Depends(get_data_manager)
):
    """
    Endpoint temporário para depurar a saída do histórico.
    """
    logger.info(f"DEBUG: Acessando endpoint de debug para o código {codigo}")
    try:
        historico_data = dm.obter_historico_ciclo_atual(codigo)
        if not historico_data:
            raise HTTPException(status_code=404, detail="Cliente não encontrado no debug.")
        logger.info(f"DEBUG: Dados retornados: {historico_data}")
        return historico_data
    except Exception as e:
        logger.error(f"DEBUG: Erro no endpoint de debug: {e}")
        raise

@app.post("/token", summary="Autentica a loja e retorna um token de acesso", response_model=models.Token)
@limiter.limit("5/minute")
def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    loja = auth.authenticate_store(form_data.username, form_data.password)
    if not loja:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário ou senha da loja incorretos")
    access_token = auth.create_access_token(data={"sub": loja["identificador"]})
    return {"access_token": access_token, "token_type": "bearer", "store_id": loja["identificador"]}


@app.post("/public/register", summary="Permite que um cliente se cadastre via formulário online",
          status_code=status.HTTP_201_CREATED, tags=["Público"])
@limiter.limit("5/minute")
def register_public_client(cliente_data: models.ClientePayload, request: Request,
                           dm: DataManager = Depends(get_data_manager)):
    if cliente_data.website:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ação suspeita detectada.")
    try:
        codigo = dm.cadastrar_cliente(nome=cliente_data.nome, telefone=cliente_data.telefone, email=cliente_data.email,
                                      data_nascimento=cliente_data.data_nascimento, sexo=cliente_data.sexo,
                                      loja_origem="Cadastro Online")
        return {"sucesso": True, "message": "Cadastro realizado com sucesso! Bem-vindo(a) ao Clube Casona!",
                "codigo_gerado": codigo}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/clientes", summary="Cadastra um novo cliente", status_code=status.HTTP_201_CREATED,
          tags=["Interno - Lojas"])
def criar_cliente(cliente_data: models.ClientePayload, current_store: dict = Depends(auth.get_current_store),
                  dm: DataManager = Depends(get_data_manager)):
    try:
        codigo = dm.cadastrar_cliente(loja_origem=current_store["identificador"],
                                      **cliente_data.dict(exclude={'website'}))
        return {"status": "sucesso", "message": "Cliente cadastrado com sucesso!", "codigo_gerado": codigo}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/clientes/buscar", summary="Busca clientes por termo", tags=["Interno - Lojas"])
def buscar_clientes(termo: str, current_store: dict = Depends(auth.get_current_store),
                    dm: DataManager = Depends(get_data_manager)):
    try:
        return dm.buscar_clientes_por_termo(termo)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/clientes/{codigo}", summary="Busca um cliente pelo código", tags=["Interno - Lojas"])
def buscar_cliente_por_codigo(codigo: str, current_store: dict = Depends(auth.get_current_store),
                              dm: DataManager = Depends(get_data_manager)):
    try:
        cliente = dm.buscar_cliente_por_codigo(codigo)
        if not cliente: raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        return cliente
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.put("/clientes/{codigo}", summary="Atualiza os dados de um cliente", tags=["Interno - Lojas"])
def atualizar_cliente_endpoint(codigo: str, cliente_data: models.ClienteUpdatePayload,
                               current_store: dict = Depends(auth.get_current_store),
                               dm: DataManager = Depends(get_data_manager)):
    try:
        if dm.atualizar_cliente(codigo=codigo, **cliente_data.dict()):
            return {"status": "sucesso", "message": "Cliente atualizado com sucesso."}
        raise HTTPException(status_code=400, detail="Não foi possível atualizar o cliente.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/compras", summary="Registra uma nova compra", tags=["Interno - Lojas"])
def adicionar_compra(compra_data: models.CompraPayload, current_store: dict = Depends(auth.get_current_store),
                     dm: DataManager = Depends(get_data_manager)):
    try:
        contagem, ganhou, media, cod_premio = dm.registrar_compra(codigo=compra_data.codigo_cliente,
                                                                  valor=compra_data.valor,
                                                                  loja_compra=current_store["identificador"])
        if contagem is None: raise HTTPException(status_code=404,
                                                 detail=f"Cliente {compra_data.codigo_cliente} não encontrado.")
        return {"contagem_atual": contagem, "ganhou_brinde": ganhou, "valor_premio": media, "codigo_premio": cod_premio}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/historico/{codigo}", summary="Obtém o histórico do ciclo de compras atual", tags=["Interno - Lojas"])
def obter_historico(codigo: str, current_store: dict = Depends(auth.get_current_store),
                    dm: DataManager = Depends(get_data_manager)):
    try:
        # <<< AQUI ESTÁ A CORREÇÃO FINAL E CORRETA >>>
        # Chamando o método correto que monta o dicionário completo.
        historico_data = dm.obter_historico_ciclo_atual(codigo)

        if not historico_data:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")

        # Retorna o dicionário completo, que agora garantidamente contém a chave 'historico'.
        return historico_data
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Erro ao obter histórico para o código {codigo}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/premios/consultar/{codigo_premio}", summary="Consulta um prêmio ativo", tags=["Interno - Lojas"])
def consultar_premio_endpoint(codigo_premio: str, current_store: dict = Depends(auth.get_current_store),
                              dm: DataManager = Depends(get_data_manager)):
    try:
        premio = dm.consultar_premio(codigo_premio)
        if not premio: raise HTTPException(status_code=404, detail="Código de prêmio inválido ou já utilizado.")
        return premio
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/premios/resgatar/{codigo_premio}", summary="Resgata um prêmio", tags=["Interno - Lojas"])
def resgatar_premio_endpoint(codigo_premio: str, current_store: dict = Depends(auth.get_current_store),
                             dm: DataManager = Depends(get_data_manager)):
    try:
        sucesso, mensagem = dm.resgatar_premio(codigo_premio, loja_resgate=current_store["identificador"])
        if sucesso:
            return {"status": "sucesso", "message": mensagem}
        raise HTTPException(status_code=400, detail=mensagem)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/dashboard/data", response_model=models.DashboardDataResponse, tags=["Dashboard"])
def get_dashboard_data(
    admin: dict = Depends(get_admin_user),
    dm: DataManager = Depends(get_data_manager)
):
    """Fornece todos os dados brutos para o dashboard."""
    try:
        return dm.get_all_dashboard_data()
    except Exception as e:
        logger.error(f"Erro ao buscar dados para o dashboard: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao processar dados do dashboard.")

@app.get("/dashboard/lojas", response_model=List[str], tags=["Dashboard"])
def get_dashboard_lojas(
    admin: dict = Depends(get_admin_user),
    dm: DataManager = Depends(get_data_manager)
):
    """Retorna uma lista de todas as lojas únicas."""
    try:
        return dm.get_all_lojas_from_db()
    except Exception as e:
        logger.error(f"Erro ao buscar lista de lojas para o dashboard: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao buscar lojas.")