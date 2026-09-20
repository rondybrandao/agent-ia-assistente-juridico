"""
Configurações da aplicação, carregadas de variáveis de ambiente.

Camada: core — não depende de nenhuma outra camada do projeto.
"""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- WhatsApp Cloud API (Meta) ---
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "troque-este-token")
    WHATSAPP_API_VERSION: str = os.getenv("WHATSAPP_API_VERSION", "v20.0")

    # --- LLM (compatível com API da OpenAI) ---
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

    # --- Busca na web (pesquisa jurídica do advogado) ---
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    # --- Valores legais que mudam periodicamente (definir_competencia) ---
    # R$ 1.621,00 (Decreto 12.797/2025, vigente desde 01/01/2026). Revisar
    # todo ano — pode ser sobrescrito por requisição também.
    SALARIO_MINIMO_VIGENTE: float = float(os.getenv("SALARIO_MINIMO_VIGENTE", "1621.00"))

    # --- Valores legais que mudam periodicamente (calcular_custas) ---
    # R$ 8.475,55 (Portaria Interministerial MPS/MF nº 13/2026), usado no
    # teto das custas trabalhistas (4x o teto do RGPS, CLT art. 789).
    TETO_RGPS_VIGENTE: float = float(os.getenv("TETO_RGPS_VIGENTE", "8475.55"))

    # --- Escritório / handoff ---
    NOME_ESCRITORIO: str = os.getenv("NOME_ESCRITORIO", "Escritório Exemplo")
    WEBHOOK_INTERNO_HANDOFF: str = os.getenv("WEBHOOK_INTERNO_HANDOFF", "")  # ex: Slack/Teams
    EMAIL_HANDOFF: str = os.getenv("EMAIL_HANDOFF", "")
    ADVOGADO_WHATSAPP_NUMERO: str = os.getenv("ADVOGADO_WHATSAPP_NUMERO", "")

    # --- Banco local (SQLite para o protótipo) ---
    DB_PATH: str = os.getenv("DB_PATH", "juridico_ia.db")
    HANDOFF_LOG_PATH: str = os.getenv("HANDOFF_LOG_PATH", "handoffs.log.jsonl")

    # --- Aplicação ---
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()