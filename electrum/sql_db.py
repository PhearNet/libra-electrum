import os
import concurrent
import queue
import threading
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from .logging import Logger


# https://stackoverflow.com/questions/26971050/sqlalchemy-sqlite-too-many-sql-variables
SQLITE_LIMIT_VARIABLE_NUMBER = 999


def sql(func):
    """wrapper for sql methods"""
    def wrapper(self, *args, **kwargs):
        assert threading.currentThread() != self.sql_thread
        f = asyncio.Future()
        self.db_requests.put((f, func, args, kwargs))
        return f
    return wrapper

class SqlDB(Logger):
    
    def __init__(self, network, path, base):
        Logger.__init__(self)
        self.base = base
        self.network = network
        self.path = path
        self.db_requests = queue.Queue()
        self.sql_thread = threading.Thread(target=self.run_sql)
        self.sql_thread.start()

    def run_sql(self):
        #return
        self.logger.info("SQL thread started")
        engine = create_engine('sqlite:///' + self.path, pool_reset_on_return=None, poolclass=StaticPool)#, echo=True)
        DBSession = sessionmaker(bind=engine, autoflush=False)
        if not os.path.exists(self.path):
            self.base.metadata.create_all(engine)
        self.DBSession = DBSession()
        while self.network.asyncio_loop.is_running():
            try:
                future, func, args, kwargs = self.db_requests.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                result = func(self, *args, **kwargs)
            except BaseException as e:
                self.DBSession.rollback()
                future.set_exception(e)
                continue
            self.DBSession.commit()
            if not future.cancelled():
                future.set_result(result)
        # write
        self.DBSession.commit()
        self.logger.info("SQL thread terminated")
