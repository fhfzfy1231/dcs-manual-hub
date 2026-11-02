<div align="center">

# ✈️ DCS Manual Hub AI (飞行手册智能知识库中枢)

**专为 Digital Combat Simulator (DCS World) 打造的下一代现代化飞行手册智能交互与战术知识库中枢**

[![Python Version](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PDF.js](https://img.shields.io/badge/PDF.js-v3.11-FF0000?style=flat&logo=adobeacrobatreader&logoColor=white)](https://mozilla.github.io/pdf.js/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![DCS World](https://img.shields.io/badge/DCS_World-Combat_Sim-000000?style=flat)](https://www.digitalcombatsimulator.com/)

[功能特性](#-核心功能特性) • [极速起步](#-极速起步指南) • [Docker部署](#-docker--1panel-部署) • [项目结构](#-项目结构) • [常见问题](#-常见问题)

</div>

---

## 📖 项目简介

官方及模组开发者提供的 DCS 飞行手册通常篇幅宏大（动辄 300~600 页），但在日常模拟飞行中，飞行员经常面临两大痛点：
1. **书签缺失与查阅困难**：许多经典手册（如官方 F-16C 抢先体验手册）未嵌入电子跳转书签，前序印刷目录无法点击，翻查特定航电或武器投放步骤极其繁琐；
2. **战术查阅不及时**：在座舱中遇到雷达模式（RWS/TWS/ACM）或武器导引（JDAM/JSOW/HARM）疑问时，无法快速检索对应页面。

**DCS Manual Hub AI** 彻底解决了这些痛点。它集成了 **PDF.js 高保真矢量渲染**、**PDF 页面内目录超链接穿透**、**基于字符物理坐标的多级目录深度还原引擎**、**BM25 混合全文检索** 与 **大模型 AI 战术副官（带精准页码引用标签 [P. xx]）**，为您提供丝滑的飞行查阅体验。

---

## 🌟 核心功能特性

### 1. ⚡ PDF.js 高清交互与页面内超链接跳转
* **页面内 `/Link` 超链接原生穿透**：集成 PDF.js `AnnotationLayer`，直接在 PDF 原文字画布上支持目录章节与页码点击，光标自动悬浮高亮，点击瞬间跳转至目标页面。
* **键盘方向键双向畅快操控**：
  * `↑` / `↓`：平滑上下滚动阅读；
  * `←` / `→` 或 `PageUp` / `PageDown`：快速翻页；
  * 内置智能输入焦点避让，打字时绝不冲突。
* **翻页自动置顶**：换页或目录跳转时，滚动条自动重置到顶部（`scrollTop = 0`），告别滚动位置残留。
* **【适合高度】一键自适应缩放**：工具栏新增高度等高贴合按钮，自动测算屏幕可见区域高度，实现 100% 垂直贴合展示。

### 2. 📑 坐标感知 & AI 多级大纲深度解析引擎
* **坐标级精准提取**：针对 F-16C 等无电子书签的手册，采用字体物理坐标（`tm[4]` 横坐标缩进与 `tm[5]` 纵坐标行聚合）算法，完美归纳出 **14 个顶级主章节**（如《最新改动》、《飞行控制》、《F-16C“蝰蛇”》、《驾驶舱简介》、《程序》、《空对空武器使用》等）与 **227 个结构分明的多级子节点**。
* **页眉页脚与封面过滤**：彻底排除 `EAGLE DYNAMICS 3/5/7...` 奇数页脚误判，严格限制匹配页码范围，过滤封面日期造成的假章节。
* **默认原生状态**：系统开机或导入新 PDF 时默认保持原生书签状态，不强制标记 AI 目录；仅由管理员在后台按需手动触发重构。

### 3. 🖼️ 高清 PDF 封面画廊与视觉速查
* **自动提取原生封面插画**：后端在索引新 PDF 时自动解析第 1 页高分辨率战机封绘插画（如 F-16C 的 1536x2048 官方高清封绘）并落盘缓存。
* **卡片视觉化展示**：首页列表卡片以 16:10 画廊画幅呈现封面，伴随平滑鼠标悬浮放大动效（）与遮罩提示，帮助飞行员通过战机涂装与封绘瞬间找到目标手册。
* **双模智能容错**：提供专属  极速接口，若手册第 1 页为矢量图形或离线状态，前端自动调用 PDF.js 矢量画布进行首屏动态渲染并缓存，杜绝任何破图。

### 4. 🔍 BM25 混合全文检索 & 多机型收录
* 支持跨手册、跨章节的中文与英文航空术语分词检索（例：`AGM-65`、`HUD`、`冷启动`、`火控雷达`）。
* 命中段落高亮预览，支持一键穿透翻越至该手册的具体命中页码。

### 5. ⚡ 预索引持久化缓存 & SSE 流式打字机问答
* **预索引持久化缓存 (Pre-Indexed Chunks Cache)**：彻底消除启动解析等待！手册在首次上传或分析时自动将分词切片持久化落盘（）。系统重启或加载只需 **0.04 秒（速度提升近 100 倍）**，彻底避免重复解析几千页 PDF 的 CPU 瓶颈。
* **SSE 实时流式打字机输出 (Server-Sent Events)**：提问后首字响应时间压入 **0.8 秒** 内！回答如同打字机般逐字输出，彻底消灭过去长时间盯着加载中卡顿的等待痛点。

### 5. 🤖 AI 战术副官 (RAG 问答 + 精准页码引用)
* 支持接入 **DeepSeek**、**OpenAI**（GPT-4o/mini）及本地离线 **Ollama** 模型。
* AI 回答严格基于手册原文，并在步骤旁自动标注可点击的引用胶囊 `[P. xx]`，点击即可联动跳转到对应 PDF 页面核对。

### 7. 🌐 URL 层级路由与 Sitemap 搜索引擎索引
* **独立手册与章节下级路径**：每本手册拥有独立下级 URL（如 ），翻页自动无缝同步页码参数（如 ），支持浏览器前进/后退（Popstate）导航，彻底杜绝误触返回退出网站。
* **隐藏前台管理按钮，保护管理安全**：前台移除“管理后台”按钮，独立管理控制台统一定位至 。
* **自动生成  与 **：自动根据知识库中所有手册和顶级章节生成标准 XML 网站地图，支持搜索引擎自动爬取，并可在管理后台一键刷新。

### 6. 🛠️ 管理控制台 (Admin Dashboard)
* **全局生效**：管理员在后台配置大模型 API Key 后全站访客即可共享使用，无需每位访客重复设置。
* **安全凭据修改**：支持在后台一键修改管理员登录密码。
* **新航电手册上传**：支持将各类战机（F/A-18C、A-10C II、AH-64D 等）PDF 手册直接拖拽上传切片。

---

## 🚀 极速起步指南

### 方式一：Windows 本地双击运行 (免配置)

1. 下载最新发行包或克隆本仓库到本地并解压；
2. 确保电脑已安装 **Python 3.9+**（安装时请勾选 `Add Python to PATH`）；
3. 直接双击运行项目目录下的 **`start.bat`**（或极简纯英脚本 **`run.bat`**）：
   * 脚本会自动检查环境、安装轻量依赖（`fastapi`, `uvicorn`, `pypdf`, `httpx`）并在本地启动服务；
   * 启动后会自动在浏览器中打开：
     * **前台知识库**：`http://localhost:8000`
     * **管理控制台**：`http://localhost:8000/admin`（默认账号：`admin`，默认密码：`admin`）

> **提示**：如果换了新电脑遇到批处理闪退问题，可直接在当前目录打开 CMD，运行 `python -m uvicorn app:app --host 0.0.0.0 --port 8000` 即可绝对保持窗口！

---

### 方式二：命令行手动运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🐳 Docker / 1Panel 部署

本项目支持极速容器化部署，支持挂载外部 `manuals` 目录持久化存储手册：

```bash
# 单行 Docker 命令运行
docker run -d \
  --name dcs-manual-hub \
  -p 8000:8000 \
  -v ./manuals:/app/manuals \
  --restart unless-stopped \
  python:3.11-slim \
  sh -c "pip install -r /app/requirements.txt && python -m uvicorn app:app --host 0.0.0.0 --port 8000"
```

在 **1Panel** 或 **Portainer** 中：
* 映射端口：`8000:8000`
* 挂载卷：`./manuals` -> `/app/manuals`
* 访问地址：`http://服务器IP:8000`

---

## 📁 项目结构

```text
dcs-manual-hub/
├── app.py                  # FastAPI 核心后端 (全文分词检索、RAG问答、坐标感知目录重构)
├── config.json             # 大模型与管理后台全局配置文件
├── requirements.txt        # 依赖清单 (fastapi, uvicorn, pypdf, httpx)
├── start.bat               # Windows 原生防闪退启动器 (GBK编码+CRLF)
├── run.bat                 # 极简纯英 ASCII 启动器
├── push_to_github.bat      # 一键全自动推送到 GitHub 远程仓库脚本
├── debug_start.bat         # 诊断模式启动脚本
├── manuals/                # 手册库目录 (持久化保存 PDF 与已生成大纲元数据)
│   ├── DCS_F-16C_Early_Access_Guide_CN.pdf  # F-16C 中文抢先体验指南完整版 (340页)
│   └── metadata.json       # 手册目录树与索引元数据
├── static/                 # 前端单页系统 (纯原生现代扁平天蓝主题，100dvh视窗锁定)
│   ├── index.html          # 前台主阅读器 + AI战术副官
│   └── admin.html          # 管理控制台
└── README.md               # 项目技术说明文档
```

---

## 📤 推送到您的 GitHub 仓库

本项目已完整配置好本地 Git 历史与 `.gitignore`，解压后推送到您个人的 GitHub 极其简单：

```bash
# 1. 在 github.com/new 创建名为 dcs-manual-hub 的仓库后执行：
git remote add origin https://github.com/fhfzfy1231/dcs-manual-hub.git
git branch -M main
git push -u origin main
```
*(Windows 用户也可直接双击文件夹内的 `push_to_github.bat` 自动推送到 GitHub)*

---

## 📜 许可证与鸣谢 (License & Credits)

* **Code License**：本项目代码基于 [MIT License](LICENSE) 开源。
* **DCS World & Manuals**：相关飞行手册与商标版权归 [Eagle Dynamics SA](https://www.digitalcombatsimulator.com/) 及相应模组开发商所有，本项目仅用于模拟飞行爱好者个人学术研究与战术查阅便利。

---

<div align="center">
  <sub>Fly safe, Check Six! 祝各位长官起落平安，索敌制胜！✈️</sub>
</div>
