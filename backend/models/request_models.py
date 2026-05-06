from typing import Optional

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """대출 분석 요청 모델"""
    company_name: str = Field(..., description="업체명")
    property_address: str = Field(..., description="담보주소")
    loan_amount: int = Field(..., gt=0, description="대출신청금액")
    # 신청건에서 분석 시 정확 매칭용 (없으면 BE가 주소로 fuzzy 매칭)
    complex_id: Optional[int] = Field(None, description="단지 ID (정확 매칭용)")
    area_id: Optional[int] = Field(None, description="평형 ID (정확 매칭용)")
    complex_name: Optional[str] = Field(None, description="단지명 스냅샷")
    pyeong: Optional[int] = Field(None, description="평수 (정확 매칭용)")

    class Config:
        json_schema_extra = {
            "example": {
                "company_name": "파란캐피탈대부",
                "property_address": "서울시 강남구 대치동 은마아파트 2동 1203호",
                "loan_amount": 800000000,
                "complex_id": 2,
                "area_id": 4,
                "complex_name": "은마아파트",
                "pyeong": 25
            }
        }
