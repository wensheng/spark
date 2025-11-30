import pytest
from spark.agents.agent import Agent
from spark.nodes.base import ExecutionContext
from spark.nodes.types import NodeMessage
from spark.models.echo import EchoModel
from spark.agents.config import AgentConfig

class TransformingAgent(Agent):
    async def process(self, context: ExecutionContext | None = None) -> NodeMessage:
        # Ensure context is not None
        if context is None:
            context = ExecutionContext()
            
        # Call the core logic
        result = await self.work(context)
        
        # Transform the result
        if isinstance(result.content, str):
            result.content += " [TRANSFORMED]"
        elif isinstance(result.content, list) and len(result.content) > 0:
            if isinstance(result.content[0], dict):
                 text = result.content[0].get('text', '')
                 result.content[0]['text'] = text + " [TRANSFORMED]"
        
        return result

@pytest.mark.asyncio
async def test_agent_subclass_orchestration():
    """Verify that a subclass can intercept and transform the result using the orchestrate method."""
    config = AgentConfig(model=EchoModel())
    agent = TransformingAgent(config=config)
    
    input_msg = NodeMessage(content="Hello")
    context = ExecutionContext(inputs=input_msg)
    
    # This calls the overridden process, which calls orchestrate
    result = await agent.process(context)
    
    # Verify transformation
    if isinstance(result.content, str):
        assert "[TRANSFORMED]" in result.content
        assert "Hello" in result.content
    else:
        # If EchoModel ever changes to return structured content
        text = result.content[0]['text']
        assert "[TRANSFORMED]" in text
