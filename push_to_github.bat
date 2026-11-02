@echo off
cd /d "%~dp0"
title 一键推送到 GitHub - dcs-manual-hub (v3.1.4 响应式界面排版修复版)

echo ========================================================
echo        DCS Manual Hub AI - 一键推送到 GitHub (v3.1.4)
echo ========================================================
echo.
echo 目标仓库: https://github.com/fhfzfy1231/dcs-manual-hub.git
echo 当前版本: 修复后台模型输入框重复、列表标签折行与阅读器窄窗口顶栏挤压问题
echo.

:: 1. 检查本地 git 工具
git --version >nul 2>&1
if errorlevel 1 goto NO_GIT

:: 2. 清理可能存在的旧 .git 索引并全新初始化
if exist ".git" attrib -r -s -h ".git" /s /d >nul 2>&1
if exist ".git" rmdir /s /q ".git" >nul 2>&1

echo [1/5] 正在初始化本地 Git 仓库...
git init
git config user.name "fhfzfy1231"
git config user.email "fhfzfy1231@users.noreply.github.com"

:: 3. 配置远程仓库关联
echo [2/5] 正在配置远程仓库关联...
git remote remove origin >nul 2>&1
git remote add origin https://github.com/fhfzfy1231/dcs-manual-hub.git

:: 4. 暂存所有工程文件
echo [3/5] 正在暂存所有工程文件 - 代码、PDF、480x640轻量封面、预训练库...
git add -A

:: 5. 生成本次版本提交记录
echo [4/5] 正在生成版本提交记录...
git commit -m "fix(v3.1.4): fix duplicate model input in admin, prevent table badge text wrapping, and fix reader toolbar squeezing on narrow windows"
echo.

:: 6. 规范主分支为 main
git branch -M main

:: 7. 强制同步推送最新完整状态到远程
echo [5/5] 正在向 GitHub 远程仓库强制同步最新版本...
git push -u origin main --force
if not errorlevel 1 goto SUCCESS

goto PUSH_FAIL

:SUCCESS
echo.
echo ========================================================
echo [成功] 本次 v3.1.4 独立完整版已 100%% 推送到您的 GitHub 个人主页！
echo 项目网址: https://github.com/fhfzfy1231/dcs-manual-hub
echo 重要提醒: 请在 1Panel 终端拉取代码并重启容器生效！
echo ========================================================
goto FINISH

:NO_GIT
echo ========================================================
echo [错误] 本机未检测到 Git 命令行工具！
echo 请前往官网下载安装 Git: https://git-scm.com/
echo ========================================================
goto FINISH

:PUSH_FAIL
echo.
echo ========================================================
echo [提示] 推送遇到问题，请排查以下两点：
echo 1. 请确认已在 https://github.com/new 创建名为 dcs-manual-hub 的空仓库；
echo 2. 首次推送若弹出 GitHub 登录/授权窗口，请选择 Sign in with your browser 完成授权。
echo ========================================================
goto FINISH

:FINISH
echo.
pause
