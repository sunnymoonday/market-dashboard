"""
시장 변동성 대시보드 데이터 수집기
- 주가지수/환율: Yahoo Finance chart API (키 불필요)
- 주요 이슈: Google 뉴스 RSS (키 불필요)
- 부동산: 한국부동산원 R-ONE Open API (무료 인증키 필요, config.json 의 rone_key)

실행: python update_data.py   →  같은 폴더에 data.js 생성, index.html 을 열면 됩니다.
표준 라이브러리만 사용합니다.
"""
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (market-dashboard)"}

INDICES = [
    # (그룹, 표시명, 심볼)
    ("국내", "KOSPI", "^KS11"),
    ("국내", "KOSDAQ", "^KQ11"),
    ("미국", "S&P 500", "^GSPC"),
    ("미국", "NASDAQ", "^IXIC"),
    ("미국", "다우존스", "^DJI"),
    ("중국", "상해종합", "000001.SS"),
    ("중국", "선전성분", "399001.SZ"),
    ("중국", "항셍(홍콩)", "^HSI"),
]
FX = [
    ("원/달러", "KRW=X", 1),
    ("원/100엔", "JPYKRW=X", 100),
    ("원/유로", "EURKRW=X", 1),
    ("원/위안", "CNYKRW=X", 1),  # Yahoo 직접 시계열이 비어 있어 USD/KRW ÷ USD/CNY 로 계산
]
CROSS = {"CNYKRW=X": ("KRW=X", "CNY=X")}
NEWS_QUERIES = [
    ("국내 증시", "코스피 증시"),
    ("미국 증시", "뉴욕증시"),
    ("중국 증시", "중국 증시 상해종합"),
    ("환율", "원달러 환율"),
    ("부동산", "서울 아파트 시장"),
]


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- 시세
def fetch_series(symbol, scale=1, rng="1y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range={rng}&interval=1d"
    d = json.loads(http_get(url))["chart"]["result"][0]
    ts = d.get("timestamp") or []
    closes = d["indicators"]["quote"][0]["close"]
    tz = timezone(timedelta(seconds=d["meta"].get("gmtoffset", 0)))
    out = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        day = datetime.fromtimestamp(t, tz).strftime("%Y-%m-%d")
        if out and out[-1][0] == day:
            out[-1] = (day, c * scale)
        else:
            out.append((day, c * scale))
    return out


def stats(series):
    closes = [c for _, c in series]
    rets = [(closes[i] / closes[i - 1] - 1) * 100 for i in range(1, len(closes))]

    def vol(n):
        r = rets[-n:]
        if len(r) < 2:
            return None
        m = sum(r) / len(r)
        sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
        return round(sd * math.sqrt(252), 2)  # 연율화 변동성(%)

    def chg(n):
        if len(closes) <= n:
            return None
        return round((closes[-1] / closes[-1 - n] - 1) * 100, 2)

    # 20일 이동 변동성 시계열
    roll = []
    for i in range(20, len(rets) + 1):
        r = rets[i - 20 : i]
        m = sum(r) / 20
        sd = math.sqrt(sum((x - m) ** 2 for x in r) / 19)
        roll.append(round(sd * math.sqrt(252), 2))
    dates = [d for d, _ in series]
    return {
        "last": round(closes[-1], 2),
        "lastDate": dates[-1],
        "prev": round(closes[-2], 2) if len(closes) > 1 else None,
        "chg1d": chg(1),
        "chg1w": chg(5),
        "chg1m": chg(21),
        "vol20": vol(20),
        "vol60": vol(60),
        "dates": dates,
        "closes": [round(c, 2) for c in closes],
        "rets": [None] + [round(x, 3) for x in rets],
        "volDates": dates[20:],
        "vol": roll,
    }


# ---------------------------------------------------------------- 뉴스
def fetch_news(query, n=6):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query + " when:2d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    )
    root = ET.fromstring(http_get(url))
    items = []
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        src = it.findtext("source") or ""
        if src and title.endswith(" - " + src):
            title = title[: -len(" - " + src)]
        pub = it.findtext("pubDate")
        try:
            dt = parsedate_to_datetime(pub).astimezone(KST)
        except Exception:
            dt = None
        items.append({
            "title": title,
            "link": it.findtext("link"),
            "source": src,
            "time": dt.strftime("%m-%d %H:%M") if dt else "",
            "ts": dt.timestamp() if dt else 0,
        })
    items.sort(key=lambda x: -x["ts"])
    return items[:n]


# ---------------------------------------------------------------- 부동산 (R-ONE)
RONE = "https://www.reb.or.kr/r-one/openapi/"
REGIONS = ["서울", "수도권", "경기", "인천", "전국"]


def rone(api, key, **params):
    params.update({"KEY": key, "Type": "json"})
    url = RONE + api + ".do?" + urllib.parse.urlencode(params)
    for attempt in range(4):  # 해외(GitHub Actions)에서 연결이 끊기는 경우가 있어 재시도
        try:
            d = json.loads(http_get(url, timeout=60))
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    if api not in d:  # 오류 응답
        raise RuntimeError(json.dumps(d, ensure_ascii=False)[:300])
    head, body = d[api][0]["head"], d[api][1]["row"] if len(d[api]) > 1 else []
    total = head[0].get("list_total_count", 0)
    return total, body


def rone_all(api, key, pSize=1000, **params):
    rows, page = [], 1
    while True:
        total, body = rone(api, key, pIndex=page, pSize=pSize, **params)
        rows += body
        if not body or len(rows) >= total:
            return rows
        page += 1


def find_table(tables, must, cycle, exclude=()):
    for t in tables:
        n = t["STATBL_NM"]
        if all(m in n for m in must) and not any(x in n for x in exclude) and cycle in (t["DTACYCLE_CD"] or ""):
            return t
    return None


def region_of(row):
    full = (row.get("CLS_FULLNM") or row.get("CLS_NM") or "").strip()
    return full if full in REGIONS else None


def table_series(key, table, cycle, start, item_hint=None, regions=None):
    sid = table["STATBL_ID"]
    # 1) 시작 시점 한 회차만 받아 지역(CLS_ID)·항목(ITM_ID) 코드를 찾는다 (응답 작게)
    probe = rone_all("SttsApiTblData", key, pSize=500, STATBL_ID=sid, DTACYCLE_CD=cycle, START_WRTTIME=start, END_WRTTIME=start)
    items = sorted({r["ITM_NM"] for r in probe})
    item = next((i for i in items if item_hint and item_hint in i), items[0] if items else None)
    itm_id = next((r["ITM_ID"] for r in probe if r["ITM_NM"] == item), None)
    cls_ids = {}
    for r in probe:
        full = (r.get("CLS_FULLNM") or r.get("CLS_NM") or "").strip()
        if full in (regions or REGIONS):
            cls_ids.setdefault(full, r["CLS_ID"])
    # 2) 필요한 지역만 전체 기간 조회
    rows = []
    for reg, cid in cls_ids.items():
        q = dict(STATBL_ID=sid, DTACYCLE_CD=cycle, START_WRTTIME=start, CLS_ID=cid)
        if itm_id is not None:
            q["ITM_ID"] = itm_id
        rows += rone_all("SttsApiTblData", key, pSize=500, **q)
    out = {}
    for r in rows:
        full = (r.get("CLS_FULLNM") or r.get("CLS_NM") or "").strip()
        reg = full if full in (regions or REGIONS) else None
        if not reg or r["ITM_NM"] != item or r["DTA_VAL"] is None:
            continue
        out.setdefault(reg, {}).setdefault(r["WRTTIME_IDTFR_ID"], (r["WRTTIME_DESC"], r["DTA_VAL"]))
    series = {}
    for reg, pts in out.items():
        ks = sorted(pts)
        series[reg] = {"periods": [pts[k][0] for k in ks], "values": [pts[k][1] for k in ks]}
    return {"table": table["STATBL_NM"], "id": table["STATBL_ID"], "item": item,
            "unit": rows[0].get("UI_NM") if rows else "", "series": series}


def fetch_realestate(cfg):
    key = (os.environ.get("RONE_KEY") or cfg.get("rone_key") or "").strip()
    if not key:
        return {"status": "nokey"}
    total, _ = rone("SttsApiTbl", key, pIndex=1, pSize=1)
    tables = rone_all("SttsApiTbl", key)
    ov = cfg.get("rone_tables", {})

    def pick(name, must, cycle, exclude=()):
        if ov.get(name):
            t = next((x for x in tables if x["STATBL_ID"] == ov[name]), None)
            if t:
                return t
        return find_table(tables, must, cycle, exclude)

    now = datetime.now(KST)
    res = {"status": "ok", "errors": []}
    y3 = str(now.year - 3) + "01"
    specs = [
        # 이름, 기본 STATBL_ID, 필수 키워드(대체 탐색용), 주기, 제외 키워드, 시작시점, 항목 힌트, 지역
        ("price_weekly", "T244183132827305", ["(주) 매매가격지수"], "WK", ["전세"],
         str(now.year - 1) + "01", "지수", ["서울", "수도권", "전국"]),
        ("price_monthly", "A_2024_00045", ["(월) 매매가격지수_아파트"], "MM", ["계절"], y3, "지수", ["서울", "수도권", "전국"]),
        ("trade", "A_2024_00554", ["(월) 행정구역별 아파트매매거래현황"], "MM", [], y3, "동(호)수", ["서울", "경기", "인천", "전국"]),
        ("supply", "T244633134461863", ["신규 분양세대수"], "MM", [], y3, "분양", ["수도권", "전국"]),
    ]
    for name, sid, must, cycle, excl, start, hint, regs in specs:
        ov.setdefault(name, "")
        if not ov[name]:
            ov[name] = sid
        t = pick(name, must, cycle, excl)
        if not t:
            res["errors"].append(f"{name}: R-ONE 통계표를 찾지 못함 (config.json 의 rone_tables 에 STATBL_ID 지정 가능)")
            continue
        try:
            res[name] = table_series(key, t, cycle, start, hint, regs)
            if name == "supply":
                res[name]["unit"] = "세대"  # API 메타의 단위 표기가 '지수'로 잘못 내려옴
            if name == "trade":
                res[name]["unit"] = "호"
        except Exception as e:
            res["errors"].append(f"{name}: {e}")
    # 주간 가격지수 → 주간 변동률(%) 추가
    pw = res.get("price_weekly")
    if pw:
        for s in pw["series"].values():
            v = s["values"]
            s["chg"] = [None] + [round((v[i] / v[i - 1] - 1) * 100, 3) for i in range(1, len(v))]
    res["catalogHint"] = [
        {"id": t["STATBL_ID"], "name": t["STATBL_NM"], "cycle": t["DTACYCLE_CD"]}
        for t in tables
        if any(k in t["STATBL_NM"] for k in ("분양", "거래", "매매가격지수"))
    ][:80]
    return res


# ---------------------------------------------------------------- main
def load_previous():
    try:
        txt = open(os.path.join(HERE, "data.js"), encoding="utf-8").read()
        return json.loads(txt[txt.index("{"): txt.rstrip().rstrip(";").rindex("}") + 1])
    except Exception:
        return {}


def main():
    cfg_path = os.path.join(HERE, "config.json")
    cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
    data = {"updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"), "errors": []}

    data["indices"] = []
    for grp, name, sym in INDICES:
        try:
            data["indices"].append({"group": grp, "name": name, "symbol": sym, **stats(fetch_series(sym))})
            print("OK ", name)
        except Exception as e:
            data["errors"].append(f"{name}: {e}")
            print("ERR", name, e)

    data["fx"] = []
    for name, sym, scale in FX:
        try:
            if sym in CROSS:
                a, b = (dict(fetch_series(s)) for s in CROSS[sym])
                series = [(d, a[d] / b[d] * scale) for d in sorted(a) if d in b]
            else:
                series = fetch_series(sym, scale)
            data["fx"].append({"name": name, "symbol": sym, **stats(series)})
            print("OK ", name)
        except Exception as e:
            data["errors"].append(f"{name}: {e}")
            print("ERR", name, e)

    data["news"] = []
    for label, q in NEWS_QUERIES:
        try:
            data["news"].append({"label": label, "items": fetch_news(q)})
            print("OK  뉴스", label)
        except Exception as e:
            data["errors"].append(f"뉴스 {label}: {e}")

    try:
        data["realestate"] = fetch_realestate(cfg)
        print("OK  부동산", data["realestate"].get("status"), data["realestate"].get("errors", ""))
    except Exception as e:
        data["realestate"] = {"status": "error", "message": str(e)}
        print("ERR 부동산", e)
    prev = load_previous().get("realestate") or {}
    if prev.get("status") == "ok":
        cur = data["realestate"]
        if cur.get("status") != "ok":
            prev["stale"] = sorted(k for k in ("price_weekly", "price_monthly", "trade", "supply") if prev.get(k))
            data["realestate"] = prev
            print("    부동산: 전체 이전 데이터 유지")
        else:
            cur["stale"] = []
            for k in ("price_weekly", "price_monthly", "trade", "supply"):
                if not cur.get(k) and prev.get(k):
                    cur[k] = prev[k]
                    cur["stale"].append(k)
                    print("    부동산: 이전 데이터 유지 →", k)
    # 실패 메시지는 로그에만 남기고 화면에는 '이전 데이터' 표시만
    re_ = data["realestate"]
    if re_.get("status") == "ok":
        re_["errors"] = [e for e in re_.get("errors", []) if e.split(":")[0] not in re_.get("stale", [])]

    with open(os.path.join(HERE, "data.js"), "w", encoding="utf-8") as f:
        f.write("window.DASH = " + json.dumps(data, ensure_ascii=False) + ";\n")
    print("data.js 저장 완료:", data["updated"])


if __name__ == "__main__":
    main()
