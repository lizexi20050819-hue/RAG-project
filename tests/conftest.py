import sys
from pathlib import Path


# 将项目代码目录（RAG-project/1）加入 import 搜索路径，便于 pytest 直接 import
ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "1"
sys.path.insert(0, str(CODE_DIR))

