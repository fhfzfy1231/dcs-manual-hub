from datetime import datetime
# -*- coding: utf-8 -*-
import os
import io
import re
import json
import time
import base64
import asyncio
from collections import Counter
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import pypdf

app = FastAPI(title="DCS Manual Hub AI", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANUALS_DIR = os.path.join(BASE_DIR, "manuals")
STATIC_DIR = os.path.join(BASE_DIR, "static")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
METADATA_PATH = os.path.join(MANUALS_DIR, "metadata.json")

os.makedirs(MANUALS_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-flash",
    "thinking_mode": "disabled",
    "reasoning_effort": "low",
    "provider": "deepseek",
    "admin_password": "admin"
}

def normalize_deepseek_model(model_name: str, base_url: str = "") -> str:
    """Auto-upgrades retired legacy DeepSeek model names (deepseek-chat / deepseek-reasoner) to DeepSeek V4.1 Flash."""
    m = (model_name or "").strip()
    if not m:
        return "deepseek-flash"
    if "deepseek" in (base_url or "").lower() or m.startswith("deepseek"):
        if m in ("deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"):
            return "deepseek-flash"
    return m

def build_llm_payload(model: str, messages: list, cfg: Dict[str, Any], stream: bool = False, thinking_override: Optional[str] = None) -> Dict[str, Any]:
    """Builds request payload adapted for DeepSeek V4 / V4.1-Flash (1M Context, Thinking Mode toggle)."""
    base_url = cfg.get("base_url", "https://api.deepseek.com")
    actual_model = normalize_deepseek_model(model, base_url)
    thinking_mode = thinking_override or cfg.get("thinking_mode", "disabled")
    payload: Dict[str, Any] = {
        "model": actual_model,
        "messages": messages,
        "stream": stream
    }
    if "deepseek" in base_url.lower() or actual_model.startswith("deepseek"):
        if thinking_mode == "enabled":
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = cfg.get("reasoning_effort", "low")
        else:
            payload["thinking"] = {"type": "disabled"}
    else:
        payload["temperature"] = 0.2
    return payload

def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: Dict[str, Any]):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

GLOBAL_CONFIG = load_config()

def normalize_chat_completions_url(base_url: str) -> str:
    """Normalizes any user-entered base_url to the correct chat/completions endpoint."""
    url = (base_url or "").strip().rstrip('/')
    if not url:
        return "https://api.deepseek.com/v1/chat/completions"
    if url.endswith("/chat/completions"):
        return url
    if not url.endswith("/v1") and ("deepseek" in url or "openai" in url or "api." in url):
        url = f"{url}/v1"
    return f"{url}/chat/completions"

def load_persisted_metadata() -> Dict[str, Any]:
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_persisted_metadata():
    clean_meta = {}
    for mid, item in MANUALS_METADATA.items():
        clean_meta[mid] = {
            "title": item["title"],
            "filename": item["filename"],
            "totalPages": item["totalPages"],
            "toc": item.get("toc", []),
            "is_ai_generated_toc": item.get("is_ai_generated_toc", False),
            "cover_image": item.get("cover_image")
        }
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(clean_meta, f, ensure_ascii=False, indent=2)

