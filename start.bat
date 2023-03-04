@echo off

PUSHD "%~dp0"
call conda activate invokeai
python .\scripts\invoke.py --web %*
