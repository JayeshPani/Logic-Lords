"""Runtime configuration for API gateway."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "api-gateway"
    service_version: str = "1.0.0"
    log_level: str = "INFO"
    metrics_enabled: bool = True

    auth_enabled: bool = True
    auth_bearer_tokens_csv: str = "dev-token"
    auth_token_roles_csv: str = "dev-token:organization|operator"

    rate_limit_enabled: bool = True
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    blockchain_verification_base_url: str = "http://127.0.0.1:8105"
    blockchain_verification_fallback_urls_csv: str = (
        "http://127.0.0.1:8235,http://127.0.0.1:8123"
    )
    blockchain_connect_timeout_seconds: float = 15.0
    blockchain_verification_timeout_seconds: float = 8.0
    sensor_ingestion_base_url: str = "http://127.0.0.1:8100"
    sensor_telemetry_timeout_seconds: float = 8.0
    report_generation_base_url: str = "http://127.0.0.1:8202"
    report_generation_timeout_seconds: float = 15.0
    orchestration_base_url: str = "http://127.0.0.1:8200"
    orchestration_timeout_seconds: float = 8.0
    assistant_enabled: bool = True
    assistant_groq_api_key: str = ""
    assistant_groq_base_url: str = "https://api.groq.com/openai/v1/chat/completions"
    assistant_model: str = "llama-3.3-70b-versatile"
    assistant_timeout_seconds: float = 30.0
    assistant_max_history_messages: int = 8
    assistant_temperature: float = 0.2
    assistant_max_tokens: int = 600

    # Optional dashboard defaults (served via /dashboard-config.js).
    # This is for convenience in local/demo environments so the UI can auto-connect to RTDB.
    dashboard_firebase_enabled: bool = False
    dashboard_firebase_db_url: str = ""
    dashboard_firebase_base_path: str = "infraguard/telemetry"

    # Load from environment variables, plus (optionally) a local .env file.
    # This allows "no-terminal" setup by putting secrets into apps/api-gateway/.env
    # (which is gitignored by repo root .gitignore).
    model_config = SettingsConfigDict(
        env_prefix="API_GATEWAY_",
        extra="ignore",
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
    )

    @property
    def auth_tokens(self) -> set[str]:
        tokens = [token.strip() for token in self.auth_bearer_tokens_csv.split(",")]
        return {token for token in tokens if token}

    @property
    def token_roles(self) -> dict[str, set[str]]:
        mapping: dict[str, set[str]] = {}
        pairs = [value.strip() for value in self.auth_token_roles_csv.split(",")]
        for pair in pairs:
            if not pair or ":" not in pair:
                continue
            token, raw_roles = pair.split(":", 1)
            token_value = token.strip()
            if not token_value:
                continue
            roles = {
                role.strip().lower()
                for role in raw_roles.split("|")
                if role.strip()
            }
            if roles:
                mapping[token_value] = roles
        return mapping

    @property
    def blockchain_verification_urls(self) -> list[str]:
        urls: list[str] = []
        for candidate in [
            self.blockchain_verification_base_url,
            *self.blockchain_verification_fallback_urls_csv.split(","),
        ]:
            value = candidate.strip()
            if value and value not in urls:
                urls.append(value)
        return urls


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
