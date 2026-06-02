import os
import uuid

import streamlit as st
import requests

import config_data as config
from file_history_store import ChatHistoryStore
from knowledge_base import KnowledgeBaseService, extract_text
from rag import RAGService


API_BASE_URL = (os.getenv("API_BASE_URL") or "").rstrip("/")


def _api_headers() -> dict:
    # 优先使用会话输入，其次使用环境变量
    key = st.session_state.get("api_key") or os.getenv("API_KEY", "")
    headers = {}
    if key:
        headers["X-API-Key"] = key
    return headers


def _api_enabled() -> bool:
    return bool(API_BASE_URL)


def _ensure_api_session_id() -> str:
    if "api_session_id" not in st.session_state:
        st.session_state["api_session_id"] = str(uuid.uuid4())
    return st.session_state["api_session_id"]


def render_upload_page():
    st.subheader("知识库更新服务")

    if "kb_service" not in st.session_state:
        st.session_state["kb_service"] = KnowledgeBaseService()
    if "upload_results" not in st.session_state:
        st.session_state["upload_results"] = {}
    if "pending_delete" not in st.session_state:
        st.session_state["pending_delete"] = None
    if "admin_auth" not in st.session_state:
        st.session_state["admin_auth"] = False

    kb_service = st.session_state["kb_service"]

    if _api_enabled():
        st.caption(f"API 模式已启用：`{API_BASE_URL}`（本地模式请取消设置环境变量 API_BASE_URL）")
        st.text_input("API Key（可选）", type="password", key="api_key", help="若后端设置了 API_KEY，需要在此填写")

    if not st.session_state["admin_auth"]:
        st.info(
            f"请使用以下凭证登录：\n\n"
            f"用户名：**{config.admin_username}**\n\n"
            f"密码：**{config.admin_password}**"
        )
        username = st.text_input("用户名", key="login_username")
        password = st.text_input("密码", type="password", key="login_password")
        if st.button("登录", key="login_btn"):
            if username == config.admin_username and password == config.admin_password:
                st.session_state["admin_auth"] = True
                st.rerun()
            else:
                st.error("用户名或密码错误")
        return

    col_title, col_logout = st.columns([3, 1])
    with col_title:
        pass
    if col_logout.button("退出登录", key="logout_btn"):
        st.session_state["admin_auth"] = False
        st.rerun()

    if _api_enabled():
        try:
            r = requests.get(f"{API_BASE_URL}/api/documents", headers=_api_headers(), timeout=30)
            r.raise_for_status()
            docs = r.json().get("documents", [])
        except Exception as e:
            st.error(f"拉取文档列表失败：{e}")
            docs = []
    else:
        docs = kb_service.list_documents()
    if docs:
        st.subheader(f"已入库文档（{len(docs)}）")
        for doc in docs:
            c1, c2, c3, c4 = st.columns([3, 1, 1.5, 1])
            c1.write(doc["source"])
            c2.write(f"{doc['chunk_count']} chunks")
            c3.write(doc["create_time"])
            if c4.button("删除", key=f"del_{doc['id']}"):
                st.session_state["pending_delete"] = doc["id"]
                st.rerun()

            if st.session_state["pending_delete"] == doc["id"]:
                st.warning(f'确认删除「{doc["source"]}」？此操作不可撤销。')
                cc1, cc2 = st.columns([1, 4])
                if cc1.button("确认", key=f"confirm_{doc['id']}"):
                    if _api_enabled():
                        try:
                            r = requests.delete(
                                f"{API_BASE_URL}/api/documents/{doc['id']}",
                                headers=_api_headers(),
                                timeout=30,
                            )
                            r.raise_for_status()
                        except Exception as e:
                            st.error(f"删除失败：{e}")
                    else:
                        kb_service.delete_document(doc["id"])
                    st.session_state["pending_delete"] = None
                    st.rerun()
                if cc2.button("取消", key=f"cancel_{doc['id']}"):
                    st.session_state["pending_delete"] = None
                    st.rerun()
        st.divider()

    uploaded_files = st.file_uploader(
        "请上传文件（支持 TXT / PDF / DOCX / Markdown）",
        type=["txt", "pdf", "docx", "md"],
        accept_multiple_files=True,
    )

    if not uploaded_files:
        st.session_state["upload_results"] = {}
        return

    upload_results = st.session_state["upload_results"]

    # 展示文件列表和预览
    st.write(f"已选择 **{len(uploaded_files)}** 个文件：")
    for f in uploaded_files:
        col1, col2 = st.columns([3, 1])
        col1.write(f"**{f.name}**")
        col2.write(f"{f.size / 1024:.1f} KB")
        with st.expander(f"预览: {f.name}"):
            file_bytes = f.getvalue()
            text = extract_text(file_bytes, f.name)
            st.write(text[:2000] if len(text) > 2000 else text)
            if len(text) > 2000:
                st.caption(f"...（共 {len(text)} 字符，仅显示前 2000）")

    if st.button("确认上传", type="primary"):
        new_results = {}
        progress = st.progress(0, text="准备中...")
        total = len(uploaded_files)

        for i, f in enumerate(uploaded_files):
            progress.progress(
                (i + 0.2) / total,
                text=f"正在处理 {i + 1}/{total}: {f.name}",
            )
            file_bytes = f.getvalue()
            if _api_enabled():
                try:
                    files_payload = [("files", (f.name, file_bytes, "application/octet-stream"))]
                    r = requests.post(
                        f"{API_BASE_URL}/api/documents/upload",
                        headers=_api_headers(),
                        files=files_payload,
                        timeout=300,
                    )
                    r.raise_for_status()
                    items = r.json().get("results", [])
                    # 后端此时只上传了 1 个文件，取第一条即可
                    if items:
                        new_results[f.name] = items[0].get("message", "")
                    else:
                        new_results[f.name] = "上传返回为空"
                except Exception as e:
                    new_results[f.name] = f"[失败] {e}"
            else:
                text = extract_text(file_bytes, f.name)
                result = kb_service.upload_by_str(text, f.name)
                new_results[f.name] = result
            progress.progress((i + 1) / total, text=f"已完成 {i + 1}/{total}")

        progress.empty()
        st.session_state["upload_results"] = new_results
        st.rerun()

    if upload_results:
        st.divider()
        st.write("**上传结果：**")
        for name, result in upload_results.items():
            if result.startswith("[跳过]"):
                st.info(f"{name}: {result}")
            elif result.startswith("[成功]"):
                st.success(f"{name}: {result}")
            else:
                st.warning(f"{name}: {result}")


