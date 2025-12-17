import os
import asyncpg
import json
import logging

logger = logging.getLogger(__name__)

db_pool = None

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_DATABASE = os.getenv("PG_CBDATABASE")
PG_USER = os.getenv("PG_CBUSER")
PG_PASSWORD = os.getenv("PG_CBPASSWORD")

def check_db_config():
    if not all([PG_DATABASE, PG_USER, PG_PASSWORD]):
        logger.error("db env vars error")
        return False
    return True

# db funcs
async def init_db_pool():
    global db_pool
    if db_pool:
        logger.warning("пул подключений уже инициализирован")
        return

    if not check_db_config():
        raise EnvironmentError("env error")

    try:
        db_pool = await asyncpg.create_pool(
            user=PG_USER,
            password=PG_PASSWORD,
            database=PG_DATABASE,
            host=PG_HOST,
            port=PG_PORT,
            min_size=1,
            max_size=10
        )
        logger.info("пул подключений PostgreSQL создан успешно")
        await create_table()
    except Exception as e:
        logger.critical(f"критическая ошибка подключения к PostgreSQL: {e}")
        raise # перевыбрасывает ошибку для остановки приложения

async def close_db_pool():
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
        logger.info("пул подключений PostgreSQL закрыт")

async def create_table():
    await db_pool.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            chat_id BIGINT PRIMARY KEY,
            history JSONB NOT NULL DEFAULT '[]'::jsonb
        );
    """)
    logger.info("таблица chat_history проверена/создана.")

async def get_history(chat_id: int) -> list:
    global db_pool
    
    if db_pool is None:
        logger.error("пул БД не инициализирован, не могу получить историю.")
        return []

    try:
        record = await db_pool.fetchrow(
            "SELECT history FROM chat_history WHERE chat_id = $1", chat_id
        )
    except Exception as e:
        logger.error(f"ошибка при чтении истории для chat_id={chat_id}: {e}")
        return []

    if record and record['history'] is not None:
        history_data = record['history']
        if isinstance(history_data, str):
            try:
                history_data = json.loads(history_data)
                logger.warning(f"история для chat_id={chat_id} была строкой. Выполнено JSON-декодирование")
            except json.JSONDecodeError:
                logger.error(f"не удалось декодировать историю чата {chat_id} из строки")
                return []
        
        if isinstance(history_data, list):
            return history_data
        else:
            logger.error(f"история чата {chat_id} в БД имеет неверный формат (не список)")
            return []
            
    return []

async def save_history(chat_id: int, history: list):
    history_json = json.dumps(history) 
    
    await db_pool.execute(
        """
        INSERT INTO chat_history (chat_id, history)
        VALUES ($1, $2::jsonb)
        ON CONFLICT (chat_id) DO UPDATE 
        SET history = EXCLUDED.history;
        """,
        chat_id, history_json
    )

async def delete_history(chat_id: int):
    await db_pool.execute(
        "DELETE FROM chat_history WHERE chat_id = $1", chat_id
    )