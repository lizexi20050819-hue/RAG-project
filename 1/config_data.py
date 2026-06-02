md5_path ="./md5.text"
#chroma的集合名称
collection_name = "rag"
persist_directory = "./chroma_db"
#spliter
chunk_size = 1000
chunk_overlap = 100
separators = ["\n", "\t", "。", ".", "，", ",", " ", ""]
max_split_char_number = 1000 #分割字符数大于1000的文本，进行分割

similarity_threshold = 2 #检索返回条数
embedding_model = "text-embedding-v4"
chat_model = "qwen3-max"
chat_history_path = "./chat_history.json"
max_history_rounds = 5  # 保留最近几轮对话，避免 prompt 过长

# 管理员登录凭证
admin_username = "admin"
admin_password = "rag2024"
