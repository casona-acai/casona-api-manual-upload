# auth.py
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

# --- INSTÂNCIA DO GERENCIADOR DE DADOS ---
# Usamos uma única instância para otimizar o uso do pool de conexões
db_manager = DataManager()


def verify_password(plain_password, hashed_password):
    """Verifica se a senha em texto plano corresponde ao hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    """Gera o hash de uma senha."""
    return pwd_context.hash(password)


def authenticate_store(username: str, password: str):
    """
    Autentica uma loja consultando o banco de dados.
    Retorna os dados da loja se for bem-sucedido, senão None.
    """
    try:
        loja = db_manager.obter_loja_por_username(username)
        if not loja:
            logger.warning(f"Tentativa de login para usuário inexistente: {username}")
            return None

        if not loja.get('is_active', False):
            logger.warning(f"Tentativa de login para loja inativa: {username}")
            return None

        if not verify_password(password, loja["hashed_password"]):
            logger.warning(f"Tentativa de login com senha incorreta para: {username}")
            return None

        return loja
    except Exception as e:
        logger.error(f"Erro crítico durante a autenticação de '{username}': {e}")
        return None


def create_access_token(data: dict):
    """Cria um token de acesso JWT."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_store(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)):
    """
    Dependência FastAPI: decodifica o token, valida e retorna o ID da loja.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou token expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        store_id: str = payload.get("sub")
        if store_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        # Valida se o identificador do token corresponde a uma loja ativa no DB
        loja_encontrada = db_manager.obter_loja_por_identificador(store_id)
        if not loja_encontrada or not loja_encontrada.get('is_active', False):
            raise credentials_exception
    except Exception as e:
        logger.error(f"Erro ao validar token para o identificador '{store_id}': {e}")
        raise credentials_exception

    return {"identificador": store_id}