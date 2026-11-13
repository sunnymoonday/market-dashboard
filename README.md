# 시장 변동성 대시보드

국내·미국·중국 주가지수와 환율(달러·엔·유로·위안)의 일일 변동성, 주요 뉴스,
서울·수도권 주택시장(가격지수·거래량·신규 분양)을 한 페이지로 보여줍니다.

- 화면: `index.html` (Chart.js) — GitHub Pages로 배포
- 데이터: `update_data.py` → `data.js`
  - 주가·환율: Yahoo Finance / 뉴스: Google 뉴스 RSS / 부동산: 한국부동산원 R-ONE Open API
- 갱신: GitHub Actions가 매일 08:00 KST에 실행 (`.github/workflows/update.yml`)

## 설정
- 저장소 Settings → Secrets and variables → Actions 에 `RONE_KEY` (R-ONE 인증키) 등록
- 로컬 실행: `config.example.json`을 `config.json`으로 복사해 키를 넣고 `python update_data.py`
