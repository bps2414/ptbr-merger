@echo off
cd /d %~dp0..
python -m src.tools.tail_log --follow --lines 80
