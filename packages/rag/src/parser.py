from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import requests

PDF_TIMEOUT_S = float(os.getenv("PDF_TIMEOUT_S", "18"))
MAX_PDF_MB = int(os.getenv("MAX_PDF_MB", "30"))

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


@dataclass(frozen=True)
class ParsedDoc:
    source: str
    title: str
    uri: str
    content_md: str
    relevant_md: str
    sha256: str


class PDFParser:
    DEFAULT_KEYWORDS = [
        "tmax",
        "t1/2",
        "half-life",
        "cmax",
        "auc",
        "within-subject",
        "intra-subject",
        "cv",
        "период полувыведения",
        "время достижения максимальной концентрации",
        "коэффициент вариации",
        "биоэквивалент",
        "washout",
    ]

    def __init__(self, cache_dir: str | None = None):
        base = Path(cache_dir) if cache_dir else Path(os.getenv("RAG_CACHE_DIR", "data/rag_cache")) / "pdf_cache"
        self.cache_dir = base
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        }

    def _sha256_bytes(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _cache_paths(self, key: str) -> Tuple[Path, Path, Path]:
        pdf_path = self.cache_dir / f"{key}.pdf"
        md_path = self.cache_dir / f"{key}.md"
        rel_path = self.cache_dir / f"{key}.rel.md"
        return pdf_path, md_path, rel_path

    def _download_pdf(self, url: str) -> Tuple[bytes, str]:
        resp = requests.get(url, headers=self.headers, timeout=PDF_TIMEOUT_S, stream=True)
        resp.raise_for_status()
        head = resp.raw.read(512)
        if b"%PDF-" not in head:
            raise ValueError("URL вернул не PDF (403/капча/HTML)")

        buf = bytearray(head)
        limit = MAX_PDF_MB * 1024 * 1024
        for chunk in resp.iter_content(chunk_size=1024 * 64):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) > limit:
                raise ValueError(f"PDF слишком большой (>{MAX_PDF_MB}MB)")
        data = bytes(buf)
        return data, self._sha256_bytes(data)

    def _extract_text_fast(self, pdf_path: str, max_pages: int = 8) -> str:
        if PdfReader is None:
            return ""
        reader = PdfReader(pdf_path)
        pages = min(max_pages, len(reader.pages))
        parts = []
        for i in range(pages):
            try:
                parts.append(reader.pages[i].extract_text() or "")
            except Exception:
                parts.append("")
        return "\n".join(parts)

    def _extract_relevant(self, text: str, keywords: Optional[List[str]] = None, window: int = 700, max_chunks: int = 12) -> str:
        if not text:
            return ""
        kws = [k.lower() for k in (keywords or self.DEFAULT_KEYWORDS)]
        low = text.lower()
        hits = []
        for kw in kws:
            for m in re.finditer(re.escape(kw), low):
                hits.append(m.start())
        if not hits:
            return text[:6000]

        hits = sorted(set(hits))
        chunks = []
        used = []
        for pos in hits:
            if len(chunks) >= max_chunks:
                break
            start = max(0, pos - window)
            end = min(len(text), pos + window)
            rng = (start, end)
            if any(not (rng[1] <= r[0] or r[1] <= rng[0]) for r in used):
                continue
            used.append(rng)
            chunks.append(text[start:end].strip())
        return "\n\n".join([f"### EXCERPT {i+1}\n{c}" for i, c in enumerate(chunks)])

    def parse(self, source: str, title: str = "", uri: str = "", keywords: Optional[List[str]] = None) -> ParsedDoc:
        if os.path.exists(source):
            data = Path(source).read_bytes()
            sha = self._sha256_bytes(data)
        else:
            data, sha = self._download_pdf(source)

        pdf_path, md_path, rel_path = self._cache_paths(sha)
        if not pdf_path.exists():
            pdf_path.write_bytes(data)

        if md_path.exists():
            md = md_path.read_text(encoding="utf-8", errors="ignore")
        else:
            txt = self._extract_text_fast(str(pdf_path))
            md = (txt or "").strip()
            md_path.write_text(md, encoding="utf-8")

        if rel_path.exists():
            rel = rel_path.read_text(encoding="utf-8", errors="ignore")
        else:
            rel = self._extract_relevant(md, keywords=keywords)
            rel_path.write_text(rel, encoding="utf-8")

        return ParsedDoc(
            source=source,
            title=title or uri or source,
            uri=uri or source,
            content_md=md,
            relevant_md=rel,
            sha256=sha,
        )

    def to_markdown(self, source: str) -> str:
        return self.parse(source).content_md

    def to_relevant_markdown(self, source: str, keywords: Optional[List[str]] = None) -> str:
        return self.parse(source, keywords=keywords).relevant_md
