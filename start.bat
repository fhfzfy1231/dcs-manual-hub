@echo off
cd /d "%~dp0"
title DCS Manual Hub AI - 飞行手册智能知识库 v2.3

echo ======================================================================
echo           DCS Manual Hub AI - 飞行手册智能知识库 (v2.3)
echo ======================================================================
echo.

echo [步骤 1/3] 检查 Python 环境...
python --version
if errorlevel 1 goto NO_PYTHON

echo.
echo [步骤 2/3] 检查并自动安装依赖库 (fastapi, uvicorn, pypdf, httpx)...
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
if errorlevel 1 goto PIP_FAIL

echo.
echo [步骤 3/3] 依赖就绪，正在启动服务...
echo ----------------------------------------------------------------------
echo 本地服务地址: http://localhost:8000
echo 管理后台地址: http://localhost:8000/admin (默认账号: admin, 默认密码: admin)
echo ----------------------------------------------------------------------
echo.

start http://localhost:8000

python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
if errorlevel 1 goto RUN_FAIL
goto FINISH

:NO_PYTHON
echo.
echo ======================================================================
echo [错误] 系统中未找到可用 Python 命令！
echo ======================================================================
echo 请确保 Python 已正确安装，并在系统环境变量 PATH 中配置。
goto FINISH

:PIP_FAIL
echo.
echo ======================================================================
echo [提示] 依赖安装遇到问题，尝试使用官方源重试...
echo ======================================================================
python -m pip install -r requirements.txt
if errorlevel 1 goto FINAL_ERROR
echo.
echo [依赖安装成功，继续启动...]
start http://localhost:8000
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
goto FINISH

:RUN_FAIL
echo.
echo ======================================================================
echo [错误] 服务启动异常中断！请查看上方的详细报错信息。
echo ======================================================================
goto FINISH

:FINAL_ERROR
echo.
echo ======================================================================
echo [错误] 依赖库安装失败！请查看上方的 pip 报错信息。
echo ======================================================================
goto FINISH

:FINISH
echo.
echo ======================================================================
echo 程序已退出。请查看上方信息。按任意键关闭窗口...
echo ======================================================================
pause >nul
