import textwrap
from typing import List, Optional

import langextract as lx

from app.core.Agents.Poi.WebSearch.Extractor.BaseExtractor import BaseExtractor
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource
from app.core.config import settings

# POI 추출을 위한 프롬프트 설명
_EXTRACTION_PROMPT = textwrap.dedent("""
    Extract all Points of Interest (POI) mentioned in the text.
    A POI is a specific named place such as a restaurant, cafe, attraction,
    hotel, museum, park, shopping area, or entertainment venue.

    For each POI, extract:
    - The exact name of the place (extraction_text)
    - A brief description or context about the place (attribute: description)
    - The category of the place (attribute: category)

    Extract POIs in order of appearance. Use exact text from the source.
    Do not extract generic location names (e.g., "Seoul", "Tokyo") unless
    they refer to a specific venue.
""").strip()

# Few-shot 예시
_EXTRACTION_EXAMPLES = [
    lx.data.ExampleData(
        text="""
해산물을 먹으러 갔지만
노미호다이와 라면만 오지게 먹고온 여행
그래도 일본 라멘의 맛을 좀 더 알게 되긴 했다.
**​**
**○ 맛 평가 (※일행 5명의 평가를 종합)**
① 에비소바 이치겐 - ★★★★★
② 라멘 신게츠 - ★★★★☆
③ 라멘 신겐 - ★★★☆☆
④ 케야키 스스키노 - ★★☆☆☆
​
가격은 어느정도 비슷했고, 양은 신겐 고기 양이 말이 안 되게 많았다.
**녹진한 육수를 좋아한다면 1번 3번을 우선적으로 방문하길**
​
에비소바 이치겐, 신게츠 라멘은 맛집 유튜버 겸 블로거 비밀이야 아저시를 보고 갔고
라멘 신겐은 현지인 친구 추천으로, 케야키 스스키노는 일행이 찾아내서 다녀옴
​
○ 영업시간
① 에비소바 이치겐 - 오전 11시 - 다음날 03시
② 라멘 신게츠 - 오후 8시 - 다음날 05시
③ 라멘 신겐 - 오전 11시 - 다음날 01시
④ 케야키 스스키노 - 오전 11시 - 다음날 02시 45
​
일본은 집에 들어가면서 해장을 하는 문화라
일본에 놀러갔다면 귀가 전 라멘으로 해장을 해보시길
​
각 집마다 가장 대중적인 메뉴로 주문했고,
홋카이도가 된장이 유명하다고 해서
미소라멘이 메인인 경우 미소라멘으로 시켰음
​
**① 에비소바 이치겐 - ★★★★★**
*   웨이팅 난이도 中- 40분 이상(일요일 점심식사 기준)
*   라면 한 그릇 당 1,000엔 이하
*   일본어 못 해도 갈 수 있음(주문 난이도 최하)
**새우된장라멘 깊은맛 - 950엔**
**★★★★★**
한국인이 가장 좋아할만한 라멘의 맛
일행 6명이 모두 만족한 맛
비밀이야 아저시가 추천한 라멘 맛집
​
위에 뿌려져있는 가루는 새우가루고
사골베이스에 새우가 들어가있다.
단 맛에 민감한 나는 좀 달다고 느끼기도 했는데
같이 간 일행 모두 단 맛을 못 느꼈다고 했음
​
새우 및 갑각류의 향을 싫어하거나
너무 짠 음식을 못 먹는 사람들은 싫어할 수도 있음
(라멘 중에서도 짠 편이고, 이치란과 비슷한 정도의 염도)
계란이 되게 신기하게도 완전한 반숙이었는데
사진을 자세히 보면 흰자까지도 살짝 덜 익어있다.
어떻게 만든건지 모르겠는데 중탕을 했나 싶긴 했음
​
특이한건 같이 주는 마늘과 시치미를 넣어먹으면
맛이 3배정도 더 좋아진다.
한국인들은 필히 마늘을 넣어서 먹을 것
교자는 일반적으로 일본에서 먹을 수 있는 맛이고
밥은 따로 안 시켰는데 말아먹으라고 주셨다.
가게 인테리어나 주방이 엄청 깔금했고
유명인들이 많이 왔다갔는지 싸인도 많았음
​
현지인 친구 말로는 지금 가장 핫한 일본 여배우도 왔다갔다고 함
메뉴 참고
(라면 맛을 정하고 국물 깊이를 정하는 시스템임)
​
**② 라멘 신게츠 - ★★★★☆**
*   웨이팅 난이도 中 - 30분 이하(평일 밤 11시경 기준)
*   라면 한 그릇당 1,000엔 이하
*   주문난이도 낮음(그림 메뉴판 있음)
​
**쇼가시오라멘 - 820엔**
**★★★★☆**
시오라멘을 좋아하면 먹어봐야 할 맛
일행 5명 중 4명은 만족, 1명은 굉장히 불만족
비밀이야 아조시가 추천 한 라멘 맛집
미슐랭 빕구르망에 선정된 적도 있다고 함
​
가운데에 있는게 다진 생강인데, 생강을 뺀 시오라멘도 있다.
국물에 생강을 섞기 전에 라면을 먹다가
나중에 생강을 섞어도 되는데
생강에 거부감이 전혀 없는 나도
생강 향이 엄청 강하다고 느껴지긴 했음
생강 싫어하는 사람은 절대 못먹는 생강 맛임
​
개인적으로는 해장으로는 가장 좋았고
평소에 먹던 시오라멘보다 조금 슴슴한 맛인데
일행 중 한 명은 면 밀가루 맛같다고 싫어했음
약간 라멘계의 평양냉면같은 느낌
​
여자들보다 남자들이 좀 더 좋아할 것 같았음
여자친구 또는 아내랑 여행간 경우 굳이 안 가는 것도 추천
생강을 섞으면 국물에 생강 향이 진자 많이 남
일행 중 하나는 면수에 생강차 탄 것 같다고 했음
​
**차항(볶음밥) - 750엔**
**★★★★★**
볶음밥은 꼭 먹어보시길
대단한 재료가 안 들어갔는데도
불향이나 염도가 완벽했음
​
일행들은 신겐 볶음밥보다 신게츠가 훨씬 맛있다고 했는데
나는 신겐이 더 맛있긴 했지만
(신게츠는 밥알이 좀 더 질은 식감이 났다)
그래도 여기도 인생 볶음밥 중 top3 는 든다.
​
어차피 7,000원밖에 안 하는거
**신게츠에 왔다면 무조건 하나는 사이드로 시키시길**
식당 자체가 오래되긴 했어도
깔끔하게 잘 관리한 노포 정도의 느낌이었다.
​
**③ 라멘 신겐 - ★★★☆☆**
*   웨이팅 난이도 중상 - 약 1시간(월요일 오픈런 기준)
*   라멘 한 그릇당 1,200엔 내외
*   주문 난이도 낮음 - 영어메뉴 있음
**풀토핑 미소라멘 - 1,350엔**
**★★★☆☆**
걸쭉하고 고기 많은 라멘의 맛
사진 보면 딱 떠오르는 맛보다 2배정도 진한 맛
일본인 현지인들이 추천해줘서 가게된 맛집
​
돼지육수 베이스 라멘
우리는 아무것도 모르고 풀토핑 라멘을 시켰는데
진짜 대식가에 느끼한 음식을 잘 먹는게 아니면
차슈 정도만 시키는걸 권장함
※고기가 실제 보쌈이 두덩어리정도 들어있다.
​
양은 가장 많았는데, 보자마자 부담스러워 지는 정도다.
​
그래도 라멘 자체는 맛있다.
다녀왔던 라멘집들 중 여자 손님의 비율이 가장 높았다.
(신겐 다음으로 여자가 많았던 곳이 에비소바 이치겐)
여자친구 또는 와이프와 여행중이라면 방문을 추천함
고기가 진짜 너무 많아서 일행 대부분이 남김
마지막 사진 주먹은 여자주먹 아니고 남자주먹임
**차항(볶음밥) - 750엔**
**★★★★★**
내 인생에서 가장 맛있었던 볶음밥
난 삿포로에 간다면 이 볶음밥 때문에 여길 다시 올것
​
이거 안 시키는 경우 인생 손해
사이드 메뉴는 무난무난 했다.
교자 맛은 다른 식당들보다 좀 더 순하고 오일리했다.
김치도 낫베드
여기도 오래됐지만 깔끔하게 잘 보존한 노포
그래도 미소라멘을 한번 먹어본다면
여기서 먹어보길 권장
볶음밥은 무조건 무조건 무조건 시키시고
​
**④ 케야키 스스키노 - ★★☆☆☆**
*   웨이팅 난이도 하 - 20분 이내(일요일 밤 11시 기준)
*   라멘 한 그릇당 1,000엔 내외
*   주문 난이도 낮음
**콘버터라멘 - 1,100엔**
**★★★☆☆**
일행 5명 중 3명은 불만족 2명은 만족한 맛
솔직히 버터라멘 말고 다른 라멘은 메리트가 있는지 모르겠음
버터만 뺀 콘 라멘도 있는데, 절대 시키지 마시길
​
다른 맛있는 집이 많다보니
일정이 길어서 라멘 먹을일이 많다면
한번즘 들러봐도 나쁘지는 않지만
삿포로 라멘집 중 순위로 따지면 가장 마지막 순위인건 사실이다.
이건 일행이 시킨 일반 콘라멘인데
이도저도 아닌 맛이 최악이었다.
술 한잔 하고 집에 가기 전
해장하러 들어가는 사람들이 꽤 있었다.
​
문 열고 추천할만한 메뉴가 있냐고 물어봤는데
대답도 안해주는 깍쟁이 아저시들이 찾는 라멘집
깍쟁이라멘
​
다들 우리처럼 라멘만 먹고 다니지 말고
스시, 카이센동, 우나기동, 스프카레, 야키니쿠, 덮밥
골고루 먹으면서 여행하시길
​
        """,
        extractions=[
            lx.data.Extraction(
                extraction_class="place",
                extraction_text="에비소바 이치겐",
                attributes={
                    "description": "한국인이 가장 좋아할만한 라멘의 맛 일행 6명이 모두 만족한 맛 비밀이야 아저시가 추천한 라멘 맛집",
                    "feature": [
                        "웨이팅 난이도 中- 40분 이상(일요일 점심식사 기준)",
                        "라면 한 그릇 당 1,000엔 이하",
                        "일본어 못 해도 갈 수 있음(주문 난이도 최하)",
                        "한국인이 가장 좋아할만한 라멘의 맛",
                        "새우된장라멘 깊은맛 - 950엔",
                        "일행 6명이 모두 만족한 맛",
                        "한국인들은 필히 마늘을 넣어서 먹을 것"
                    ]
                },
            ),
            lx.data.Extraction(
                extraction_class="place",
                extraction_text="라멘 신게츠",
                attributes={
                    "description": "시오라멘을 좋아하면 먹어봐야 할 맛. 일행 5명 중 4명은 만족, 1명은 굉장히 불만족. 비밀이야 아조시가 추천 한 라멘 맛집. 미슐랭 빕구르망에 선정된 적도 있다고 함",
                    "feature": [
                        "웨이팅 난이도 中 - 30분 이하(평일 밤 11시경 기준)",
                        "라면 한 그릇당 1,000엔 이하",
                        "주문난이도 낮음(그림 메뉴판 있음)",
                        "쇼가시오라멘 - 820엔",
                        "여자친구 또는 아내랑 여행간 경우 굳이 안 가는 것도 추천",
                        "생강을 섞으면 국물에 생강 향이 진자 많이 남",
                        "일행 중 하나는 면수에 생강차 탄 것 같다고 했음",
                        "차항(볶음밥) - 750엔"
                    ]
                },
            ),
            lx.data.Extraction(
                extraction_class="place",
                extraction_text="라멘 신겐",
                attributes={
                    "description": "걸쭉하고 고기 많은 라멘의 맛. 사진 보면 딱 떠오르는 맛보다 2배정도 진한 맛. 일본인 현지인들이 추천해줘서 가게된 맛집",
                    "feature": [
                        "웨이팅 난이도 중상 - 약 1시간(월요일 오픈런 기준)",
                        "라멘 한 그릇당 1,200엔 내외",
                        "주문 난이도 낮음 - 영어메뉴 있음",
                        "풀토핑 미소라멘 - 1,350엔",
                        "여자친구 또는 와이프와 여행중이라면 방문을 추천함",
                        "사이드 메뉴는 무난무난 했다."
                    ]
                },
            ),
            lx.data.Extraction(
                extraction_class="place",
                extraction_text="케야키 스스키노",
                attributes={
                    "description": "일행 5명 중 3명은 불만족 2명은 만족한 맛. 솔직히 버터라멘 말고 다른 라멘은 메리트가 있는지 모르겠음.",
                    "feature": [
                        "웨이팅 난이도 하 - 20분 이내(일요일 밤 11시 기준)",
                        "라멘 한 그릇당 1,000엔 내외",
                        "콘버터라멘 - 1,100엔`주문 난이도 낮음",                        
                    ]
                },
            ),
        ],
    ),
]


