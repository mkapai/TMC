import os
from dotenv import load_dotenv
from pathlib import Path
from version import get_version


BACKEND_DIR = Path(__file__).resolve().parent
_repository_root = BACKEND_DIR.parent.parent
PROJECT_ROOT = _repository_root if (_repository_root / 'config').is_dir() else BACKEND_DIR


def _project_path(env_name: str, default: str) -> str:
    path = Path(os.getenv(env_name, default))
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def _default_database_url() -> str:
    return f"sqlite:///{(PROJECT_ROOT / 'data/bot.db').as_posix()}"


# 统一配置文件加载器
class ConfigLoader:
    """统一配置文件加载器，支持多种配置文件格式"""
    
    @staticmethod
    def load_config():
        """按优先级加载配置文件，环境变量优先"""
        # 配置文件搜索路径（按优先级排序）
        config_files = [
            PROJECT_ROOT / 'config/app.config',
            PROJECT_ROOT / 'app.config',
            PROJECT_ROOT / 'config/config.env',
            PROJECT_ROOT / 'config.env',
            PROJECT_ROOT / 'config/.env',
            PROJECT_ROOT / '.env',
        ]
        
        # 加载所有存在的配置文件，按优先级顺序（后加载的覆盖先加载的）
        loaded_files = []
        for config_file in reversed(config_files):  # 反向加载，让高优先级的文件最后加载
            if os.path.exists(config_file):
                print(f"[CONFIG] 加载配置文件: {config_file}")
                load_dotenv(config_file, override=True)  # 允许覆盖，实现优先级
                loaded_files.append(config_file)
        
        if not loaded_files:
            print("[WARNING] 未找到配置文件，使用默认配置")
        else:
            priority = ' > '.join(str(path) for path in reversed(loaded_files))
            print(f"[CONFIG] 已加载 {len(loaded_files)} 个配置文件，最终优先级: {priority}")
        
        # 环境变量已经在系统中，优先级最高

# 加载配置
ConfigLoader.load_config()

