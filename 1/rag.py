from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda

import config_data as config
from file_history_store import ChatHistoryStore
from vector_stores import VectorStoreService


def format_document(docs: list[Document]) -> str:
    if not docs:
        return "无相关参考资料"

    formatted_str = ""
    for doc in docs:
        formatted_str += f"文档片段: {doc.page_content}\n文档元数据: {doc.metadata}\n\n"
    return formatted_str


def _extract_input(payload) -> str:
    if isinstance(payload, dict):
        return payload["input"]
    return payload


def _extract_history(payload) -> list:
    if isinstance(payload, dict):
        return payload.get("history", [])
    return []


class RAGService:
    def __init__(self):
        self.vector_service = VectorStoreService(
            embedding=DashScopeEmbeddings(model=config.embedding_model)
        )
        self.retriever = self.vector_service.get_retriever()

        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个专业的服装搭配师。请结合以下参考资料和历史对话，回答用户当前问题。"
                    "优先依据参考资料作答；若资料中没有相关信息，请结合对话上下文如实说明。\n\n"
                    "参考资料:\n{context}",
                ),
                MessagesPlaceholder("history"),
                ("user", "{input}"),
            ]
        )
        self.chat_model = ChatTongyi(model=config.chat_model)

        self.chain = (
            {
                "input": RunnableLambda(_extract_input),
                "context": RunnableLambda(lambda x: x.get("context", "")),
                "history": RunnableLambda(_extract_history),
            }
            | self.prompt_template
            | self.chat_model
            | StrOutputParser()
        )

    @staticmethod
    def _build_history_messages(history: list) -> list:
        messages = []
        for item in history:
            if isinstance(item, tuple):
                messages.append(HumanMessage(content=item[0]))
                messages.append(AIMessage(content=item[1]))
            elif isinstance(item, dict):
                role = item.get("role")
                content = item.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))
        return messages

    def chat(self, question: str, history: list | None = None) -> tuple[str, list[Document]]:
        trimmed_history = history or []
        if trimmed_history and isinstance(trimmed_history[0], dict):
            trimmed_history = ChatHistoryStore.trim(
                trimmed_history, config.max_history_rounds
            )

        history_messages = self._build_history_messages(trimmed_history)
        results = self.vector_service.vector_store.similarity_search_with_relevance_scores(
            question, k=config.similarity_threshold
        )
        # 策略A：引用与生成上下文一致——Top-K 检索到的全部文档都用于 context，也全部返回给调用方做 citations 展示
        all_docs: list[Document] = []
        for doc, score in results:
            meta = (doc.metadata or {}).copy()
            meta["relevance_score"] = float(score)
            doc.metadata = meta
            all_docs.append(doc)
        context = format_document(all_docs)

        answer = self.chain.invoke({
            "input": question, "context": context, "history": history_messages
        })
        return answer, all_docs


if __name__ == "__main__":
    service = RAGService()
    history = []

    q1 = "冷白皮适合穿什么颜色的衣服？"
    a1, docs1 = service.chat(q1, history=history)
    print("Q1:", q1)
    print("A1:", a1)
    history.extend([{"role": "user", "content": q1}, {"role": "assistant", "content": a1}])

    q2 = "刚才你说的颜色里，哪个最适合正式场合？"
    a2, docs2 = service.chat(q2, history=history)
    print("\nQ2:", q2)
    print("A2:", a2)
