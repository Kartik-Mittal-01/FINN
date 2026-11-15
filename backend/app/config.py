from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'finn.db'}"
    data_dir: Path = BASE_DIR / "data"
    llm_provider: str = "auto"  # auto | ollama | none
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    embeddings_provider: str = "tfidf"  # tfidf | sentence-transformers
    st_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    refresh_interval_min: int = 0
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    http_timeout: float = 20.0
    user_agent: str = "Mozilla/5.0 (compatible; FINN-prototype/0.1; research use)"

    @property
    def documents_dir(self) -> Path:
        p = self.data_dir / "documents"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cache_dir(self) -> Path:
        p = self.data_dir / "cache"
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
