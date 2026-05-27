declare global {
  interface Window {
    daum: any;
  }
}

/**
 * Daum 우편번호 팝업 (postcode.v2.js, key 없이 사용).
 * 사용자가 결과를 선택하면 `data.buildingName` 을 resolve, 취소하면 null.
 * `query` 가 있으면 검색창에 사전 입력해 1-클릭으로 진행 가능.
 */
export function pickDaumBuildingName(query?: string): Promise<string | null> {
  return new Promise((resolve) => {
    let picked = false;
    new window.daum.Postcode({
      oncomplete(data: { buildingName?: string }) {
        picked = true;
        resolve(data.buildingName || null);
      },
      onclose() {
        if (!picked) resolve(null);
      },
    }).open({ q: query });
  });
}
