"""Template for an optional, trusted external ``encipher.py`` module.

Copy this file to ``encipher.py`` and implement only the signer classes you
need. The application executes that file with its own permissions, so never use
an implementation from an untrusted source.
"""

__all__ = ["ABogus", "XBogus", "XGnarly"]


class ABogus:
    def get_value(
        self,
        query: dict | str | None = None,
        data: dict | str | None = None,
        method: str | None = None,
        user_agent: str = "",
    ) -> str:
        raise NotImplementedError


class XBogus:
    def get_x_bogus(
        self,
        query: dict | str | None = None,
        data: dict | str | None = None,
        method: str | None = None,
        user_agent: str = "",
    ) -> str:
        raise NotImplementedError


class XGnarly:
    def generate(
        self,
        query: dict | str | None = None,
        data: dict | str | None = None,
        method: str | None = None,
        user_agent: str = "",
    ) -> str:
        raise NotImplementedError
