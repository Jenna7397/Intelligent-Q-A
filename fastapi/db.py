"""
数据库模型：对话历史 + 用户记忆
用SQLAlchemy，SQLite开发，以后换PostgreSQL只改DATABASE_URL
"""
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'kb_store' / 'agent.db'
DATABASE_URL = f'sqlite:///{DB_PATH}'
# 以后换PostgreSQL: DATABASE_URL = 'postgresql://user:pass@localhost:5432/qiaoxiang'

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Conversation(Base):
    """对话会话"""
    __tablename__ = 'conversations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), default='新对话')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    # 用户偏好memory（JSON）：{preferences: "喜欢美食", budget: "中等"}
    memory = Column(JSON, default=dict)

    messages = relationship('Message', back_populates='conversation', order_by='Message.id')


class Message(Base):
    """单条消息"""
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey('conversations.id'))
    role = Column(String(20))  # user / assistant / tool / system
    content = Column(Text)
    tool_calls = Column(JSON, nullable=True)  # 如果是模型调用工具
    tokens = Column(Integer, default=0)  # 这条消息的token数
    created_at = Column(DateTime, default=datetime.now)

    conversation = relationship('Conversation', back_populates='messages')


# 建表
Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
