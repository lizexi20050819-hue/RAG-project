import os
import config_data as config
import hashlib
from io import BytesIO
from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from datetime import datetime

def check_md5(md5_str: str):
    """检查传入的md5字符串是否已经被处理过了
    return False(md5未处理过) True(已经处理过，已有记录)
    """
    if not os.path.exists(config.md5_path):
        # if进入表示文件不存在，那肯定没有处理过这个md5了
        open(config.md5_path, 'w', encoding='utf-8').close()
        return False
    else:
        for line in open(config.md5_path, 'r', encoding='utf-8').readlines():
            line = line.strip()  # 处理字符串前后的空格和回车
            if line == md5_str:
                return True  # 已处理过

        return False

def save_md5(md5_str: str):
    """将传入的md5字符串，记录到文件内保存"""
    with open(config.md5_path, 'a', encoding="utf-8") as f:
        f.write(md5_str + '\n')

def remove_md5(md5_values: list[str]):
    """从 md5 记录文件中删除指定的 md5 值"""
    if not os.path.exists(config.md5_path):
        return
    with open(config.md5_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    remove_set = set(md5_values)
    with open(config.md5_path, 'w', encoding='utf-8') as f:
        for line in lines:
            if line.strip() not in remove_set:
                f.write(line)

def get_string_md5(input_str: str, encoding='utf-8'):
    """将传入的字符串转换为md5字符串"""

    # 将字符串转换为bytes字节数组
    str_bytes = input_str.encode(encoding=encoding)

    # 创建md5对象
    md5_obj = hashlib.md5()           # 得到md5对象
    md5_obj.update(str_bytes)          # 更新内容（传入即将要转换的字节数组）
    md5_hex = md5_obj.hexdigest()      # 得到md5的十六进制字符串

    return md5_hex

def extract_text_from_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8")

def extract_text_from_md(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8")

def extract_text_from_pdf(file_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)

def extract_text_from_docx(file_bytes: bytes) -> str:
    from docx import Document

    doc = Document(BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)

def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    parsers = {
        ".txt": extract_text_from_txt,
        ".md": extract_text_from_md,
        ".pdf": extract_text_from_pdf,
        ".docx": extract_text_from_docx,
    }
    parser = parsers.get(ext)
    if parser is None:
        raise ValueError(f"不支持的文件格式: {ext}")
    return parser(file_bytes)

class KnowledgeBaseService(object):

    def __init__(self):
        #如果文件夹不存在就创建文件夹
        os.makedirs(config.persist_directory, exist_ok=True)
        self.chroma = Chroma(
            collection_name=config.collection_name,
            embedding_function=DashScopeEmbeddings(
                model="text-embedding-v4"),
                persist_directory=config.persist_directory,
        )     
        # 向量存储的实例 Chroma向量库对象
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=config.separators,
            length_function=len,#测长度
        )      # 文本分割器的对象

    def upload_by_str(self, data, filename):
        #data: 字符串数据
        #filename: 文件名
        """将传入的字符串，进行向量化，存入向量数据库中"""
        #检查是否已有同名文件
        existing = self.chroma.get(where={"source": filename}, limit=1)
        if existing and existing["ids"]:
            return "[跳过]已存在同名文件"

        #先拿md5值，检查是否已经处理过了
        md5_hex = get_string_md5(data)
        if check_md5(md5_hex):
            return "[跳过]内容已经存在知识库中"
        
        if len(data) > config.max_split_char_number:
            knowledge_chunks:list[str] = self.spliter.split_text(data)
        else:
            knowledge_chunks:list[str] = [data]
        
        Metadata = {
            "source": filename,
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator": "user_xi",
            "md5": md5_hex,
        }
        self.chroma.add_texts( #添加文本到向量数据库中
            knowledge_chunks,
            metadatas=[Metadata for _ in knowledge_chunks],
        )
        save_md5(md5_hex)
        return "[成功]已成功上传文件内容到知识库"

    def list_documents(self) -> list[dict]:
        """列出知识库中所有文档（按 source+md5 聚合），返回每个文档的 chunk 数和上传时间"""
        result = self.chroma.get(include=["metadatas"])
        if not result or not result["metadatas"]:
            return []

        docs: dict[str, dict] = {}
        for meta in result["metadatas"]:
            source = meta.get("source", "未知文件")
            md5_val = meta.get("md5", "")
            doc_id = f"{source}#{md5_val}"
            if doc_id not in docs:
                docs[doc_id] = {
                    "id": doc_id,
                    "source": source,
                    "chunk_count": 0,
                    "create_time": meta.get("create_time", ""),
                }
            docs[doc_id]["chunk_count"] += 1

        return sorted(docs.values(), key=lambda d: d["create_time"], reverse=True)

    def delete_document(self, doc_id: str) -> int:
        """删除指定文档的所有 chunks（doc_id 格式: source#md5），返回删除数量"""
        parts = doc_id.rsplit("#", 1)
        source = parts[0]
        md5_val = parts[1] if len(parts) == 2 else ""
        where = {"$and": [{"source": source}, {"md5": md5_val}]} if md5_val else {"source": source}
        result = self.chroma.get(where=where, include=["metadatas"])
        if not result or not result["ids"]:
            return 0

        ids = result["ids"]
        md5_set_meta = {m["md5"] for m in result["metadatas"] if "md5" in m}
        self.chroma.delete(ids=ids)
        if md5_set_meta:
            remove_md5(list(md5_set_meta))
        else:
            # 旧数据没有 md5 元数据，清空全部 md5 记录作为兜底
            if os.path.exists(config.md5_path):
                open(config.md5_path, 'w', encoding='utf-8').close()
        return len(ids)

    def upload_by_file(self, file_bytes: bytes, filename: str):
        text = extract_text(file_bytes, filename)
        return self.upload_by_str(text, filename)

