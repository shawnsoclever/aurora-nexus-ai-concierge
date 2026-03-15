from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams

from core.config import get_settings
from core.llm import get_agent_model_name


def get_model_name() -> str:
    return get_agent_model_name()


def get_mcp_toolset() -> MCPToolset:
    settings = get_settings()
    return MCPToolset(
        connection_params=StreamableHTTPConnectionParams(url=settings.mcp_server_url)
    )
