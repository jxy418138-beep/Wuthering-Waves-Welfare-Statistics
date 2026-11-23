#!/usr/bin/env python3
"""鸣潮 福利 / 兑换码 / 活动时间表 爬虫 (按版本归类) -> data.json
用法:  python wuwa_crawler.py            # 抓取 SOURCES 全部页面
       python wuwa_crawler.py -u URL     # 临时追加页面
依赖:  pip install requests beautifulsoup4
"""
import argparse, json, re, time
from collections import defaultdict
from datetime import datetime
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

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; wuwa-welfare-crawler)"}
TITLE_VER = re.compile(r"(?<![\d.])([1-4]\.\d)(?![\d.])")
HEAD_VER = re.compile(r"(?<![\d.])([1-4]\.\d)\s*(?:新?版本|版)")
TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Z0-9]{6,20}(?![A-Za-z0-9])")
KEYWORDS = ("星声", "漂泉", "浮金波纹", "唤声涡纹", "铸潮波纹", "溢彩", "福利", "补偿", "奖励")
# 官方公告格式:  [活动名]活动类型 描述…… ✦活动时间：起 ~ 止
ACT = re.compile(r"\[\s*([^\[\]]{2,25}?)\s*\]\s*([^\s✦\[\]]{0,14})[^✦\[]*?✦\s*(?:活动|开放)时间[：:]\s*([^✦\[（(]{0,80})")
DT = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*(\d{1,2}):(\d{2})")
MAINT = re.compile(r"更新维护时间[：:]\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
FMT = "%Y-%m-%d %H:%M"


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    lines = [re.sub(r"\s+", " ", x).strip() for x in soup.get_text("\n").split("\n")]
    return title, [x for x in lines if x]


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


def parse_activities(text, name, url):
    mm = MAINT.search(text)
    vstart = datetime(int(mm[1]), int(mm[2]), int(mm[3]), 4, 0) if mm else None
    acts = []
    for m in ACT.finditer(text):
        aname, atype, tstr = m.group(1).strip(), m.group(2), m.group(3)
        dts = [to_dt(x) for x in DT.finditer(tstr)]
        start, end, days = None, None, None
        if len(dts) >= 2:
            start, end = dts[0], dts[1]
        elif len(dts) == 1 and "更新后" in tstr:
            start, end = vstart, dts[0]
        elif "永久" in tstr:
            start, end = vstart, "永久"
        elif "下个版本" in tstr:
            start, end = vstart, "下版本前"
        else:
            continue
        if isinstance(start, datetime) and isinstance(end, datetime):
            days = round((end - start).total_seconds() / 86400)
        elif end in ("永久", "下版本前"):
            days = end
        nxt = text.find("[", m.end())
        block = text[m.start(): nxt if nxt > 0 else m.end() + 300][:600]
        acts.append({
            "name": aname, "type": atype,
            "start": start.strftime(FMT) if isinstance(start, datetime) else "",
            "end": end.strftime(FMT) if isinstance(end, datetime) else (end or ""),
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-u", "--url", action="append", default=[])
    ap.add_argument("-o", "--out", default="data.json")
    args = ap.parse_args()
    sources = SOURCES + [(u.split("/")[2], u) for u in args.url]

    merged = defaultdict(lambda: {"start": "", "codes": {}, "welfare": {}, "acts": {}})
    vtext = defaultdict(list)
    for name, url in sources:
        try:
            title, lines = fetch(url)
            pver, res = parse(title, lines, name, url)
            text = " ".join(lines)
            vstart, acts = parse_activities(text, name, url)
        except Exception as e:
            print(f"[失败] {name} {url}: {e}")
            continue
        vtext[pver].append(text)
        for v, d in res.items():
            for c in d["codes"]:
                merged[v]["codes"].setdefault(c["code"], c)
            for w in d["welfare"]:
                merged[v]["welfare"].setdefault(w["text"], w)
        for a in acts:
            merged[pver]["acts"].setdefault(a["name"], a)
        if vstart:
            merged[pver]["start"] = vstart.strftime("%Y-%m-%d")
        print(f"[完成] {name} 《{title[:24]}》版本{pver}: {len(acts)} 个活动, "
              f"{sum(len(d['codes']) for d in res.values())} 个兑换码")
        time.sleep(1)

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

    key = lambda v: (v == "未知", [int(x) for x in v.split(".")] if v != "未知" else [])
    data = {
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "versions": {v: {"start": merged[v]["start"],
                         "activities": sorted(merged[v]["acts"].values(), key=lambda a: a["start"] or "9"),
                         "codes": list(merged[v]["codes"].values()),
                         "welfare": list(merged[v]["welfare"].values())}
                     for v in sorted(merged, key=key)},
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已写入 {args.out}")


if __name__ == "__main__":
    main()
