"""
Tests for Agent prompt building and templates.
"""

import pytest
from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.agents.memory import MemoryPolicyType
from spark.models.echo import EchoModel
from spark.nodes.types import NodeMessage, ExecutionContext


class TestPromptBuilding:
    """Test agent prompt building."""

    def test_build_prompt_with_simple_string(self):
        """Test building prompt from simple string input."""
        agent = Agent()
        context = ExecutionContext(
            inputs=NodeMessage(content="Hello", metadata={}),
            state=agent.state
        )

        messages = agent.build_prompt(context)

        assert len(messages) == 1
        assert messages[0]['role'] == 'user'
        assert messages[0]['content'][0]['text'] == 'Hello'

    def test_build_prompt_with_dict_input(self):
        """Test building prompt from dict input."""
        agent = Agent()
        context = ExecutionContext(
            inputs=NodeMessage(content={'query': 'test'}, metadata={}),
            state=agent.state
        )

        messages = agent.build_prompt(context)

        assert len(messages) == 1
        assert messages[0]['role'] == 'user'

    def test_build_prompt_with_existing_messages(self):
        """Test building prompt with existing messages in input."""
        agent = Agent()

        input_messages = [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi there'}
        ]

        context = ExecutionContext(
            inputs=NodeMessage(content={'messages': input_messages}, metadata={}),
            state=agent.state
        )

        messages = agent.build_prompt(context)

        # Should have the two input messages
        assert len(messages) == 2
        assert messages[0]['role'] == 'user'
        assert messages[1]['role'] == 'assistant'

    def test_build_prompt_respects_memory_policy(self):
        """Test build prompt respects memory policy."""
        config = AgentConfig(
            model=EchoModel(),
            memory_config={'policy': MemoryPolicyType.NULL}
        )
        agent = Agent(config=config)

        context = ExecutionContext(
            inputs=NodeMessage(content="Hello", metadata={}),
            state=agent.state
        )

        messages = agent.build_prompt(context)

        # NULL policy should not persist messages
        assert len(agent.memory_manager.memory) == 0

    def test_build_prompt_with_template(self):
        """Test building prompt with Jinja2 template."""
        config = AgentConfig(
            model=EchoModel(),
            prompt_template="Hello {{ name }}, you are {{ age }} years old."
        )
        agent = Agent(config=config)

        context = ExecutionContext(
            inputs=NodeMessage(content={'name': 'Alice', 'age': 30}, metadata={}),
            state=agent.state
        )

        messages = agent.build_prompt(context)

        assert len(messages) == 1
        text = messages[0]['content'][0]['text']
        assert 'Hello Alice' in text
        assert '30 years old' in text

    def test_build_prompt_persists_to_memory(self):
        """Test that built prompts are persisted to memory."""
        agent = Agent()

        context = ExecutionContext(
            inputs=NodeMessage(content="Test message", metadata={}),
            state=agent.state
        )

        agent.build_prompt(context)

        # Check memory was updated
        assert len(agent.memory_manager.memory) == 1
        assert agent.memory_manager.memory[0]['role'] == 'user'


