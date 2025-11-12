import unittest.mock

import openai
import pydantic
import pytest

from spark.models.openai import OpenAIModel
from spark.models.exceptions import ContextWindowOverflowException, ModelThrottledException


from spark.models.openai import OpenAIModel


class _StubFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _StubToolCall:
    def __init__(self, id: str, function: _StubFunction) -> None:
        self.id = id
        self.type = "function"
        self.function = function


class _StubMessage:
    def __init__(self, content, tool_calls) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _StubChoice:
    def __init__(self, finish_reason: str, message: _StubMessage) -> None:
        self.finish_reason = finish_reason
        self.message = message


class _StubResponse:
    def __init__(self, choices) -> None:
        self.choices = choices


def test_openai_normalizes_tool_calls_finish_reason_and_parses_tool_arguments():
    model = OpenAIModel(model_id="dummy-model")

    fn = _StubFunction(name="word_count", arguments='{"query": "hello world"}')
    tool_call = _StubToolCall(id="call_1", function=fn)
    message = _StubMessage(content=None, tool_calls=[tool_call])
    choice = _StubChoice(finish_reason="tool_calls", message=message)
    response = _StubResponse(choices=[choice])

    result = model._format_response(response)  # type: ignore[arg-type]

    assert result["stop_reason"] == "tool_use"
    assert result["tool_calls"] and result["tool_calls"][0]["function"]["name"] == "word_count"
    assert result["tool_calls"][0]["function"]["arguments"] == {"query": "hello world"}
    assert result.get("content") is None


def test_openai_maps_text_content_when_present():
    model = OpenAIModel(model_id="dummy-model")

    message = _StubMessage(content="Hello", tool_calls=None)
    choice = _StubChoice(finish_reason="stop", message=message)
    response = _StubResponse(choices=[choice])

    result = model._format_response(response)  # type: ignore[arg-type]

    assert result["stop_reason"] == "stop"
    assert result.get("tool_calls") is None or result.get("tool_calls") == []
    assert result.get("content") == "Hello"



@pytest.fixture
def openai_client():
    with unittest.mock.patch.object(openai, "AsyncOpenAI") as mock_client_cls:
        mock_client = unittest.mock.AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        yield mock_client


@pytest.fixture
def model_id():
    return "m1"


@pytest.fixture
def model(openai_client, model_id):
    _ = openai_client

    return OpenAIModel(model_id=model_id, params={"max_tokens": 1})


@pytest.fixture
def messages():
    return [{"role": "user", "content": [{"text": "test"}]}]


@pytest.fixture
def tool_specs():
    return [
        {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {"type": "string"},
                },
                "required": ["input"],
            },
        },
    ]


@pytest.fixture
def system_prompt():
    return "s1"


@pytest.fixture
def test_output_model_cls():
    class TestOutputModel(pydantic.BaseModel):
        name: str
        age: int

    return TestOutputModel


def test__init__(model_id):
    model = OpenAIModel(model_id=model_id, params={"max_tokens": 1})

    tru_config = model.get_config()
    exp_config = {"model_id": "m1", "params": {"max_tokens": 1}}

    assert tru_config == exp_config


def test_update_config(model, model_id):
    model.update_config(model_id=model_id)

    tru_model_id = model.get_config().get("model_id")
    exp_model_id = model_id

    assert tru_model_id == exp_model_id


@pytest.mark.parametrize(
    "content, exp_result",
    [
        # Document
        (
            {
                "document": {
                    "format": "pdf",
                    "name": "test doc",
                    "source": {"bytes": b"document"},
                },
            },
            {
                "file": {
                    "file_data": "data:application/pdf;base64,ZG9jdW1lbnQ=",
                    "filename": "test doc",
                },
                "type": "file",
            },
        ),
        # Image
        (
            {
                "image": {
                    "format": "jpg",
                    "source": {"bytes": b"image"},
                },
            },
            {
                "image_url": {
                    "detail": "auto",
                    "format": "image/jpeg",
                    "url": "data:image/jpeg;base64,aW1hZ2U=",
                },
                "type": "image_url",
            },
        ),
        # Text
        (
            {"text": "hello"},
            {"type": "text", "text": "hello"},
        ),
    ],
)
def test_format_request_message_content(content, exp_result):
    tru_result = OpenAIModel.format_request_message_content(content)
    assert tru_result == exp_result


def test_format_request_message_tool_call():
    tool_use = {
        "input": {"expression": "2+2"},
        "name": "calculator",
        "toolUseId": "c1",
    }

    tru_result = OpenAIModel.format_request_message_tool_call(tool_use)
    exp_result = {
        "function": {
            "arguments": '{"expression": "2+2"}',
            "name": "calculator",
        },
        "id": "c1",
        "type": "function",
    }
    assert tru_result == exp_result


