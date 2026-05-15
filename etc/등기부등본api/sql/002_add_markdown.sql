-- MinerU 가 추출한 등기부 markdown 캐시. PDF 다운로드 직후 1회 변환해 저장.
-- 같은 ic_id 의 권리분석/면적추출 호출자가 재변환 없이 재사용.
ALTER TABLE registry_request ADD COLUMN IF NOT EXISTS markdown TEXT;
