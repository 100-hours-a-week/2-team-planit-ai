from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000

    # LLM Client Settings
    llm_client_timeout: int = 60
    llm_client_max_retries: int = 3
    llm_client_max_tokens: int = 4096
    llm_client_temperature: Optional[float] = 0.24
    llm_client_top_p: float = 0.9

    # OpenAI Settings
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: Optional[str] = None
    
    # VLLM Settings
    vllm_base_url: Optional[str] = None
    vllm_model: Optional[str] = None

    @model_validator(mode='after')
    def validate_llm_settings(self) -> 'Settings':
        # 1. gpt-5 이상이거나 o1 모델인 경우 temperature를 사용하지 않음 (None 설정)
        model_name = self.openai_model.lower()
        if "gpt-5" in model_name or "o1-" in model_name:
            self.llm_client_temperature = None
        
        return self


settings = Settings()