def test_format_request_tool_message():
    tool_result = {
        "content": [{"text": "4"}, {"json": ["4"]}],
        "status": "success",
        "toolUseId": "c1",
    }

    tru_result = OpenAIModel.format_request_tool_message(tool_result)
    exp_result = {
        "content": [{"text": "4", "type": "text"}, {"text": '["4"]', "type": "text"}],
        "role": "tool",
        "tool_call_id": "c1",
    }
    assert tru_result == exp_result


def test_format_request_tool_choice_auto():
    tool_choice = {"auto": {}}

    tru_result = OpenAIModel._format_request_tool_choice(tool_choice)
    exp_result = {"tool_choice": "auto"}
    assert tru_result == exp_result


def test_format_request_tool_choice_any():
    tool_choice = {"any": {}}

    tru_result = OpenAIModel._format_request_tool_choice(tool_choice)
    exp_result = {"tool_choice": "required"}
    assert tru_result == exp_result


def test_format_request_tool_choice_tool():
    tool_choice = {"tool": {"name": "test_tool"}}

    tru_result = OpenAIModel._format_request_tool_choice(tool_choice)
    exp_result = {"tool_choice": {"type": "function", "function": {"name": "test_tool"}}}
    assert tru_result == exp_result


def test_format_request_messages(system_prompt):
    messages = [
        {
            "content": [],
            "role": "user",
        },
        {
            "content": [{"text": "hello"}],
            "role": "user",
        },
        {
            "content": [
                {"text": "call tool"},
                {
                    "toolUse": {
                        "input": {"expression": "2+2"},
                        "name": "calculator",
                        "toolUseId": "c1",
                    },
                },
            ],
            "role": "assistant",
        },
        {
            "content": [{"toolResult": {"toolUseId": "c1", "status": "success", "content": [{"text": "4"}]}}],
            "role": "user",
        },
    ]

    tru_result = OpenAIModel.format_request_messages(messages, system_prompt)
    exp_result = [
        {
            "content": system_prompt,
            "role": "system",
        },
        {
            "content": [{"text": "hello", "type": "text"}],
            "role": "user",
        },
        {
            "content": [{"text": "call tool", "type": "text"}],
            "role": "assistant",
            "tool_calls": [
                {
                    "function": {
                        "name": "calculator",
                        "arguments": '{"expression": "2+2"}',
                    },
                    "id": "c1",
                    "type": "function",
                }
            ],
        },
        {
            "content": [{"text": "4", "type": "text"}],
            "role": "tool",
            "tool_call_id": "c1",
        },
    ]
    assert tru_result == exp_result


def test_format_request(model, messages, tool_specs, system_prompt):
    tru_request = model.format_request(messages, tool_specs, system_prompt)
    exp_request = {
        "messages": [
            {
                "content": system_prompt,
                "role": "system",
            },
            {
                "content": [{"text": "test", "type": "text"}],
                "role": "user",
            },
        ],
        "model": "m1",
        "stream": True,
        "stream_options": {"include_usage": True},
        "tools": [
            {
                "function": {
                    "description": "A test tool",
                    "name": "test_tool",
                    "parameters": {
                        "properties": {
                            "input": {"type": "string"},
                        },
                        "required": ["input"],
                        "type": "object",
                    },
                },
                "type": "function",
            },
        ],
        "max_tokens": 1,
    }
    assert tru_request == exp_request


def test_format_request_with_tool_choice_auto(model, messages, tool_specs, system_prompt):
    tool_choice = {"auto": {}}
    tru_request = model.format_request(messages, tool_specs, system_prompt, tool_choice)
    exp_request = {
        "messages": [
            {
                "content": system_prompt,
                "role": "system",
            },
            {
                "content": [{"text": "test", "type": "text"}],
                "role": "user",
            },
        ],
        "model": "m1",
        "stream": True,
        "stream_options": {"include_usage": True},
        "tools": [
            {
                "function": {
                    "description": "A test tool",
                    "name": "test_tool",
                    "parameters": {
                        "properties": {
                            "input": {"type": "string"},
                        },
                        "required": ["input"],
                        "type": "object",
                    },
                },
                "type": "function",
            },
        ],
        "tool_choice": "auto",
        "max_tokens": 1,
    }
    assert tru_request == exp_request


