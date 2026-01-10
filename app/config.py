import os
from dotenv import load_dotenv
load_dotenv()


class Config:
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano-2025-08-07")
    OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    CHROMA_HOST = os.getenv("CHROMA_HOST")
    CHROMA_PORT = os.getenv("CHROMA_PORT")
    CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "DTMI")
    TOP_K = os.getenv('TOP_K')
    DEFAULT_CONTEXT_EXPANSION_WINDOW = os.getenv("DEFAULT_CONTEXT_EXPANSION_WINDOW")
    WABLASS_API_KEY = os.getenv("WABLASS_API_KEY")
    WABLASS_WEBHOOK_SECRET = os.getenv("WABLASS_WEBHOOK_SECRET")
    SECRET_KEY = os.getenv("SECRET_KEY")
    METADATA_PROCESSING_TIMEOUT = int(os.getenv("METADATA_PROCESSING_TIMEOUT", "300"))
    CONTEXT_TOKEN_LIMIT = int(os.getenv("CONTEXT_TOKEN_LIMIT", "2000"))
    SECRET_KEY = os.getenv("SECRET_KEY")
    # Validation
    if not WABLASS_API_KEY:
        raise RuntimeError("WABLASS_API_KEY is not set in .env")
    if not WABLASS_WEBHOOK_SECRET:
        raise RuntimeError("WABLASS_WEBHOOK_SECRET is not set in .env")
    if not OPENAI_API_KEY:
        raise ValueError("FATAL ERROR: OPENAI_API_KEY is not set in the environment.")
    if not SECRET_KEY:
        raise ValueError("FATAL ERROR: SECRET_KEY is not set in the environment.")

    @classmethod
    def get_all(cls):
        """
        Return a dict of all configuration attributes (uppercase names) and their values.
        """
        return {
            name: getattr(cls, name)
            for name in dir(cls)
            if name.isupper()
        }
