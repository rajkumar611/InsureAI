@echo off
set VIRTUAL_ENV=
set PYTHONPATH=%CD%\backend\src;%PYTHONPATH%
uv run streamlit run frontend/streamlit_app.py
