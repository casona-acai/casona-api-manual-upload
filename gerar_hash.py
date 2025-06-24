# gerar_hash.py
from passlib.context import CryptContext

# Esta linha é a mesma que está no seu auth.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    """Gera o hash de uma senha."""
    return pwd_context.hash(password)

# A senha que queremos usar
senha_texto_plano = "admin_fidelidade"

# Gerar o hash
novo_hash = get_password_hash(senha_texto_plano)

print("--- NOVO HASH GERADO ---")
print(f"Para a senha '{senha_texto_plano}', o novo hash é:")
print(novo_hash)
print("--------------------------")
print("\nCopie a linha do hash (a que começa com '$2b$...') e substitua no seu arquivo auth.py.")