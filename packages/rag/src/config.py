import os
from pathlib import Path


class Config:
    """Мини-настройки окружения."""

    @staticmethod
    def setup_windows_env() -> None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass

        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(cache_dir))

        rag_cache = Path(os.getenv("RAG_CACHE_DIR", "data/rag_cache"))
        rag_cache.mkdir(parents=True, exist_ok=True)
        (rag_cache / "search").mkdir(parents=True, exist_ok=True)
        (rag_cache / "pdf").mkdir(parents=True, exist_ok=True)
