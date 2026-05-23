"""
Kernel 診断ログ設定 (loguru).

- ファイル出力: 常に有効（file_level でレベル制御）
- コンソール出力: console_level が設定されている場合のみ stderr へ
  （UI 表示は Output プロセスの責務。このハンドラは Kernel 自身の診断用）

使用方法:
    from iris.kernel.logging import setup_logging
    setup_logging(config.logging)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
import re
import sys

from loguru import logger

from .config import LoggingConfig

_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} [{level}] {name} ({file}:{line}): {message}"
_CONSOLE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} [{level}] {name}: {message}"

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


def _module_level_filter(levels: dict[str, str]) -> Callable[[dict], bool]:
    """loguru フィルタ: 指定モジュールのログレベルを個別制御する。"""
    _level_map = {name: logger.level(lvl).no for name, lvl in levels.items()}

    def _filter(record: dict) -> bool:
        name = record["name"]
        if not name:
            return True
        for prefix, lvl_no in _level_map.items():
            if name.startswith(prefix):
                return bool(record["level"].no >= lvl_no)
        return True

    return _filter


def _console_sink(msg: object) -> None:
    """コンソール出力: 行頭に \\r を挿入し、プロンプト再表示で追従する。"""
    text = str(msg).rstrip("\n")
    sys.stderr.write("\r" + text + "\n> ")
    sys.stderr.flush()


def setup_logging(cfg: LoggingConfig) -> None:
    """loguru でログ構成を行う。"""
    logger.remove()

    log_dir = Path(cfg.dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"iris_{now}.log"

    filter_fn = _module_level_filter(cfg.loggers) if cfg.loggers else None

    # ファイル sink（常に有効）
    logger.add(
        sink=str(log_path),
        level=cfg.file_level.upper(),
        format=_FILE_FORMAT,
        rotation=cfg.max_bytes,
        retention=3,
        encoding="utf-8",
        filter=filter_fn,
    )

    # コンソール sink（条件付き。Kernel 診断用、UI 表示とは無関係）
    if cfg.console_level:
        fmt = cfg.console_format or _CONSOLE_FORMAT
        logger.add(
            sink=_console_sink,
            level=cfg.console_level.upper(),
            format=fmt,
            filter=filter_fn,
        )

    # 起動世代クリーンアップ
    _cleanup_old_sessions(log_dir, cfg.backup_count)

    log_overrides = ", ".join(f"{k}={v}" for k, v in cfg.loggers.items()) or "(none)"
    logger.info(
        "Logging initialized: file_level={}, console_level={}, loggers={}, file={}",
        cfg.file_level,
        cfg.console_level or "(none)",
        log_overrides,
        log_path,
    )
