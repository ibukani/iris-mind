"""
Capability Registry — ツールの一元管理と動的発見。

capabilities/*/server.py の register() 関数を動的に発見・登録する。
ConversationService から ToolExecutionEngine 経由で利用される。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


class Capability:
    """1つのツール（関数）を表す。"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
        allowed_roles: set[str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
        self.allowed_roles = allowed_roles or {"base", "smart"}

    def to_openai_tool(self) -> dict:
        """OpenAI 形式のツール定義を返す。"""
        required: list[str] = []
        clean_params: dict = {}
        for k, v in self.parameters.items():
            if v.get("required"):
                required.append(k)
            clean_params[k] = {kk: vv for kk, vv in v.items() if kk != "required"}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": clean_params,
                    "required": required,
                },
            },
        }

    def execute(self, **kwargs: object) -> str:
        """ツールを実行する。"""
        return self.func(**kwargs)


class CapabilityRegistry:
    """全 Capability を一元管理するレジストリ。"""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._drivers: dict[str, dict] = {}

    def register(self, capability: Capability) -> None:
        self._capabilities[capability.name] = capability

    def register_func(
        self,
        name: str | None = None,
        description: str | None = None,
        parameters: dict | None = None,
        allowed_roles: set[str] | None = None,
    ) -> Callable:
        """デコレータとして capability を登録する。"""

        def decorator(func: Callable) -> Callable:
            c = Capability(
                name=name or func.__name__,
                description=description or (func.__doc__ or "").strip(),
                parameters=parameters or {},
                func=func,
                allowed_roles=allowed_roles,
            )
            self.register(c)
            return func

        return decorator

    def get(self, name: str) -> Capability | None:
        return self._capabilities.get(name)

    def list_tools(self) -> list[dict]:
        return [c.to_openai_tool() for c in self._capabilities.values()]

    def list_tools_for_role(self, role: str) -> list[dict]:
        return [c.to_openai_tool() for c in self._capabilities.values() if role in c.allowed_roles]

    def register_driver(
        self,
        kind: str,
        driver_id: str,
        description: str,
        **kwargs: object,
    ) -> None:
        """I/O ドライバーを登録する。

        Args:
            kind: "input" または "output"
            driver_id: 一意の識別子 ("cli", "tcp", "file")
            description: 説明文
            kwargs: Provider固有の追加データ
        """
        self._drivers[driver_id] = {
            "kind": kind,
            "driver_id": driver_id,
            "description": description,
            **kwargs,
        }

    def list_drivers(self, kind: str | None = None) -> list[dict]:
        """登録されたドライバー一覧を返す。kind でフィルタ可能。"""
        if kind is None:
            return list(self._drivers.values())
        return [d for d in self._drivers.values() if d["kind"] == kind]

    def execute(self, name: str, **kwargs: object) -> str:
        cap = self.get(name)
        if not cap:
            return f"Error: capability '{name}' not found"
        return cap.execute(**kwargs)

    def discover_modules(
        self,
        base_paths: list[str] | None = None,
    ) -> None:
        """
        capabilities/*/server.py または driver.py を動的に発見・登録する。

        Args:
            base_paths: 検索するディレクトリ一覧。
                        デフォルトは ["iris/capabilities"]
        """
        if base_paths is None:
            base_paths = ["iris/capabilities"]

        import importlib

        for base in base_paths:
            p = Path(base).resolve()
            if not p.is_dir():
                continue
            base_module = base.replace("/", ".").replace("\\", ".")
            for module_file in p.rglob("*.py"):
                if module_file.name not in ("server.py", "driver.py"):
                    continue
                rel = module_file.relative_to(p)
                relative_module = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")
                module_path = f"{base_module}.{relative_module}"
                try:
                    mod = importlib.import_module(module_path)
                    if hasattr(mod, "register"):
                        mod.register(self)
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).warning(
                        "Failed to load capability %s: %s",
                        module_path,
                        e,
                    )