def render_chat_page():
    st.subheader("服装搭配问答")

    if _api_enabled():
        st.caption(f"API 模式已启用：`{API_BASE_URL}`")
        st.text_input("API Key（可选）", type="password", key="api_key", help="若后端设置了 API_KEY，需要在此填写")
        _ensure_api_session_id()
        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = []
        messages = st.session_state["chat_history"]
    else:
        if "rag_service" not in st.session_state:
            st.session_state["rag_service"] = RAGService()
        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = ChatHistoryStore().load()
        history_store = ChatHistoryStore()
        rag_service = st.session_state["rag_service"]
        messages = st.session_state["chat_history"]

    if st.button("清空对话", key="clear_chat"):
        st.session_state["chat_history"] = []
        if _api_enabled():
            # 新 session_id 视为新会话
            st.session_state["api_session_id"] = str(uuid.uuid4())
        else:
            history_store.clear()
        st.rerun()

    messages_container = st.container()

    with messages_container:
        for msg in messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if prompt := st.chat_input("请输入你的问题"):
        messages.append({"role": "user", "content": prompt})
        with messages_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        past_messages = messages[:-1]
        with messages_container:
            with st.chat_message("assistant"):
                with st.spinner("思考中..."):
                    if _api_enabled():
                        r = requests.post(
                            f"{API_BASE_URL}/api/chat",
                            headers=_api_headers(),
                            json={
                                "session_id": st.session_state["api_session_id"],
                                "question": prompt,
                            },
                            timeout=300,
                        )
                        r.raise_for_status()
                        data = r.json()
                        answer = data.get("answer", "")
                        docs = data.get("citations", [])
                    else:
                        answer, docs = rag_service.chat(prompt, history=past_messages)
                st.markdown(answer)
                if docs:
                    with st.expander("参考来源"):
                        if _api_enabled():
                            for i, item in enumerate(docs, 1):
                                meta = item.get("metadata") or {}
                                source = item.get("source") or meta.get("source") or "未知文件"
                                st.caption(f"**{i}. {source}**")
                                st.text((item.get("page_content") or "")[:200])
                        else:
                            for i, doc in enumerate(docs, 1):
                                source = doc.metadata.get("source", "未知文件")
                                st.caption(f"**{i}. {source}**")
                                st.text(doc.page_content[:200])

        messages.append({"role": "assistant", "content": answer})
        st.session_state["chat_history"] = ChatHistoryStore.trim(messages, config.max_history_rounds)
        if not _api_enabled():
            history_store.save(st.session_state["chat_history"])
        st.rerun()


def main():
    st.set_page_config(page_title="RAG 服装搭配助手", page_icon="👔", layout="wide")
    st.title("RAG 服装搭配助手")

    tab_upload, tab_chat = st.tabs(["📁 知识库更新", "💬 智能问答"])

    with tab_upload:
        render_upload_page()

    with tab_chat:
        render_chat_page()
