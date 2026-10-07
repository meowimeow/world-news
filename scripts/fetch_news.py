#!/usr/bin/env python3
"""해외 뉴스 RSS와 환율을 모아 data/ 아래 JSON 파일로 저장한다.

표준 라이브러리만 쓴다. GitHub Actions가 1시간마다 실행한다.
접속에 실패한 피드는 건너뛰고, 어느 피드가 성공했는지 data/index.json에 기록한다.
"""
import datetime as dt
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KST = dt.timezone(dt.timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; WorldBriefingBot/1.0)"
TIMEOUT = 20
KEEP_DAYS = 120       # 이보다 오래된 날짜 파일은 지운다
MAX_PER_DAY = 250     # 하루 파일에 보관할 최대 기사 수
SUMMARY_LEN = 220

FX_CODES = ["KRW", "JPY", "EUR", "CNY", "GBP"]
FX_LABELS = {
    "USD": ("미국 달러", 1),
    "JPY": ("일본 엔", 100),
    "EUR": ("유로", 1),
    "CNY": ("중국 위안", 1),
    "GBP": ("영국 파운드", 1),
}

STOP = set("""
a an the and or of to in on at for with from by as is are was were be been it its this that these those
after before over under into out up down off about than then but not no new says say said will would could can
may might has have had how what why who when where which more most amid against just first one two year years
day days week news live update latest video watch report reports you your we our they their his her he she all
here there now back set get gets make makes take takes among between during through while still also only many
much very next last former us has says per via
analysis opinion know explained explainer podcast review editorial comment today tonight morning photos pictures
gallery briefing newsletter breaking exclusive interview inside why whats thats both above below across
""".split())


def http_get(url):
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


# ---------- RSS 파싱 ----------
def local(tag):
    return tag.rsplit("}", 1)[-1]


def text_of(e):
    return "".join(e.itertext()).strip()


IMG_EXT = re.compile(r"\.(jpe?g|png|webp)(\?|$)", re.I)


def parse_feed(raw):
    """RSS 2.0, RSS 1.0(RDF), Atom을 모두 읽는다."""
    root = ET.fromstring(raw)
    out = []
    for e in root.iter():
        if local(e.tag) not in ("item", "entry"):
            continue
        rec = {"title": "", "link": "", "pub": "", "desc": "", "img": ""}
        for c in e:
            k = local(c.tag)
            if k == "title":
                rec["title"] = text_of(c)
            elif k == "link":
                href = c.get("href")
                if href:
                    if c.get("rel") in (None, "alternate") and not rec["link"]:
                        rec["link"] = href
                elif c.text and c.text.strip():
                    rec["link"] = c.text.strip()
            elif k in ("pubDate", "published", "updated", "date") and not rec["pub"]:
                rec["pub"] = text_of(c)
            elif k in ("description", "summary") and not rec["desc"]:
                rec["desc"] = text_of(c)
            elif k in ("thumbnail", "content", "enclosure") and not rec["img"]:
                url, typ, med = c.get("url"), c.get("type") or "", c.get("medium") or ""
                if url and (
                    k == "thumbnail"
                    or typ.startswith("image")
                    or med == "image"
                    or (not typ and not med and IMG_EXT.search(url))
                ):
                    rec["img"] = url
        out.append(rec)
    return out


def parse_dt(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except Exception:
            return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


BLOCK_TAG = re.compile(r"</?(?:p|br|div|li|ul|ol|h[1-6])\b[^>]*>", re.I)
TAG = re.compile(r"<[^>]+>")


def clean(s, limit=None):
    # 문단 태그는 공백으로, 글자 사이의 인라인 태그(<b> 등)는 그냥 지운다
    s = html.unescape(TAG.sub("", BLOCK_TAG.sub(" ", s or "")))
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return s


def safe_url(u, https_only=False):
    u = (u or "").strip()
    if https_only:
        return u if u.startswith("https://") else ""
    return u if u.startswith(("http://", "https://")) else ""


def norm_link(u):
    p = urlsplit(u)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))


