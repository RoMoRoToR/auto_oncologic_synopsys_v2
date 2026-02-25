import time
import random
import logging
from typing import List, Optional, Dict
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GoogleScholarFulltextFinder:
    BASE_URL = "https://scholar.google.com/scholar"

    def __init__(
        self,
        user_agents: Optional[List[str]] = None,
        min_delay: float = 5.0,
        max_delay: float = 10.0,
        timeout: float = 20.0,
        proxies: Optional[Dict[str, str]] = None,
    ):
        """
        :param user_agents: список user-agent строк для рандомизации
        :param min_delay: минимальная пауза между запросами (сек)
        :param max_delay: максимальная пауза между запросами (сек)
        :param timeout: таймаут HTTP-запросов
        :param proxies: словарь прокси для requests (http/https)
        """
        self.session = requests.Session()
        self.user_agents = user_agents or [
            # можно расширить список; идея взята из практик готовых парсеров.[web:7]
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Safari/605.1.15",
        ]
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self.proxies = proxies or {}

    def _sleep(self):
        delay = random.uniform(self.min_delay, self.max_delay)
        logger.debug("Sleeping for %.2f seconds", delay)
        time.sleep(delay)

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", random.choice(self.user_agents))
        try:
            resp = self.session.get(
                url,
                headers=headers,
                timeout=self.timeout,
                proxies=self.proxies,
                **kwargs,
            )
            if resp.status_code == 200:
                return resp
            logger.warning("Non-200 response %s for %s", resp.status_code, url)
            return None
        except requests.RequestException as e:
            logger.warning("Request failed for %s: %s", url, e)
            return None

    def search(self, query: str, num_pages: int = 1, hl: str = "en") -> List[Dict]:
        """
        Ищет статьи по запросу, возвращает список результатов Scholar
        (без перехода на внешние сайты).
        """
        results = []
        start = 0
        for page in range(num_pages):
            params = f"q={quote_plus(query)}&hl={hl}&start={start}"
            url = f"{self.BASE_URL}?{params}"
            logger.info("Fetching search page %d: %s", page + 1, url)

            self._sleep()
            resp = self._get(url)
            if not resp:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            page_results = self._parse_search_page(soup, url)
            if not page_results:
                break

            results.extend(page_results)
            start += 10  # Scholar выводит по 10 результатов.[web:6]

        return results

    @staticmethod
    def _parse_search_page(soup: BeautifulSoup, page_url: str) -> List[Dict]:
        """
        Парсит HTML страницы поиска Scholar.
        """
        items = []
        for item in soup.select(".gs_ri"):  # общий контейнер результата.[web:6]
            title_tag = item.select_one(".gs_rt")
            if not title_tag:
                continue

            link_tag = title_tag.find("a")
            title = ""
            main_url = None

            if link_tag:
                title = link_tag.get_text(strip=True)
                main_url = link_tag.get("href")
            else:
                # Иногда это цитаты без прямой ссылки.
                title = title_tag.get_text(strip=True)

            # блок слева с PDF (если есть).[web:6][web:7]
            pdf_link = None
            left_block = item.find_previous_sibling("div", class_="gs_ggs gs_fl")
            if not left_block:
                left_block = item.parent.select_one(".gs_or_ggsm")
            if left_block:
                a_pdf = left_block.find("a")
                if a_pdf and ("pdf" in (a_pdf.get_text() or "").lower()
                              or ".pdf" in (a_pdf.get("href") or "").lower()):
                    pdf_link = a_pdf.get("href")

            meta_tag = item.select_one(".gs_a")
            meta = meta_tag.get_text(strip=True) if meta_tag else ""

            snippet_tag = item.select_one(".gs_rs")
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

            items.append(
                {
                    "title": title,
                    "main_url": main_url,
                    "pdf_url": pdf_link,
                    "meta": meta,
                    "snippet": snippet,
                    "scholar_page": page_url,
                }
            )
        return items

    def _find_fulltext_on_landing(self, url: str) -> Optional[str]:
        """
        Пытается найти ссылку на полный текст на целевой странице статьи.
        Стратегия вдохновлена типовыми приёмами из гайдов по парсингу.[web:6][web:7]
        """
        if not url:
            return None

        self._sleep()
        resp = self._get(url)
        if not resp:
            return None

        content_type = resp.headers.get("Content-Type", "").lower()
        if "application/pdf" in content_type:
            # Ссылка ведёт прямо на pdf.
            return url

        soup = BeautifulSoup(resp.text, "lxml")

        # 1. Ищем <a> на pdf по расширению.
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                return urljoin(url, href)

        # 2. Ищем по тексту "PDF" / "Full text" / "Download".
        keywords = [
            "pdf",
            "full text",
            "download",
            "article",
            "полный текст",
            "скачать",
        ]
        for a in soup.find_all(["a", "button"], href=True):
            text = (a.get_text() or "").strip().lower()
            if any(kw in text for kw in keywords):
                href = a["href"]
                return urljoin(url, href)

        return None

    def find_fulltexts_for_query(
        self, query: str, num_pages: int = 1
    ) -> List[Dict]:
        """
        Высокоуровневая функция:
        1) ищет статьи в Scholar,
        2) для каждой пытается найти полный текст.
        """
        base_results = self.search(query, num_pages=num_pages)
        enriched = []
        for r in base_results:
            fulltext_url = None
            source = None

            # 1. PDF сразу из Scholar.
            if r.get("pdf_url"):
                fulltext_url = r["pdf_url"]
                source = "scholar_pdf_link"
            # 2. Переход на основную страницу и поиск там.
            elif r.get("main_url"):
                fulltext = self._find_fulltext_on_landing(r["main_url"])
                if fulltext:
                    fulltext_url = fulltext
                    source = "landing_page"

            r["fulltext_url"] = fulltext_url
            r["fulltext_source"] = source
            enriched.append(r)

        return enriched

    def batch_search(
            self,
            queries: List[str],
            num_pages_per_query: int = 1
    ) -> List[Dict]:
        """
        Ищет по списку запросов (до 3), возвращает все результаты с меткой запроса.

        Пример:
        queries = [
            "",  # Заполни свой первый запрос
            "",  # второй
            ""   # третий
        ]
        """
        if len(queries) > 3:
            logger.warning("Ограничиваю до 3 запросов")
            queries = queries[:3]

        all_results = []
        for i, query in enumerate(queries, 1):
            if not query.strip():
                logger.info(f"Пропускаю пустой запрос #{i}")
                continue

            logger.info(f"🔍 Запрос #{i}: '{query}'")
            results = self.find_fulltexts_for_query(query, num_pages=num_pages_per_query)
            for r in results:
                r["query_id"] = i
                r["query_text"] = query
            all_results.extend(results)

        return all_results


