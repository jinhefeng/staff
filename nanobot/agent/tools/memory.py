"""Memory learning tool for dynamic knowledge ingestion."""

from datetime import datetime
from nanobot.agent.tools.base import Tool
from nanobot.agent.memory import MemoryStore

class MemorizeFactTool(Tool):
    """Tool allowing the agent to dynamically learn new facts and store them in memory."""
    
    name = "memorize_fact"
    description = "Use this tool to permanently save a new rule, preference, or fact taught by the Master into the Core Knowledge Base."
    
    def __init__(self, workspace):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self._is_master = False
        
    def set_context(self, is_master: bool = False) -> None:
        """Set the identity context for the current turn."""
        self._is_master = is_master

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category of the fact (e.g. 'Rule', 'Preference', 'Contact Info', 'General Fact').",
                },
                "fact_content": {
                    "type": "string",
                    "description": "The specific knowledge or rule to remember. Must be detailed and self-contained.",
                }
            },
            "required": ["category", "fact_content"],
        }
        
    async def execute(self, category: str, fact_content: str) -> str:
        """Execute the tool."""
        if not self._is_master:
            # We guide the LLM to deliver a polite and humorous rejection.
            return (
                "Permission Denied. Only the Master can teach you new core rules. "
                "However, please DO NOT say 'Permission Denied' to the user. "
                "Instead, reply politely and humorously. For example, you can say: "
                "'这听起来是个很棒的建议呢！不过在这个级别的手册上，我还没有权限直接落笔修改。我会把您的建议整理好交给老板定夺的～'"
            )
            
        current_global = self.memory.read_global()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Determine insertion format
        new_entry = f"\n- **[{category}]** ({now_str}): {fact_content}"
        
        # Find the [Learning Facts] section or append to the end.
        if "## Dynamic Learnt Facts" not in current_global:
            updated_global = current_global + f"\n\n## Dynamic Learnt Facts\n{new_entry}"
        else:
            updated_global = current_global + f"{new_entry}"

        await self.memory.write_global(updated_global)
        return "SUCCESS: The fact has been permanently recorded in the core memory bank."

