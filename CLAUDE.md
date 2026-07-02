# 项目工作约定

## 工具使用

- **不要使用 WebSearch**:该功能在本环境不可用,调用会失败。
- **改用 context7**:涉及任何库、框架、SDK、API、CLI 工具时,用 context7 MCP 工具(`mcp__plugin_context7_context7__resolve-library-id` 解析库 ID,再 `mcp__plugin_context7_context7__query-docs` 拉取当前文档与代码示例)获取准确信息,而非凭记忆作答。
- WebFetch 仅在必要时使用(且目标 URL 已知可达时)。

## 开发环境

- 详细环境与版本锁定见 `docs/superpowers/specs/` 下的设计文档。
- ROS1 Noetic 锁定 Python 3.8;AI/agent 相关库可能要求 Python 3.10+,需要双虚拟环境(见总体架构 spec)。

## 文档约定

- `docs/设计稿/`(初始设计稿.md、ui.md)是项目的**原始 prompt**,反映最初设想,部分内容可能不合理或已过时。
- 权威设计以 `docs/superpowers/specs/` 下的 spec 为准;原始 prompt 与 spec 冲突时,一律以 spec 为准。
- 原始 prompt 仅作为需求背景参考,不再追加更新。