class Config:
    """统一配置类 - Telegram消息转发机器人"""
    
    # === 应用信息 ===
    APP_NAME = os.getenv('APP_NAME', 'TMC (Telegram Message Central)')
    APP_VERSION = os.getenv('APP_VERSION', get_version())
    APP_DESCRIPTION = os.getenv('APP_DESCRIPTION', f'Telegram消息中心 - TMC v{get_version()}')
    
    # === Telegram API 配置 ===
    try:
        API_ID = int(os.getenv('API_ID', '0')) if os.getenv('API_ID', '0').isdigit() else 0
    except (ValueError, TypeError):
        API_ID = 0
        
    API_HASH = os.getenv('API_HASH', '')
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    PHONE_NUMBER = os.getenv('PHONE_NUMBER', '')
    
    # === 管理员配置 ===
    @staticmethod
    def _parse_admin_ids(ids_str):
        try:
            return [int(x.strip()) for x in ids_str.split(',') if x.strip() and x.strip().isdigit()]
        except (ValueError, AttributeError):
            return []
    
    ADMIN_USER_IDS = _parse_admin_ids(os.getenv('ADMIN_USER_IDS', ''))
    
    # === 数据库配置 ===
    DATABASE_URL = os.getenv('DATABASE_URL', _default_database_url())
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    RESOURCE_CACHE_DIR = _project_path('RESOURCE_CACHE_DIR', 'data/message-resources')
    RESOURCE_CACHE_MAX_GB = float(os.getenv('RESOURCE_CACHE_MAX_GB', '100'))
    PUBLIC_RESOURCE_TTL_DAYS = int(os.getenv('PUBLIC_RESOURCE_TTL_DAYS', '7'))
    DELIVERY_SECRET_KEY = os.getenv('DELIVERY_SECRET_KEY', '')
    
    # === 文件路径配置 ===
    DATA_DIR = _project_path('DATA_DIR', 'data')
    LOGS_DIR = _project_path('LOGS_DIR', 'logs')
    TEMP_DIR = _project_path('TEMP_DIR', 'temp')
    SESSIONS_DIR = _project_path('SESSIONS_DIR', 'sessions')
    
    # === 日志配置 ===
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = _project_path('LOG_FILE', 'logs/bot.log')
    ENABLE_LOG_CLEANUP = os.getenv('ENABLE_LOG_CLEANUP', 'true').lower() == 'true'
    LOG_RETENTION_DAYS = int(os.getenv('LOG_RETENTION_DAYS', '30'))
    LOG_CLEANUP_TIME = os.getenv('LOG_CLEANUP_TIME', '02:00')
    MAX_LOG_SIZE = int(os.getenv('MAX_LOG_SIZE', '100'))
    
    # === 转发配置 ===
    MAX_FORWARD_DELAY = int(os.getenv('MAX_FORWARD_DELAY', '5'))
    ENABLE_KEYWORD_FILTER = os.getenv('ENABLE_KEYWORD_FILTER', 'true').lower() == 'true'
    ENABLE_REGEX_REPLACE = os.getenv('ENABLE_REGEX_REPLACE', 'true').lower() == 'true'
    
    # === Web界面配置 ===
    WEB_PORT = int(os.getenv('WEB_PORT', '9393'))
    WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
    
    # === 权限配置（Docker用户映射） ===
    PUID = int(os.getenv('PUID', '1000'))
    PGID = int(os.getenv('PGID', '1000'))
    
    # === 代理配置 ===
    # 支持标准HTTP_PROXY环境变量
    HTTP_PROXY = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
    HTTPS_PROXY = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
    
    # 代理启用状态检查
    # 优先检查显式的 ENABLE_PROXY 设置
    enable_proxy_env = os.getenv('ENABLE_PROXY', '').lower()
    if enable_proxy_env in ['true', 'false']:
        # 如果明确设置了 ENABLE_PROXY，使用该设置
        ENABLE_PROXY = enable_proxy_env == 'true'
    else:
        # 如果没有明确设置，则检查是否有代理URL环境变量
        ENABLE_PROXY = HTTP_PROXY is not None or HTTPS_PROXY is not None
    
    # 解析代理URL或使用传统配置
    PROXY_TYPE = 'http'
    PROXY_HOST = '127.0.0.1'
    PROXY_PORT = 1080
    PROXY_USERNAME = ''
    PROXY_PASSWORD = ''
    
    # 只有在启用代理的情况下才设置代理参数
    if ENABLE_PROXY:
        if HTTP_PROXY or HTTPS_PROXY:
            # 优先使用HTTPS_PROXY，fallback到HTTP_PROXY
            proxy_url = HTTPS_PROXY or HTTP_PROXY
            try:
                from urllib.parse import urlparse
                parsed = urlparse(proxy_url)
                if parsed.hostname:
                    PROXY_TYPE = parsed.scheme or 'http'
                    PROXY_HOST = parsed.hostname
                    PROXY_PORT = parsed.port or (1080 if PROXY_TYPE in ['socks4', 'socks5'] else 8080)
                    PROXY_USERNAME = parsed.username or ''
                    PROXY_PASSWORD = parsed.password or ''
            except Exception:
                # 解析失败，使用传统配置
                pass
        else:
            # 使用传统配置方式（仅在启用代理时）
            PROXY_TYPE = os.getenv('PROXY_TYPE', 'http').lower()
            PROXY_HOST = os.getenv('PROXY_HOST', '127.0.0.1')
            PROXY_PORT = int(os.getenv('PROXY_PORT', '1080'))
            PROXY_USERNAME = os.getenv('PROXY_USERNAME', '')
            PROXY_PASSWORD = os.getenv('PROXY_PASSWORD', '')
    
    # === Docker配置 ===
    TZ = os.getenv('TZ', 'Asia/Shanghai')
    MEMORY_LIMIT = os.getenv('MEMORY_LIMIT', '512M')
    CPU_LIMIT = float(os.getenv('CPU_LIMIT', '0.5'))
    
    # === 安全配置 ===
    SESSION_SECRET = os.getenv('SESSION_SECRET', 'your_random_session_secret_key_here')
    
    @classmethod
    def reload(cls):
        """重新加载配置"""
        print("🔄 重新加载配置...")
        ConfigLoader.load_config()
        
        # 重新设置所有属性
        api_id_str = os.getenv('API_ID', '0').strip()
        cls.API_ID = int(api_id_str) if api_id_str and api_id_str.isdigit() else 0
        cls.API_HASH = os.getenv('API_HASH', '')
        cls.BOT_TOKEN = os.getenv('BOT_TOKEN', '')
        cls.PHONE_NUMBER = os.getenv('PHONE_NUMBER', '')
        cls.ADMIN_USER_IDS = cls._parse_admin_ids(os.getenv('ADMIN_USER_IDS', ''))
        
        # 更新其他配置
        cls.DATABASE_URL = os.getenv('DATABASE_URL', _default_database_url())
        cls.PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
        cls.RESOURCE_CACHE_DIR = _project_path('RESOURCE_CACHE_DIR', 'data/message-resources')
        resource_cache_max_gb = os.getenv('RESOURCE_CACHE_MAX_GB', '100').strip()
        cls.RESOURCE_CACHE_MAX_GB = float(resource_cache_max_gb or '100')
        public_resource_ttl_days = os.getenv('PUBLIC_RESOURCE_TTL_DAYS', '7').strip()
        cls.PUBLIC_RESOURCE_TTL_DAYS = (
            int(public_resource_ttl_days)
            if public_resource_ttl_days and public_resource_ttl_days.isdigit()
            else 7
        )
        cls.DELIVERY_SECRET_KEY = os.getenv('DELIVERY_SECRET_KEY', '')
        cls.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        cls.DATA_DIR = _project_path('DATA_DIR', 'data')
        cls.LOGS_DIR = _project_path('LOGS_DIR', 'logs')
        cls.TEMP_DIR = _project_path('TEMP_DIR', 'temp')
        cls.SESSIONS_DIR = _project_path('SESSIONS_DIR', 'sessions')
        cls.LOG_FILE = _project_path('LOG_FILE', 'logs/bot.log')
        
        # 安全的int转换
        max_delay = os.getenv('MAX_FORWARD_DELAY', '5').strip()
        cls.MAX_FORWARD_DELAY = int(max_delay) if max_delay and max_delay.isdigit() else 5
        
        cls.ENABLE_KEYWORD_FILTER = os.getenv('ENABLE_KEYWORD_FILTER', 'true').lower() == 'true'
        cls.ENABLE_REGEX_REPLACE = os.getenv('ENABLE_REGEX_REPLACE', 'true').lower() == 'true'
        
        web_port = os.getenv('WEB_PORT', '9393').strip()
        cls.WEB_PORT = int(web_port) if web_port and web_port.isdigit() else 9393
        cls.WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
        
        # 重载代理配置
        cls.ENABLE_PROXY = os.getenv('ENABLE_PROXY', 'false').lower() == 'true'
        cls.PROXY_TYPE = os.getenv('PROXY_TYPE', 'http')
        cls.PROXY_HOST = os.getenv('PROXY_HOST', '127.0.0.1')
        
        proxy_port = os.getenv('PROXY_PORT', '1080').strip()
        cls.PROXY_PORT = int(proxy_port) if proxy_port and proxy_port.isdigit() else 1080
        cls.PROXY_USERNAME = os.getenv('PROXY_USERNAME', '')
        cls.PROXY_PASSWORD = os.getenv('PROXY_PASSWORD', '')
        
        # 重载日志管理配置
        cls.ENABLE_LOG_CLEANUP = os.getenv('ENABLE_LOG_CLEANUP', 'true').lower() == 'true'
        
        retention_days = os.getenv('LOG_RETENTION_DAYS', '30').strip()
        cls.LOG_RETENTION_DAYS = int(retention_days) if retention_days and retention_days.isdigit() else 30
        cls.LOG_CLEANUP_TIME = os.getenv('LOG_CLEANUP_TIME', '02:00')
        
        max_log_size = os.getenv('MAX_LOG_SIZE', '100').strip()
        cls.MAX_LOG_SIZE = int(max_log_size) if max_log_size and max_log_size.isdigit() else 100
        
        # 重载Session配置
        cls.SESSION_SECRET = os.getenv('SESSION_SECRET', 'default-secret-key-change-in-production')
        
        print("✅ 配置重载完成")
    
    @staticmethod
    def create_directories():
        """创建必要的目录"""
        directories = [Config.DATA_DIR, Config.LOGS_DIR, Config.TEMP_DIR, Config.SESSIONS_DIR]
        for directory in directories:
            Path(directory).mkdir(exist_ok=True)
            
    @classmethod
    def get_config_summary(cls):
        """获取配置摘要（隐藏敏感信息）"""
        return {
            'app_name': cls.APP_NAME,
            'app_version': cls.APP_VERSION,
            'web_port': cls.WEB_PORT,
            'web_host': cls.WEB_HOST,
            'database_type': 'sqlite' if 'sqlite' in cls.DATABASE_URL else 'postgresql',
            'proxy_enabled': cls.ENABLE_PROXY,
            'proxy_type': cls.PROXY_TYPE if cls.ENABLE_PROXY else None,
            'admin_count': len(cls.ADMIN_USER_IDS),
            'features': {
                'keyword_filter': cls.ENABLE_KEYWORD_FILTER,
                'regex_replace': cls.ENABLE_REGEX_REPLACE,
            }
        }