class LangExtractor(BaseExtractor):
    """
    langextract 라이브러리를 사용하여 raw_content에서 POI를 추출하는 구현체

    Google의 langextract를 활용하여 마크다운 텍스트에서
    장소(POI) 정보를 구조적으로 추출합니다.
    """

    def __init__(
        self,
        model_id: str = "gemini-2.5-flash",
        model_url: Optional[str] = None,
    ):
        """
        Args:
            model_id: langextract에서 사용할 모델 ID
                      (예: "gemini-2.5-flash", "gpt-4o", 또는 Ollama 모델명)
            model_url: 로컬 모델 사용 시 URL (예: "http://localhost:11434")
            api_key: API 키 (None이면 환경변수 LANGEXTRACT_API_KEY 사용)
        """
        self.model_id = model_id    
        self.model_url = model_url

    def extract(self, raw_content: str, url: str = None) -> List[PoiSearchResult]:
        """
        마크다운 raw_content에서 POI 정보를 추출

        Args:
            raw_content: Tavily API에서 반환된 마크다운 형식의 원본 콘텐츠
            url: 원본 페이지 URL

        Returns:
            추출된 PoiSearchResult 리스트
        """
        if not raw_content or not raw_content.strip():
            return []

        try:
            extract_kwargs = {
                "text_or_documents": raw_content,
                "prompt_description": _EXTRACTION_PROMPT,
                "examples": _EXTRACTION_EXAMPLES,
                "api_key": settings.langextract_api_key,
                # "max_workers": 10
            }
            
            result = lx.extract(**extract_kwargs)
            print(result)

            return self._convert_to_poi_results(result, url)

        except Exception as e:
            print(f"LangExtractor error: {e}")
            return []

    def _convert_to_poi_results(
        self, extraction_result, url: str = None
    ) -> List[PoiSearchResult]:
        """
        langextract 결과를 PoiSearchResult 리스트로 변환

        Args:
            extraction_result: lx.extract()의 반환 결과
            url: 원본 페이지 URL

        Returns:
            PoiSearchResult 리스트
        """
        results = []

        extractions = getattr(extraction_result, "extractions", [])
        for extraction in extractions:
            if extraction.extraction_class not in ("poi", "place"):
                continue

            title = extraction.extraction_text or ""
            attributes = extraction.attributes or {}
            description = attributes.get("description", "")

            result = PoiSearchResult(
                title=title,
                snippet=description,
                url=url,
                source=PoiSource.WEB_SEARCH,
                relevance_score=0.5,
            )
            results.append(result)

        return results
