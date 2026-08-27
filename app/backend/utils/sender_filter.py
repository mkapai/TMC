"""Sender allow/deny list filtering."""
import json
from typing import Any, Optional


class SenderFilter:
    @staticmethod
    def parse_sender_list(value: Optional[str]) -> list[dict]:
        if not value:
            return []
        value = value.strip()
        if value.startswith(("[", "{")):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                pass
        result = []
        for item in (part.strip().lstrip("@") for part in value.split(",")):
            if item:
                result.append({
                    "id": item if item.isdigit() else None,
                    "username": None if item.isdigit() else item,
                })
        return result

    @classmethod
    def is_sender_allowed(
        cls,
        sender_id: str,
        sender_username: Optional[str],
        filter_mode: str,
        whitelist_json: Optional[str],
        blacklist_json: Optional[str],
    ) -> bool:
        entries = cls.parse_sender_list(
            whitelist_json if filter_mode == "whitelist" else blacklist_json
        )
        matched = any(
            (entry.get("id") is not None and str(entry["id"]) == str(sender_id))
            or (sender_username and entry.get("username") == sender_username)
            for entry in entries
        )
        if filter_mode == "whitelist":
            return matched
        if filter_mode == "blacklist":
            return not matched
        return True

    @staticmethod
    def get_sender_info(message: Any) -> dict[str, Any]:
        sender = getattr(message, "sender", None)
        return {
            "id": str(getattr(sender, "id", None) or getattr(message, "sender_id", "") or "") or None,
            "username": getattr(sender, "username", None),
            "first_name": getattr(sender, "first_name", None),
            "last_name": getattr(sender, "last_name", None),
        }
