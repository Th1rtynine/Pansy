"""The declarative base shared by every table module.

Kept in its own module so that table modules can import Base without
importing the package, which would be circular.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