class TestTemplateRendering:
    """Test Jinja2 template rendering."""

    def test_render_template_simple(self):
        """Test simple template rendering."""
        config = AgentConfig(
            model=EchoModel(),
            prompt_template="Hello {{ name }}"
        )
        agent = Agent(config=config)

        rendered = agent._render_template({'name': 'World'}, None)
        assert rendered == "Hello World"

    def test_render_template_with_state(self):
        """Test template rendering with state access."""
        config = AgentConfig(
            model=EchoModel(),
            prompt_template="Count: {{ count }}"
        )
        agent = Agent(config=config)

        # Add count to state
        agent._state['count'] = 42

        context = ExecutionContext(
            inputs=NodeMessage(content={}, metadata={}),
            state=agent.state
        )

        rendered = agent._render_template({}, context)
        assert rendered == "Count: 42"

    def test_render_template_with_history(self):
        """Test template rendering with history access."""
        config = AgentConfig(
            model=EchoModel(),
            prompt_template="Steps: {{ history|length }}"
        )
        agent = Agent(config=config)

        # Add history to state
        agent._state['history'] = [
            {'step': 1, 'action': 'search'},
            {'step': 2, 'action': 'analyze'}
        ]

        context = ExecutionContext(
            inputs=NodeMessage(content={}, metadata={}),
            state=agent.state
        )

        rendered = agent._render_template({}, context)
        assert rendered == "Steps: 2"

    def test_render_template_no_template(self):
        """Test rendering without template returns string of input."""
        agent = Agent()  # No template

        rendered = agent._render_template("Plain text", None)
        assert rendered == "Plain text"

    def test_render_template_complex(self):
        """Test complex template with loops and conditions."""
        template = """
        {% for item in items %}
        - {{ item }}
        {% endfor %}
        """
        config = AgentConfig(
            model=EchoModel(),
            prompt_template=template
        )
        agent = Agent(config=config)

        rendered = agent._render_template({'items': ['a', 'b', 'c']}, None)
        assert '- a' in rendered
        assert '- b' in rendered
        assert '- c' in rendered

    def test_render_template_with_filters(self):
        """Test template with Jinja2 filters."""
        config = AgentConfig(
            model=EchoModel(),
            prompt_template="{{ text|upper }}"
        )
        agent = Agent(config=config)

        rendered = agent._render_template({'text': 'hello'}, None)
        assert rendered == "HELLO"

    def test_render_template_fallback_on_error(self):
        """Test template falls back gracefully on error."""
        config = AgentConfig(
            model=EchoModel(),
            prompt_template="{{ undefined_var }}"
        )
        agent = Agent(config=config)

        # Should not raise, should fallback
        rendered = agent._render_template({'other': 'value'}, None)
        # Fallback should return something (not crash)
        assert rendered is not None


class TestMessageNormalization:
    """Test message format normalization."""

    def test_normalize_string_content(self):
        """Test normalizing string content to ContentBlock format."""
        agent = Agent()

        input_messages = [
            {'role': 'user', 'content': 'Hello'}
        ]

        context = ExecutionContext(
            inputs=NodeMessage(content={'messages': input_messages}, metadata={}),
            state=agent.state
        )

        messages = agent.build_prompt(context)

        # Should normalize to list of ContentBlocks
        assert isinstance(messages[0]['content'], list)
        assert messages[0]['content'][0]['text'] == 'Hello'

    def test_normalize_list_of_strings(self):
        """Test normalizing list of strings."""
        agent = Agent()

        input_messages = [
            {'role': 'user', 'content': ['Line 1', 'Line 2']}
        ]

        context = ExecutionContext(
            inputs=NodeMessage(content={'messages': input_messages}, metadata={}),
            state=agent.state
        )

        messages = agent.build_prompt(context)

        # Each string should become a text block
        assert len(messages[0]['content']) == 2
        assert messages[0]['content'][0]['text'] == 'Line 1'
        assert messages[0]['content'][1]['text'] == 'Line 2'

    def test_normalize_dict_content(self):
        """Test normalizing dict content."""
        agent = Agent()

        input_messages = [
            {'role': 'user', 'content': {'text': 'Hello'}}
        ]

        context = ExecutionContext(
            inputs=NodeMessage(content={'messages': input_messages}, metadata={}),
            state=agent.state
        )

        messages = agent.build_prompt(context)

        # Dict with 'text' key should be wrapped as ContentBlock
        assert isinstance(messages[0]['content'], list)
        assert messages[0]['content'][0]['text'] == 'Hello'

    def test_normalize_empty_content(self):
        """Test handling empty/falsy content."""
        agent = Agent()

        input_messages = [
            {'role': 'user', 'content': 'Hello'},
            None,  # Falsy entry - should be skipped
            {'role': 'assistant', 'content': 'Hi'}
        ]

        context = ExecutionContext(
            inputs=NodeMessage(content={'messages': input_messages}, metadata={}),
            state=agent.state
        )

        messages = agent.build_prompt(context)

        # Should skip None entry
        assert len(messages) == 2

    def test_normalize_preserves_content_blocks(self):
        """Test that existing ContentBlocks are preserved."""
        agent = Agent()

        input_messages = [
            {
                'role': 'user',
                'content': [
                    {'text': 'Hello'},
                    {'image': {'url': 'http://example.com/image.jpg'}}
                ]
            }
        ]

        context = ExecutionContext(
            inputs=NodeMessage(content={'messages': input_messages}, metadata={}),
            state=agent.state
        )

        messages = agent.build_prompt(context)

        # Should preserve the ContentBlocks as-is
        assert len(messages[0]['content']) == 2
        assert 'text' in messages[0]['content'][0]
        assert 'image' in messages[0]['content'][1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
