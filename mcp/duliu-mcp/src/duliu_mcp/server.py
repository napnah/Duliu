"""Duliu MCP server entrypoint (stdio transport)."""

from mcp.server.fastmcp import FastMCP

from duliu_mcp import __version__
from duliu_mcp.tools import register_tools

mcp = FastMCP("duliu_mcp", version=__version__)
register_tools(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
