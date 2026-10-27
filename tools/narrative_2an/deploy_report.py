# 리포트 HTML 한 장을 별도 Cloudflare Pages 프로젝트로 배포(아침 작업 설정은 건드리지 않음). TLS 검증 켬.
import base64, json, sys, pathlib
import truststore
truststore.inject_into_ssl()  # Windows 인증서 저장소로 검증(사내 SSL 검사 인증서 포함)
import requests
from blake3 import blake3
sys.path.insert(0, r"C:\hsmoa_jobs\홈쇼핑모아 정보수집")
from email_config import CLOUDFLARE_API_TOKEN as TOK, CLOUDFLARE_ACCOUNT_ID as ACC

API = "https://api.cloudflare.com/client/v4"
html, project = pathlib.Path(sys.argv[1]).read_bytes(), sys.argv[2]
h = blake3(html).hexdigest()[:32]
hdr = {"Authorization": f"Bearer {TOK}"}

r = requests.get(f"{API}/accounts/{ACC}/pages/projects/{project}", headers=hdr, timeout=20)
if r.status_code == 404:
    r = requests.post(f"{API}/accounts/{ACC}/pages/projects", headers=hdr, timeout=20,
                      json={"name": project, "production_branch": "main"})
assert r.status_code in (200, 201), r.status_code
proj = r.json()["result"]

jwt = requests.get(f"{API}/accounts/{ACC}/pages/projects/{project}/upload-token", headers=hdr, timeout=20).json()["result"]["jwt"]
jh = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}
r = requests.post(f"{API}/pages/assets/upload", headers=jh, timeout=120,
                  json=[{"key": h, "value": base64.b64encode(html).decode(),
                         "metadata": {"contentType": "text/html; charset=utf-8"}, "base64": True}])
assert r.status_code in (200, 201, 202), r.status_code
requests.post(f"{API}/pages/assets/upsert-hashes", headers=jh, json={"hashes": [h]}, timeout=30)
r = requests.post(f"{API}/accounts/{ACC}/pages/projects/{project}/deployments", headers=hdr, timeout=60,
                  files={"manifest": (None, json.dumps({"/index.html": h}), "application/json"),
                         "branch": (None, "main")})
assert r.status_code in (200, 201), r.status_code
print("project:", "https://" + (proj.get("subdomain") or f"{project}.pages.dev"))
print("deployment:", r.json()["result"].get("url"))
