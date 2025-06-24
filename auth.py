# auth.py (VERSÃO FINAL - COM INJEÇÃO DE DEPENDÊNCIA)

from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

import config
from datamanager import DataManager

logger = logging.getLogger(__name__)

# --- CONFIGURAÇÃO DE SEGURANÇA ---
SECRET_KEY = config.JWT_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_scheme = HTTPBearer()

# --- VARIÁVEL GLOBAL PARA ARMAZENAR A INSTÂNCIA DO DATAMANAGER ---
data_manager: DataManager = None


def set_data_manager(dm: DataManager):
    """Função para injetar a instância do DataManager que este módulo deve usar."""
    global data_manager
    data_manager = dm


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def authenticate_store(username: str, password: str):
    if data_manager is None:
        raise Exception("DataManager não foi inicializado no módulo de autenticação.")
    try:
        loja = data_manager.obter_loja_por_username(username)
        if not loja or not loja.get('is_active', False) or not verify_password(password, loja["hashed_password"]):
            return None
        return loja
    except Exception as e:
        logger.error(f"Erro crítico durante a autenticação de '{username}': {e}")
        return None


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_store(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)):
    if data_manager is None:
        raise HTTPException(status_code=500, detail="Serviço de autenticação não configurado.")

    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou token expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        store_id: str = payload.get("sub")
        if store_id is None: raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        loja_encontrada = data_manager.obter_loja_por_identificador(store_id)
        if not loja_encontrada or not loja_encontrada.get('is_active', False):
            raise credentials_exception
    except Exception as e:
        logger.error(f"Erro ao validar token para o identificador '{store_id}': {e}")
        raise credentials_exception

    return {"identificador": store_id}