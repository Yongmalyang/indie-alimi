"""소스별 지원공고 파서.

- kocca: 콘진원 지원공고 게시판 전용 파서 (테이블 구조를 정확히 읽음)
- gcon: 경기콘텐츠진흥원 사업공고 게시판 전용 파서 (접수중만 필터링)
- generic: 구조를 모르는 사이트용 - 키워드가 들어간 링크 텍스트를 공고로 취급
"""

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

KOCCA_MENU_NO = "204104"


def _parse_intc_no(href: str) -> str:
    query = href.split("?", 1)[1] if "?" in href else ""
    for pair in query.split("&"):
        if pair.startswith("intcNo="):
            return pair.split("=", 1)[1]
    return href


def fetch_kocca(source: dict, keywords: list) -> list:
    items = []
    seen_ids_this_call = set()
    for keyword in keywords:
        params = {"menuNo": KOCCA_MENU_NO, "search": "1", "searchWrd": keyword}
        resp = requests.get(source["url"], params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        for row in soup.select("table tbody tr"):
            link = row.select_one('a[href*="pims/view"]')
            if not link:
                continue
            intc_no = _parse_intc_no(link["href"])
            if intc_no in seen_ids_this_call:
                continue
            seen_ids_this_call.add(intc_no)

            category_el = row.select_one('td[data-label="구분"] span')
            date_el = row.select_one('td[data-label="공고일"]')
            period_el = row.select_one('td[data-label="접수기간"]')

            items.append(
                {
                    "source_id": source["id"],
                    "source_label": source["label"],
                    "id": f"{source['id']}:{intc_no}",
                    "title": link.get_text(strip=True),
                    "url": f"https://www.kocca.kr/kocca/pims/view.do?intcNo={intc_no}&menuNo={KOCCA_MENU_NO}",
                    "category": category_el.get_text(strip=True) if category_el else "",
                    "posted": date_el.get_text(strip=True) if date_el else "",
                    "period": period_el.get_text(strip=True) if period_el else "",
                    "keyword": keyword,
                }
            )
    return items


GCON_MENU_NO = "200061"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def fetch_gcon(source: dict, keywords: list) -> list:
    """경기콘텐츠진흥원 사업공고 게시판. srchTp=1(접수중)만 가져와서
    이미 마감된 공고는 애초에 안 실립니다."""
    items = []
    seen_ids_this_call = set()
    for keyword in keywords:
        params = {
            "menuNo": GCON_MENU_NO,
            "srchTp": "1",  # 접수중(모집중)만
            "srchCnd": "1",  # 제목 검색
            "srchWrd": keyword,
        }
        resp = requests.get(source["url"], params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        for row in soup.select("table tbody tr"):
            link = row.select_one('td.title a[href*="view.do"]') or row.select_one(
                'a[href*="gconNotice/view"]'
            )
            if not link:
                continue

            href = link["href"]
            query = href.split("?", 1)[1] if "?" in href else ""
            pbanc_id = None
            for pair in query.split("&"):
                if pair.startswith("pbancSrnm="):
                    pbanc_id = pair.split("=", 1)[1]
            if not pbanc_id or pbanc_id in seen_ids_this_call:
                continue
            seen_ids_this_call.add(pbanc_id)

            row_text = row.get_text(" ", strip=True)
            date_match = _DATE_RE.search(row_text)

            items.append(
                {
                    "source_id": source["id"],
                    "source_label": source["label"],
                    "id": f"{source['id']}:{pbanc_id}",
                    "title": link.get_text(strip=True),
                    "url": f"https://www.gcon.or.kr/gcon/business/gconNotice/view.do?pbancSrnm={pbanc_id}&menuNo={GCON_MENU_NO}",
                    "category": "접수중",
                    "posted": date_match.group(0) if date_match else "",
                    "period": "",
                    "keyword": keyword,
                }
            )
    return items


def fetch_generic(source: dict, keywords: list) -> list:
    """구조를 모르는 사이트: 페이지의 링크 텍스트에 키워드가 들어가면 공고로 취급.

    콘진원처럼 표 구조를 정확히 아는 사이트가 아니라면, 목록 페이지에서
    새로 생기는 링크 = 새 공고라는 가정으로 동작합니다. 사이트 구조에 따라
    정확도가 떨어질 수 있습니다.
    """
    resp = requests.get(source["url"], headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    seen_hrefs = set()
    for a in soup.find_all("a", href=True):
        text = re.sub(r"\s+", " ", a.get_text(strip=True))
        if len(text) < 6:
            continue
        matched = next((k for k in keywords if k in text), None)
        if not matched:
            continue

        href = urljoin(source["url"], a["href"])
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        items.append(
            {
                "source_id": source["id"],
                "source_label": source["label"],
                "id": f"{source['id']}:{href}",
                "title": text,
                "url": href,
                "category": "",
                "posted": "",
                "period": "",
                "keyword": matched,
            }
        )
    return items


PARSERS = {
    "kocca": fetch_kocca,
    "gcon": fetch_gcon,
    "generic": fetch_generic,
}


def fetch_source(source: dict, keywords: list) -> list:
    parser = PARSERS.get(source.get("parser", "generic"), fetch_generic)
    return parser(source, keywords)


def fetch_all(sources: list, keywords: list, require_keywords: list | None = None) -> list:
    """require_keywords에 있는 단어는 전부(AND) 제목에 포함되어야 살아남습니다.
    예: require_keywords=["게임"]이면 "게임"이 없는 글(예: "인디"만 걸린 글)은 제외."""
    items = []
    for source in sources:
        try:
            items.extend(fetch_source(source, keywords))
        except requests.RequestException as exc:
            print(f"[경고] {source['label']} 크롤링 실패: {exc}")

    if require_keywords:
        items = [
            item for item in items if all(rk in item["title"] for rk in require_keywords)
        ]
    return items
