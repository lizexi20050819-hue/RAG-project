## 项目简介

这是一个面向**服装搭配/尺码/洗涤养护**等场景的 RAG（Retrieval-Augmented Generation，检索增强生成）小项目：

- **知识入库**：上传文档 → 文本解析/切分 → 向量化 → 写入 Chroma 向量库（本地持久化）
- **智能问答**：用户提问 → 向量检索 Top-K 参考资料 → 结合历史对话 + 参考资料 → 通义千问生成回答

前端使用 **Streamlit**，后端使用 **LangChain + Chroma + DashScope（通义）**。

---

## 已实现功能

### 1) 知识库管理（上传/查看/删除）

- **管理员登录**（默认账号密码见下文配置）
- **多文件上传**（支持 `TXT / PDF / DOCX / Markdown`）
- **预览内容**（超长截断显示）
- **批量入库进度条**
- **去重策略**
  - 同名文件：`[跳过]已存在同名文件`
  - 同内容：按 MD5 指纹去重，`[跳过]内容已经存在知识库中`
- **已入库文档列表**
  - 展示 source、chunk 数、创建时间
  - 支持二次确认后删除，并同步清理 `md5.text`

### 2) 智能问答（RAG）

- **向量检索**：Chroma Top-K（默认 k=2）
- **相似度过滤**：用于前端展示引用来源（默认阈值 0.3）
- **多轮对话**：保留最近 N 轮历史（默认 5 轮）
- **参考来源展示**：回答后可展开查看引用片段（来源文件 + 片段内容）
- **对话持久化**：保存到 `chat_history.json`，刷新页面不丢

---

## 项目结构

主要代码位于 `1/` 目录：

- `1/app.py`：Streamlit 统一入口（推荐用它启动）
- `1/app_main.py`：前端页面（知识库更新 + 智能问答两个 Tab）
- `1/knowledge_base.py`：知识入库（解析/切分/去重/入库/文档列表/删除）
- `1/vector_stores.py`：向量库封装（Chroma + retriever）
- `1/rag.py`：RAG 链（历史对话 + 参考资料 + LLM）
- `1/file_history_store.py`：对话历史 JSON 读写
- `1/config_data.py`：项目配置（向量库路径、模型名、管理员账号等）

数据文件：

- `1/chroma_db/`：Chroma 向量库持久化目录（本地）
- `1/md5.text`：已入库内容的 MD5 指纹记录（用于去重）
- `1/chat_history.json`：对话历史（本地持久化）
- `1/data/`：示例知识文件（txt）

---

## 环境准备

### 1) Python 版本

建议使用 **Python 3.11**（本项目依赖在 3.11 下验证过）。

如果你电脑上有多个 Python（例如 3.14），请显式指定 3.11 运行，避免出现：

- `No module named streamlit`
- 依赖装到了另一个 Python 里导致运行找不到包

### 2) 安装依赖

在项目根目录执行：

```bash
pip install -r requirements.txt
```

若 pip 受 SOCKS 代理影响（出现 `Missing dependencies for SOCKS support`），可先临时清空代理环境变量再安装：

```powershell
$env:HTTP_PROXY=""; $env:HTTPS_PROXY=""; $env:ALL_PROXY=""
$env:http_proxy=""; $env:https_proxy=""; $env:all_proxy=""
pip install -r requirements.txt
```

### 3) 配置 DashScope API Key

需要在环境变量中配置 `DASHSCOPE_API_KEY`（通义的 API Key），例如：

```powershell
$env:DASHSCOPE_API_KEY="你的key"
```

（也可以在系统环境变量中永久设置。）

---

## 启动方式

### 方式 A：启动统一 Web 应用（推荐）

进入 `1/` 目录后运行：

```powershell
cd .\1
py -3.11 -m streamlit run app.py
```

浏览器会打开 `http://localhost:8501`（默认端口）。

页面包含两个 Tab：

- **📁 知识库更新**：登录后上传/查看/删除文档
- **💬 智能问答**：多轮问答 + 参考来源展示

### 方式 B：命令行测试 RAG（可选）

```powershell
cd .\1
py -3.11 rag.py
```

---

## 配置说明（`1/config_data.py`）

常用配置项：

- **向量库**
  - `collection_name`：集合名称
  - `persist_directory`：向量库目录（默认 `./chroma_db`）
- **检索**
  - `similarity_threshold`：检索返回条数（Top-K）
- **对话历史**
  - `chat_history_path`：对话历史 JSON 文件
  - `max_history_rounds`：保留最近几轮对话
- **管理员账号**
  - `admin_username` / `admin_password`

---

## 数据是否会丢？

- 关闭网页/刷新页面：**不会丢**（向量库在 `1/chroma_db/`）
- 删除 `1/chroma_db/`：会变成空库，但下次启动会自动创建空目录（历史知识无法自动恢复，需要重新上传）
- 仅删除 `1/chroma_db/` 不删除 `1/md5.text`：可能出现“提示跳过但库里没有”的不一致，建议清库时同时删除 `md5.text`

清空重来（谨慎）：

```text
删除 1/chroma_db/ 和 1/md5.text
```

---

## 常见问题

### 1) `No module named streamlit`

原因：你用的 Python 环境没有安装 streamlit（常见于系统默认指向另一个 Python）。

解决：显式用 3.11 启动：

```powershell
py -3.11 -m streamlit run app.py
```

### 2) pip 安装时报 `Missing dependencies for SOCKS support`

原因：系统代理是 SOCKS，pip 被代理影响。

解决：临时清空代理环境变量后再安装依赖（见上文“安装依赖”）。

---

## 备注

这是一个可演示的 RAG Demo 项目，偏学习/实习作品集用途。若要上线级别，还可进一步补齐：更完善的 README/部署方式、日志与错误处理、检索效果评测、更多格式与引用渲染等。