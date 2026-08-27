"""
Utils package for TMC backend
"""
# 导入日志解析器
from .log_parser import LogParser, LogAggregator, parse_log_line, parse_log_lines

from .sender_filter import SenderFilter

# 从根目录的 utils.py 导入其他工具函数
import sys
import os
# 添加父目录到路径
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 导入根目录 utils.py 的内容
import importlib.util
utils_py_path = os.path.join(parent_dir, 'utils.py')
if os.path.exists(utils_py_path):
    spec = importlib.util.spec_from_file_location("_utils_module", utils_py_path)
    _utils_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_utils_module)
    
    # 导出 utils.py 中的所有函数
    setup_logging = _utils_module.setup_logging
    get_datetime_str = getattr(_utils_module, 'get_datetime_str', None)
    clean_old_files = getattr(_utils_module, 'clean_old_files', None)

__all__ = [
    'LogParser', 'LogAggregator', 'parse_log_line', 'parse_log_lines', 
    'setup_logging', 'SenderFilter'
]
