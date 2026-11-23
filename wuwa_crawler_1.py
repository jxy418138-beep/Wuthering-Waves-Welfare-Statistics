#!/usr/bin/env python3
"""鸣潮 福利 / 兑换码 / 活动时间表 爬虫 (按版本归类) -> data.json
用法:  python wuwa_crawler.py            # 抓取 SOURCES 全部页面
       python wuwa_crawler.py -u URL     # 临时追加页面
依赖:  pip install requests beautifulsoup4 playwright && playwright install chromium
       (没装 playwright 也能运行，只是动态加载的页面可能读不到)
"""
import argparse, base64, glob, json, os, re, time
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import parse_qs, urlparse
import requests
from bs4 import BeautifulSoup

# (来源名, URL)。版本号取自页面标题。
# 活动时间表主要来自官方「X.X版本内容说明」；兑换码和星声统计来自攻略站。
SOURCES = [
    # —— 官方版本公告（活动名 / 起止时间）——
    ("官方公告", "https://www.bilibili.com/read/cv53233769"),                     # 3.7
    ("IT之家转载官方", "https://www.ithome.com/0/969/268.htm"),                    # 3.5
    ("官方公告", "https://www.bilibili.com/opus/1150147651539304472"),            # 3.0
    ("官方公告", "https://www.bilibili.com/opus/1105988490044112932"),            # 2.6
    # —— 攻略站（星声统计 / 兑换码）——
    ("3DM手游", "https://shouyou.3dmgame.com/gl/638440.html"),                    # 3.7 星声统计
    ("3DM手游", "https://shouyou.3dmgame.com/gl/637136.html"),                    # 3.7 前瞻福利码
    ("17173", "https://news.17173.com/content/05202026/140644629.shtml"),         # 3.3 下半星声
    ("18183", "https://www.18183.com/gonglue/202603/vq8t2mkn.html"),              # 3.2 兑换码
    ("17173", "https://news.17173.com/content/02042026/010934445.shtml"),         # 3.1 福利汇总
    ("17173", "https://news.17173.com/content/12132025/045438660.shtml"),         # 3.0 前瞻兑换码
    ("17173", "https://news.17173.com/content/09272025/091505959.shtml"),         # 2.7 前瞻兑换码
    ("17173", "https://news.17173.com/content/08252025/232419196.shtml"),         # 2.6 星声汇总
    ("17173", "https://news.17173.com/content/08172025/202705895.shtml"),         # 2.6 前瞻兑换码
    ("18183", "https://www.18183.com/gonglue/202508/6ev39m2b.html"),              # 2.6 星声汇总
    ("17173", "https://news.17173.com/content/07232025/234514596.shtml"),         # 2.5 星声汇总
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
FOUND_HOSTS = ("bilibili.com", "ithome.com", "17173.com", "3dmgame.com", "18183.com")
TITLE_VER = re.compile(r"(?<![\d.])([1-4]\.\d)(?![\d.])")
HEAD_VER = re.compile(r"(?<![\d.])([1-4]\.\d)\s*(?:新?版本|版)")
TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Z0-9]{6,20}(?![A-Za-z0-9])")
KEYWORDS = ("星声", "漂泉", "浮金波纹", "唤声涡纹", "铸潮波纹", "溢彩", "福利", "补偿", "奖励")
# 官方公告格式:  [活动名]活动类型 描述…… ✦活动时间：起 ~ 止      (活动名也可能写成 「活动名」)
ACT = re.compile(r"(?:\[\s*([^\[\]]{2,25}?)\s*\]|「([^」]{2,25})」)\s*\**\s*((?:[^\s✦\[\]「」，。*]{1,12}(?:活动|玩法))?)[^✦\[]*?"
                 r"✦\s*(?:【[^】]*】)?\s*(?:活动|开放|上架)时间[：:]\s*([^✦\[（(「※【]{0,90})")
