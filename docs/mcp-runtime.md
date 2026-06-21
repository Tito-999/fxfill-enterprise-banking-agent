# MCP Runtime

## Classification: MCP_COMPATIBLE_IN_PROCESS_ADAPTER
Current implementation uses BankingMCPServer — an in-process adapter,
not a full subprocess MCP protocol transport. Tools are discovered and
invoked through direct Python calls.

## MCPClientAdapter
- Implements MCPClient protocol
- Injectable MCPTransport for testing
- Connect/disconnect lifecycle, tool discovery, invocation
- No authorization decisions — delegated to graph
