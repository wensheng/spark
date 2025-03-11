import pytest
from spark.messages.message import Message
from spark.agents.chat_agent import ChatAgent


def test_chat_agent_initialization():
    """Test that ChatAgent initializes with correct default values."""
    agent = ChatAgent()
    assert agent.name == "ChatBot"
    assert agent.chat_history == []


def test_chat_agent_custom_name():
    """Test that ChatAgent accepts a custom name."""
    agent = ChatAgent(name="CustomBot")
    assert agent.name == "CustomBot"


@pytest.mark.asyncio
async def test_chat_agent_process():
    """Test that ChatAgent processes messages correctly."""
    agent = ChatAgent()
    
    # Create a test message
    # test_message = Message.user("Hello, bot!")
    test_message = Message(role="user", content="Hello, bot!")
    
    # Process the message
    response = await agent.process(test_message)
    
    # Verify response content
    assert response.content == "Hello! You said: 'Hello, bot!'"
    assert response.role == "assistant"
    
    # Verify chat history is updated
    assert len(agent.chat_history) == 2
    assert agent.chat_history[0] == test_message


@pytest.mark.asyncio
async def test_chat_agent_multiple_messages():
    """Test that ChatAgent handles multiple messages correctly."""
    agent = ChatAgent()
    
    # Send multiple messages
    messages = [
        Message.user("First message"),
        Message.user("Second message"),
        Message.user("Third message")
    ]
    
    responses = []
    for msg in messages:
        responses.append(await agent.process(msg))
    
    # Verify all responses
    assert len(responses) == 3
    assert responses[0].content == "Hello! You said: 'First message'"
    assert responses[1].content == "Hello! You said: 'Second message'"
    assert responses[2].content == "Hello! You said: 'Third message'"
    
    # Verify chat history contains all messages
    assert len(agent.chat_history) == 6
    assert agent.chat_history[-1] == responses[-1]
    assert agent.chat_history[-2] == messages[-1]


@pytest.mark.asyncio
async def test_chat_agent_clear_history():
    """Test that ChatAgent can clear its chat history."""
    agent = ChatAgent()
    
    # Add some messages to history
    await agent.process(Message.user("Test message"))
    assert len(agent.chat_history) == 2
    
    # Clear history
    agent.clear_history()
    assert len(agent.chat_history) == 0
