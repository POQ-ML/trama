#!/usr/bin/env bash
set -euo pipefail
docker compose run --rm api alembic upgrade head
