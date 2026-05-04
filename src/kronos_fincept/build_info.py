"""Safe deployment build metadata helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os


DEFAULT_APP_VERSION = "v10.6.2"
UNKNOWN = "unknown"
_MAX_FIELD_LENGTH = 160


@dataclass(frozen=True)
class BuildInfo:
    app_version: str
    build_commit: str
    build_ref: str
    build_source: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().replace("\r", " ").replace("\n", " ")
    if not cleaned:
        return None
    return cleaned[:_MAX_FIELD_LENGTH]


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = _clean_env_value(os.environ.get(name))
        if value:
            return value
    return None


def get_build_info() -> BuildInfo:
    """Return safe build metadata from an explicit environment-variable allowlist."""
    return BuildInfo(
        app_version=_first_env(("KRONOS_APP_VERSION",)) or DEFAULT_APP_VERSION,
        build_commit=_first_env(
            (
                "KRONOS_BUILD_COMMIT",
                "KRONOS_GIT_COMMIT",
                "ZEABUR_GIT_COMMIT_SHA",
                "VERCEL_GIT_COMMIT_SHA",
                "GITHUB_SHA",
                "COMMIT_SHA",
                "SOURCE_COMMIT",
            )
        )
        or UNKNOWN,
        build_ref=_first_env(
            (
                "KRONOS_BUILD_REF",
                "KRONOS_GIT_REF",
                "ZEABUR_GIT_BRANCH",
                "VERCEL_GIT_COMMIT_REF",
                "GITHUB_REF_NAME",
                "BRANCH_NAME",
            )
        )
        or UNKNOWN,
        build_source=_first_env(
            (
                "KRONOS_BUILD_SOURCE",
                "ZEABUR_SERVICE_NAME",
                "ZEABUR_PROJECT_NAME",
                "VERCEL_ENV",
                "CI",
            )
        )
        or UNKNOWN,
    )
