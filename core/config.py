import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    # API Keys
    OPENAI_API_KEY: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    GEMINI_API_KEY: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    
    # LLM Settings
    DEFAULT_LLM_MODEL: str = field(default_factory=lambda: os.getenv("DEFAULT_LLM_MODEL", "gemini-2.5-flash"))
    EMBEDDING_MODEL: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    
    # Multi-Agent StateGraph Limits
    MAX_ORCHESTRATOR_RETRY: int = int(os.getenv("MAX_ORCHESTRATOR_RETRY", "3"))
    DEFAULT_MAX_INTERNAL_RETRY: int = int(os.getenv("DEFAULT_MAX_INTERNAL_RETRY", "2"))
    
    # Paths
    CORPUS_PATH: str = field(default_factory=lambda: os.getenv("CORPUS_PATH", "data/corpus.jsonl"))
    ARTIFACTS_DIR: str = field(default_factory=lambda: os.getenv("ARTIFACTS_DIR", "artifacts"))

settings = Settings()
