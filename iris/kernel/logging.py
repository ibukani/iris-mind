"""
Kernel 診断ログ設定。

- ファイル出力: 常に有効（file_level でレベル制御）
- コンソール出力: console_level が設定されている場合のみ stderr へ
  （UI 表示は Output プロセスの責務。このハンドラは Kernel 自身の診断用）

使用方法:
    from iris.kernel.logging import setup_logging
    setup_logging(config.logging)
"""

from __future__ import annotations

from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import sys

from .config import LoggingConfig

_CONSOLE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
_FILE_DATE = "%Y-%m-%d %H:%M:%S"


class _ConsoleHandler(logging.StreamHandler):
    """コンソール出力用ハンドラ。ログ行の前に \r を挿入し、直後にプロンプトを再表示する。

    これにより ``input("> ")`` のプロンプト行にログが混入する問題を防ぐ。
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.stream.write("\r" + msg + "\n> ")
            self.flush()
        except Exception:
            self.handleError(record)


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
    """ルートロガーを構成する。"""
    root = logging.getLogger()
    root.setLevel(cfg.file_level.upper())

    # --- ファイルハンドラ（常に有効） ---
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
    file_handler.setLevel(cfg.file_level.upper())
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_FILE_DATE))
    root.addHandler(file_handler)

    # --- コンソールハンドラ（条件付き。Kernel 診断用、UI 表示とは無関係） ---
    # カスタムハンドラ: ログ出力時に \r で行頭に戻り、ログ行を出力後、プロンプトを再表示する
    if cfg.console_level:
        fmt = cfg.console_format or _CONSOLE_FORMAT
        console_handler = _ConsoleHandler(sys.stderr)
        console_handler.setLevel(cfg.console_level.upper())
        console_handler.setFormatter(logging.Formatter(fmt))
        root.addHandler(console_handler)

    # --- 既存の起動世代クリーンアップ ---
    _cleanup_old_sessions(log_dir, cfg.backup_count)

    # --- ロガー個別レベルの適用（config.loggers） ---
    for name, level in cfg.loggers.items():
        logging.getLogger(name).setLevel(level.upper())

    log_overrides = ", ".join(f"{k}={v}" for k, v in cfg.loggers.items()) or "(none)"
    logging.info(
        "Logging initialized: file_level=%s, console_level=%s, loggers=%s, file=%s",
        cfg.file_level,
        cfg.console_level or "(none)",
        log_overrides,
        log_path,
    )
