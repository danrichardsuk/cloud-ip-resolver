"""PyInstaller entry point for the Windows desktop executable.

The normal development launcher is installed from ``pyproject.toml``. PyInstaller
needs a concrete script file to analyse, so this tiny wrapper imports and calls
the same desktop ``main`` function rather than duplicating any GUI or resolver
logic.
"""

from cloud_ip_resolver.desktop import main


if __name__ == "__main__":
    raise SystemExit(main())
