"""Contract definitions for dev warehouse.

Baseline contracts match the actual DuckDB schema exactly. DuckDB columns
default to nullable, so all columns are declared as ``T | None``.

After drift, schema changes cause violations:
- Customers.email is dropped
- Products.price is altered from DOUBLE to VARCHAR
"""

from datetime import datetime

from olly.contracts import TableContract


class Orders(TableContract):
    __table__ = "orders"

    id: int | None
    customer_id: int | None
    amount: float | None
    created_at: datetime | None
    updated_at: datetime | None


class Products(TableContract):
    __table__ = "products"

    id: int | None
    name: str | None
    price: float | None


class Customers(TableContract):
    __table__ = "customers"

    id: int | None
    name: str | None
    email: str | None
