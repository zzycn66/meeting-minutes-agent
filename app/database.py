# -*- coding: utf-8 -*-
"""
数据库连接管理模块

本模块负责：
1. 创建 SQLAlchemy 数据库引擎
2. 配置 SQLite 性能优化参数
3. 提供数据库会话管理
4. 记录慢查询日志
"""
import time
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL

logger = logging.getLogger(__name__)

# ========== 创建数据库引擎 ==========
# SQLAlchemy 的核心组件，负责管理数据库连接池和执行 SQL
engine = create_engine(
    DATABASE_URL,                           # 数据库连接字符串 (sqlite:///meeting_agent.db)
    connect_args={"check_same_thread": False},  # SQLite 允许多线程访问
    pool_pre_ping=True,     # 每次使用连接前检测是否有效（防止使用断开的连接）
    pool_size=5,            # 连接池保持 5 个空闲连接
    max_overflow=5,         # 超出 pool_size 的最大连接数（最多 10 个并发连接）
    pool_recycle=3600,      # 连接使用超过 1 小时后回收（防止长时间连接被服务器断开）
    echo=False,             # 不打印 SQL 语句（生产环境设为 False）
)

# ========== SQLite 性能优化 ==========
# 使用 SQLAlchemy 事件监听器，在每次建立连接时执行 PRAGMA 命令
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """
    SQLite PRAGMA 设置

    这些设置在每次建立连接时执行，用于优化 SQLite 性能：
    - WAL 模式：允许读写并发，性能提升 2-5 倍
    - synchronous=NORMAL：平衡性能和安全
    - cache_size：设置缓存大小
    - temp_store：临时表存储在内存
    """
    cursor = dbapi_connection.cursor()

    # WAL (Write-Ahead Logging) 模式
    # 优势：允许读写并发（普通模式下写操作会阻塞读操作）
    cursor.execute("PRAGMA journal_mode=WAL")

    # synchronous 模式：NORMAL 平衡性能和安全
    cursor.execute("PRAGMA synchronous=NORMAL")

    # 缓存大小：-64000 表示 64MB（负数表示 KB）
    cursor.execute("PRAGMA cache_size=-64000")

    # 临时表存储在内存（更快）
    cursor.execute("PRAGMA temp_store=MEMORY")

    cursor.close()

# ========== 慢查询日志 ==========
# 记录 SQL 执行时间，超过 1 秒的记录为慢查询
@event.listens_for(engine, "before_cursor_execute")
def _log_slow_queries(conn, cursor, statement, parameters, context, executemany):
    """SQL 执行前：记录开始时间"""
    conn.info.setdefault("query_start_time", []).append(time.monotonic())

@event.listens_for(engine, "after_cursor_execute")
def _log_query_duration(conn, cursor, statement, parameters, context, executemany):
    """SQL 执行后：计算耗时，超过 1 秒记录为慢查询"""
    start_times = conn.info.get("query_start_time", [])
    if start_times:
        start_time = start_times.pop()
        duration = time.monotonic() - start_time
        if duration > 1.0:
            logger.warning("Slow query (%.2fs): %s", duration, statement[:200])

# ========== 创建会话工厂 ==========
# SessionLocal 是会话类，每次调用会创建一个新的数据库会话
SessionLocal = sessionmaker(
    autocommit=False,   # 不自动提交，需要手动 db.commit()
    autoflush=False,    # 不自动刷新，需要手动 db.flush()
    bind=engine         # 绑定到数据库引擎
)

# 声明式基类，所有数据库模型（如 Meeting, User）都继承此类
Base = declarative_base()

def get_db():
    """
    FastAPI 依赖注入：获取数据库会话

    使用方式（在 API 路由中）：
    @router.get("/api/meetings")
    async def list_meetings(db: Session = Depends(get_db)):
        meetings = db.query(Meeting).all()

    执行流程：
    1. FastAPI 调用 get_db()
    2. 创建数据库会话
    3. yield 给请求处理函数
    4. 请求处理完成后关闭会话
    """
    db = SessionLocal()
    try:
        yield db  # 返回会话给请求处理
    finally:
        db.close()  # 请求结束后关闭会话（无论成功或失败）

def init_db():
    """初始化数据库表（根据模型定义创建表）"""
    Base.metadata.create_all(bind=engine)
