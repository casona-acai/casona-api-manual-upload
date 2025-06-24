# models.py (VERSÃO CORRIGIDA)

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import date


# --- Modelos de Requisição (Entrada) ---

class ClientePayload(BaseModel):
    nome: str = Field(..., min_length=3)
    telefone: str = Field(..., pattern=r'^\d{2} \d{5}-\d{4}$')
    email: Optional[EmailStr] = None
    data_nascimento: date
    sexo: str
    cep: Optional[str] = Field(None, pattern=r'^\d{5}-\d{3}$')
    website: Optional[str] = None


class CompraPayload(BaseModel):
    codigo_cliente: str = Field(..., min_length=5, max_length=5)
    valor: float = Field(..., gt=0)


class ClienteUpdatePayload(ClientePayload):
    website: Optional[str] = Field(None, exclude=True)


# --- Modelos de Resposta (Saída) ---

class ClienteResponse(BaseModel):
    """
    Modelo de dados para retornar as informações de um cliente
    para as interfaces.
    """
    codigo: str
    nome: str
    telefone: Optional[str] = None
    email: Optional[EmailStr] = None
    cep: Optional[str] = None
    total_compras: int
    total_gasto: float

    # <<< ALTERAÇÃO AQUI >>>
    # Trocamos 'contagem_brinde' por 'compras_ciclo_atual' para corresponder
    # ao schema atual do banco de dados.
    compras_ciclo_atual: int

    loja_origem: str
    data_nascimento: Optional[date] = None
    ano_ultimo_email_aniversario: Optional[int] = None
    sexo: Optional[str] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    store_id: str


# --- NOVOS MODELOS PARA RESPOSTA DO DASHBOARD ---

class CompraDashboard(BaseModel):
    id: int
    codigo_cliente: str
    numero_compra_geral: int
    valor: float
    data: date  # Este campo espera um 'date', não 'datetime'.
    loja_compra: Optional[str] = None


class PremioResgatadoDashboard(BaseModel):
    id: int
    codigo_premio: str
    valor_premio: float  # Mantemos a correção anterior.
    codigo_cliente: str
    data_geracao: date
    data_resgate: date
    loja_resgate: Optional[str] = None


class DashboardDataResponse(BaseModel):
    clientes: List[ClienteResponse]
    compras: List[CompraDashboard]
    premios_resgatados: List[PremioResgatadoDashboard]