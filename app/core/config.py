from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str
    port: int

    # LLM Client Settings
    llm_client_timeout: int 
    llm_client_max_retries: int 
    vllm_client_max_tokens: int 
    llm_client_temperature: Optional[float] 
    llm_client_top_p: float

    # OpenAI Settings
    openai_api_key: Optional[str]
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: Optional[str]
    
    # VLLM Settings
    vllm_base_url: Optional[str]
    vllm_model: Optional[str]

    # Google Maps Settings
    google_maps_api_key: Optional[str]

    tavily_api_key: Optional[str]
    langextract_api_key: Optional[str]

    # MongoDB Settings
    mongodb_uri: Optional[str] = "mongodb://127.0.0.1:27017"
    mongodb_db_name: str = "planit_chat"

    # Redis Settings
    redis_url: str = "redis://:localpass@localhost:6379/0"
    # redis_request_stream: str = "itinerary:request"
    redis_request_stream: str = "stream:ai-jobs"
    # redis_result_stream: str = "itinerary:result"
    redis_result_stream: str = "stream:itinerary-results"
    redis_consumer_group: str = "planit-workers"
    redis_consumer_name: str = "worker-1"
    redis_block_ms: int = 5000
    redis_max_stream_len: int = 10000

    # Vector DB Settings
    # vector_db_path: str

    @model_validator(mode='after')
    def validate_llm_settings(self) -> 'Settings':
        # 1. gpt-5 이상이거나 o1 모델인 경우 temperature를 사용하지 않음 (None 설정)
        if self.openai_model:
            model_name = self.openai_model.lower()
            if "gpt-5" in model_name or "o1-" in model_name:
                self.llm_client_temperature = None

        return self


settings = Settings()