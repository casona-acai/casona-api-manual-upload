# models.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import date  # Importa o tipo date


# --- Modelos de Requisição (Entrada) ---
class ClientePayload(BaseModel):
    nome: str
    telefone: str = Field(..., pattern=r'^\d{2} \d{5}-\d{4}$')
    email: Optional[EmailStr] = None

    # --- ALTERADO: Usa o tipo `date` do Python.
    # O front-end DEVE enviar a data no formato "YYYY-MM-DD".
    data_nascimento: date
    sexo: str
    website: Optional[str] = None


class CompraPayload(BaseModel):
    codigo_cliente: str = Field(..., min_length=5, max_length=5)
    valor: float = Field(..., gt=0)


class ClienteUpdatePayload(ClientePayload):
    website: Optional[str] = Field(None, exclude=True)


# --- Modelos de Resposta (Saída) ---
class ClienteResponse(BaseModel):
    codigo: str
    nome: str
    telefone: Optional[str] = None
    email: Optional[EmailStr] = None
    total_compras: int
    total_gasto: float
    contagem_brinde: int
    loja_origem: str
    # --- ALTERADO: O tipo de resposta também é `date`.
    data_nascimento: Optional[date] = None
    sexo: Optional[str] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    store_id: str