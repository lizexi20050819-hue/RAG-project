import json
import os

import config_data as config


class ChatHistoryStore:
    """对话历史持久化到本地 JSON 文件"""

    def __init__(self, path: str | None = None):
        self.path = path or config.chat_history_path

    def load(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []

        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    def save(self, messages: list[dict]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

    def clear(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)

    @staticmethod
    def trim(messages: list[dict], max_rounds: int) -> list[dict]:
        if max_rounds <= 0:
            return []
        max_messages = max_rounds * 2
        return messages[-max_messages:]