def item_id(link):
    return hashlib.sha1(norm_link(link).encode()).hexdigest()[:12]


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def collect(feeds):
    items, status = [], []
    for f in feeds:
        n = 0
        try:
            for r in parse_feed(http_get(f["url"])):
                title = clean(r["title"])
                link = safe_url(r["link"])
                d = parse_dt(r["pub"])
                if not title or not link or not d:
                    continue
                items.append({
                    "id": item_id(link),
                    "title": title,
                    "link": link,
                    "summary": clean(r["desc"], SUMMARY_LEN),
                    "source": f["source"],
                    "cats": [f["cat"]],
                    "published": iso(d),
                    "img": safe_url(r["img"], https_only=True),
                })
                n += 1
        except Exception as e:  # 한 피드가 실패해도 계속 진행
            print(f"[건너뜀] {f['source']} / {f['cat']}: {e}", file=sys.stderr)
        status.append({"source": f["source"], "cat": f["cat"], "ok": n > 0, "count": n})
    return items, status


# ---------- 병합과 키워드 ----------
def merge_day(existing, new):
    by_id = {i["id"]: i for i in existing}
    titles = {norm_title(i["title"]): i["id"] for i in existing}
    for it in new:
        cur = by_id.get(it["id"])
        if cur:
            cur["cats"] = sorted(set(cur["cats"]) | set(it["cats"]))
            if not cur.get("img") and it.get("img"):
                cur["img"] = it["img"]
            continue
        nt = norm_title(it["title"])
        if nt in titles:  # 다른 매체가 같은 제목을 재전송한 경우
            continue
        by_id[it["id"]] = it
        titles[nt] = it["id"]
    items = sorted(by_id.values(), key=lambda x: x["published"], reverse=True)
    return items[:MAX_PER_DAY]


def keywords(items, top=8):
    """서로 다른 매체 2곳 이상의 제목에 나온 단어를 이슈 키워드로 뽑는다."""
    srcs, cnt, forms = defaultdict(set), Counter(), defaultdict(Counter)
    proper = Counter()  # 제목 중간에서 대문자로 쓰인 횟수(고유명사일 가능성)
    for it in items:
        seen = set()
        for pos, w in enumerate(re.findall(r"[A-Za-z][A-Za-z'’\-]{2,}", it["title"])):
            w = re.sub(r"['’]s$", "", w)
            k = w.lower()
            if k in STOP or len(k) < 3:
                continue
            forms[k][w] += 1
            if pos > 0 and w[0].isupper():
                proper[k] += 1
            if k in seen:
                continue
            seen.add(k)
            cnt[k] += 1
            srcs[k].add(it["source"])
    ranked = [k for k in cnt if len(srcs[k]) >= 2]
    ranked.sort(key=lambda k: (-len(srcs[k]), -(proper[k] > 0), -cnt[k], k))
    out = []
    for k in ranked[:top]:
        form = forms[k].most_common(1)[0][0]
        out.append(form.capitalize() if form.islower() else form)
    return out


# ---------- 환율 ----------
def normalize_fx(data):
    """Frankfurter v2(행 배열)와 v1(날짜별 사전) 응답을 {날짜: {통화: 값}}로 바꾼다."""
    out = defaultdict(dict)
    if isinstance(data, list):
        for r in data:
            out[r["date"]][r["quote"]] = float(r["rate"])
    elif isinstance(data, dict) and isinstance(data.get("rates"), dict):
        rates = data["rates"]
        if rates and all(isinstance(v, dict) for v in rates.values()):
            for d, row in rates.items():
                for q, v in row.items():
                    out[d][q] = float(v)
        elif "date" in data:
            for q, v in rates.items():
                out[data["date"]][q] = float(v)
    return dict(out)


def krw_series(by_date):
    """USD 기준 값을 '외화 1단위(엔은 100엔)당 원화'로 바꾼다."""
    pairs = {c: [] for c in FX_LABELS}
    for d in sorted(by_date):
        row = by_date[d]
        if "KRW" not in row:
            continue
        krw = row["KRW"]
        pairs["USD"].append({"d": d, "v": krw})
        for c in ("JPY", "EUR", "CNY", "GBP"):
            if c in row and row[c]:
                unit = FX_LABELS[c][1]
                pairs[c].append({"d": d, "v": krw / row[c] * unit})
    return pairs


