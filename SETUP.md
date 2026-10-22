# 홈쇼핑 채널별 화법 비교 봇 - 설정 가이드

## 설치 및 실행

### 1단계: 패키지 설치
```bash
pip install -r requirements.txt
```

### 2단계: DataHub 쿠키 설정

`.env.example` 파일을 `.env` 또는 `.secrets/datahub.cookie`로 변경하고, 
[datahub.hsmoa.com](https://datahub.hsmoa.com)에서 로그인 후 쿠키를 복사해 저장합니다.

**Windows (PowerShell):**
```powershell
$env:HSMOA_DATAHUB_COOKIE = "your_cookie_here"
python -m hsbot webapp
```

**Windows (cmd.exe):**
```cmd
set HSMOA_DATAHUB_COOKIE=your_cookie_here
python -m hsbot webapp
```

**Mac/Linux:**
```bash
export HSMOA_DATAHUB_COOKIE="your_cookie_here"
python -m hsbot webapp
```

또는 `.secrets/datahub.cookie` 파일에 쿠키값을 저장:
```bash
mkdir -p .secrets
echo "your_cookie_here" > .secrets/datahub.cookie
python -m hsbot webapp
```

### 3단계: 웹앱 실행
```bash
python -m hsbot webapp
```

브라우저에서 **http://127.0.0.1:8765** 접속

---

## 기능

1. **검색**: 제품 키워드로 방송 찾기
2. **비교**: 2개 이상의 방송 선택해 소구축별 강도 비교
3. **분석**: 채널별 판매 화법 차이 파악
4. **타임라인**: 방송 진행 시간대별 소구축 분포 + 실시간 대사 확인

---

## 프로젝트 구조

```
홈쇼핑비교봇/
├── hsbot/                     # 메인 코드
│   ├── lexicons/              # 소구축 키워드 사전
│   ├── metrics.py             # 분석 엔진
│   ├── report.py              # HTML 리포트 생성
│   └── webapp.py              # 웹 서버
├── tests/                     # 테스트
├── requirements.txt           # Python 패키지
├── .env.example               # 쿠키 설정 템플릿
└── SETUP.md                   # 이 파일
```

---

## 테스트

```bash
python -m unittest tests.test_hsbot tests.test_discover tests.test_time_weight
```

---

## 주의사항

- **쿠키 보안**: `.secrets/datahub.cookie`는 절대 공유하지 마세요
- **Python 버전**: 3.10 이상 필요
- **로컬 전용**: 브라우저는 http://127.0.0.1:8765 로만 접속 (외부 접근 불가)
