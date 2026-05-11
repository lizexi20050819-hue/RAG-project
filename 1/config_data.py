md5_path ="./md5.text"
#chroma的集合名称
collection_name = "rag"
persist_directory = "./chroma_db"
#spliter
chunk_size = 1000
chunk_overlap = 100
separators = ["\n", "\t", "。", ".", "，", ",", " ", ""]
max_split_char_number = 1000 #分割字符数大于1000的文本，进行分割