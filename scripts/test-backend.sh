#!/bin/sh
set -e
cd apps/api
pip install -r requirements.txt
pytest -q
