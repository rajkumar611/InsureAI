@echo off
set VIRTUAL_ENV=
set PYTHONPATH=%CD%\backend\src;%PYTHONPATH%
uv run python backend/run.py