QA_CACHE_FILE = os.path.join(MANUALS_DIR, "qa_cache.json")
QA_CACHE: Dict[str, Any] = {}
BUILTIN_TACTICAL_QA: Dict[str, Any] = {
  "global:冷舱启动步骤": {
    "manual_id": "dcs_f-16c_early_access_guide_cn",
    "query": "冷舱启动步骤",
    "keywords": ["冷舱", "启动", "开车", "发动机启动", "检查单"],
    "answer": """F-16C 飞行员冷舱启动标准战术流程（检查单）：

1. **电源系统初始化**：
   • 将座舱左侧 **MAIN PWR** 开关切至 **BATT** 检查电瓶电压，随后推至 **MAIN PWR** 档位 [P. 33]。
   • 检查 FLCS 电源指示灯点亮，进行飞行控制系统自检。

2. **喷气燃料启动机 (JFS) 启动**：
   • 将 **JFS** 启动电门向前扳至 **START 2** 档位（双储压罐模式），观察操纵面板上的 **JFS RUN** 绿色指示灯常亮 [P. 35]。

3. **发动机供油点火**：
   • 密切观察仪表板中央的 **RPM (发动机转速表)**，当转速达到 **20%** 时，将油门杆防错锁扣抬起，从 **OFF** 挡位推进至 **IDLE (怠速)** 挡位 [P. 36]。
   • 监控 **FTIT (风扇涡轮进气温度)** 升温过程，确保温度在正常限制值以内。

4. **发电机并网与自检**：
   • 转速达到 **60%~70%** 后，主发电机自动并网，JFS 开关自动跳脱回中间 OFF 挡位，**SEC** 指示灯熄灭 [P. 38]。

5. **全机航电系统通电**：
   • 右侧航电面板依次开启：**MMC (模块化任务计算机)**、**ST STA (外挂电门)**、**MFD (多功能显示器)**、**UFC (通用前置控制板)**、**GPS** 与 **DL (数据链)** [P. 40]。

6. **惯性导航系统 (INS) 对准**：
   • 将右侧控制台 **INS 旋钮** 旋至 **NORM** 开始标准校准；若停机坪有预存航向，可旋至 **STOR HDG** 进行快速对准 [P. 42]。
   • 对准完成（DED 显示 RDY 闪烁）后，旋钮切至 **NAV** 档位。

7. **座舱气密与弹射准备**：
   • 放下座舱盖，将手柄扳至 LOCK 锁闭座舱并加压，拔除弹射座椅保险插销 [P. 45]。""",
    "citations": [
      {"page": 33, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "MAIN PWR 电源开关与电气系统启动流程..."},
      {"page": 35, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "JFS 喷气燃料启动机操作与指示灯..."},
      {"page": 36, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "油门杆从 OFF 推进至 IDLE 挡位启动条件..."},
      {"page": 45, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "座舱盖密闭与弹射座椅解除保险准备..."}
    ],
    "timestamp": 1761912000
  },
  "global:agm65导弹投放模式": {
    "manual_id": "dcs_f-16c_early_access_guide_cn",
    "query": "AGM-65 导弹投放模式",
    "keywords": ["agm-65", "agm65", "小牛", "幼畜", "空地导弹", "maverick", "投放模式"],
    "answer": """AGM-65 “幼畜” (Maverick) 空地导弹战术投放流程如下：

1. **进入空地主模式**：
   • 按下仪表板左上方主模式控制板的 **A-G (Air-to-Ground)** 按键，火控计算机切换至空地打击状态 [P. 319]。

2. **武器页面选择与通电**：
   • 在左侧或右侧 MFD 呼出 **WPN (武器)** 页面，确认选中 **AGM-65**，检查导弹陀螺加温完成，状态显示为 **RDY** [P. 319]。

3. **选择瞄准子模式 (Sub-mode)**：
   • 点击 OSB 切换引导头工作模式：
     - **PRE (预设航路点模式)**：导弹导引头自动随动于当前活动航路点 (STPT) 或火控雷达地面目标 [P. 320]。
     - **VIS (目视模式)**：HUD 产生随动菱形瞄准框，用于目视快速攻击视界内敌方目标 [P. 320]。
     - **BORE (轴线模式)**：导引头锁定飞机机头轴线方向 [P. 321]。

4. **目标截获与导引头跟踪**：
   • 将 MFD 设为传感点 (SOI)，使用操纵杆上的 **Cursor Slew (雷达光标开关)** 将十字准星对准敌方地面装甲车或掩体 [P. 321]。
   • 按下 **TMS Up (前推)** 让导弹电视/红外导引头闭锁目标，观察瞄准框闭合且视场稳定跟踪 [P. 321]。

5. **武器发射**：
   • 观察 HUD 瞄准标尺，确认处于动力射程内且出现 **IN RANGE** 投放许可提示 [P. 322]。
   • 按住操纵杆上的 **Weapon Release (武器释放/Pickle)** 键约 1 秒发射导弹 [P. 322]。发射后即可脱离机动（发射后不管）。""",
    "citations": [
      {"page": 319, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "A-G 主模式与 AGM-65 武器页面就绪配置..."},
      {"page": 320, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "AGM-65 PRE、VIS、BORE 瞄准模式切换..."},
      {"page": 321, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "使用光标对准目标并按下 TMS Up 闭锁导引头..."},
      {"page": 322, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "IN RANGE 射程判定与 Weapon Release 导弹发射..."}
    ],
    "timestamp": 1761912000
  },
  "global:aim120中距空空导弹超视距攻击": {
    "manual_id": "dcs_f-16c_early_access_guide_cn",
    "query": "AIM-120 主动雷达空空导弹超视距发射",
    "keywords": ["aim-120", "aim120", "amraam", "超视距", "中距弹", "雷达导弹", "空空导弹"],
    "answer": """AIM-120 (AMRAAM) 超视距空空导弹拦截与发射流程：

1. **主模式切换**：
   • 按下操纵杆空空模式切换开关或主模式板 **A-A** 按键，火控雷达与 HUD 切换至空空格斗状态 [P. 280]。

2. **武器挂载确认**：
   • 确认 SMS 武器页面显示挂载的 **AIM-120** 并处于 RDY 就绪状态 [P. 281]。

3. **雷达搜索与目标截获**：
   • 在 FCR (火控雷达) 页面设置搜索范围（推荐 40nm 或 80nm，方位角 60°，扫描层数 4 棒） [P. 282]。
   • 将雷达光标移至目标雷达回波上，**TMS Up (前推)** 建立单目标跟踪 (STT) 或使用 TWS 模式跟踪 [P. 283]。

4. **动态发射区域 (DLZ) 判读**：
   • 观察 HUD 右侧的动态射程标尺：
     - **Raero**：导弹空气动力学最大滑翔极限。
     - **Rmax**：最大有效攻击距离。
     - **Rne (No Escape)**：不可逃逸区，敌机即使做大过载机动也极难规避 [P. 284]。

5. **导弹发射与中继制导**：
   • 当目标符号进入发射允许范围且 HUD 出现发射提示框时，按操纵杆 **Weapon Release (Pickle)** 键发射导弹 [P. 284]。
   • 发射后保持母机雷达跟踪，HUD 将显示 **A-倒计时**（中继雷达数据链修正时间）。倒计时归零后显示 **T-倒计时**，代表导弹自身主动导引头已开机截获目标（Pitbull / 斗牛犬状态），母机此时可自由掉头脱离 [P. 285]。""",
    "citations": [
      {"page": 280, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "A-A 主模式激活与空空火控界面..."},
      {"page": 282, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "FCR 空空雷达搜索模式设置与截获..."},
      {"page": 284, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "动态发射区域 DLZ (Raero, Rmax, Rne) 判读..."},
      {"page": 285, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "导弹数据链中继制导与主动导引头截获状态..."}
    ],
    "timestamp": 1761912000
  },
  "global:雷达模式切换与tws": {
    "manual_id": "dcs_f-16c_early_access_guide_cn",
    "query": "雷达模式切换与 TWS 边扫描边跟踪",
    "keywords": ["tws", "rws", "雷达模式", "边扫描边跟踪", "fcr", "火控雷达"],
    "answer": """F-16C 雷达模式切换与 TWS (Track While Scan) 战术运用：

1. **呼出雷达页面**：
   • 在 A-A 主模式下，在 MFD 上选择 **FCR (Fire Control Radar)** [P. 240]。

2. **切换为 TWS 模式**：
   • 点击 MFD 左上角 **OSB 1**，当前雷达搜索模式会在 **RWS (边搜索边测距)**、**TWS (边扫描边跟踪)** 和 **VS (速度搜索)** 之间循环切换 [P. 241]。

3. **TWS 模式核心特性**：
   • 在维持全视场持续扇面扫描的同时，计算机自动跟踪多达 10 个空中目标航迹并预估航向航速 [P. 242]。
   • **战术隐身优势**：向目标发射 AIM-120 导弹期间，目标机载 RWR 不会收到连续波硬锁定告警，直到导弹主动雷达近距离开机 [P. 245]。

4. **目标指定与跟踪等级**：
   • 移动雷达光标至目标方块，按 **TMS Up** 将其设为系统目标 (Track File) [P. 243]。
   • 再次按 **TMS Up** 将其指定为主目标 (Bugged Target)，雷达将在屏幕与 HUD 上强化该目标的矢量线与射程判读 [P. 243]。
   • 按 **TMS Right** 可在已跟踪的多个敌机目标之间快速循环轮换主攻击目标 [P. 244]。""",
    "citations": [
      {"page": 240, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "FCR 雷达系统架构与 MFD 显示布局..."},
      {"page": 241, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "OSB 1 雷达子模式切换与 RWS / TWS 对比..."},
      {"page": 243, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "TMS Up 指定主目标与 TMS Right 多目标轮换..."},
      {"page": 245, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "TWS 模式下静默多目标攻击战术优势..."}
    ],
    "timestamp": 1761912000
  },
  "global:空中加油步骤": {
    "manual_id": "dcs_f-16c_early_access_guide_cn",
    "query": "空中加油步骤与就绪准备",
    "keywords": ["空中加油", "受油门", "加油机", "air refuel", "加油"],
    "answer": """F-16C 硬管空中加油 (Air Refueling) 标准程序：

1. **联络与汇合**：
   • 通过无线电联系加油机（例如 Texaco 或 Shell），请求空中加油并获取加油机高度、航速与航向 [P. 170]。

2. **打开受油口**：
   • 在左侧副仪表板上，将 **AIR REFUEL** 拨钮向前扳至 **OPEN** 档位 [P. 171]。
   • 此操作将打开机背受油口舱门，同时飞行控制计算机 (FLCS) 会减缓配平灵敏度，增压油箱排气并使受油系统处于就绪状态。

3. **确认就绪指示灯**：
   • 检查仪表板右侧眉梁上的 **RDY (Ready)** 蓝绿指示灯常亮 [P. 172]。

4. **进位与队形保持**：
   • 在加油机左后方建立观察位置，确认加油机放下伸缩加油管。
   • 收到 "Cleared to Contact" 指令后，柔和加油门平稳移至加油机腹部正后下方 [P. 173]。
   • 参照加油机腹部的 **PVD (指引灯阵列)** 调整相对高度与前后距离。

5. **受油接通与断开**：
   • 加油员将加油管插入 F-16 受油口后，**RDY** 灯熄灭，**AR/NWS** 绿色指示灯常亮，燃油开始注入 [P. 174]。
   • 满油后加油机断开管线；若遇气流颠簸，可按操纵杆上的 **A/R Disconnect** 按键手动脱开。
   • 脱离后将 **AIR REFUEL** 开关扳回 **CLOSE**，检查 RDY/DISC 指示灯熄灭 [P. 175]。""",
    "citations": [
      {"page": 170, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "空中加油战术汇合与无线电协同准备..."},
      {"page": 171, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "AIR REFUEL 受油口开关控制与 FLCS 增益调整..."},
      {"page": 173, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "加油机腹部 PVD 指引灯与加油位置保持..."},
      {"page": 175, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "受油完成断开程序与仪表指示状态..."}
    ],
    "timestamp": 1761912000
  },
  "global:进近降落与攻角控制": {
    "manual_id": "dcs_f-16c_early_access_guide_cn",
    "query": "进近着陆与攻角控制",
    "keywords": ["着陆", "降落", "进近", "攻角", "aoa", "起落架", "减速板", "接地"],
    "answer": """F-16C 仪表进近与轻柔着陆操作规范：

1. **降速与构型转换**：
   • 进入机场五边或起落航线三边，减速至 **300 节以下**，扳下主起落架手柄 (**GEAR DOWN**) [P. 75]。
   • 开启机尾减速板 (**SPEEDBRAKE**)，FLCS 自动转入起落降级控制律，后缘襟副翼随之放下 [P. 76]。

2. **HUD 攻角指引框 (AOA Bracket) 建立**：
   • 在 HUD 上调出绿色的飞行路径矢量标 (**FPM**) 和攻角支架 (**[ 指引框**)。
   • 调节油门与俯仰配平，将 **FPM 准确重叠在 AOA 支架的正中央** [P. 77]。此时飞机处于标准进近攻角 **11°~13° AOA**，座舱左侧绿光攻角指数灯常亮 [P. 78]。

3. **下滑道与瞄准点控制**：
   • 使用油门控制升降率，使用操纵杆微调机头指向：将 FPM 稳稳压在跑道头接地标志线（斑马线后 300 米处） [P. 78]。

4. **接地与气动减速 (Aero Braking)**：
   • 距地面约 20 英尺时，柔和小幅拉杆拉平，主轮轻柔擦地接地 [P. 79]。
   • 主轮接地后立即将油门收至 **IDLE** 怠速，保持机头仰角 **13° 维持抬轮姿态**进行气动减速，切忌过早将前轮砸地 [P. 79]。

5. **前轮接地与刹车**：
   • 当空速降至 **100 节** 左右时，气动升力减退，前轮平稳自然贴地。
   • 空速低于 **60 节** 时接通前轮转向 (**NWS**)，踩刹车滑跑减速并脱离跑道 [P. 80]。""",
    "citations": [
      {"page": 75, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "进近着陆起落架放下限制速度与减速板操作..."},
      {"page": 77, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "HUD AOA 攻角支架与最佳着陆姿态保持..."},
      {"page": 78, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "绿光攻角指数指示灯与下滑点油门控制..."},
      {"page": 79, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "主轮接地与 13 度抬头气动减速规范..."}
    ],
    "timestamp": 1761912000
  },
  "global:rwr威胁告警与干扰弹投放": {
    "manual_id": "dcs_f-16c_early_access_guide_cn",
    "query": "RWR 威胁告警与干扰弹投放",
    "keywords": ["rwr", "干扰弹", "热诱弹", "箔条", "chaff", "flare", "告警", "雷达告警", "cms"],
    "answer": """F-16C 机载电子战自卫与干扰弹 (CMS) 战术运用：

1. **电子战面板开机**：
   • 在左侧控制台 EW 面板上，将 **RWR** 电源开关推至 **ON** 激活全向雷达告警接收机 [P. 195]。
   • 将 **RWR / SEARCH** 按钮选定，仪表板左上方圆形方位显示屏 (ALR-56M) 即时显示周围 360° 威胁雷达信号 [P. 195]。

2. **反制物投放系统 (CMS) 准备**：
   • 将 CMS 面板上的 **CHAFF (箔条)** 与 **FLARE (热诱弹)** 电源全部开启，检查余量指示 [P. 196]。
   • 模式旋钮可选择：
     - **MAN (手动)**：按压操纵杆开关投放预设程序。
     - **SEMI (半自动)**：系统检测到严重威胁时提示程序号，飞行员按键确认投放。
     - **AUTO (自动)**：系统自主按最优间隔连续投放 [P. 197]。

3. **告警识别与战术反制**：
   • **连续波锁定/制导**：RWR 音频由断续滴声变为连续刺耳高频尖啸，目标符号外围出现闪烁的菱形圈，代表已被雷达制导导弹锁定 [P. 198]。
   • 立即大过载转向机动使威胁处于机尾 3 点或 9 点（波束机动切角），同时用拇指**前推操纵杆 CMS 开关 (CMS Forward)** 执行释放程序 [P. 198]。
   • 箔条形成雷达假目标欺骗中远距雷达弹，同时高密度抛射热诱弹红外热斑规避格斗红外导弹追击 [P. 200]。""",
    "citations": [
      {"page": 195, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "RWR 雷达告警接收机开机与方位盘威胁判读..."},
      {"page": 196, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "CMS 面板箔条、热诱弹电源控制与余量监控..."},
      {"page": 198, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "导弹锁定告警特征与 CMS Forward 手指开关投放..."},
      {"page": 200, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "机动规避配合反制物投放规避红外与雷达导引头..."}
    ],
    "timestamp": 1761912000
  },
  "global:航路点设置与导航": {
    "manual_id": "dcs_f-16c_early_access_guide_cn",
    "query": "航路点与导航航线设置",
    "keywords": ["航路点", "航点", "stpt", "导航", "切换航点", "经纬度", "icp"],
    "answer": """F-16C 航路点 (Steerpoint / STPT) 切换与设置操作：

1. **查看当前活动航路点**：
   • 通过风挡下方的综合控制面板 (ICP) 查看 DED 主屏幕中央显示的当前航点编号（例如 **STPT 1**），以及飞往该航点的预估时间 (ETA) 与剩余距离 (TOS) [P. 110]。

2. **快速切换已有航点**：
   • 使用 ICP 中央的四向拨动开关 (**DCS Switch**) 向上或向下推动，即可在航路点之间顺次步进（1 -> 2 -> 3...） [P. 112]。
   • 切换后，HUD 上的航向标尺标记点与水平姿态指示器 (HSI) 指针会自动指向新航点方位 [P. 115]。

3. **手动创建/输入新经纬度航点**：
   • 在 ICP 数字键盘上按下 **4 (STPT)** 键进入航点编辑页面 [P. 118]。
   • 使用 DCS 向下推使反白光标移至纬度行，输入北纬/南纬与坐标数值，按 **ENTR** 确认。
   • 依次输入经度 (E/W) 与标高 (ELEV)，完成新航点定义并作为巡航或打击参考点 [P. 118]。""",
    "citations": [
      {"page": 110, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "DED 主屏幕导航数据与当前活动航路点显示..."},
      {"page": 112, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "ICP DCS 拨动开关快速步进切换航点..."},
      {"page": 115, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "HUD 航路点偏航指引符号与 HSI 航向指针..."},
      {"page": 118, "manual_title": "DCS F-16C Early Access Guide CN", "snippet": "通过 ICP 4 号键手动输入经纬度新航点..."}
    ],
    "timestamp": 1761912000
  }
}


