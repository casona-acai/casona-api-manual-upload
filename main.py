# main.py (VERSÃO FINAL - GERENCIADOR CENTRAL)

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import logging

import auth
import models
from datamanager import DataManager
from logging_config import setup_logging

# --- CONFIGURAÇÃO INICIAL ---
setup_logging()
logger = logging.getLogger(__name__)
app = FastAPI(title="Casona Fidelidade API", version="3.2.0-central-manager")

# --- GERENCIAMENTO CENTRALIZADO DA INSTÂNCIA DO DATAMANAGER ---
data_manager_instance = DataManager()
auth.set_data_manager(data_manager_instance)

# --- CONFIGURAÇÃO DA API E MIDDLEWARES ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

origins = ["https://monumental-chaja-fb2a91.netlify.app", "http://127.0.0.1:5500", "http://localhost:8000", "null"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
    return response

# --- AGENDADOR DE TAREFAS ---
def job_aniversariantes():
    logger.info("EXECUTANDO TAREFA AGENDADA: Verificação de aniversariantes.")
    data_manager_instance.enviar_emails_aniversariantes_do_dia()

def job_clientes_inativos():
    logger.info("EXECUTANDO TAREFA AGENDADA: Verificação de clientes inativos.")
    data_manager_instance.enviar_emails_clientes_inativos()

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
scheduler.add_job(job_aniversariantes, 'cron', hour=8, minute=0)
scheduler.add_job(job_clientes_inativos, 'cron', hour=11, minute=0)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())


# --- ENDPOINTS ---
@app.post("/token", summary="Autentica a loja e retorna um token de acesso", response_model=models.Token)
@limiter.limit("5/minute")
def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    loja = auth.authenticate_store(form_data.username, form_data.password)
    if not loja:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário ou senha da loja incorretos")
    access_token = auth.create_access_token(data={"sub": loja["identificador"]})
    logger.info(f"Login bem-sucedido para a loja: {loja['identificador']}")
    return {"access_token": access_token, "token_type": "bearer", "store_id": loja["identificador"]}

@app.post("/public/register", summary="Permite que um cliente se cadastre via formulário online", status_code=status.HTTP_201_CREATED, tags=["Público"])
@limiter.limit("5/minute")
def register_public_client(cliente_data: models.ClientePayload, request: Request):
    if cliente_data.website:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ação suspeita detectada.")
    try:
        codigo = data_manager_instance.cadastrar_cliente(nome=cliente_data.nome, telefone=cliente_data.telefone, email=cliente_data.email, data_nascimento=cliente_data.data_nascimento, sexo=cliente_data.sexo, loja_origem="Cadastro Online")
        return {"sucesso": True, "message": "Cadastro realizado com sucesso! Bem-vindo(a) ao Clube Casona!", "codigo_gerado": codigo}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.post("/clientes", summary="Cadastra um novo cliente", status_code=status.HTTP_201_CREATED, tags=["Interno - Lojas"])
def criar_cliente(cliente_data: models.ClientePayload, current_store: dict = Depends(auth.get_current_store)):
    try:
        codigo = data_manager_instance.cadastrar_cliente(loja_origem=current_store["identificador"], **cliente_data.dict(exclude={'website'}))
        return {"status": "sucesso", "message": "Cliente cadastrado com sucesso!", "codigo_gerado": codigo}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.get("/clientes/buscar", summary="Busca clientes por termo", tags=["Interno - Lojas"])
def buscar_clientes(termo: str, current_store: dict = Depends(auth.get_current_store)):
    try:
        return data_manager_instance.buscar_clientes_por_termo(termo)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/clientes/{codigo}", summary="Busca um cliente pelo código", tags=["Interno - Lojas"])
def buscar_cliente_por_codigo(codigo: str, current_store: dict = Depends(auth.get_current_store)):
    try:
        cliente = data_manager_instance.buscar_cliente_por_codigo(codigo)
        if not cliente: raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        return cliente
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.put("/clientes/{codigo}", summary="Atualiza os dados de um cliente", tags=["Interno - Lojas"])
def atualizar_cliente_endpoint(codigo: str, cliente_data: models.ClienteUpdatePayload, current_store: dict = Depends(auth.get_current_store)):
    try:
        if data_manager_instance.atualizar_cliente(codigo=codigo, **cliente_data.dict()):
            return {"status": "sucesso", "message": "Cliente atualizado com sucesso."}
        raise HTTPException(status_code=400, detail="Não foi possível atualizar o cliente.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/compras", summary="Registra uma nova compra", tags=["Interno - Lojas"])
def adicionar_compra(compra_data: models.CompraPayload, current_store: dict = Depends(auth.get_current_store)):
    try:
        contagem, ganhou, media, cod_premio = data_manager_instance.registrar_compra(codigo=compra_data.codigo_cliente, valor=compra_data.valor, loja_compra=current_store["identificador"])
        if contagem is None: raise HTTPException(status_code=404, detail=f"Cliente {compra_data.codigo_cliente} não encontrado.")
        return {"contagem_atual": contagem, "ganhou_brinde": ganhou, "valor_premio": media, "codigo_premio": cod_premio}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/historico/{codigo}", summary="Obtém o histórico do ciclo de compras atual", tags=["Interno - Lojas"])
def obter_historico(codigo: str, current_store: dict = Depends(auth.get_current_store)):
    try:
        historico_data = data_manager_instance.obter_historico_ciclo_atual(codigo)
        if not historico_data: raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        return historico_data
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/premios/consultar/{codigo_premio}", summary="Consulta um prêmio ativo", tags=["Interno - Lojas"])
def consultar_premio_endpoint(codigo_premio: str, current_store: dict = Depends(auth.get_current_store)):
    try:
        premio = data_manager_instance.consultar_premio(codigo_premio)
        if not premio: raise HTTPException(status_code=404, detail="Código de prêmio inválido ou já utilizado.")
        return premio
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/premios/resgatar/{codigo_premio}", summary="Resgata um prêmio", tags=["Interno - Lojas"])
def resgatar_premio_endpoint(codigo_premio: str, current_store: dict = Depends(auth.get_current_store)):
    try:
        sucesso, mensagem = data_manager_instance.resgatar_premio(codigo_premio, loja_resgate=current_store["identificador"])
        if sucesso:
            return {"status": "sucesso", "message": mensagem}
        raise HTTPException(status_code=400, detail=mensagem)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))