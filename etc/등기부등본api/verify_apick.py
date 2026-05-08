"""
에이픽 부동산등기부등본 API 단독 검증 스크립트.

DB·FastAPI 없이 .env의 APICK_AUTH_KEY만으로 1건 발급해보고
PDF 시그니처까지 확인하여 통합 전에 외부 연동만 빠르게 검증.

사용법:
  $ cp .env.example .env   # APICK_AUTH_KEY 채우기
  $ python verify_apick.py
  $ python verify_apick.py --address "상계동 1285 불암대림아파트 103동 102호"
  $ python verify_apick.py --unique-num 1234567890123 --type 집합건물
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx


def load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def request_iros(base_url: str, auth_key: str, address: str, type_: str,
                 unique_num: str | None, timeout: int) -> dict | None:
    data = {"type": type_}
    if unique_num:
        data["unique_num"] = unique_num
    else:
        data["address"] = address
    r = httpx.post(
        f"{base_url}/rest/iros/1",
        headers={"CL_AUTH_KEY": auth_key},
        data=data,
        timeout=timeout,
    )
    print(f"  HTTP {r.status_code}  ({len(r.content):,} bytes)")
    # 에이픽은 비즈니스 실패에도 HTTP 401을 쓰고 body는 정상 JSON.
    # status code로 가르지 않고 JSON 파싱 가능 여부로 판정한다.
    try:
        body = r.json()
    except ValueError:
        print(f"  not json: {r.text[:300]}")
        return None
    print(f"  body: {body}")
    return body


def download_iros(base_url: str, auth_key: str, ic_id: int, timeout: int) -> httpx.Response:
    return httpx.post(
        f"{base_url}/rest/iros_download/1",
        headers={"CL_AUTH_KEY": auth_key},
        data={"ic_id": str(ic_id), "format": "pdf"},
        timeout=timeout,
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--address", default="상계동 1285 불암대림아파트 103동 102호")
    p.add_argument("--type", default="집합건물", choices=["토지", "집합건물", "건물"])
    p.add_argument("--unique-num", default=None,
                   help="부동산 고유번호. 지정 시 --address 무시")
    p.add_argument("--output", default=None,
                   help="PDF 저장 경로 (기본: ./verify_{ic_id}.pdf)")
    p.add_argument("--poll-interval", type=int, default=5)
    p.add_argument("--poll-max", type=int, default=18,
                   help="최대 폴링 횟수 (기본 18 = 약 90초)")
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--base-url", default=None)
    args = p.parse_args()

    load_env()
    auth_key = os.environ.get("APICK_AUTH_KEY", "").strip()
    if not auth_key or auth_key == "your_md5_auth_key_here":
        print("ERROR: APICK_AUTH_KEY not set in .env", file=sys.stderr)
        return 2
    base_url = args.base_url or os.environ.get("APICK_BASE_URL", "https://apick.app")

    print("==== 등기부등본 API 검증 ====")
    print(f"시각:        {datetime.now().isoformat(timespec='seconds')}")
    print(f"base_url:    {base_url}")
    print(f"type:        {args.type}")
    if args.unique_num:
        print(f"unique_num:  {args.unique_num}")
    else:
        print(f"address:     {args.address}")
    print()

    print("[1/3] 열람 요청 (POST /rest/iros/1)")
    body = request_iros(base_url, auth_key, args.address, args.type,
                        args.unique_num, args.timeout)
    if not body:
        print("FAIL: 열람 응답 없음")
        return 3

    data = body.get("data") or {}
    api = body.get("api") or {}
    ic_id = data.get("ic_id")
    success = int(data.get("success", 0) or 0)
    cost = int(api.get("cost", 0) or 0)

    print()
    print(f"  ic_id   = {ic_id}")
    print(f"  success = {success}   (1:성공, 0:실패, 3:timeout)")
    print(f"  cost    = {cost} 원")
    print(f"  pl_id   = {api.get('pl_id')}")
    print(f"  ms      = {api.get('ms')}")
    print()

    if success != 1 or not ic_id:
        err = data.get("error") or "(no error message)"
        print(f"FAIL: 열람 실패 — {err}")
        return 4

    print(f"[2/3] PDF 다운로드 폴링 (간격 {args.poll_interval}s, 최대 {args.poll_max}회)")
    pdf_bytes: bytes | None = None
    for i in range(args.poll_max):
        r = download_iros(base_url, auth_key, int(ic_id), args.timeout)
        result_hdr = r.headers.get("result", "?")
        ctype = r.headers.get("content-type", "")
        print(f"  try {i+1:>2}/{args.poll_max}  "
              f"http={r.status_code} result={result_hdr} "
              f"ct={ctype} bytes={len(r.content):,}")
        if r.status_code == 200 and result_hdr == "1" and r.content:
            pdf_bytes = r.content
            break
        if result_hdr == "2":
            time.sleep(args.poll_interval)
            continue
        # 알 수 없는 응답: 한 번 더 대기 후 시도
        if i < args.poll_max - 1:
            time.sleep(args.poll_interval)

    if not pdf_bytes:
        print("FAIL: 폴링 만료 — PDF 미수신")
        return 5

    out_path = args.output or f"./verify_{ic_id}.pdf"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    is_pdf = pdf_bytes[:4] == b"%PDF"

    print()
    print(f"[3/3] 저장 완료: {out_path}")
    print(f"      크기: {len(pdf_bytes):,} bytes")
    print(f"      시그니처: {'OK (%PDF)' if is_pdf else '비정상 — 첫 4바이트=' + repr(pdf_bytes[:4])}")
    print()
    print("==== DONE ====" if is_pdf else "==== DONE (PDF 시그니처 비정상) ====")
    return 0 if is_pdf else 6


if __name__ == "__main__":
    sys.exit(main())