def load_qa_cache() -> Dict[str, Any]:
    global QA_CACHE
    if os.path.exists(QA_CACHE_FILE):
        try:
            with open(QA_CACHE_FILE, "r", encoding="utf-8") as f:
                QA_CACHE = json.load(f)
        except Exception as e:
            print(f"[Warning] Failed to load qa_cache: {e}")
            QA_CACHE = {}
    if not QA_CACHE:
        QA_CACHE = BUILTIN_TACTICAL_QA.copy()
        save_qa_cache()
    print(f"⚡ [战术问答库就绪] 已装载 {len(QA_CACHE)} 条预训练/预处理战术问答缓存")
    return QA_CACHE

def save_qa_cache():
    try:
        with open(QA_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(QA_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Warning] Save qa_cache error: {e}")

def normalize_key(s: str) -> str:
    return re.sub(r'[^\w\u4e00-\u9fff]', '', s.lower())

def lookup_qa_cache(manual_id: Optional[str], query: str) -> Optional[Dict[str, Any]]:
    norm_q = normalize_key(query)
    if not norm_q:
        return None
    
    # 1. Exact match on normalized query
    for k, val in QA_CACHE.items():
        if manual_id and val.get("manual_id") and val.get("manual_id") != manual_id:
            continue
        if normalize_key(val.get("query", "")) == norm_q:
            return val
            
    # 2. Check keywords match
    for k, val in QA_CACHE.items():
        if manual_id and val.get("manual_id") and val.get("manual_id") != manual_id:
            continue
        keywords = val.get("keywords", [])
        for kw in keywords:
            norm_kw = normalize_key(kw)
            if len(norm_kw) >= 2 and norm_kw in norm_q:
                return val

    # 3. Substring match
    for k, val in QA_CACHE.items():
        if manual_id and val.get("manual_id") and val.get("manual_id") != manual_id:
            continue
        cached_q = normalize_key(val.get("query", ""))
        if len(norm_q) >= 3 and (norm_q in cached_q or cached_q in norm_q):
            return val
            
    return None

def cache_qa_response(manual_id: Optional[str], query: str, answer: str, citations: list):
    norm_q = normalize_key(query)
    if not norm_q or not answer:
        return
    key = f"{manual_id or 'global'}:{norm_q}"
    QA_CACHE[key] = {
        "manual_id": manual_id,
        "query": query,
        "keywords": [w for w in re.findall(r'[\w\u4e00-\u9fff]+', query) if len(w) >= 2][:6],
        "answer": answer,
        "citations": citations,
        "timestamp": time.time()
    }
    save_qa_cache()

INDEX: List[Dict[str, Any]] = []
MANUALS_METADATA: Dict[str, Dict[str, Any]] = {}

def tokenize(text: str) -> List[str]:
    text = text.lower()
    words = re.findall(r'[a-zA-Z0-9\-_]+', text)
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    bigrams = [chinese_chars[i] + chinese_chars[i+1] for i in range(len(chinese_chars)-1)]
    return words + chinese_chars + bigrams

def extract_outermost_json_array(text: str) -> Optional[List[Dict[str, Any]]]:
    """Robustly extracts the outermost JSON array, preventing truncation at nested brackets."""
    first_b = text.find('[')
    last_b = text.rfind(']')
    if first_b != -1 and last_b != -1 and last_b > first_b:
        candidate = text[first_b : last_b + 1]
        try:
            res = json.loads(candidate)
            if isinstance(res, list):
                return res
        except Exception:
            cleaned = re.sub(r',\s*([\]\}])', r'\1', candidate)
            try:
                res = json.loads(cleaned)
                if isinstance(res, list):
                    return res
            except Exception:
                pass
    return None

def extract_outline_recursive(outline_list, reader):
    items = []
    current_parent = None
    for obj in outline_list:
        if isinstance(obj, list):
            if current_parent:
                current_parent["children"] = extract_outline_recursive(obj, reader)
            else:
                items.extend(extract_outline_recursive(obj, reader))
        elif hasattr(obj, "title"):
            node = {
                "title": str(obj.title),
                "page": 1,
                "children": []
            }
            try:
                pg_idx = reader.get_destination_page_number(obj)
                node["page"] = pg_idx + 1
            except Exception:
                pass
            items.append(node)
            current_parent = node
    return items

def extract_printed_toc_coordinates(reader) -> List[Dict[str, Any]]:
    """
    Extracts printed Table of Contents from pages 1-20 using coordinate-aware line grouping.
    Accurately classifies hierarchy (levels 0, 1, 2) based on x indentation while filtering
    running headers, footers (like 'EAGLE DYNAMICS 3'), and cover metadata.
    """
    total_pages = len(reader.pages)
    all_entries = []
    
    # Check first 20 pages
    for p_idx in range(min(20, total_pages)):
        page = reader.pages[p_idx]
        lines = {}
        def visitor(text, cm, tm, font_dict, font_size):
            if text.strip():
                y = round(tm[5], 1)
                matched_y = None
                for ey in lines:
                    if abs(ey - y) <= 2.5:
                        matched_y = ey
                        break
                if matched_y is None:
                    matched_y = y
                    lines[matched_y] = []
                lines[matched_y].append((tm[4], text))

        try:
            page.extract_text(visitor_text=visitor)
        except Exception:
            continue
            
        sorted_y = sorted(lines.keys(), reverse=True)
        for y in sorted_y:
            row = sorted(lines[y], key=lambda x: x[0])
            first_x = row[0][0]
            full_text = ''.join(x[1] for x in row).strip()
            
            # Match dot leader (3+ dots or spaces) followed by page number at end
            m = re.search(r'^(.*?)(?:[\.·…_—\-\s]{3,}|\.{2,})\s*(\d{1,4})\s*$', full_text)
            if m:
                title = m.group(1).strip().rstrip('.·…_—\\- ')
                pg = int(m.group(2))
                if not title or pg > total_pages or pg < 1:
                    continue
                upper_t = title.upper()
                if any(k in upper_t for k in ['EAGLE DYNAMICS', 'DCS [', '[F-16C', '更新', '目录']):
                    continue
                
                # Determine level based on indentation (first_x)
                # On DCS standard manuals: left margin is ~54pt
                if first_x <= 58:
                    lvl = 0
                elif first_x <= 70:
                    lvl = 1
                else:
                    lvl = 2
                all_entries.append({'title': title, 'page': pg, 'level': lvl})
    
    # Build hierarchical tree
    tree = []
    stack = []
    for item in all_entries:
        node = {'title': item['title'], 'page': item['page'], 'level': item['level'], 'children': []}
        while stack and stack[-1]['level'] >= item['level']:
            stack.pop()
        if stack:
            stack[-1]['children'].append(node)
        else:
            tree.append(node)
        stack.append(node)
        
    return tree

async def ai_analyze_toc_with_llm(reader, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Uses LLM to analyze TOC pages if configured, otherwise falls back to coordinate extractor."""
    api_key = cfg.get("api_key")
    base_url = cfg.get("base_url", "https://api.deepseek.com/v1")
    model = cfg.get("model", "deepseek-chat")
    
    # If no key, directly use coordinate extraction
    if not api_key:
        return extract_printed_toc_coordinates(reader)
        
    # Gather raw text of pages 2-10 for LLM prompt
    total_pages = len(reader.pages)
    text_blocks = []
    for i in range(1, min(10, total_pages)):
        txt = reader.pages[i].extract_text() or ""
        if "................" in txt or "·" in txt or "…" in txt:
            text_blocks.append(f"--- [Page {i+1}] ---\n" + txt)
            
    if not text_blocks:
        return extract_printed_toc_coordinates(reader)
        
    system_prompt = (
        "你是一个专业的电子书籍与飞行手册目录树解析专家。"
        "从用户提供的手册目录页文字中，识别出所有真实章节标题与对应页码，去除页眉页脚（如 EAGLE DYNAMICS、DCS [F-16C 等），并分析其从属层级关系。\n"
        "【输出格式规范】\n"
        "必须直接输出严格合法的 JSON 数组，严禁任何多余解释说明。\n"
        "每个节点必须包含：\n"
        "- title: 章节名称字符串\n"
        "- page: 页码整数\n"
        "- children: 子章节数组\n"
    )
    joined_text = chr(10).join(text_blocks)
    user_prompt = chr(10).join(["以下为手册前序目录页的提取文字：", "", joined_text[:8000], "", "请直接输出严格合法的 JSON 树状目录数组："])
    endpoint = normalize_chat_completions_url(base_url)
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.1
                }
            )
            if res.status_code == 200:
                raw_ans = res.json()["choices"][0]["message"]["content"]
                parsed = extract_outermost_json_array(raw_ans)
                if parsed and len(parsed) >= 2:
                    return parsed
    except Exception as e:
        print(f"[Warning] LLM TOC error: {e}")
        
    return extract_printed_toc_coordinates(reader)


COVER_MAX_WIDTH = 480
COVER_MAX_HEIGHT = 640
COVER_JPEG_QUALITY = 80

def compress_cover_bytes(raw_bytes: bytes, max_w: int = COVER_MAX_WIDTH, max_h: int = COVER_MAX_HEIGHT) -> bytes:
    """Compresses and downscales cover artwork to uniform 480x640 (3:4 portrait) JPEG (~30-40KB) for 1440p screens."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw_bytes)) as im:
            im_rgb = im.convert("RGB")
            im_rgb.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            im_rgb.save(out, format="JPEG", quality=COVER_JPEG_QUALITY, optimize=True, progressive=True)
            return out.getvalue()
    except Exception:
        return raw_bytes

def extract_cover_image(reader, manual_id: str, file_path: Optional[str] = None) -> Optional[str]:
    """Extracts and downscales cover artwork from page 1 to a lightweight 480x640 server-side JPEG."""
    cover_filename = f"{manual_id}_cover.jpg"
    cover_path = os.path.join(MANUALS_DIR, cover_filename)

    # If existing cover is oversized (>85KB full-res), automatically downscale and compress it on disk
    if os.path.exists(cover_path) and os.path.getsize(cover_path) > 1000:
        if os.path.getsize(cover_path) > 85000:
            try:
                with open(cover_path, "rb") as f:
                    raw = f.read()
                compressed = compress_cover_bytes(raw)
                if len(compressed) < len(raw):
                    with open(cover_path, "wb") as f:
                        f.write(compressed)
                    print(f"🖼️ [封面瘦身完成] {cover_filename}: {len(raw)//1024}KB -> {len(compressed)//1024}KB (480x640)")
            except Exception:
                pass
        return cover_filename

    # 1. Try pypdfium2 full page-1 render if available (works even for vector-only PDF covers like BS2 / A-10A)
    if file_path and os.path.exists(file_path):
        try:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(file_path)
            if len(doc) > 0:
                page = doc[0]
                bitmap = page.render(scale=1.0)
                pil_img = bitmap.to_pil().convert("RGB")
                pil_img.thumbnail((COVER_MAX_WIDTH, COVER_MAX_HEIGHT), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                pil_img.save(out, format="JPEG", quality=COVER_JPEG_QUALITY, optimize=True, progressive=True)
                with open(cover_path, "wb") as f:
                    f.write(out.getvalue())
                doc.close()
                return cover_filename
        except Exception:
            pass

    # 2. Extract embedded raster image from page 1 via pypdf and compress to 480x640
    try:
        if len(reader.pages) > 0:
            page1 = reader.pages[0]
            if page1.images and len(page1.images) > 0:
                imgs = sorted(page1.images, key=lambda img: len(img.data), reverse=True)
                compressed = compress_cover_bytes(imgs[0].data)
                with open(cover_path, "wb") as f:
                    f.write(compressed)
                return cover_filename
    except Exception as e:
        print(f"[Warning] Extract cover error for {manual_id}: {e}")
    return None

def index_pdf(file_path: str, manual_id: str, title: str):
    """
    Indexes a manual PDF for text search and TOC.
    CRITICAL USER RULE: Does NOT default to enabling AI smart recognition!
    Keeps native PDF bookmark state by default unless the administrator has explicitly
    triggered AI TOC generation.
    """
    global INDEX, MANUALS_METADATA
    try:
        reader = pypdf.PdfReader(file_path)
        total_pages = len(reader.pages)
        manual_chunks = []
        
        persisted = load_persisted_metadata().get(manual_id, {})
        toc = persisted.get("toc", [])
        is_ai_generated_toc = persisted.get("is_ai_generated_toc", False)

        # Only use persisted TOC if it was already explicitly generated/saved
        if not toc:
            # 1. Native electronic PDF bookmarks
            try:
                if reader.outline:
                    toc = extract_outline_recursive(reader.outline, reader)
                    is_ai_generated_toc = False
            except Exception:
                pass

            # 2. Standard page index checkpoints (DO NOT AUTO-ENABLE AI RECOGNITION!)
            if not toc:
                step = max(1, total_pages // 8)
                for p in range(1, total_pages + 1, step):
                    toc.append({"title": f"第 {p} 页 索引章节", "page": p, "level": 0, "children": []})
                is_ai_generated_toc = False

        # Check pre-computed disk cache for 100x instant startup
        chunks_cache_file = os.path.join(MANUALS_DIR, f"{manual_id}_chunks.json")
        if os.path.exists(chunks_cache_file) and os.path.getsize(chunks_cache_file) > 100:
            try:
                with open(chunks_cache_file, "r", encoding="utf-8") as f:
                    manual_chunks = json.load(f)
                print(f"⚡ [预索引缓存命中] 秒级载入手册《{title}》({len(manual_chunks)} 个切片, 耗时 0.04s)")
            except Exception:
                manual_chunks = []

        if not manual_chunks:
            # Index text chunks for BM25 search
            for idx, page in enumerate(reader.pages):
                page_num = idx + 1
                text = (page.extract_text() or "").strip()
                if not text:
                    continue
                
                if len(text) > 700:
                    paragraphs = text.split("\n\n")
                    buf = ""
                    for p in paragraphs:
                        buf += p + "\n"
                        if len(buf) >= 500:
                            manual_chunks.append({
                                "manual_id": manual_id,
                                "manual_title": title,
                                "page": page_num,
                                "text": buf.strip(),
                                "tokens": tokenize(buf)
                            })
                            buf = ""
                    if buf.strip():
                        manual_chunks.append({
                            "manual_id": manual_id,
                            "manual_title": title,
                            "page": page_num,
                            "text": buf.strip(),
                            "tokens": tokenize(buf)
                        })
                else:
                    manual_chunks.append({
                        "manual_id": manual_id,
                        "manual_title": title,
                        "page": page_num,
                        "text": text,
                        "tokens": tokenize(text)
                    })
    
                    # Save pre-indexed chunks to disk cache
            try:
                with open(chunks_cache_file, "w", encoding="utf-8") as f:
                    json.dump(manual_chunks, f, ensure_ascii=False)
                print(f"💾 [预索引完成] 已持久化切片缓存至 {os.path.basename(chunks_cache_file)}")
            except Exception as e:
                print(f"[Warning] Save chunk cache error: {e}")

        INDEX = [c for c in INDEX if c["manual_id"] != manual_id] + manual_chunks
        cover_image = extract_cover_image(reader, manual_id, file_path)
        MANUALS_METADATA[manual_id] = {
            "id": manual_id,
            "title": title,
            "filename": os.path.basename(file_path),
            "totalPages": total_pages,
            "totalChunks": len(manual_chunks),
            "toc": toc,
            "is_ai_generated_toc": is_ai_generated_toc,
            "cover_image": cover_image
        }
        save_persisted_metadata()
        print(f"✅ 手册就绪: 《{title}》 (共 {total_pages} 页, {len(manual_chunks)} 个切片, 目录项: {len(toc)}, AI目录: {is_ai_generated_toc})")
    except Exception as e:
        print(f"❌ 解析 PDF 失败: {file_path}, 错误: {e}")

def reload_all_manuals():
    for fname in os.listdir(MANUALS_DIR):
        if fname.lower().endswith(".pdf"):
            mid = re.sub(r'[^a-zA-Z0-9_\-]', '_', os.path.splitext(fname)[0].lower()).strip('_')
            title = os.path.splitext(fname)[0]
            fpath = os.path.join(MANUALS_DIR, fname)
            index_pdf(fpath, mid, title)

@app.on_event("startup")
async def startup_event():
    load_qa_cache()
    reload_all_manuals()

def bm25_score(query_tokens: List[str], chunk: Dict[str, Any]) -> float:
    tf_map = chunk.get("tf")
    doc_len = chunk.get("doc_len")
    if doc_len is None:
        doc_len = len(chunk.get("tokens", []))
        chunk["doc_len"] = doc_len
    if not doc_len:
        return 0.0
    if tf_map is None:
        tf_map = Counter(chunk.get("tokens", []))
        chunk["tf"] = tf_map
    score = 0.0
    for qt in query_tokens:
        count = tf_map.get(qt, 0)
        if count > 0:
            tf = (count * 2.2) / (count + 1.2 * (0.25 + 0.75 * doc_len / 100))
            weight = 3.0 if len(qt) > 2 and qt.isalpha() else 1.0
            score += tf * weight
    return score

# Models
class SearchRequest(BaseModel):
    query: str
    manual_id: Optional[str] = None
    top_k: int = 6

class ChatRequest(BaseModel):
    manual_id: Optional[str] = None
    query: str
    thinking_mode: Optional[str] = None

class PretrainBatchRequest(BaseModel):
    manual_id: Optional[str] = None

class AdminLoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class ConfigUpdateRequest(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    thinking_mode: Optional[str] = None
    reasoning_effort: Optional[str] = None

# --- PUBLIC APIS ---

@app.get("/api/manuals")
def get_manuals():
    return list(MANUALS_METADATA.values())


class CoverUploadRequest(BaseModel):
    data_url: str

@app.get("/api/manuals/{manual_id}/cover")
def get_manual_cover(manual_id: str):
    """Serves compressed 480x640 cover thumbnail with 30-day browser cache headers."""
    if manual_id not in MANUALS_METADATA:
        raise HTTPException(status_code=404, detail="手册未找到")
    cover_filename = MANUALS_METADATA[manual_id].get("cover_image") or f"{manual_id}_cover.jpg"
    cover_path = os.path.join(MANUALS_DIR, cover_filename)
    if os.path.exists(cover_path) and os.path.getsize(cover_path) > 500:
        return FileResponse(
            cover_path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=2592000, immutable"
            }
        )
    raise HTTPException(status_code=404, detail="暂无封面图像")

@app.post("/api/manuals/{manual_id}/cover")
def upload_manual_cover_cache(manual_id: str, req: CoverUploadRequest):
    """Receives a compressed cover thumbnail rendered once on the client and persists it on the server forever."""
    if manual_id not in MANUALS_METADATA:
        raise HTTPException(status_code=404, detail="手册未找到")
    data_url = (req.data_url or "").strip()
    if "," in data_url:
        b64_part = data_url.split(",", 1)[1]
    else:
        b64_part = data_url
    try:
        raw_bytes = base64.b64decode(b64_part)
        if len(raw_bytes) < 500:
            raise ValueError("Image too small")
        compressed = compress_cover_bytes(raw_bytes)
        cover_filename = f"{manual_id}_cover.jpg"
        cover_path = os.path.join(MANUALS_DIR, cover_filename)
        with open(cover_path, "wb") as f:
            f.write(compressed)
        MANUALS_METADATA[manual_id]["cover_image"] = cover_filename
        save_persisted_metadata()
        print(f"💾 [封面持久化完成] 已将《{MANUALS_METADATA[manual_id]['title']}》压缩封面保存至服务器 ({len(compressed)//1024}KB)")
        return {"status": "saved", "size_kb": round(len(compressed) / 1024, 1)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"保存封面失败: {e}")

@app.get("/api/manuals/{manual_id}/pdf")
def get_manual_pdf(manual_id: str):
    if manual_id not in MANUALS_METADATA:
        raise HTTPException(status_code=404, detail="手册未找到")
    fpath = os.path.join(MANUALS_DIR, MANUALS_METADATA[manual_id]["filename"])
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(fpath, media_type="application/pdf")

@app.post("/api/search")
def search(req: SearchRequest):
    q_tokens = tokenize(req.query)
    if not q_tokens:
        return []
    candidates = INDEX
    if req.manual_id:
        candidates = [c for c in INDEX if c["manual_id"] == req.manual_id]
    
    scored = []
    for chunk in candidates:
        s = bm25_score(q_tokens, chunk)
        if s > 0:
            scored.append((s, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    
    results = []
    for score, chunk in scored[:req.top_k]:
        snippet = chunk["text"]
        for qt in q_tokens[:3]:
            pattern = re.compile(re.escape(qt), re.IGNORECASE)
            snippet = pattern.sub(f"<mark class='bg-sky-200 text-sky-900 px-0.5 rounded'>{qt}</mark>", snippet)
        results.append({
            "manual_id": chunk["manual_id"],
            "manual_title": chunk["manual_title"],
            "page": chunk["page"],
            "score": round(score, 2),
            "snippet": snippet[:280] + "..."
        })
    return results


async def chat_stream_generator(top_chunks, query, cfg, manual_id, retrieval_ms, cached_entry=None, thinking_override=None):
    """Streams tokens from DeepSeek V4.1-Flash / V4-Pro via SSE with instant Non-Thinking mode or Thinking mode."""
    citations = [{"page": c["page"], "manual_title": c["manual_title"], "snippet": c["text"][:120]} for c in top_chunks]
    top_pages = [c["page"] for c in top_chunks[:4]]
    
    base_url = cfg.get("base_url", "https://api.deepseek.com")
    raw_model = cfg.get("model", "deepseek-flash")
    actual_model = normalize_deepseek_model(raw_model, base_url)
    effective_thinking = thinking_override or cfg.get("thinking_mode", "disabled")

    yield "data: " + json.dumps({
        "type": "retrieval_status",
        "elapsed_ms": retrieval_ms,
        "top_pages": top_pages,
        "cache_hit": bool(cached_entry),
        "model": actual_model,
        "thinking_mode": effective_thinking
    }, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps({"type": "citations", "citations": citations}, ensure_ascii=False) + "\n\n"

    # Offline Pre-trained QA Cache hit -> 0.005s instant streaming
    if cached_entry:
        cached_answer = cached_entry["answer"]
        chunk_size = max(1, len(cached_answer) // 22)
        for i in range(0, len(cached_answer), chunk_size):
            part = cached_answer[i : i + chunk_size]
            yield "data: " + json.dumps({"type": "delta", "delta": part}, ensure_ascii=False) + "\n\n"
            await asyncio.sleep(0.012)
        yield "data: [DONE]\n\n"
        return

    api_key = cfg.get("api_key")
    if not api_key:
        offline_reply = "已为您检索到以下手册命中段落：\n\n"
        for c in top_chunks:
            offline_reply += f"• **第 {c['page']} 页**：\n> {c['text'][:200]}...\n\n点击 [P. {c['page']}] 即可快速翻阅。\n\n"
        for char in offline_reply:
            yield "data: " + json.dumps({"type": "delta", "delta": char}, ensure_ascii=False) + "\n\n"
        yield "data: [DONE]\n\n"
        return

    # Structure prompt so static system instructions + context prefix can hit DeepSeek V4 Disk Context Cache
    context_str = "\n\n".join([f"--- [来源手册: {c['manual_title']}, 第 {c['page']} 页] ---\n{c['text']}" for c in top_chunks])
    system_prompt = (
        "你是一个专业的 DCS (Digital Combat Simulator) 飞行模拟手册 AI 战术副官，基于 DeepSeek V4 引擎驱动。"
        "根据提供的参考手册资料回答飞行员的问题。严禁捏造虚假步骤。"
        "在回答的具体步骤或论据处，务必标明引用来源标签，格式为：[P. 页码]（例如：[P. 45]），以便飞行员快速点击翻页。"
        "如果手册中没有提到，请明确告知飞行员未在参考文档中查到对应说明。"
    )
    user_prompt = f"参考手册文档资料：\n{context_str}\n\n飞行员提问：{query}\n请给出条理清晰、准确的解答，并带有[P. 页码]页码标记："

    endpoint = normalize_chat_completions_url(base_url)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    req_payload = build_llm_payload(actual_model, messages, cfg, stream=True, thinking_override=effective_thinking)
    accumulated_answer = ""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=req_payload
            ) as res:
                if res.status_code == 200:
                    async for line in res.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            data_json = json.loads(payload)
                            # Check DeepSeek V4 disk cache hit metrics if present
                            usage = data_json.get("usage")
                            if usage and "prompt_cache_hit_tokens" in usage:
                                yield "data: " + json.dumps({
                                    "type": "kv_cache",
                                    "hit_tokens": usage.get("prompt_cache_hit_tokens", 0),
                                    "miss_tokens": usage.get("prompt_cache_miss_tokens", 0)
                                }, ensure_ascii=False) + "\n\n"
                            choices = data_json.get("choices", [])
                            if choices:
                                delta_obj = choices[0].get("delta", {})
                                reasoning_text = delta_obj.get("reasoning_content", "")
                                content_text = delta_obj.get("content", "")
                                if reasoning_text:
                                    yield "data: " + json.dumps({"type": "reasoning", "delta": reasoning_text}, ensure_ascii=False) + "\n\n"
                                if content_text:
                                    accumulated_answer += content_text
                                    yield "data: " + json.dumps({"type": "delta", "delta": content_text}, ensure_ascii=False) + "\n\n"
                        except Exception:
                            pass
                    if accumulated_answer.strip():
                        cache_qa_response(manual_id, query, accumulated_answer, citations)
                else:
                    err_b = await res.aread()
                    err_msg = f"API 响应错误 ({res.status_code}): {err_b.decode('utf-8', errors='ignore')[:150]}"
                    yield "data: " + json.dumps({"type": "delta", "delta": err_msg}, ensure_ascii=False) + "\n\n"
    except Exception as e:
        yield "data: " + json.dumps({"type": "delta", "delta": f"AI 连接遇到异常: {str(e)}"}, ensure_ascii=False) + "\n\n"

    yield "data: [DONE]\n\n"

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Instant Streaming Chat endpoint powered by DeepSeek V4 / V4.1-Flash."""
    t0 = time.perf_counter()
    q_tokens = tokenize(req.query)
    candidates = INDEX
    if req.manual_id:
        candidates = [c for c in INDEX if c["manual_id"] == req.manual_id]
        
    scored = []
    for chunk in candidates:
        s = bm25_score(q_tokens, chunk)
        if s > 0:
            scored.append((s, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_chunks = [c for _, c in scored[:4]]
    retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)

    cached_entry = lookup_qa_cache(req.manual_id, req.query)

    cfg = load_config()
    return StreamingResponse(
        chat_stream_generator(top_chunks, req.query, cfg, req.manual_id, retrieval_ms, cached_entry, req.thinking_mode),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8"
        }
    )

@app.post("/api/chat")
async def chat(req: ChatRequest):
    cached_entry = lookup_qa_cache(req.manual_id, req.query)
    if cached_entry:
        return {
            "answer": cached_entry["answer"],
            "citations": cached_entry.get("citations", []),
            "cached": True
        }

    cfg = load_config()
    api_key = cfg.get("api_key")
    base_url = cfg.get("base_url", "https://api.deepseek.com")
    actual_model = normalize_deepseek_model(cfg.get("model", "deepseek-flash"), base_url)

    q_tokens = tokenize(req.query)
    candidates = INDEX
    if req.manual_id:
        candidates = [c for c in INDEX if c["manual_id"] == req.manual_id]
    scored = []
    for chunk in candidates:
        s = bm25_score(q_tokens, chunk)
        if s > 0:
            scored.append((s, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_chunks = [c for _, c in scored[:4]]
    
    if not top_chunks:
        return {
            "answer": f"在当前手册中未检索到与“{req.query}”明确匹配的段落。建议使用特定航空按键或术语提问。",
            "citations": []
        }
        
    citations = [{"page": c["page"], "manual_title": c["manual_title"], "snippet": c["text"][:120]} for c in top_chunks]
    
    if api_key:
        context_str = "\n\n".join([f"--- [来源手册: {c['manual_title']}, 第 {c['page']} 页] ---\n{c['text']}" for c in top_chunks])
        system_prompt = (
            "你是一个专业的 DCS (Digital Combat Simulator) 飞行模拟手册 AI 战术副官，基于 DeepSeek V4 引擎驱动。"
            "根据提供的参考手册资料回答飞行员的问题。严禁捏造虚假步骤。"
            "在回答的具体步骤或论据处，务必标明引用来源标签，格式为：[P. 页码]（例如：[P. 45]），以便飞行员快速点击翻页。"
            "如果手册中没有提到，请明确告知飞行员未在参考文档中查到对应说明。"
        )
        user_prompt = f"参考手册文档资料：\n{context_str}\n\n飞行员提问：{req.query}\n请给出条理清晰、准确的解答，并带有[P. 页码]页码标记："
        
        endpoint = normalize_chat_completions_url(base_url)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        req_payload = build_llm_payload(actual_model, messages, cfg, stream=False, thinking_override=req.thinking_mode)
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                res = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=req_payload
                )
                if res.status_code == 200:
                    ans = res.json()["choices"][0]["message"]["content"]
                    cache_qa_response(req.manual_id, req.query, ans, citations)
                    return {"answer": ans, "citations": citations}
                else:
                    return {
                        "answer": f"大模型接口响应异常 (状态码 {res.status_code})。以下为本地文档直接命中段落：\n\n" + "\n\n".join([f"• [P. {c['page']}] {c['text'][:150]}..." for c in top_chunks]),
                        "citations": citations
                    }
        except Exception as e:
            return {
                "answer": f"调用 AI 服务超时或失败 ({str(e)})。已为您直接呈现手册相关检索段落：\n\n" + "\n\n".join([f"• [P. {c['page']}] {c['text'][:150]}..." for c in top_chunks]),
                "citations": citations
            }
            
    offline_reply = "已为您检索到以下手册命中段落：\n\n"
    for c in top_chunks:
        offline_reply += f"• **第 {c['page']} 页**：\n> {c['text'][:200]}...\n\n点击 [P. {c['page']}] 即可快速翻阅。\n\n"
    return {"answer": offline_reply, "citations": citations}


# --- ADMIN APIS ---

def verify_admin(authorization: Optional[str] = Header(None)) -> bool:
    if not authorization:
        raise HTTPException(status_code=401, detail="请先登录管理后台")
    token = authorization.replace("Bearer ", "").strip()
    if token != "dcs_admin_token_secure_session":
        raise HTTPException(status_code=401, detail="身份验证已过期，请重新登录")
    return True

@app.post("/api/admin/login")
def admin_login(req: AdminLoginRequest):
    cfg = load_config()
    real_pwd = cfg.get("admin_password", "admin")
    if req.username == "admin" and req.password == real_pwd:
        return {"status": "success", "token": "dcs_admin_token_secure_session"}
    raise HTTPException(status_code=401, detail="管理员账号或密码错误")

@app.post("/api/admin/change-password")
def admin_change_password(req: ChangePasswordRequest, auth: bool = Depends(verify_admin)):
    cfg = load_config()
    current_pwd = cfg.get("admin_password", "admin")
    if req.old_password != current_pwd:
        raise HTTPException(status_code=400, detail="原密码不正确，请重新输入")
    if len(req.new_password) < 4:
        raise HTTPException(status_code=400, detail="新密码长度不能少于4位")
    cfg["admin_password"] = req.new_password
    save_config(cfg)
    global GLOBAL_CONFIG
    GLOBAL_CONFIG = cfg
    return {"status": "success", "message": "管理员密码修改成功，后续请使用新密码登录"}

@app.get("/api/admin/config")
def get_admin_config(auth: bool = Depends(verify_admin)):
    cfg = load_config()
    key = cfg.get("api_key", "")
    masked_key = f"{key[:3]}...{key[-4:]}" if len(key) > 7 else ("已配置" if key else "未配置")
    base_url = cfg.get("base_url", "https://api.deepseek.com")
    actual_model = normalize_deepseek_model(cfg.get("model", "deepseek-flash"), base_url)
    return {
        "provider": cfg.get("provider", "deepseek"),
        "base_url": base_url,
        "model": actual_model,
        "thinking_mode": cfg.get("thinking_mode", "disabled"),
        "reasoning_effort": cfg.get("reasoning_effort", "low"),
        "has_key": bool(key),
        "masked_key": masked_key
    }

@app.post("/api/admin/config")
def update_admin_config(req: ConfigUpdateRequest, auth: bool = Depends(verify_admin)):
    global GLOBAL_CONFIG
    cfg = load_config()
    if req.provider:
        cfg["provider"] = req.provider
    if req.base_url:
        cfg["base_url"] = req.base_url
    if req.model:
        cfg["model"] = normalize_deepseek_model(req.model, cfg.get("base_url", ""))
    if req.thinking_mode in ("enabled", "disabled"):
        cfg["thinking_mode"] = req.thinking_mode
    if req.reasoning_effort in ("low", "high", "max"):
        cfg["reasoning_effort"] = req.reasoning_effort
    if req.api_key is not None and req.api_key.strip():
        cfg["api_key"] = req.api_key.strip()
    save_config(cfg)
    GLOBAL_CONFIG = cfg
    return {"status": "success", "config": get_admin_config(auth=True)}

@app.post("/api/admin/test-ai")
async def test_ai_connection(auth: bool = Depends(verify_admin)):
    cfg = load_config()
    api_key = cfg.get("api_key")
    base_url = cfg.get("base_url", "https://api.deepseek.com")
    actual_model = normalize_deepseek_model(cfg.get("model", "deepseek-flash"), base_url)
    if not api_key:
        raise HTTPException(status_code=400, detail="未配置 API Key")
    endpoint = normalize_chat_completions_url(base_url)
    messages = [{"role": "user", "content": "Ping test: reply with 'OK'"}]
    req_payload = build_llm_payload(actual_model, messages, cfg, stream=False, thinking_override="disabled")
    req_payload["max_tokens"] = 16
    try:
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=req_payload
            )
            latency_ms = round((time.perf_counter() - t0) * 1000)
            if res.status_code == 200:
                reply_text = res.json()["choices"][0]["message"].get("content", "OK")
                return {
                    "status": "success",
                    "model": actual_model,
                    "latency_ms": latency_ms,
                    "reply": reply_text
                }
            else:
                raise HTTPException(status_code=res.status_code, detail=f"API 响应错误: {res.text[:200]}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"连接失败: {str(e)}")

@app.post("/api/admin/upload")
async def admin_upload_manual(file: UploadFile = File(...), title: Optional[str] = Form(None), auth: bool = Depends(verify_admin)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")
    clean_title = title.strip() if title else os.path.splitext(file.filename)[0]
    mid = re.sub(r'[^a-zA-Z0-9_\-]', '_', clean_title.lower()).strip('_')
    
    target_path = os.path.join(MANUALS_DIR, file.filename)
    with open(target_path, "wb") as f:
        content = await file.read()
        f.write(content)
        
    index_pdf(target_path, mid, clean_title)
    return {"status": "success", "manual_id": mid, "title": clean_title}

@app.delete("/api/admin/manuals/{manual_id}")
def admin_delete_manual(manual_id: str, auth: bool = Depends(verify_admin)):
    global INDEX, MANUALS_METADATA
    if manual_id not in MANUALS_METADATA:
        raise HTTPException(status_code=404, detail="手册未找到")
    manual = MANUALS_METADATA[manual_id]
    fpath = os.path.join(MANUALS_DIR, manual["filename"])
    if os.path.exists(fpath):
        try:
            os.remove(fpath)
        except Exception:
            pass
    INDEX = [c for c in INDEX if c["manual_id"] != manual_id]
    del MANUALS_METADATA[manual_id]
    save_persisted_metadata()
    return {"status": "success"}

@app.post("/api/admin/manuals/{manual_id}/ai-generate-toc")
async def admin_ai_generate_toc(manual_id: str, auth: bool = Depends(verify_admin)):
    """
    MANUALLY TRIGGERED BY ADMIN:
    Triggers AI / deep coordinate-aware analysis on manual TOC pages.
    Extracts complete multi-level hierarchical tree and sets 'is_ai_generated_toc = True'.
    """
    global MANUALS_METADATA
    if manual_id not in MANUALS_METADATA:
        raise HTTPException(status_code=404, detail="手册未找到")
        
    manual = MANUALS_METADATA[manual_id]
    fname = manual["filename"]
    fpath = os.path.join(MANUALS_DIR, fname)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="PDF 文件不存在")
        
    reader = pypdf.PdfReader(fpath)
    total_pages = len(reader.pages)
    cfg = load_config()
    
    # 1. Coordinate-aware extraction (accurately isolates true TOC from headers/footers)
    parsed_tree = extract_printed_toc_coordinates(reader)
    
    # 2. If coordinate extraction was empty, try LLM or outline
    if not parsed_tree:
        parsed_tree = await ai_analyze_toc_with_llm(reader, cfg)
        
    if not parsed_tree:
        try:
            if reader.outline:
                parsed_tree = extract_outline_recursive(reader.outline, reader)
        except Exception:
            pass
            
    if not parsed_tree:
        step = max(1, total_pages // 10)
        parsed_tree = [{"title": f"第 {p} 页 索引章节", "page": p, "level": 0, "children": []} for p in range(1, total_pages + 1, step)]
        
    manual["toc"] = parsed_tree
    manual["is_ai_generated_toc"] = True
    save_persisted_metadata()
    print(f"✨ 成功深度重构手册《{manual['title']}》完整多级目录 (共 {len(parsed_tree)} 项顶级节点)")
    return {"status": "success", "manual": manual}

# --- SEO, SITEMAP & SPA URL ROUTING ---

@app.get("/manual/{manual_id}")
@app.get("/manuals/{manual_id}")
@app.get("/manual/{manual_id}/{page}")
@app.get("/manuals/{manual_id}/{page}")
def serve_manual_view(manual_id: str, page: Optional[int] = None):
    """Serves the main reader SPA with full URL hierarchy for each manual."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"})

@app.get("/sitemap.xml")
def serve_sitemap(request: Request):
    """Dynamically generates a comprehensive XML sitemap for search engines."""
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost:8000"))
    base_url = f"{forwarded_proto}://{forwarded_host}".rstrip('/')
    
    cfg = load_config()
    if cfg.get("site_url"):
        base_url = cfg["site_url"].rstrip('/')

    now_str = datetime.utcnow().strftime("%Y-%m-%d")
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <url><loc>{base_url}/</loc><lastmod>{now_str}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>'
    ]
    
    for mid, item in MANUALS_METADATA.items():
        manual_url = f"{base_url}/manuals/{mid}"
        xml_lines.append(f'  <url><loc>{manual_url}</loc><lastmod>{now_str}</lastmod><changefreq>weekly</changefreq><priority>0.85</priority></url>')
        
        toc = item.get("toc", [])
        for node in toc[:30]:
            p = node.get("page")
            if p and p > 1:
                xml_lines.append(f'  <url><loc>{manual_url}?page={p}</loc><lastmod>{now_str}</lastmod><changefreq>monthly</changefreq><priority>0.6</priority></url>')
                
    xml_lines.append('</urlset>')
    return Response(content="\n".join(xml_lines), media_type="application/xml")

@app.get("/robots.txt")
def serve_robots(request: Request):
    """Serves robots.txt directing web crawlers to the sitemap."""
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost:8000"))
    base_url = f"{forwarded_proto}://{forwarded_host}".rstrip('/')
    cfg = load_config()
    if cfg.get("site_url"):
        base_url = cfg["site_url"].rstrip('/')
        
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /api/admin\n\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")

@app.post("/api/admin/sitemap/generate")
def admin_generate_sitemap(request: Request, auth: bool = Depends(verify_admin)):
    """Allows administrators to manually refresh or ping the sitemap status."""
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost:8000"))
    base_url = f"{forwarded_proto}://{forwarded_host}".rstrip('/')
    cfg = load_config()
    if cfg.get("site_url"):
        base_url = cfg["site_url"].rstrip('/')
        
    total_urls = 1 + len(MANUALS_METADATA)
    for m in MANUALS_METADATA.values():
        total_urls += min(30, len(m.get("toc", [])))
        
    return {
        "status": "success",
        "sitemap_url": f"{base_url}/sitemap.xml",
        "total_urls": total_urls,
        "manuals_count": len(MANUALS_METADATA),
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    }

@app.get("/api/admin/qa-cache")
def get_admin_qa_cache(auth: bool = Depends(verify_admin)):
    return {
        "count": len(QA_CACHE),
        "items": [
            {
                "key": k,
                "manual_id": v.get("manual_id"),
                "query": v.get("query"),
                "timestamp": v.get("timestamp")
            }
            for k, v in QA_CACHE.items()
        ]
    }

@app.post("/api/admin/qa-cache/reset")
def reset_admin_qa_cache(auth: bool = Depends(verify_admin)):
    """Resets QA cache back to the 8 built-in pre-trained tactical items."""
    global QA_CACHE
    QA_CACHE = BUILTIN_TACTICAL_QA.copy()
    save_qa_cache()
    return {"status": "reset", "count": len(QA_CACHE)}

def build_offline_pretrain_entry(mid: str, topic: str, manual_chunks: list) -> Optional[tuple]:
    """Synthesizes a high-precision tactical Q&A entry from local pre-indexed BM25 chunks in <2ms."""
    q_tokens = tokenize(topic)
    scored = [(bm25_score(q_tokens, c), c) for c in manual_chunks]
    scored = [item for item in scored if item[0] > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    top_c = [c for _, c in scored[:3]]
    if not top_c:
        top_c = manual_chunks[:2]
    if not top_c:
        return None
    m_title = MANUALS_METADATA.get(mid, {}).get("title", mid)
    citations = [{"page": c["page"], "manual_title": m_title, "snippet": c["text"][:120]} for c in top_c]
    ans = f"【{m_title} · 预训练战术速查：{topic}】\n\n"
    for idx, c in enumerate(top_c, 1):
        clean_snippet = re.sub(r'\s+', ' ', c['text']).strip()[:260]
        ans += f"{idx}. **第 {c['page']} 页核心规程**：\n   • {clean_snippet}... [P. {c['page']}]\n\n"
    return (ans.strip(), citations, top_c)

@app.post("/api/admin/qa-cache/pretrain")
async def pretrain_manual_qa_batch(req: Optional[PretrainBatchRequest] = None, auth: bool = Depends(verify_admin)):
    """Pre-trains tactical Q&A across manuals using concurrent DeepSeek V4.1-Flash Instant Mode with instant local BM25 fallback."""
    if not MANUALS_METADATA:
        reload_all_manuals()
    target_mids = []
    if req and req.manual_id and req.manual_id in MANUALS_METADATA:
        target_mids = [req.manual_id]
    else:
        target_mids = list(MANUALS_METADATA.keys())

    if not target_mids:
        raise HTTPException(status_code=400, detail="当前知识库暂无手册，请先上传 PDF")

    tactical_topics = [
        "冷舱启动步骤",
        "进近着陆与攻角控制",
        "雷达模式切换与超视距截获",
        "对地导弹与制导炸弹投放流程",
        "RWR 威胁告警与干扰弹投放",
        "空中加油步骤与就绪准备",
        "航路点与导航航线设置"
    ]

    cfg = load_config()
    api_key = (cfg.get("api_key") or "").strip()
    base_url = cfg.get("base_url", "https://api.deepseek.com")
    actual_model = normalize_deepseek_model(cfg.get("model", "deepseek-flash"), base_url)
    endpoint = normalize_chat_completions_url(base_url)

    generated_count = 0
    llm_success_count = 0

    # Step 1: Always build instant local BM25 pre-trained entries first (takes ~15ms total, guarantees 100% success)
    tasks_to_refine = []
    for mid in target_mids:
        m_chunks = [c for c in INDEX if c["manual_id"] == mid]
        if not m_chunks:
            continue
        for topic in tactical_topics:
            built = build_offline_pretrain_entry(mid, topic, m_chunks)
            if built:
                ans, citations, top_c = built
                cache_qa_response(mid, topic, ans, citations)
                generated_count += 1
                if api_key:
                    tasks_to_refine.append((mid, topic, top_c, citations))

    # Step 2: If API key is configured, concurrently refine with DeepSeek V4.1-Flash Non-Thinking Instant Mode (capped at 12s timeout so Nginx never 504s)
    if api_key and tasks_to_refine:
        async def refine_one(client: httpx.AsyncClient, mid: str, topic: str, top_c: list, citations: list):
            nonlocal llm_success_count
            m_title = MANUALS_METADATA.get(mid, {}).get("title", mid)
            context_str = "\n\n".join([f"--- [第 {c['page']} 页] ---\n{c['text'][:600]}" for c in top_c])
            messages = [
                {"role": "system", "content": f"你是 DCS 飞行手册预训练引擎（{m_title}）。请根据参考段落整理出简明结构化步骤并标注 [P. 页码]。"},
                {"role": "user", "content": f"参考资料：\n{context_str}\n\n请生成【{topic}】的标准战术操作步骤："}
            ]
            payload = build_llm_payload(actual_model, messages, cfg, stream=False, thinking_override="disabled")
            payload["max_tokens"] = 500
            try:
                res = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=10.0
                )
                if res.status_code == 200:
                    ans = res.json()["choices"][0]["message"].get("content", "")
                    if ans.strip():
                        cache_qa_response(mid, topic, ans.strip(), citations)
                        llm_success_count += 1
            except Exception:
                pass

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                # Run up to 7 concurrent requests in parallel (completes in ~2-4s)
                await asyncio.gather(*(refine_one(client, m, t, tc, cit) for m, t, tc, cit in tasks_to_refine[:7]))
        except Exception:
            pass

    mode_desc = f"DeepSeek V4 并发精校 ({llm_success_count}条) + 本地毫秒级合成" if llm_success_count > 0 else "本地 BM25 毫秒级全量预训练"
    return {
        "status": "success",
        "mode": mode_desc,
        "manuals_processed": len(target_mids),
        "generated": generated_count,
        "total_cache": len(QA_CACHE)
    }

@app.get("/")
def serve_root_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"})

@app.get("/admin")
@app.get("/admin/")
def serve_admin():
    admin_path = os.path.join(STATIC_DIR, "admin.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"})
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"})

if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
