# 🏪 홈쇼핑 방송 분석 봇 (Homeshopping Analysis BOT)

**홈쇼핑 방송의 판매 전략을 AI로 분석하고 채널 간 차이를 비교하는 도구**

## 🚀 빠른 시작 (5분)

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. DataHub 쿠키 설정
```bash
# .env.example을 참고해서 쿠키 설정
export HSMOA_DATAHUB_COOKIE="your_cookie_here"
```

또는 Windows PowerShell:
```powershell
$env:HSMOA_DATAHUB_COOKIE = "your_cookie_here"
```

### 3. 웹앱 실행
```bash
python -m hsbot webapp
```

**http://127.0.0.1:8765** 접속 → 완료! 🎉

---

## ✨ 기능

### 1️⃣ 검색 (Search)
- 제품명, 채널, 키워드로 방송 찾기
- 최근 20개 방송 표시
- 편성 추정 매출 실시간 확인

### 2️⃣ 비교 (Compare)
- 2개 이상 선택해서 **채널별 판매 전략** 분석
- 7가지 소구축 (축)으로 화법 분류:
  - 💰 **혜택** (가격, 할인, 사은품)
  - 🔔 **콜유도** (긴급, 주문 지시)
  - 🎨 **시각·디자인** (시연, 외관, 디자인)
  - 😊 **감성·생활** (편의, 감정, 가족)
  - 🏆 **브랜드 소구** (수상, 판매량, 우위)
  - 💬 **고객 증언** (후기, 만족도)
  - 💪 **안심·리스크해소** (보증, 체험)

### 3️⃣ 분석 (Analyze)
- **분당 강도**: 1분에 몇 번 말했나 (정규화)
- **판촉강도 반영**: 소스 강조도까지 반영한 가산점
- **분당주문액**: 시간대 보정된 예상 매출
- **채널 간 편차**: 어디서 갈렸는지 명확히

### 4️⃣ 타임라인 (Timeline)
- 분(分) 단위 소구축 분포 히트맵
- 실제 방송 리듬 (판촉강도 %)
- **셀을 클릭** → 그 분에 실제 한 말 보기

---

## 📁 폴더 구조

```
HomeshoppingCompareBOT/
├── hsbot/                     # 메인 코드
│   ├── lexicons/              # 소구축 키워드 사전
│   │   ├── core_ko.json       # 공통 축
│   │   ├── product_fridge.json
│   │   ├── product_circulator.json
│   │   └── product_robot_vacuum.json
│   ├── data/
│   │   └── time_weights.json  # 시간대별 가중치
│   ├── metrics.py             # 분석 엔진
│   ├── report.py              # HTML 리포트
│   ├── webapp.py              # 웹 서버
│   ├── webapp.py              
│   └── ...
├── tests/                     # 테스트
├── .secrets/
│   └── datahub.cookie         # API 쿠키 (보안)
├── requirements.txt           # Python 패키지
├── .env.example               # 쿠키 설정 템플릿
├── SETUP.md                   # 상세 설정 가이드
└── README.md                  # 이 파일
```

---

## 🧪 테스트

```bash
python -m unittest tests.test_hsbot tests.test_discover tests.test_time_weight
```

---

## 🔐 보안

- ⚠️ `.secrets/datahub.cookie` 는 **절대 공유 금지**
- 로컬(127.0.0.1)에서만 접속 가능
- GitHub/공개 저장소에 업로드하지 마세요

---

## 📋 필수 요구사항

- **Python 3.10+**
- **인터넷 연결** (DataHub API 호출)
- **DataHub 계정** (datahub.hsmoa.com)

---

## 💡 팁

1. **3개 이상 채널 비교** → 갈린 지점이 더 명확
2. **타임라인 셀 클릭** → 실제 멘트 확인 가능
3. **판촉강도 토글** → "가산점 반영" 체크박스로 변경

---

## 📞 상세 가이드

더 자세한 설정은 **SETUP.md** 참고

---

**마지막 업데이트**: 2026-10-12  
**버전**: 1.0.0