def build_fx(fetch=http_get, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    start = (today - dt.timedelta(days=45)).isoformat()
    quotes = ",".join(FX_CODES)
    urls = [
        f"https://api.frankfurter.dev/v2/rates?from={start}&base=USD&quotes={quotes}",
        f"https://api.frankfurter.dev/v1/{start}..?base=USD&symbols={quotes}",
    ]
    by_date, last_err = {}, None
    for u in urls:
        try:
            by_date = normalize_fx(json.loads(fetch(u)))
            if by_date:
                break
        except Exception as e:
            last_err = e
    if not by_date:
        raise RuntimeError(f"환율을 가져오지 못했습니다: {last_err}")
    pairs_out = []
    for code, series in krw_series(by_date).items():
        series = series[-30:]
        if len(series) < 2:
            continue
        cur, prev = series[-1]["v"], series[-2]["v"]
        pairs_out.append({
            "code": code,
            "label": FX_LABELS[code][0],
            "unit": FX_LABELS[code][1],
            "value": round(cur, 2),
            "change": round(cur - prev, 2),
            "pct": round((cur - prev) / prev * 100, 2),
            "series": [{"d": s["d"], "v": round(s["v"], 2)} for s in series],
        })
    if not pairs_out:
        raise RuntimeError("환율 계산에 필요한 데이터가 부족합니다")
    return {
        "updated": iso(dt.datetime.now(dt.timezone.utc)),
        "asof": max(by_date),
        "source": "Frankfurter (중앙은행 기준 환율, 하루 1회 갱신)",
        "pairs": pairs_out,
    }


# ---------- 저장 ----------
def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def update_days(items, data_dir=None, now=None):
    data_dir = data_dir or DATA
    now = now or dt.datetime.now(dt.timezone.utc)
    by_day = defaultdict(list)
    for it in items:
        d = dt.datetime.strptime(it["published"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        by_day[d.astimezone(KST).date().isoformat()].append(it)
    days_dir = data_dir / "days"
    for day, new in by_day.items():
        path = days_dir / f"{day}.json"
        existing = json.loads(path.read_text("utf-8"))["items"] if path.exists() else []
        merged = merge_day(existing, new)
        write_json(path, {"date": day, "updated": iso(now), "items": merged, "keywords": keywords(merged)})
    # 오래된 날짜 삭제
    limit = (now.astimezone(KST).date() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    if days_dir.exists():
        for p in days_dir.glob("*.json"):
            if p.stem < limit:
                p.unlink()


def build_index(status, data_dir=None, now=None, extra=None):
    data_dir = data_dir or DATA
    now = now or dt.datetime.now(dt.timezone.utc)
    dates = []
    for p in sorted((data_dir / "days").glob("*.json"), reverse=True):
        d = json.loads(p.read_text("utf-8"))
        dates.append({"date": d["date"], "count": len(d["items"]), "top": d.get("keywords", [])[:2]})
    idx = {"updated": iso(now), "dates": dates, "feeds": status}
    if extra:
        idx.update(extra)
    write_json(data_dir / "index.json", idx)


def main():
    feeds = json.loads((ROOT / "feeds.json").read_text("utf-8"))
    problems = []

    try:
        write_json(DATA / "fx.json", build_fx())
    except Exception as e:
        print(f"[환율 실패] {e}", file=sys.stderr)
        problems.append("fx")

    items, status = collect(feeds)
    ok = sum(1 for s in status if s["ok"])
    print(f"피드 {ok}/{len(status)}곳 성공, 기사 {len(items)}건")
    if ok == 0:
        print("[오류] 성공한 피드가 없어 기존 데이터를 그대로 둡니다", file=sys.stderr)
        return 1
    update_days(items)
    build_index(status)
    if problems:  # 환율만 실패하면 뉴스는 저장하고, Actions 로그에 경고만 남긴다
        print("::warning::환율 갱신에 실패했습니다. 이전 값이 그대로 표시됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
