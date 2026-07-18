from sqlalchemy import inspect


def test_leads_table_has_expected_columns(app):
    """The leads table exists with exactly the columns from SYSTEM_DESIGN.md."""
    from database import engine

    inspector = inspect(engine)

    assert "leads" in inspector.get_table_names()
    columns = {col["name"] for col in inspector.get_columns("leads")}
    assert columns == {
        "id",
        "first_name",
        "last_name",
        "email",
        "resume_url",
        "state",
        "created_at",
        "updated_at",
    }


def test_leads_id_is_primary_key(app):
    """id is the sole primary key column on leads."""
    from database import engine

    inspector = inspect(engine)
    pk = inspector.get_pk_constraint("leads")

    assert pk["constrained_columns"] == ["id"]


def test_create_all_is_idempotent(app):
    """The startup hook's create_all() is safe to call again once tables exist."""
    from database import Base, engine

    Base.metadata.create_all(bind=engine)  # should not raise