DT = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(\d{1,2})\s*[:：]\s*(\d{2})")
MAINT = re.compile(r"更新维护时间[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
UPD = re.compile(r"(?<![\d.])([1-4]\.\d)\s*版本更新后")
FMT = "%Y-%m-%d %H:%M"


def script_strings(scripts):
    """页面是动态加载时，内容常藏在 <script> 的 JSON 里：把含中文的字符串取出来拼成文本"""
    out = []
    for sc in scripts:
        for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', sc):
            if re.search(r"[\u4e00-\u9fa5]", lit):
                try:
                    out.append(json.loads('"%s"' % lit))
                except Exception:
                    pass
    return out


def to_lines(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    scripts = [t.get_text() for t in soup.find_all("script")]
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    lines = [re.sub(r"\s+", " ", x).strip() for x in soup.get_text("\n").split("\n")]
    lines = [x for x in lines if x]
    if not has_acts(lines):
        lines += script_strings(scripts)
    return title, lines


def has_acts(lines):
    t = " ".join(lines)
    return "✦" in t and "时间" in t


_browser = None


def render(url):
    """用无头浏览器打开页面（B站等动态页面需要）"""
    global _browser
    from playwright.sync_api import sync_playwright
    if _browser is None:
        _browser = sync_playwright().start().chromium.launch()
    page = _browser.new_page(user_agent=UA)
    try:
        page.goto(url, wait_until="networkidle", timeout=45000)
        return page.content()
    finally:
        page.close()


def fetch(url, render_ok=False):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.encoding = r.apparent_encoding or "utf-8"
    title, lines = to_lines(r.text)
    if render_ok and not has_acts(lines):
        try:
            t2, l2 = to_lines(render(url))
            if has_acts(l2):
                title, lines = t2, l2
        except Exception as e:
            print(f"[渲染失败] {url}: {e}")
    return title, lines


def real_url(h):
    if "bing.com/ck/a" in h:
        u = parse_qs(urlparse(h).query).get("u", [""])[0]
        if u.startswith("a1"):
            u = u[2:]
            try:
                return base64.urlsafe_b64decode(u + "=" * (-len(u) % 4)).decode()
            except Exception:
                return ""
    return h


def search(q):
    r = requests.get("https://www.bing.com/search", params={"q": q, "setlang": "zh-CN"}, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for a in soup.select("li.b_algo h2 a"):
        u = real_url(a.get("href", ""))
        if u.startswith("http") and any(h in u for h in FOUND_HOSTS):
            out.append(u)
    return out[:5]


def next_ver(v):
    a, b = map(int, v.split("."))
    return f"{a}.{b + 1}" if b < 9 else f"{a + 1}.0"


def vkey(v):
    return tuple(int(x) for x in v.split("."))


def is_code(s):
    return re.search(r"[A-Z]", s) is not None


def to_dt(m):
    y, mo, d, h, mi = map(int, m.groups())
    return datetime(y, mo, d, h, mi)


def rewards(seg):
    """从一段文字里提取 星声×N / N抽 / 材料×N"""
    r = []
    for n in re.findall(r"(\d{2,5})\s*星声", seg):
        r.append(f"星声×{n}")
    for n in re.findall(r"(?<![\d.])(\d{1,3})\s*抽", seg):
        r.append(f"{n}抽")
    for k, n in re.findall(r"([\u4e00-\u9fa5]{2,8})\s*\*\s*(\d+)", seg):
        r.append(f"{k}×{n}")
    return list(dict.fromkeys(r))


def body_version(text, title):
    """官方公告的版本号：正文里最常出现的 “X.X 版本更新后”，否则取标题"""
    c = Counter(UPD.findall(text))
    if c and c.most_common(1)[0][1] >= 2:
        return c.most_common(1)[0][0]
    m = TITLE_VER.search(title)
    return m.group(1) if m else "未知"


def parse_activities(text, name, url):
    mm = MAINT.search(text)
    vstart = datetime(int(mm[1]), int(mm[2]), int(mm[3]), 4, 0) if mm else None
    acts = []
    for m in ACT.finditer(text):
        aname = (m.group(1) or m.group(2)).strip()
        atype, tstr = m.group(3), m.group(4)
        nxt = text.find("[", m.end())
        block = text[m.start(): nxt if nxt > 0 else m.end() + 300][:600]
        own = re.search(r"✦\s*【%s】\s*(?:活动|开放)时间[：:]\s*([^✦\[（(「※【]{0,90})" % re.escape(aname), block)
        if own:
            tstr = own.group(1)
        dts = [to_dt(x) for x in DT.finditer(tstr)]
        txt = re.sub(r"\s+", "", tstr)
        parts = re.split(r"[~～]", txt)
        vs = vstart or "版本更新"
        if len(dts) >= 2:
            start, end = dts[0], dts[1]
        elif len(dts) == 1 and "永久" in txt:
            start, end = dts[0], "永久"
        elif len(dts) == 1 and "更新后" in txt:
            start, end = vs, dts[0]
        elif "永久" in txt:
            start, end = vs, "永久"
        elif "更新后" in txt:
            start = vs
            end = parts[-1].split("※")[0][:16] if len(parts) > 1 else ""
        else:
            continue
        days = None
        if isinstance(start, datetime) and isinstance(end, datetime):
            days = round((end - start).total_seconds() / 86400)
        elif end == "永久":
            days = "永久"
        acts.append({
            "name": aname, "type": atype,
            "start": start.strftime(FMT) if isinstance(start, datetime) else start,
            "end": end.strftime(FMT) if isinstance(end, datetime) else end,
            "days": days, "reward": rewards(block), "source": name, "url": url,
        })
    return vstart, acts


def parse(title, lines, name, url):
    out = defaultdict(lambda: {"codes": [], "welfare": []})
    m = TITLE_VER.search(title)
    page_ver = m.group(1) if m else None
    ver, zone = page_ver or "未知", 0
    for ln in lines:
        h = HEAD_VER.search(ln)
        if h and len(ln) < 80 and not page_ver:
            ver = h.group(1)
        if "兑换码" in ln:
            zone = 8
            for t in TOKEN.findall(ln):
                if is_code(t):
                    out[ver]["codes"].append({"code": t, "source": name, "url": url})
        elif zone and TOKEN.fullmatch(ln) and is_code(ln):
            out[ver]["codes"].append({"code": ln, "source": name, "url": url})
            zone -= 1
        elif zone:
            zone -= 1
        if re.search(r"\d", ln) and len(ln) < 120:
            if re.search(r"零氪|小月卡|大月卡", ln) and re.search(r"星声|抽", ln):
                out[ver]["welfare"].append({"text": ln, "kind": "汇总", "source": name, "url": url})
            elif any(k in ln for k in KEYWORDS):
                out[ver]["welfare"].append({"text": ln, "kind": "条目", "source": name, "url": url})
    return page_ver or "未知", out


def absorb(name, url, title, lines, merged, vtext):
    pver, res = parse(title, lines, name, url)
    text = " ".join(lines)
    vstart, acts = parse_activities(text, name, url)
    aver = body_version(text, title) if acts else pver
    vtext[aver].append(text)
    if aver != pver:
        vtext[pver].append(text)
    for v, d in res.items():
        for c in d["codes"]:
            merged[v]["codes"].setdefault(c["code"], c)
        for w in d["welfare"]:
            merged[v]["welfare"].setdefault(w["text"], w)
    for a in acts:
        merged[aver]["acts"].setdefault(a["name"], a)
    if vstart:
        merged[aver]["start"] = vstart.strftime("%Y-%m-%d")
    print(f"[完成] {name} 《{title[:20]}》文字{len(text)}字 → 版本{aver}: {len(acts)} 个活动, "
          f"{sum(len(d['codes']) for d in res.values())} 个兑换码")
    return aver, acts


def discover(merged, vtext, seen):
    """自动查找：给还没有活动表的版本（含下一个新版本），去搜索官方「版本内容说明」"""
    known = [v for v in merged if re.fullmatch(r"\d\.\d", v)]
    if not known:
        return
    top = next_ver(next_ver(max(known, key=vkey)))
    v, ladder = "3.0", []
    while vkey(v) <= vkey(top):
        ladder.append(v)
        v = next_ver(v)
    tried = 0
    for v in ladder:
        if v in merged and len(merged[v]["acts"]) >= 3:
            continue
        tried += 1
        if tried > 12:
            break
        try:
            urls = search(f"鸣潮 {v}版本内容说明")
        except Exception as e:
            print(f"[搜索失败] {v}: {e}")
            continue
        print(f"[自动查找] {v}: 找到 {len(urls)} 个候选页面")
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            try:
                title, lines = fetch(u, render_ok=True)
                text = " ".join(lines)
                _, acts = parse_activities(text, "自动查找", u)
                if len(acts) >= 3 and body_version(text, title) == v:
                    absorb("官方公告(自动)", u, title, lines, merged, vtext)
                    break
            except Exception as e:
                print(f"[候选失败] {u}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-u", "--url", action="append", default=[])
    ap.add_argument("-o", "--out", default="data.json")
    args = ap.parse_args()
    sources = SOURCES + [(u.split("/")[2], u) for u in args.url]

    merged = defaultdict(lambda: {"start": "", "codes": {}, "welfare": {}, "acts": {}})
    vtext, seen = defaultdict(list), set()
    for name, url in sources:
        seen.add(url)
        try:
            title, lines = fetch(url, render_ok=name.startswith("官方"))
        except Exception as e:
            print(f"[失败] {name} {url}: {e}")
            continue
        absorb(name, url, title, lines, merged, vtext)
    # 官方公告文字：notices/3.7.txt 或仓库根目录 notice_3.7.txt（文件名里写版本号）
    for p in sorted(glob.glob("notices/*.txt") + glob.glob("notice_*.txt")):
        txt = open(p, encoding="utf-8").read()
        absorb("官方公告", "", os.path.basename(p), [x.strip() for x in txt.splitlines() if x.strip()], merged, vtext)
    try:
        discover(merged, vtext, seen)
    except Exception as e:
        print(f"[自动查找失败] {e}")

    # 保留上次 data.json 里已有的内容（本次没抓到也不丢）
    if os.path.exists(args.out):
        try:
            prev = json.load(open(args.out, encoding="utf-8"))
            for v, d in prev.get("versions", {}).items():
                m = merged[v]
                m["start"] = m["start"] or d.get("start", "")
                for a in d.get("activities", []):
                    m["acts"].setdefault(a["name"], a)
                for c in d.get("codes", []):
                    m["codes"].setdefault(c["code"], c)
                for w in d.get("welfare", []):
                    m["welfare"].setdefault(w["text"], w)
        except Exception as e:
            print(f"[读取旧数据失败] {e}")

    # 用其他文章补充活动福利（在文中找到活动名，取其后一小段里的星声/抽数）
    for v, d in merged.items():
        for a in d["acts"].values():
            got = list(a["reward"])
            for text in vtext.get(v, []):
                i = text.find(a["name"])
                if i < 0:
                    continue
                seg = text[i + len(a["name"]): i + len(a["name"]) + 250]
                cut = re.search(r"[【\[]", seg)
                got += rewards(seg[: cut.start()] if cut else seg)
            a["reward"] = list(dict.fromkeys(got))[:6]

    key = lambda v: (v == "未知", vkey(v) if v != "未知" else ())
    skey = lambda a: a["start"] if a["start"][:1].isdigit() else "0000"
    data = {
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "versions": {v: {"start": merged[v]["start"],
                         "activities": sorted(merged[v]["acts"].values(), key=skey),
                         "codes": list(merged[v]["codes"].values()),
                         "welfare": list(merged[v]["welfare"].values())}
                     for v in sorted(merged, key=key)},
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已写入 {args.out}")


if __name__ == "__main__":
    main()