def test_format_request_with_tool_choice_any(model, messages, tool_specs, system_prompt):
    tool_choice = {"any": {}}
    tru_request = model.format_request(messages, tool_specs, system_prompt, tool_choice)
    exp_request = {
        "messages": [
            {
                "content": system_prompt,
                "role": "system",
            },
            {
                "content": [{"text": "test", "type": "text"}],
                "role": "user",
            },
        ],
        "model": "m1",
        "stream": True,
        "stream_options": {"include_usage": True},
        "tools": [
            {
                "function": {
                    "description": "A test tool",
                    "name": "test_tool",
                    "parameters": {
                        "properties": {
                            "input": {"type": "string"},
                        },
                        "required": ["input"],
                        "type": "object",
                    },
                },
                "type": "function",
            },
        ],
        "tool_choice": "required",
        "max_tokens": 1,
    }
    assert tru_request == exp_request


def test_format_request_with_tool_choice_tool(model, messages, tool_specs, system_prompt):
    tool_choice = {"tool": {"name": "test_tool"}}
    tru_request = model.format_request(messages, tool_specs, system_prompt, tool_choice)
    exp_request = {
        "messages": [
            {
                "content": system_prompt,
                "role": "system",
            },
            {
                "content": [{"text": "test", "type": "text"}],
                "role": "user",
            },
        ],
        "model": "m1",
        "stream": True,
        "stream_options": {"include_usage": True},
        "tools": [
            {
                "function": {
                    "description": "A test tool",
                    "name": "test_tool",
                    "parameters": {
                        "properties": {
                            "input": {"type": "string"},
                        },
                        "required": ["input"],
                        "type": "object",
                    },
                },
                "type": "function",
            },
        ],
        "tool_choice": {"type": "function", "function": {"name": "test_tool"}},
        "max_tokens": 1,
    }
    assert tru_request == exp_request


@pytest.mark.asyncio
async def test_get_json(openai_client, model, test_output_model_cls):
    pass


def test_config_validation_warns_on_unknown_keys(openai_client, captured_warnings):
    """Test that unknown config keys emit a warning."""
    OpenAIModel({"api_key": "test"}, model_id="test-model", invalid_param="test")

    assert len(captured_warnings) == 1
    assert "Invalid configuration parameters" in str(captured_warnings[0].message)
    assert "invalid_param" in str(captured_warnings[0].message)


def test_update_config_validation_warns_on_unknown_keys(model, captured_warnings):
    """Test that update_config warns on unknown keys."""
    model.update_config(wrong_param="test")

    assert len(captured_warnings) == 1
    assert "Invalid configuration parameters" in str(captured_warnings[0].message)
    assert "wrong_param" in str(captured_warnings[0].message)


def test_tool_choice_supported_no_warning(model, messages, captured_warnings):
    """Test that toolChoice doesn't emit warning for supported providers."""
    tool_choice = {"auto": {}}
    model.format_request(messages, tool_choice=tool_choice)

    assert len(captured_warnings) == 0


def test_tool_choice_none_no_warning(model, messages, captured_warnings):
    """Test that None toolChoice doesn't emit warning."""
    model.format_request(messages, tool_choice=None)

    assert len(captured_warnings) == 0


def test_format_request_messages_excludes_reasoning_content():
    """Test that reasoningContent is excluded from formatted messages."""
    messages = [
        {
            "content": [
                {"text": "Hello"},
                {"reasoningContent": {"reasoningText": {"text": "excluded"}}},
            ],
            "role": "user",
        },
    ]

    tru_result = OpenAIModel.format_request_messages(messages)

    # Only text content should be included
    exp_result = [
        {
            "content": [{"text": "Hello", "type": "text"}],
            "role": "user",
        },
    ]
    assert tru_result == exp_result


def test_format_request_messages_with_system_prompt_content():
    """Test format_request_messages with system_prompt_content parameter."""
    messages = [{"role": "user", "content": [{"text": "Hello"}]}]
    system_prompt_content = [{"text": "You are a helpful assistant."}]

    result = OpenAIModel.format_request_messages(messages, system_prompt=system_prompt_content)

    expected = [
        {"role": "system", "content": [{"text": "You are a helpful assistant."}]},
        {"role": "user", "content": [{"text": "Hello", "type": "text"}]},
    ]

    assert result == expected


def test_format_request_messages_with_none_system_prompt_content():
    """Test format_request_messages with system_prompt_content parameter."""
    messages = [{"role": "user", "content": [{"text": "Hello"}]}]

    result = OpenAIModel.format_request_messages(messages)

    expected = [{"role": "user", "content": [{"text": "Hello", "type": "text"}]}]

    assert result == expected
