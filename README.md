# 📰 매일 2회 투자용 경제뉴스 자동 브리핑

미국·한국 거시경제 지표, 금리/CPI/인플레이션, 주요 인물 발언, 산업 전망, 주목
상장사, 반복 키워드 빈도를 **팩트 기반으로 요약**해 매일 **오전 7시 / 오후 7시(KST)**
자동으로 생성·저장하는 시스템입니다.

## 구조
```
news/
├── prompt/briefing-prompt.md   # 리서치+작성 지시문(브리핑 품질의 핵심)
├── scripts/run-briefing.sh     # 실행 래퍼 (launchd가 호출)
├── scripts/install.sh          # launchd 자동실행 등록 (1회)
├── briefings/YYYY-MM-DD-AM/PM.md# 날짜·회차별 브리핑(자동 생성)
├── data/keyword-index.json     # 누적 키워드 빈도/이력
├── data/latest.md              # 가장 최근 브리핑 사본
└── logs/run.log                # 실행 로그
```

## 설치 (자동 실행 등록)
```bash
bash scripts/install.sh
```
- 매일 07:00 / 19:00 자동 실행됩니다.
- 예약 시각에 Mac이 자고 있었으면 **깨어난 직후 1회 보강 실행**됩니다(launchd 기본 동작).

## 수동 실행(테스트)
```bash
# 오전 회차 즉시 실행
bash scripts/run-briefing.sh AM
# 오후 회차 즉시 실행
bash scripts/run-briefing.sh PM
# (인자 없으면 현재 시각으로 AM/PM 자동 판정)
```

## 결과 보기
- 최신 브리핑: `data/latest.md`
- 과거 기록:   `briefings/` 폴더
- 키워드 추세: `data/keyword-index.json` / 회사: `data/company-index.json`
- 3일 종합:   `data/synthesis-3day.md`

## 🌐 공개 웹사이트 (대시보드)
`docs/` 폴더가 공개 사이트입니다. 5개 탭으로 구성:
- 🗞️ 최신 브리핑 · 🧭 3일 중간 종합
- 🔑 키워드 빈도·증감율 (전일 대비 ▲/▼ %, 7일/30일 누적, 정렬, Top10 차트)
- 🏢 회사 언급 빈도·증감율 (시장/증감/누적 + 차트)
- 🗂️ 아카이브 (과거 브리핑 열람)

**로컬 미리보기** (file:// 직접 열기는 데이터 로드가 막히므로 서버로):
```bash
bash scripts/serve.sh        # http://localhost:8765
```

**공개 배포 (GitHub Pages, 무료·1회 설정):**
1. github.com 에서 빈 public 저장소 생성 (예: `my-invest-news`)
2. `bash scripts/deploy-setup.sh https://github.com/USERNAME/my-invest-news.git`
3. 저장소 Settings → Pages → Branch: `main` / 폴더: `/docs` → Save
4. 공개 주소: `https://USERNAME.github.io/my-invest-news/`

이후 매 브리핑(오전7시/오후7시)마다 `build-site.sh`가 데이터를 `docs/`로 갱신하고
자동 커밋·푸시 → 사이트가 자동 업데이트됩니다.

> 참고: `docs/data/`의 샘플(미리보기) 데이터는 **첫 실제 브리핑 실행 시 실데이터로 교체**됩니다.

## 시간 변경 / 중지
- **시간 변경**: `scripts/install.sh`의 `StartCalendarInterval` Hour/Minute 수정 후 다시
  `bash scripts/install.sh` 실행.
- **중지**: `launchctl unload ~/Library/LaunchAgents/com.shinhee.news-briefing.plist`
- **등록 확인**: `launchctl list | grep news-briefing`

## (선택) 정시 자동 깨우기
Mac이 자고 있어도 정확히 정시에 실행되길 원하면, 1회만 아래를 실행하세요(관리자 암호 필요).
단, `pmset repeat`는 **하루 1회 깨우기**만 지원하므로 오전 회차 기준으로 설정합니다.
```bash
sudo pmset repeat wakeorpoweron MTWRFSU 06:55:00
```
오후 회차까지 보장하려면 전원 연결 + 절전 시 깨우기 허용 설정을 권장합니다.
설정 없이도 launchd 보강 실행으로 대부분 커버됩니다.

## ⚠️ 면책
본 시스템은 공개 정보를 요약·정리하는 도구이며 **투자 권유가 아닙니다**.
모든 투자 판단과 책임은 투자자 본인에게 있습니다.
