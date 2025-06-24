# models.py (VERSÃO COM CAMPO CEP)

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import date


# --- Modelos de Requisição (Entrada) ---

class ClientePayload(BaseModel):
    """
    Modelo de dados para receber informações de um novo cliente,
    seja pelo formulário web ou pela interface interna.
    """
    nome: str = Field(..., min_length=3)
    telefone: str = Field(..., pattern=r'^\d{2} \d{5}-\d{4}$')
    email: Optional[EmailStr] = None
    data_nascimento: date
    sexo: str

    # <<< NOVO CAMPO ADICIONADO >>>
    # O CEP é opcional. A validação `pattern` garante que, se for enviado,
    # ele deve estar no formato "XXXXX-XXX".
    cep: Optional[str] = Field(None, pattern=r'^\d{5}-\d{3}$')

    # Campo Honeypot para segurança do formulário público
    website: Optional[str] = None


class CompraPayload(BaseModel):
    """Modelo para registrar uma nova compra."""
    codigo_cliente: str = Field(..., min_length=5, max_length=5)
    valor: float = Field(..., gt=0)


class ClienteUpdatePayload(ClientePayload):
    """
    Modelo para atualizar os dados de um cliente.
    Herda de ClientePayload, mas exclui o campo honeypot.
    """
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

    # <<< NOVO CAMPO ADICIONADO >>>
    # Incluído para que a API possa retornar o CEP quando um cliente é consultado.
    cep: Optional[str] = None

    total_compras: int
    total_gasto: float
    contagem_brinde: int
    loja_origem: str
    data_nascimento: Optional[date] = None
    sexo: Optional[str] = None

    class Config:
        # Permite que o Pydantic crie o modelo a partir de um objeto de banco de dados.
        from_attributes = True


class Token(BaseModel):
    """Modelo para a resposta do endpoint de login/token."""
    access_token: str
    token_type: str
    store_id: str

# --- NOVOS MODELOS PARA RESPOSTA DO DASHBOARD ---

class CompraDashboard(BaseModel):
    id: int
    codigo_cliente: str
    numero_compra_geral: int
    valor: float
    data: date
    loja_compra: Optional[str] = None

class PremioResgatadoDashboard(BaseModel):
    id: int
    codigo_premio: str
    valor_premio: float
    codigo_cliente: str
    data_geracao: date
    data_resgate: date
    loja_resgate: Optional[str] = None

class DashboardDataResponse(BaseModel):
    clientes: List[ClienteResponse]
    compras: List[CompraDashboard]
    premios_resgatados: List[PremioResgatadoDashboard]