from sqlalchemy import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    __abstract__ = True


def create_all(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
