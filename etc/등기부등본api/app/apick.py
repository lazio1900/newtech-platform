from typing import Optional, Tuple

import httpx

from .config import settings


class ApickError(Exception):
    pass


class ApickClient:
    def __init__(self) -> None:
        self.base_url = settings.APICK_BASE_URL
        self.headers = {"CL_AUTH_KEY": settings.APICK_AUTH_KEY}
        self.timeout = settings.APICK_TIMEOUT

    def request_iros(
        self,
        address: str,
        type_: str = "집합건물",
        unique_num: Optional[str] = None,
    ) -> dict:
        url = f"{self.base_url}/rest/iros/1"
        data: dict = {"type": type_}
        if unique_num:
            data["unique_num"] = unique_num
        else:
            data["address"] = address

        # httpx 네트워크 에러를 ApickError 로 정규화 — 백그라운드 스레드가 silently
        # 죽지 않고 _download_in_background 에서 status='failed' 처리되도록 함.
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, headers=self.headers, data=data)
        except httpx.HTTPError as e:
            raise ApickError(f"iros: network error {type(e).__name__}: {e}") from e
        # 에이픽은 비즈니스 실패에도 HTTP 401을 쓰고 body는 정상 JSON으로 옴.
        # status code로 분기하지 않고 JSON 파싱 가능 여부로 분기한다.
        try:
            return r.json()
        except ValueError as e:
            raise ApickError(
                f"iros: non-json response http={r.status_code} body={r.text[:300]}"
            ) from e

    def download(self, ic_id: int, fmt: str = "pdf") -> Tuple[Optional[bytes], int]:
        url = f"{self.base_url}/rest/iros_download/1"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(
                    url,
                    headers=self.headers,
                    data={"ic_id": str(ic_id), "format": fmt},
                )
        except httpx.HTTPError as e:
            raise ApickError(f"download: network error {type(e).__name__}: {e}") from e
        # 가이드: 응답 헤더 result (1=성공, 2=처리중)
        result_raw = r.headers.get("result", "0")
        try:
            result = int(result_raw)
        except ValueError:
            result = 0

        if result == 1 and r.status_code == 200:
            return r.content, 1
        if result == 2:
            return None, 2

        detail = ""
        try:
            body = r.json()
            err = (body.get("data") or {}).get("error")
            detail = err or str(body)[:200]
        except ValueError:
            detail = r.text[:200]
        raise ApickError(
            f"download failed: http={r.status_code} result={result_raw} {detail}"
        )
