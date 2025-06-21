import os
import sqlite3
from pathlib import Path


def test_database_connection_and_stats():
    """Ensure the API database exists and basic queries return results."""
    repo_root = Path(__file__).resolve().parents[1]
    db_path = repo_root / "api_gateway" / "connectwise_api.db"

    assert db_path.exists(), (
        f"Database file not found at {db_path}. Run build_database.py first."
    )

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM endpoints")
        endpoint_count = cursor.fetchone()[0]
        assert endpoint_count > 0

        cursor.execute("SELECT COUNT(*) FROM parameters")
        parameter_count = cursor.fetchone()[0]
        assert parameter_count > 0

        cursor.execute("SELECT COUNT(DISTINCT category) FROM endpoints")
        category_count = cursor.fetchone()[0]
        assert category_count > 0

        cursor.execute(
            """
            SELECT path, method, description
            FROM endpoints
            WHERE path LIKE '%ticket%'
            LIMIT 3
            """
        )
        sample_tickets = cursor.fetchall()
        assert isinstance(sample_tickets, list)

