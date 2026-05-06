from typing import Any, Dict, List
from datetime import date
import logging
from connectors.base import BaseConnector

logger = logging.getLogger(__name__)


class MolitTransactionConnector(BaseConnector):
    """
    국토교통부 실거래가 OpenAPI 커넥터
    
    공공 데이터 포털 OpenAPI를 사용합니다.
    ServiceKey 필요: https://www.data.go.kr/
    """

    def __init__(self, api_key: str = None, rate_limit_per_minute: int = 60):
        super().__init__(
            name="MolitTransactionConnector",
            rate_limit_per_minute=rate_limit_per_minute,
        )
        self.api_key = api_key

    def fetch(
        self, 
        region_code: str,
        contract_month: str,  # YYYYMM
        **kwargs
    ) -> Dict[str, Any]:
        """
        국토부 실거래가 API 호출
        
        Args:
            region_code: 지역코드 (법정동코드)
            contract_month: 계약월 (YYYYMM)
        
        실제 구현 시:
        - httpx로 API 호출
        - XML 응답 파싱
        - 페이징 처리
        """
        logger.info(
            f"Fetching MOLIT transactions for region={region_code}, "
            f"month={contract_month}"
        )
        
        if not self.api_key:
            logger.warning("MOLIT API key not set. Using mock data.")
            # Mock data
            mock_transactions = [
                {
                    "단지명": "테스트아파트",
                    "거래금액": "50,000",  # 만원 단위
                    "건축년도": "2010",
                    "년": "2024",
                    "월": "12",
                    "일": "15",
                    "전용면적": "84.50",
                    "층": "10",
                }
            ]
            
            return {
                "data": mock_transactions,
                "metadata": {
                    "source": "molit_mock",
                    "region_code": region_code,
                    "contract_month": contract_month,
                }
            }
        
        # TODO: 실제 API 호출 구현
        # url = "http://openapi.molit.go.kr/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSDataSvcAptTradeDev"
        # params = {
        #     "serviceKey": self.api_key,
        #     "LAWD_CD": region_code,
        #     "DEAL_YMD": contract_month,
        # }
        # response = httpx.get(url, params=params)
        # ...
        
        raise NotImplementedError("Real API implementation pending")

    def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        """Parse 국토부 실거래가 데이터"""
        parsed_items = []
        
        for item in raw_data:
            # 금액 파싱 (만원 단위 → 원)
            price_str = item["거래금액"].replace(",", "").strip()
            price = int(price_str) * 10000
            
            # 날짜 파싱
            contract_date = date(
                int(item["년"]),
                int(item["월"]),
                int(item["일"])
            )
            
            parsed_items.append({
                "contract_date": contract_date.isoformat(),
                "price": price,
                "exclusive_m2": float(item["전용면적"]),
                "floor": int(item.get("층", 0)) if item.get("층") else None,
                "source": "molit",
            })
        
        return parsed_items
