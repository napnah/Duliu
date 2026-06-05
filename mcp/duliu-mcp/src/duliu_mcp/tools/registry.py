from mcp.server.fastmcp import FastMCP

from duliu_mcp.tools import artifacts, export_data, problems


def register_tools(mcp: FastMCP) -> None:
    problems.register(mcp)
    artifacts.register(mcp)
    export_data.register(mcp)
