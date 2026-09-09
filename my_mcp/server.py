from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from dataclasses import dataclass
from .logging_config import setup_logging
from typing import Annotated
from pydantic import Field
from pathlib import Path

setup_logging()

import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


mcp_server = MCPServer("insurance-agent")

@dataclass
class FileSearchResult:
    query:str
    files: list[str]
    directories: list[str]
    total_returned: int
    truncated: bool

@mcp_server.tool(
        name="search_project_files",
        description="查找项目根路径下的文件或者文件夹名称",
        annotations=ToolAnnotations(read_only_hint=True),
        structured_output=True
)
def search_project_files(name_pattern:Annotated[str,Field(description="文件的搜索关键字",min_length=1,max_length=100)],
                         relative_dir:Annotated[str,Field(default=".",description="相对路径，默认'.'")] = ".",
                         max_results:Annotated[int,Field(default=5,description="最大返回的结果")] = 5) -> FileSearchResult:
    target = (PROJECT_ROOT / relative_dir).resolve()
    if not target.is_relative_to(PROJECT_ROOT):
        logger.error(f"禁止访问根路径以外的文件夹！")
        raise ValueError(f"禁止访问根目录以外的文件夹！")
    if not target.exists():
        raise FileNotFoundError(f"目录不存在: {target}")
    if not target.is_dir():
        raise ValueError(f"目标不是文件夹: {relative_dir}")

    keyword = name_pattern.strip()

    if not keyword:
        raise ValueError("搜索关键词不能为空")

    keyword_lower = keyword.lower()

    files:list[str] = []
    directories:list[str] = []

    # 多取一个，用于判断是否截断
    matched_count = 0

    logger.info(f"搜索路径：{str(target)}")

    for path in target.rglob("*"):
        if keyword_lower not in path.name.lower():
            continue

        matched_count += 1

        if len(files) + len(directories) >= max_results:
            continue

        relative_path = path.relative_to(PROJECT_ROOT).as_posix()

        if path.is_file():
            files.append(relative_path)
        elif path.is_dir():
            directories.append(relative_path)

    total_returned = len(files) + len(directories)

    return FileSearchResult(
        query=keyword,
        files=files,
        directories=directories,
        total_returned=total_returned,
        truncated=matched_count > total_returned
    )

if __name__ == "__main__":
    mcp_server.run(transport='stdio')