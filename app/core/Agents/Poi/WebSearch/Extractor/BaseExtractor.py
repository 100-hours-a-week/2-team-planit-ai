from abc import ABC, abstractmethod
from typing import List

from app.core.models.PoiAgentDataclass.poi import PoiSearchResult


class BaseExtractor(ABC):
    """웹 검색 raw_content에서 POI 정보를 추출하는 추상 기본 클래스"""

    @abstractmethod
    def extract(self, raw_content: str, url: str = None) -> List[PoiSearchResult]:
        """
        마크다운 raw_content에서 POI 정보를 추출하여 PoiSearchResult 리스트 반환

        Args:
            raw_content: Tavily API에서 반환된 마크다운 형식의 원본 콘텐츠
            url: 원본 페이지 URL

        Returns:
            추출된 POI 검색 결과 리스트
        """
        pass
