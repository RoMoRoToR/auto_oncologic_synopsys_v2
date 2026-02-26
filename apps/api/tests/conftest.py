import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAG = ROOT / "packages" / "rag"
API = ROOT / "apps" / "api"

sys.path.append(str(RAG))
sys.path.append(str(API))
