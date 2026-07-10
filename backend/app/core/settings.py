"""Application configuration, read from the environment.

Implements: NFR-20 (`.env` is never committed; `.env.example` is), NFR-21
(reproducible setup), AD-14 (JWT parameters), AD-11 (seeding is the seed
command's job, so seed inputs are configuration, not migration literals).

Every field below has a matching placeholder entry in the repository's
`.env.example`. AC1 requires that the three-command setup sequence never needs a
value absent from that file, so a field added here without a corresponding entry
there is a defect.
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `.env` sits at the repository root, but tooling (pytest, host-run alembic) may be
# invoked from `backend/`. Resolving the path from this file rather than from the
# working directory means the same `.env` is found whichever directory the operator
# stands in.
#
# settings.py -> core -> app -> backend -> repository root
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Inside the `api` container no `.env` is copied: compose injects real environment
# variables instead. pydantic-settings ignores a missing env_file, so this resolves
# to a nonexistent path there and the environment wins — which is what NFR-20 wants.
_ENV_FILE = _REPOSITORY_ROOT / ".env"


class Settings(BaseSettings):
    """Environment-backed settings. Instantiated once, via `get_settings()`."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        # The compose file passes real environment variables; .env is a
        # local-development convenience. Variables only other services read
        # (PROXY_HTTPS_PORT and friends) must not raise here.
        extra="ignore",
    )

    # --- Database -------------------------------------------------------------
    #
    # DATABASE_URL is an OPTIONAL override. When absent — the normal case — the URL
    # is built below from the POSTGRES_* parts, with the password URL-quoted. One
    # source of truth: the operator sets POSTGRES_PASSWORD once, and a password
    # containing `@ : / # %` cannot silently corrupt the DSN (review D2).
    #
    # psycopg 3 uses one driver name for sync and async: postgresql+psycopg://
    database_url: str | None = None

    postgres_user: str
    postgres_password: str
    postgres_db: str
    # Two vantage points, one database: host tooling reaches the published port
    # (localhost:5433, the defaults below); inside the compose network the api
    # container is handed POSTGRES_HOST=postgres, POSTGRES_PORT=5432.
    postgres_host: str = "localhost"
    postgres_port: int = Field(
        default=5433,
        # POSTGRES_HOST_PORT is the variable `.env` already declares for compose's
        # publish mapping; reading it here keeps the two in lockstep when the
        # operator moves the published port. An explicit POSTGRES_PORT wins.
        validation_alias=AliasChoices("POSTGRES_PORT", "POSTGRES_HOST_PORT"),
        gt=0,
    )

    # AD-14. Consumed by `core/security.py` in Story 1.2.
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = Field(default=8, gt=0)

    # AD-11 — a migration never inserts a row. The seed command reads these.
    # Story 1.2 seeds the Admin and their Department; Story 2.1 the Leave Types.
    seed_admin_email: str
    seed_admin_password: str
    seed_admin_full_name: str
    seed_department_name: str

    @field_validator("postgres_password", "jwt_secret_key", "seed_admin_password")
    @classmethod
    def _reject_placeholder_secrets(cls, value: str, info) -> str:  # type: ignore[no-untyped-def]
        """An unreplaced placeholder must fail at startup, not sign tokens quietly.

        Without this, `.env.example` copied verbatim boots cleanly and Story 1.2
        signs JWTs with a secret that is committed to version control.
        """
        if not value or value.startswith("CHANGE_ME"):
            raise ValueError(
                f"{info.field_name} is empty or still a CHANGE_ME placeholder — "
                "set a real value in .env (see .env.example)"
            )
        return value

    @model_validator(mode="after")
    def _build_database_url(self) -> "Settings":
        """Fill `database_url` from the POSTGRES_* parts when no override is given.

        `quote(..., safe="")` is what makes a password containing URL-special
        characters survive the trip; hand-built URLs (the old .env DATABASE_URL)
        had no such guarantee.
        """
        if self.database_url is None:
            self.database_url = (
                "postgresql+psycopg://"
                f"{quote(self.postgres_user, safe='')}:"
                f"{quote(self.postgres_password, safe='')}@"
                f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, constructed on first use.

    Cached so that `Settings()` reads the environment once. Tests that need a
    different environment call `get_settings.cache_clear()`.

    `database_url` is always a `str` after construction — the model validator
    fills it — the `| None` in its annotation exists only for the optional
    override's sake.
    """
    return Settings()  # type: ignore[call-arg]  # pydantic-settings fills from env
