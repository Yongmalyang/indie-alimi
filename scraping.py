"""소스별 지원공고 파서.

- kocca: 콘진원 지원공고 게시판 전용 파서 (테이블 구조를 정확히 읽음)
- gcon: 경기콘텐츠진흥원 사업공고 게시판 전용 파서 (접수중만 필터링)
- startupplus: 서울게임콘텐츠센터 사업공고 게시판 전용 파서
- playx4: 플레이엑스포(게임쇼) 공지사항 게시판 전용 파서
- gstar: 지스타(게임쇼) News 게시판 전용 파서
- indielog: 스마일게이트 인디로그(STOVE) 참여자 모집 게시판 전용 파서 (모집중만 필터링)
- generic: 구조를 모르는 사이트용 - 키워드가 들어간 링크 텍스트를 공고로 취급
"""

import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_POSTED_DATE_FORMATS = ["%Y-%m-%d", "%y.%m.%d", "%Y.%m.%d", "%y-%m-%d"]


def _parse_posted_date(posted: str):
    posted = (posted or "").strip()
    if not posted:
        return None
    for fmt in _POSTED_DATE_FORMATS:
        try:
            return datetime.strptime(posted, fmt).date()
        except ValueError:
            continue
    return None

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


def fetch_startupplus(source: dict, keywords: list) -> list:
    """서울게임콘텐츠센터 사업공고. 화면은 JS(SPA)라 직접 스크레이핑이 안 돼서
    화면이 호출하는 내부 JSON API(/api/cportal/board)를 그대로 호출."""
    board_id = source["url"].rstrip("/").split("/")[-1]
    api_url = "https://gamecontents.startup-plus.kr/api/cportal/board"
    params = {"size": 20, "page": 0, "portalSeqNo": 320, "boardId": board_id}
    resp = requests.get(api_url, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    items = []
    for post in data.get("data", {}).get("contents", []):
        seq_no = post.get("seqNo")
        if seq_no is None:
            continue
        items.append(
            {
                "source_id": source["id"],
                "source_label": source["label"],
                "id": f"{source['id']}:{seq_no}",
                "title": post.get("title", ""),
                "url": f"https://gamecontents.startup-plus.kr/board/{board_id}/{seq_no}",
                "category": "",
                "posted": (post.get("createDateTime") or "")[:10],
                "period": "",
                "keyword": "",
            }
        )
    return items


def fetch_playx4(source: dict, keywords: list) -> list:
    """플레이엑스포 공지사항. 검색 API가 없어서 최신 목록(1페이지)만 확인."""
    resp = requests.get(source["url"], headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for row in soup.select("table.board_box tbody tr"):
        link = row.select_one("td.list_title a")
        if not link:
            continue
        href = urljoin(source["url"], link["href"])
        query = href.split("?", 1)[1] if "?" in href else ""
        bid = None
        for pair in query.split("&"):
            if pair.startswith("bid="):
                bid = pair.split("=", 1)[1]
        if not bid:
            continue
        date_el = row.select_one("td.list_date")

        items.append(
            {
                "source_id": source["id"],
                "source_label": source["label"],
                "id": f"{source['id']}:{bid}",
                "title": link.get_text(strip=True),
                "url": href,
                "category": "",
                "posted": date_el.get_text(strip=True) if date_el else "",
                "period": "",
                "keyword": "",
            }
        )
    return items


def fetch_gstar(source: dict, keywords: list) -> list:
    """지스타 News 게시판. 검색 API가 없어서 최신 목록(1페이지)만 확인."""
    resp = requests.get(source["url"], headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for row in soup.select("table tbody tr"):
        link = row.select_one('td[data-content="제목"] a')
        if not link:
            continue
        href = link["href"]
        query = href.split("?", 1)[1] if "?" in href else ""
        bd_idx = None
        for pair in query.split("&"):
            if pair.startswith("bd_idx="):
                bd_idx = pair.split("=", 1)[1]
        if not bd_idx:
            continue
        category_el = row.select_one('td[data-content="구분"]')
        date_el = row.select_one('td[data-content="등록일자"]')

        items.append(
            {
                "source_id": source["id"],
                "source_label": source["label"],
                "id": f"{source['id']}:{bd_idx}",
                "title": link.get_text(strip=True),
                "url": f"https://www.gstar.or.kr/board/board_user_view.do?bmt_idx=1&bd_idx={bd_idx}",
                "category": category_el.get_text(strip=True) if category_el else "",
                "posted": date_el.get_text(strip=True) if date_el else "",
                "period": "",
                "keyword": "",
            }
        )
    return items


def fetch_indielog(source: dict, keywords: list) -> list:
    """스마일게이트 인디로그(STOVE) '참여자 모집' 게시판. 화면은 SPA라 내부
    JSON API를 직접 호출. headline_info.headline_name에 "모집중"/"모집마감"이
    정확히 찍혀 나와서 마감된 건 걸러낼 수 있음."""
    board_seq = source["url"].split("?", 1)[0].rstrip("/").split("/")[-1]
    api_url = f"https://api.onstove.com/cwms/v3.0/article_group/BOARD/{board_seq}/article/list"
    params = {
        "interaction_type_code": "LIKE,DISLIKE,COMMENT,VIEW",
        "content_yn": "Y",
        "summary_yn": "Y",
        "sort_type_code": "LATEST",
        "headline_title_yn": "Y",
        "translation_yn": "N",
        "page": 1,
        "size": 30,
    }
    resp = requests.get(api_url, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    items = []
    for post in data.get("value", {}).get("list", []):
        status = (post.get("headline_info") or {}).get("headline_name", "")
        if "마감" in status or "종료" in status:
            continue

        article_id = post.get("article_id")
        if not article_id:
            continue

        posted = ""
        create_ms = post.get("create_datetime")
        if create_ms:
            posted = datetime.utcfromtimestamp(create_ms / 1000).strftime("%Y-%m-%d")

        items.append(
            {
                "source_id": source["id"],
                "source_label": source["label"],
                "id": f"{source['id']}:{article_id}",
                "title": post.get("title", ""),
                "url": f"https://page.onstove.com/devlog/kr/view/{article_id}",
                "category": status,
                "posted": posted,
                "period": "",
                "keyword": "",
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
    "startupplus": fetch_startupplus,
    "playx4": fetch_playx4,
    "gstar": fetch_gstar,
    "indielog": fetch_indielog,
    "generic": fetch_generic,
}


def fetch_source(source: dict, keywords: list) -> list:
    parser = PARSERS.get(source.get("parser", "generic"), fetch_generic)
    return parser(source, keywords)


def fetch_all(
    sources: list,
    keywords: list,
    require_keywords: list | None = None,
    exclude_keywords: list | None = None,
) -> list:
    """require_keywords/exclude_keywords는 둘 다 "이 중 하나라도" 방식(OR)입니다.
    require: 하나도 없으면 전부 제외 (예: ["모집","결과"] -> 둘 중 하나는 제목에 있어야 함)
    exclude: 하나라도 있으면 제외 (예: ["과몰입","중독"] -> 이 단어 들어간 글은 버림)

    소스별로 sources.json에 "require_keywords"/"exclude_keywords"를 따로 적어두면
    그 소스에서는 전역 설정 대신 그 값을 씁니다 (게임쇼 사이트처럼 "게임"이란
    단어가 굳이 제목에 안 들어가는 곳에 유용).

    "max_age_days"도 소스별로 줄 수 있습니다 - 콘진원/경콘진처럼 사이트 자체가
    "접수중만" 걸러주는 곳은 필요 없지만, 그런 필터가 없는 사이트(startupplus,
    playx4, gstar)는 그냥 최신 목록만 긁다 보니 마감 지난 지 한참 된 글도 섞여서
    등록일 기준으로 오래된 건 걸러냅니다."""
    items = []
    today = date.today()
    for source in sources:
        try:
            source_items = fetch_source(source, keywords)
        except requests.RequestException as exc:
            print(f"[경고] {source['label']} 크롤링 실패: {exc}")
            continue

        req = source.get("require_keywords", require_keywords)
        exc_kw = source.get("exclude_keywords", exclude_keywords)
        max_age = source.get("max_age_days")

        if req:
            source_items = [i for i in source_items if any(k in i["title"] for k in req)]
        if exc_kw:
            source_items = [i for i in source_items if not any(k in i["title"] for k in exc_kw)]
        if max_age:
            cutoff = today - timedelta(days=max_age)
            kept = []
            for item in source_items:
                posted = _parse_posted_date(item.get("posted"))
                if posted is None or posted >= cutoff:
                    kept.append(item)
            source_items = kept

        items.extend(source_items)
    return items