def validate_config():
    """
    验证配置的完整性
    
    注意：API_ID、API_HASH、BOT_TOKEN、PHONE_NUMBER 现在是可选的全局配置
    这些配置可以在网页端为每个客户端单独设置，全局配置仅作为 fallback
    """
    errors = []
    warnings = []
    
    # 全局配置警告（不再是必需的）
    if not Config.API_ID or Config.API_ID == 0:
        warnings.append("⚠️  全局 API_ID 未设置，将使用客户端配置（网页端添加时设置）")
    
    if not Config.API_HASH:
        warnings.append("⚠️  全局 API_HASH 未设置，将使用客户端配置（网页端添加时设置）")
    
    if not Config.BOT_TOKEN:
        warnings.append("⚠️  全局 BOT_TOKEN 未设置，将使用客户端配置（网页端添加时设置）")
    
    if not Config.PHONE_NUMBER:
        warnings.append("⚠️  全局 PHONE_NUMBER 未设置，将使用客户端配置（网页端添加时设置）")
    
    # 可选配置警告
    if not Config.ADMIN_USER_IDS:
        warnings.append("⚠️  ADMIN_USER_IDS 未设置，所有用户都可以管理")
    
    if Config.SESSION_SECRET == 'your_random_session_secret_key_here':
        warnings.append("⚠️  SESSION_SECRET 使用默认值，建议修改")
    
    if Config.ENABLE_PROXY and not Config.PROXY_HOST:
        warnings.append("⚠️  启用了代理但未设置 PROXY_HOST")
    
    # 输出结果
    if warnings:
        print("\n配置警告:")
        for warning in warnings:
            print(f"  {warning}")
        print()
    
    if errors:
        error_msg = "配置错误:\n" + "\n".join(f"  {error}" for error in errors)
        raise ValueError(error_msg)
    
    print("✅ 配置验证通过（全局配置为可选，可通过网页端设置客户端配置）")
    return True

def print_config_info():
    """打印配置信息"""
    print(f"""
🔧 配置信息
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📱 应用名称: {Config.APP_NAME}
📊 版本号: {Config.APP_VERSION}
🌐 Web端口: {Config.WEB_PORT}
🗄️  数据库: {"SQLite" if "sqlite" in Config.DATABASE_URL else "PostgreSQL"}
🔌 代理状态: {"启用" if Config.ENABLE_PROXY else "禁用"}
👥 管理员数量: {len(Config.ADMIN_USER_IDS)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)
