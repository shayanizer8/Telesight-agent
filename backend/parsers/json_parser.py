import json


def parse_json(file_path: str) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        if not isinstance(payload, dict):
            raise ValueError("JSON file must contain an object at the top level")

        return payload
    except Exception as exc:
        raise RuntimeError(f"Failed to parse JSON file '{file_path}': {exc}") from exc