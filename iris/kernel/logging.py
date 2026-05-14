"""
Kernel ログ設定 — ファイル出力の初期化。
コンソール出力はアダプター層（CLIなど）の責務。

使用方法:
    from iris.kernel.logging import setup_logging
    setup_logging(config.logging)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import LoggingConfig

_FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
_FILE_DATE = "%Y-%m-%d %H:%M:%S"

_LOG_PATTERN = re.compile(r"^iris_\d{8}_\d{6}\.log(?:\.\d+)?$")


def _cleanup_old_sessions(log_dir: Path, keep: int) -> None:
    """起動世代クリーンアップ — 古いログファイルを削除する。"""
    if keep < 1:
        return

    groups: dict[str, list[Path]] = {}
    for f in sorted(log_dir.iterdir()):
        if not _LOG_PATTERN.match(f.name):
            continue
        base = f.name.split(".log")[0]
        groups.setdefault(base, []).append(f)

    sorted_bases = sorted(groups.keys())
    if len(sorted_bases) > keep:
        for base in sorted_bases[:-keep]:
            for f in groups[base]:
                f.unlink(missing_ok=True)


def setup_logging(cfg: LoggingConfig) -> None:
    """ルートロガーを構成する（ファイル出力のみ。コンソール出力はアダプター層で管理）。"""
    root = logging.getLogger()
    root.setLevel(cfg.level.upper())

    # --- ファイルハンドラ ---
    log_dir = Path(cfg.dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"iris_{now}.log"

    file_handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=cfg.max_bytes,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(cfg.level.upper())
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_FILE_DATE))
    root.addHandler(file_handler)

    # --- 既存の起動世代クリーンアップ ---
    _cleanup_old_sessions(log_dir, cfg.backup_count)

    logging.info("Logging initialized: level=%s, file=%s", cfg.level, log_path)
