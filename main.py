# main.py (VERSÃO MODIFICADA E LIMPA)

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
from typing import List

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
    logger.info("Iniciando a aplicação (worker)...")

    # Criamos a instância do DataManager, mas informamos para NÃO rodar a migração.
    # A migração agora é responsabilidade do script `migrate.py` no build.
    data_manager_instance = DataManager(run_init=False)
    auth.set_data_manager(data_manager_instance)
    app.state.data_manager = data_manager_instance

    yield

    logger.info("Encerrando a aplicação (worker)...")
    # Apenas fechamos o pool de conexões deste worker.
    app.state.data_manager.close_pool()


# --- CRIAÇÃO DA APLICAÇÃO FASTAPI COM O LIFESPAN ---
app = FastAPI(title="Casona Fidelidade API", version="5.0.0-pontos", lifespan=lifespan)


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
    return response


#
# >>> TODA A LÓGICA DO APSCHEDULER FOI REMOVIDA DESTE ARQUIVO <<<
#

# --- DEPENDÊNCIA DE SEGURANÇA PARA O DASHBOARD ---
def get_admin_user(current_store: dict = Depends(auth.get_current_store)):
    if current_store.get("identificador") != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Acesso negado: Requer privilégios de administrador.")
    return current_store


# --- ENDPOINTS ---
# O resto do arquivo main.py permanece EXATAMENTE O MESMO.
# Cole todos os seus endpoints aqui, eles não precisam de nenhuma alteração.

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
        codigo = dm.cadastrar_cliente(loja_origem="Cadastro Online", **cliente_data.dict(exclude={'website'}))
        return {"sucesso": True, "message": "Cadastro realizado com sucesso! Bem-vindo(a) ao Clube Casona!",
                "codigo_gerado": codigo}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/clientes", summary="Cadastra um novo cliente (interno)", status_code=status.HTTP_201_CREATED,
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
    return dm.buscar_clientes_por_termo(termo)


@app.get("/clientes/{codigo}", summary="Busca dados cadastrais de um cliente", tags=["Interno - Lojas"])
def buscar_cliente_por_codigo(codigo: str, current_store: dict = Depends(auth.get_current_store),
                              dm: DataManager = Depends(get_data_manager)):
    cliente = dm.buscar_cliente_por_codigo(codigo)
    if not cliente: raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return cliente


@app.put("/clientes/{codigo}", summary="Atualiza os dados de um cliente", tags=["Interno - Lojas"])
def atualizar_cliente_endpoint(codigo: str, cliente_data: models.ClienteUpdatePayload,
                               current_store: dict = Depends(auth.get_current_store),
                               dm: DataManager = Depends(get_data_manager)):
    if dm.atualizar_cliente(codigo=codigo, **cliente_data.dict()):
        return {"status": "sucesso", "message": "Cliente atualizado com sucesso."}
    raise HTTPException(status_code=400, detail="Não foi possível atualizar o cliente.")


@app.post("/compras", summary="Registra uma nova compra e atualiza os pontos", tags=["Interno - Lojas"])
def adicionar_compra(compra_data: models.CompraPayload, current_store: dict = Depends(auth.get_current_store),
                     dm: DataManager = Depends(get_data_manager)):
    try:
        resultado = dm.registrar_compra(codigo=compra_data.codigo_cliente, valor=compra_data.valor,
                                        loja_compra=current_store["identificador"])
        if resultado is None:
            raise HTTPException(status_code=404, detail=f"Cliente {compra_data.codigo_cliente} não encontrado.")
        return {"sucesso": True, "message": "Compra registrada com sucesso!", **resultado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/fidelidade/{codigo}", summary="Obtém o status de fidelidade e histórico de um cliente",
         tags=["Interno - Lojas"])
def obter_status_fidelidade_endpoint(codigo: str, current_store: dict = Depends(auth.get_current_store),
                                     dm: DataManager = Depends(get_data_manager)):
    status_data = dm.obter_status_fidelidade(codigo)
    if not status_data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return status_data


@app.get("/premios/consultar/{codigo_premio}", summary="Consulta um prêmio ativo pelo código", tags=["Interno - Lojas"])
def consultar_premio_endpoint(codigo_premio: str, current_store: dict = Depends(auth.get_current_store),
                              dm: DataManager = Depends(get_data_manager)):
    premio = dm.consultar_premio(codigo_premio)
    if not premio:
        raise HTTPException(status_code=404, detail="Código de prêmio inválido ou já utilizado.")
    return premio


@app.post("/premios/resgatar/{codigo_premio}", summary="Resgata um prêmio usando o código", tags=["Interno - Lojas"])
def resgatar_premio_endpoint(codigo_premio: str, current_store: dict = Depends(auth.get_current_store),
                             dm: DataManager = Depends(get_data_manager)):
    try:
        sucesso, mensagem = dm.resgatar_premio(codigo_premio, loja_resgate=current_store["identificador"])
        if sucesso:
            return {"status": "sucesso", "message": mensagem}
        raise HTTPException(status_code=400, detail=mensagem)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/data", response_model=models.DashboardDataResponse, tags=["Dashboard"])
def get_dashboard_data(admin: dict = Depends(get_admin_user), dm: DataManager = Depends(get_data_manager)):
    return dm.get_all_dashboard_data()


@app.get("/dashboard/lojas", response_model=List[str], tags=["Dashboard"])
def get_dashboard_lojas(admin: dict = Depends(get_admin_user), dm: DataManager = Depends(get_data_manager)):
    return dm.get_all_lojas_from_db()