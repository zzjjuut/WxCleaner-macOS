import os


def move_to_trash(paths, send_to_trash):
    """Move existing paths to Trash and report only successful moves."""
    deleted = []
    errors = []

    for path in paths:
        if not path or not path.strip():
            errors.append(f"路径无效或不存在: {path}")
            continue

        normalized = os.path.normpath(path)
        if not normalized or not os.path.exists(normalized):
            errors.append(f"路径无效或不存在: {normalized}")
            continue

        try:
            send_to_trash(normalized)
            deleted.append(path)
        except Exception as error:
            errors.append(f"删除失败: {normalized}\n{error}")

    return deleted, errors
