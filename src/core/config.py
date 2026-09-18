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