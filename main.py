# main.py
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

# --- CONFIGURAÇÃO DO LOGGING ---
setup_logging()
logger = logging.getLogger(__name__)

# --- CONFIGURAÇÃO DA API E SEGURANÇA ---
limiter = Limiter(key_func=get_remote_address)
# Atualizando a versão para refletir a nova arquitetura de autenticação
app = FastAPI(title="Casona Fidelidade API", version="3.0.0-db-auth")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CONFIGURAÇÃO DE CORS ---
origins = [
    "https://monumental-chaja-fb2a91.netlify.app",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "null"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MIDDLEWARE DE CABEÇALHOS DE SEGURANÇA ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
    return response

# --- INICIALIZAÇÃO DO GERENCIADOR DE DADOS PARA OS ENDPOINTS ---
# <<< ESTA LINHA É IMPORTANTE E DEVE PERMANECER >>>
# Os endpoints definidos neste arquivo precisam desta instância para interagir com o banco.
data_manager = DataManager()


# --- AGENDADOR DE TAREFAS ---
def job_aniversariantes():
    logger.info("EXECUTANDO TAREFA AGENDADA: Verificação de aniversariantes.")
    data_manager.enviar_emails_aniversariantes_do_dia()

def job_clientes_inativos():
    logger.info("EXECUTANDO TAREFA AGENDADA: Verificação de clientes inativos.")
    data_manager.enviar_emails_clientes_inativos()

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
scheduler.add_job(job_aniversariantes, 'cron', hour=8, minute=0)
scheduler.add_job(job_clientes_inativos, 'cron', hour=11, minute=0)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())


# --- ENDPOINTS DE AUTENTICAÇÃO E UTILITÁRIOS ---
@app.post("/token", summary="Autentica a loja e retorna um token de acesso", response_model=models.Token)
@limiter.limit("5/minute")
def login_for_access_token(
    request: Request,  # <<< ADICIONE ESTE PARÂMETRO AQUI
    form_data: OAuth2PasswordRequestForm = Depends()
):
    loja = auth.authenticate_store(form_data.username, form_data.password)
    if not loja:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha da loja incorretos"
        )
    # O identificador da loja vem do banco de dados.
    access_token = auth.create_access_token(data={"sub": loja["identificador"]})
    logger.info(f"Login bem-sucedido para a loja: {loja['identificador']}")
    return {"access_token": access_token, "token_type": "bearer", "store_id": loja["identificador"]}

# --- ENDPOINTS PÚBLICOS ---
@app.post(
    "/public/register",
    summary="Permite que um cliente se cadastre via formulário online",
    status_code=status.HTTP_201_CREATED,
    tags=["Público"]
)
@limiter.limit("5/minute")
def register_public_client(cliente_data: models.ClientePayload, request: Request):
    if cliente_data.website:
        logger.warning(f"Detecção de Honeypot. IP: {request.client.host}. Dados: {cliente_data.dict()}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ação suspeita detectada.")
    try:
        codigo = data_manager.cadastrar_cliente(
            nome=cliente_data.nome,
            telefone=cliente_data.telefone,
            email=cliente_data.email,
            data_nascimento=cliente_data.data_nascimento,
            sexo=cliente_data.sexo,
            loja_origem="Cadastro Online"
        )
        logger.info(f"Novo cliente cadastrado online: {codigo} - {cliente_data.nome}")
        return {"sucesso": True, "message": "Cadastro realizado com sucesso! Bem-vindo(a) ao Clube Casona!",
                "codigo_gerado": codigo}
    except Exception as e:
        logger.error(f"Erro no cadastro público: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# --- ENDPOINTS INTERNOS (PARA LOJAS AUTENTICADAS) ---
@app.post("/clientes", summary="Cadastra um novo cliente (Requer Autenticação)", status_code=status.HTTP_201_CREATED,
          tags=["Interno - Lojas"])
def criar_cliente(cliente_data: models.ClientePayload, current_store: dict = Depends(auth.get_current_store)):
    try:
        codigo = data_manager.cadastrar_cliente(loja_origem=current_store["identificador"],
                                                **cliente_data.dict(exclude={'website'}))
        return {"status": "sucesso", "message": "Cliente cadastrado com sucesso!", "codigo_gerado": codigo}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/clientes/buscar", summary="Busca clientes por nome, telefone, email ou código", tags=["Interno - Lojas"])
def buscar_clientes(termo: str, current_store: dict = Depends(auth.get_current_store)):
    try:
        clientes = data_manager.buscar_clientes_por_termo(termo)
        return clientes
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/clientes/{codigo}", summary="Busca um cliente específico pelo código", tags=["Interno - Lojas"])
def buscar_cliente_por_codigo(codigo: str, current_store: dict = Depends(auth.get_current_store)):
    try:
        cliente = data_manager.buscar_cliente_por_codigo(codigo)
        if not cliente: raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        return cliente
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.put("/clientes/{codigo}", summary="Atualiza os dados de um cliente", tags=["Interno - Lojas"])
def atualizar_cliente_endpoint(codigo: str, cliente_data: models.ClienteUpdatePayload,
                               current_store: dict = Depends(auth.get_current_store)):
    try:
        sucesso = data_manager.atualizar_cliente(codigo=codigo, **cliente_data.dict())
        if sucesso:
            return {"status": "sucesso", "message": "Cliente atualizado com sucesso."}
        else:
            raise HTTPException(status_code=400, detail="Não foi possível atualizar o cliente.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/compras", summary="Registra uma nova compra para um cliente", tags=["Interno - Lojas"])
def adicionar_compra(compra_data: models.CompraPayload, current_store: dict = Depends(auth.get_current_store)):
    try:
        contagem, ganhou, media, cod_premio = data_manager.registrar_compra(codigo=compra_data.codigo_cliente,
                                                                            valor=compra_data.valor,
                                                                            loja_compra=current_store["identificador"])
        if contagem is None: raise HTTPException(status_code=404,
                                                 detail=f"Cliente {compra_data.codigo_cliente} não encontrado.")
        return {"contagem_atual": contagem, "ganhou_brinde": ganhou, "valor_premio": media, "codigo_premio": cod_premio}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/historico/{codigo}", summary="Obtém o histórico do ciclo de compras atual de um cliente",
         tags=["Interno - Lojas"])
def obter_historico(codigo: str, current_store: dict = Depends(auth.get_current_store)):
    try:
        historico_data = data_manager.obter_historico_ciclo_atual(codigo)
        if not historico_data: raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        return historico_data
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/premios/consultar/{codigo_premio}", summary="Consulta o valor de um prêmio ativo", tags=["Interno - Lojas"])
def consultar_premio_endpoint(codigo_premio: str, current_store: dict = Depends(auth.get_current_store)):
    try:
        premio = data_manager.consultar_premio(codigo_premio)
        if not premio: raise HTTPException(status_code=404, detail="Código de prêmio inválido ou já utilizado.")
        return premio
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/premios/resgatar/{codigo_premio}", summary="Resgata um prêmio", tags=["Interno - Lojas"])
def resgatar_premio_endpoint(codigo_premio: str, current_store: dict = Depends(auth.get_current_store)):
    try:
        sucesso, mensagem = data_manager.resgatar_premio(codigo_premio, loja_resgate=current_store["identificador"])
        if sucesso:
            return {"status": "sucesso", "message": mensagem}
        else:
            raise HTTPException(status_code=400, detail=mensagem)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))