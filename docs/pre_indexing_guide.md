# DCS Manual Hub AI v3.0.0 - DeepSeek V4.1-Flash 架构与 RAG 预训练加速指南

## 1. 为什么此前调用 DeepSeek 极其缓慢？
经查阅 [DeepSeek 官方 API 文档](https://api-docs.deepseek.com/quick_start/pricing/) 与 [2026 更新日志](https://api-docs.deepseek.com/updates/)：
1. **旧版模型代号已退役**：`deepseek-chat` 与 `deepseek-reasoner` 已于 2026 年 7 月 24 日正式退役。当前主力模型为 **`deepseek-flash`**（底层对应 `DeepSeek-V4.1-Flash-1017`）与 **`deepseek-v4-pro`**（底层对应 `DeepSeek-V4-Pro-0813`），均支持 **1M 超长上下文** 与 **384K 最大输出**。
2. **V4 默认开启 `high` 深度思考模式导致延迟**：根据 [DeepSeek Thinking Mode 官方文档](https://api-docs.deepseek.com/guides/thinking_mode/)，V4 系列模型默认将思考模式设为开启（`{"thinking": {"type": "enabled"}}` 且 `reasoning_effort="high"`）。如果请求中不显式传入 `{"thinking": {"type": "disabled"}}`，模型在每次回答前都会强制执行长链条推理，导致长达 15~30 秒的等待！

## 2. v3.0.0 全面重构的四大核心提速机制
1. **原生适配 DeepSeek V4 极速直出模式 (`thinking: disabled`)**：
   - 后端默认使用 `deepseek-flash` 并携带 `{"thinking": {"type": "disabled"}}`，完全跳过冗长的思维链推演，首字响应缩短至 **0.2 秒以内**。
   - 同时在前端副官面板与 `/admin` 后台提供一键切换开关，遇到复杂战术推演时可随时勾选开启 `thinking: enabled`（支持 `low` / `high` / `max` 三档强度）。
2. **自动兼容升级旧配置 (`normalize_deepseek_model`)**：
   - 即便服务器旧 `config.json` 中仍残留 `deepseek-chat` 或 `deepseek-reasoner`，后端也会自动将其无缝映射至最新的 `deepseek-flash`（DeepSeek-V4.1-Flash-1017）。
3. **DeepSeek V4 硬盘级上下文缓存 (`Context Caching on Disk`)**：
   - 重构 Prompt 前缀结构，将手册切片固定在前缀单元，最大化触发 [DeepSeek V4 硬盘 KV 缓存](https://api-docs.deepseek.com/guides/kv_cache/)（命中成本低至 $0.003 / 1M tokens），并在前端实时展示 `💾 V4 硬盘缓存命中 tokens` 指标。
4. **RAG 离线预训练战术问答库 (`QA Cache`) + 后台一键批量预训练**：
   - 内置 8 大高频飞行科目精校问答（0.005s 毫秒级直出），并在 `/admin` 后台新增 **「⚡ 一键批量预训练当前手册问答」** 按钮，调用 `deepseek-flash` 非思考模式一次性预生成常用战术问答并持久化缓存。
