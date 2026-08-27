import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
LEGACY_REVISION = "20251021_add_notification_types_to_rules"
PIPELINE_REVISION = "20260815_message_delivery_pipeline"
HEAD_REVISION = "20260827_cleanup_rule_targets"


def _run_alembic(database: Path, revision: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "alembic", "upgrade", revision],
        cwd=BACKEND_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_legacy_rule_is_migrated_to_automatic_telegram_target(tmp_path):
    database = tmp_path / "legacy.db"
    _run_alembic(database, LEGACY_REVISION)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO forward_rules "
            "(name, source_chat_id, target_chat_id, target_chat_name, client_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("legacy", "-1001", "-2002", "archive", "account-a"),
        )
        connection.commit()

    _run_alembic(database, "head")

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(forward_rules)")
        }
        rule = connection.execute(
            "SELECT id, delivery_mode FROM forward_rules WHERE name = 'legacy'"
        ).fetchone()
        target = connection.execute(
            "SELECT id, target_type, config_json FROM delivery_targets"
        ).fetchone()
        binding = connection.execute(
            "SELECT rule_id, target_id FROM rule_delivery_targets"
        ).fetchone()
        delivery_indexes = {
            row[1]: row[2]
            for row in connection.execute("PRAGMA index_list(delivery_jobs)")
        }
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]

    assert revision == HEAD_REVISION
    assert rule[1] == "auto"
    assert target[1] == "telegram"
    assert json.loads(target[2]) == {
        "client_id": "account-a",
        "chat_id": "-2002",
        "chat_name": "archive",
    }
    assert binding == (rule[0], target[0])
    assert delivery_indexes["ix_delivery_jobs_delivery_id"] == 1
    assert "target_chat_id" not in columns
    assert "target_chat_name" not in columns
    assert {"queued_messages", "message_resources", "delivery_jobs"} <= tables
    assert not {
        "message_logs",
        "media_files",
        "download_tasks",
        "media_monitor_rules",
        "resource_monitor_rules",
        "notification_rules",
        "notification_logs",
    } & tables


def test_orphan_rule_target_associations_are_removed(tmp_path):
    database = tmp_path / "orphan.db"
    _run_alembic(database, LEGACY_REVISION)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO forward_rules "
            "(name, source_chat_id, target_chat_id, target_chat_name, client_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("deleted", "-1001", "-2002", "archive", "account-a"),
        )
        connection.commit()

    _run_alembic(database, PIPELINE_REVISION)

    with sqlite3.connect(database) as connection:
        rule_id, target_id = connection.execute(
            "SELECT rule_id, target_id FROM rule_delivery_targets"
        ).fetchone()
        connection.execute("DELETE FROM forward_rules WHERE id = ?", (rule_id,))
        connection.commit()
        assert connection.execute(
            "SELECT rule_id, target_id FROM rule_delivery_targets"
        ).fetchone() == (rule_id, target_id)

    _run_alembic(database, "head")

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM rule_delivery_targets"
        ).fetchone()[0] == 0