'''if __name__ == "__main__":
    finder = GoogleScholarFulltextFinder()
    drug_name = 'Rivaroxaban'
    dosage = '20 mg'
    query = f'Detailed pharmacokinetics of {drug_name} {dosage}: T1/2, CVintra, AUC, Cmax, tmax, BCS class'
    results = finder.find_fulltexts_for_query(query, num_pages=1)

    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   Meta: {r['meta']}")
        print(f"   Scholar main URL: {r['main_url']}")
        print(f"   PDF (Scholar): {r['pdf_url']}")
        print(f"   Full text: {r['fulltext_url']} (source={r['fulltext_source']})")
        print()'''

if __name__ == "__main__":
    finder = GoogleScholarFulltextFinder()

    drug_name = 'Rivaroxaban'
    dosage = '20 mg'

    # ЗАПОЛНИ СВОИ ЗАПРОСЫ ЗДЕСЬ
    my_queries = [
        f"Detailed pharmacokinetics of {drug_name} {dosage}: T1/2, AUC, Cmax, tmax, CVintra",  # пример для первого
        f"Detailed pharmacokinetics of {drug_name} {dosage}: BCS class",  # второй запрос
        f"Detailed pharmacokinetics of {drug_name} {dosage}: toxicity"  # третий запрос
    ]

    results = finder.batch_search(my_queries, num_pages_per_query=2)

    print(f"📊 Всего найдено: {len(results)} статей")
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r['query_id']}] {r['title']}")
        print(f"   Fulltext: {r['fulltext_url'] or 'НЕ НАЙДЕН'}")
        print()

