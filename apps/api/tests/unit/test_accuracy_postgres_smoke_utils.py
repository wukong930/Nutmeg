from __future__ import annotations

from nutmeg.accuracy.postgres_smoke import split_sql_statements


def test_split_sql_statements_ignores_empty_segments() -> None:
    assert split_sql_statements(
        """
        CREATE TABLE example (id INT);

        CREATE INDEX example_id_idx ON example(id);
        """
    ) == [
        "CREATE TABLE example (id INT)",
        "CREATE INDEX example_id_idx ON example(id)",
    ]


def test_split_sql_statements_ignores_comment_only_segments() -> None:
    assert split_sql_statements(
        """
        -- already applied by previous migration;
        CREATE TABLE example (id INT);
        """
    ) == ["CREATE TABLE example (id INT)"]


def test_split_sql_statements_keeps_semicolons_inside_quoted_values() -> None:
    assert split_sql_statements(
        """
        INSERT INTO review_markers (summary)
        VALUES ('Seeded template review marker; needs follow-up');

        SELECT 'done';
        """
    ) == [
        (
            "INSERT INTO review_markers (summary)\n"
            "        VALUES ('Seeded template review marker; needs follow-up')"
        ),
        "SELECT 'done'",
    ]


def test_split_sql_statements_keeps_semicolons_inside_dollar_blocks() -> None:
    assert split_sql_statements(
        """
        DO $$
        BEGIN
          PERFORM 1;
        END $$;

        CREATE TABLE example (id INT);
        """
    ) == [
        "DO $$\n        BEGIN\n          PERFORM 1;\n        END $$",
        "CREATE TABLE example (id INT)",
    ]
