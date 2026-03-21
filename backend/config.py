import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    default_mode: str
    target_latency_ms: int
    scaledown_force_all_inputs: bool
    require_api_key: bool
    app_api_key: str
    auto_strict_sla_on_fast: bool
    force_strict_sla_all_requests: bool



def get_settings() -> Settings:
    force_scaledown = os.getenv("SCALEDOWN_FORCE_ALL_INPUTS", "true").strip().lower() in {"1", "true", "yes", "y"}
    require_api_key = os.getenv("REQUIRE_API_KEY", "false").strip().lower() in {"1", "true", "yes", "y"}
    auto_strict_sla_on_fast = os.getenv("AUTO_STRICT_SLA_ON_FAST", "true").strip().lower() in {"1", "true", "yes", "y"}
    force_strict_sla_all_requests = os.getenv("FORCE_STRICT_SLA_ALL_REQUESTS", "true").strip().lower() in {"1", "true", "yes", "y"}
    return Settings(
        app_name=os.getenv("APP_NAME", "PranaAI - Emergency Triage Assistant"),
        app_version=os.getenv("APP_VERSION", "1.0.0"),
        default_mode=os.getenv("TRIAGE_DEFAULT_MODE", "auto"),
        target_latency_ms=int(os.getenv("TARGET_LATENCY_MS", "500")),
        scaledown_force_all_inputs=force_scaledown,
        require_api_key=require_api_key,
        app_api_key=os.getenv("APP_API_KEY", "").strip(),
        auto_strict_sla_on_fast=auto_strict_sla_on_fast,
        force_strict_sla_all_requests=force_strict_sla_all_requests,
    )
