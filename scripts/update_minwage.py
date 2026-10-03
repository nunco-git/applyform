#!/usr/bin/env python3
"""다음 연도 최저임금을 뉴스에서 자동으로 찾아 minwage.json에 추가합니다.

- GitHub Actions(.github/workflows/minwage.yml)가 매년 8~12월에 자동으로 실행합니다.
- 구글 뉴스·빙 뉴스 RSS에서 'YYYY년 최저임금 … N원' 제목을 모아,
  '결정·확정·고시'라는 말이 들어간 기사 3건 이상이 같은 금액을 말할 때만 반영합니다.
  (노동계·경영계 '요구안' 같은 다른 숫자가 잘못 들어가지 않도록)
- 월 환산액은 시급 × 209시간(주 40시간 기준)으로 계산합니다.
- 바뀐 것이 없으면 파일을 건드리지 않습니다.
"""
import json, re, sys, datetime, urllib.request, urllib.parse, html
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'minwage.json'
UA = {'User-Agent': 'Mozilla/5.0 (minwage-updater; +https://github.com)'}

def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception as e:
        print('  가져오기 실패:', url, e)
        return ''

def headlines(year):
    q = f'{year}년 최저임금 시급'
    urls = [
        'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': q, 'hl': 'ko', 'gl': 'KR', 'ceid': 'KR:ko'}),
        'https://www.bing.com/news/search?' + urllib.parse.urlencode({'q': q, 'format': 'rss', 'setlang': 'ko-KR'}),
    ]
    out = []
    for u in urls:
        xml = fetch(u)
        for t in re.findall(r'<title>(.*?)</title>', xml, re.S) + re.findall(r'<description>(.*?)</description>', xml, re.S):
            t = html.unescape(re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+>', ' ', t))
            out.append(re.sub(r'\s+', ' ', t))
    return out

AMOUNT = re.compile(r'(20\d\d)년\s*(?:도\s*)?(?:적용\s*)?최저임금[^0-9]{0,25}?(?:시급|시간급)?[^0-9]{0,6}?([1-9]\d?,\d{3})\s*원')
AMOUNT_MAN = re.compile(r'(20\d\d)년\s*(?:도\s*)?(?:적용\s*)?최저임금[^0-9]{0,25}?(?:시급|시간급)?[^0-9]{0,6}?([1-9])만\s*(\d{1,4})\s*원')   # '1만700원'
DECIDED = re.compile(r'결정|확정|고시|의결|최종')
NOT_FINAL = re.compile(r'요구|제시|요청|제안|주장|촉구|전망|예상|수정안|최초안|초안')

def find(year, prev):
    votes = Counter()
    for t in headlines(year):
        if not DECIDED.search(t) or NOT_FINAL.search(t):
            continue
        found = [(y, int(a.replace(',', ''))) for y, a in AMOUNT.findall(t)] + [(y, int(m) * 10000 + int(r)) for y, m, r in AMOUNT_MAN.findall(t)]
        for y, v in found:
            if int(y) == year:
                if prev and not (prev * 0.97 <= v <= prev * 1.30):   # 말이 안 되는 숫자는 버림
                    continue
                votes[v] += 1
    print(f'  {year}년 후보:', dict(votes))
    if not votes:
        return None
    (best, n), = votes.most_common(1)
    total = sum(votes.values())
    return best if n >= 3 and n / total >= 0.6 else None

def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    years = data.setdefault('years', {})
    now = datetime.date.today()
    changed = False
    for year in (now.year + 1,):                      # 다음 연도 (보통 8월 5일 전후 고시)
        if str(year) in years:
            print(f'{year}년은 이미 있음:', years[str(year)]); continue
        prev = (years.get(str(year - 1)) or {}).get('hourly')
        v = find(year, prev)
        if v:
            years[str(year)] = {'hourly': v, 'monthly': v * 209}
            print(f'{year}년 최저임금 추가: 시급 {v:,}원 · 월 {v * 209:,}원'); changed = True
        else:
            print(f'{year}년: 확실한 결정 기사가 아직 부족함 – 다음 실행 때 다시 확인')
    if changed:
        data['updated'] = now.isoformat()
        data['years'] = dict(sorted(years.items()))
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0

if __name__ == '__main__':
    sys.exit(main())
