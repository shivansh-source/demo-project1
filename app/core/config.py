from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-5-5"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"

_DEFAULTS = {
    "enrichment_provider": "mock",
    "crm_provider": "mock",
    "anthropic_model": DEFAULT_ANTHROPIC_MODEL,
    "reasoning_provider": "groq",
    "groq_model": DEFAULT_GROQ_MODEL,
    "groq_base_url": "https://api.groq.com/openai/v1",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://leadgen:leadgen@localhost:5432/leadgen"
    test_database_url: str = "postgresql+psycopg://leadgen:leadgen@localhost:5432/leadgen_test"
    log_level: str = "INFO"

    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "leadgen"
    job_max_attempts: int = 5
    job_backoff_base_seconds: float = 2.0
    # RQ kills a job running longer than this; a crashed worker's job is retried/failed by RQ.
    job_timeout_seconds: int = 300
    job_result_ttl_seconds: int = 3600  # how long finished jobs stay visible in GET /jobs
    job_failure_ttl_seconds: int = 604800  # failed jobs stay inspectable for 7 days
    score_defer_seconds: float = 5.0  # score_lead waits this long for pending enrichment

    enrichment_provider: str = "mock"
    enrichment_api_key: str = ""
    crm_provider: str = "mock"
    crm_api_token: str = ""
    # HubSpot (CRM_PROVIDER=hubspot). Custom property names are optional: HubSpot rejects
    # properties that do not exist in the portal, so nothing custom is sent unless named.
    hubspot_base_url: str = "https://api.hubapi.com"
    hubspot_score_property: str = ""
    hubspot_segment_property: str = ""

    reasoning_enabled: bool = False
    reasoning_provider: str = "groq"  # "groq" or "anthropic"
    groq_api_key: str = ""
    groq_model: str = DEFAULT_GROQ_MODEL
    # gpt-oss models "think" first and can use the whole token cap before answering.
    groq_reasoning_effort: str = "low"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    anthropic_api_key: str = ""
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    reasoning_max_tokens: int = 150

    scoring_config_path: str = "config/scoring.yaml"

    # .env.example ships these keys with empty values; treat empty as "use the default".
    @field_validator(
        "enrichment_provider",
        "crm_provider",
        "anthropic_model",
        "reasoning_provider",
        "groq_model",
        "groq_base_url",
        mode="before",
    )
    @classmethod
    def _empty_means_default(cls, v: object, info: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return _DEFAULTS.get(getattr(info, "field_name", ""), v)
        return v

    @field_validator("reasoning_enabled", mode="before")
    @classmethod
    def _empty_bool_is_false(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return False
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
