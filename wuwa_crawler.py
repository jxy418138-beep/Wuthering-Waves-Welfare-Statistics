#!/usr/bin/env python3
"""鸣潮 福利 / 兑换码 爬虫 (按版本归类)
用法:  python wuwa_crawler.py            # 抓取 SOURCES 全部页面 -> data.json
       python wuwa_crawler.py -u URL     # 临时追加页面
依赖:  pip install requests beautifulsoup4
"""
import argparse, json, re, time
from collections import defaultdict
import requests
from bs4 import BeautifulSoup

# (来源名, URL)。版本号优先取自页面标题，如 "鸣潮3.2版本兑换码"。
# 新版本出来后，把 17173 / 18183 / 3DM手游 上的新文章链接追加到这里即可。
SOURCES = [
    ("官方公告(B站)", "https://www.bilibili.com/read/cv53233769"),          # 3.7 维护补偿
    ("3DM手游", "https://shouyou.3dmgame.com/gl/638440.html"),              # 3.7 星声统计
    ("3DM手游", "https://shouyou.3dmgame.com/gl/637136.html"),              # 3.7 前瞻福利码
    ("17173", "https://news.17173.com/content/05202026/140644629.shtml"),   # 3.3 下半星声
    ("18183", "https://www.18183.com/gonglue/202603/vq8t2mkn.html"),        # 3.2 兑换码
    ("17173", "https://news.17173.com/content/02042026/010934445.shtml"),   # 3.1 福利汇总
    ("17173", "https://news.17173.com/content/12132025/045438660.shtml"),   # 3.0 前瞻兑换码
    ("17173", "https://news.17173.com/content/09272025/091505959.shtml"),   # 2.7 前瞻兑换码
    ("17173", "https://news.17173.com/content/08252025/232419196.shtml"),   # 2.6 星声汇总
    ("17173", "https://news.17173.com/content/08172025/202705895.shtml"),   # 2.6 前瞻兑换码
    ("18183", "https://www.18183.com/gonglue/202508/6ev39m2b.html"),        # 2.6 星声汇总
    ("17173", "https://news.17173.com/content/07232025/234514596.shtml"),   # 2.5 星声汇总
    ("18183", "https://www.18183.com/183youxituijian/202511/8820707.html"), # 历史兑换码合集(无版本)
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; wuwa-welfare-crawler)"}
TITLE_VER = re.compile(r"(?<![\d.])([1-4]\.\d)(?![\d.])")
HEAD_VER = re.compile(r"(?<![\d.])([1-4]\.\d)\s*(?:新?版本|版)")
TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Z0-9]{6,20}(?![A-Za-z0-9])")
KEYWORDS = ("星声", "漂泉", "浮金波纹", "唤声涡纹", "铸潮波纹", "溢彩", "福利", "补偿", "奖励")


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


def parse(title, lines, name, url):
    out = defaultdict(lambda: {"codes": [], "welfare": []})
    m = TITLE_VER.search(title)
    page_ver = m.group(1) if m else None
    ver, zone = page_ver or "未知", 0
    for ln in lines:
        h = HEAD_VER.search(ln)
        if h and len(ln) < 80 and not page_ver:
            ver = h.group(1)
        # 兑换码：同一行，或“兑换码”标题后几行里独占一行的大写串
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
        # 福利：零氪/月卡汇总行单独标记，其余含关键词+数字的短句为条目
        if re.search(r"\d", ln) and len(ln) < 120:
            if re.search(r"零氪|小月卡|大月卡", ln) and re.search(r"星声|抽", ln):
                out[ver]["welfare"].append({"text": ln, "kind": "汇总", "source": name, "url": url})
            elif any(k in ln for k in KEYWORDS):
                out[ver]["welfare"].append({"text": ln, "kind": "条目", "source": name, "url": url})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-u", "--url", action="append", default=[])
    ap.add_argument("-o", "--out", default="data.json")
    args = ap.parse_args()
    sources = SOURCES + [(u.split("/")[2], u) for u in args.url]

    merged = defaultdict(lambda: {"codes": {}, "welfare": {}})
    for name, url in sources:
        try:
            title, lines = fetch(url)
            res = parse(title, lines, name, url)
        except Exception as e:
            print(f"[失败] {name} {url}: {e}")
            continue
        for v, d in res.items():
            for c in d["codes"]:
                merged[v]["codes"].setdefault(c["code"], c)
            for w in d["welfare"]:
                merged[v]["welfare"].setdefault(w["text"], w)
        print(f"[完成] {name} 《{title[:20]}》: {sum(len(d['codes']) for d in res.values())} 码")
        time.sleep(1)

    key = lambda v: (v == "未知", [int(x) for x in v.split(".")] if v != "未知" else [])
    data = {
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "versions": {v: {"codes": list(merged[v]["codes"].values()),
                         "welfare": list(merged[v]["welfare"].values())}
                     for v in sorted(merged, key=key)},
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已写入 {args.out}")


if __name__ == "__main__":
    main()
