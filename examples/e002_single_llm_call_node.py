"""
A simple example of a node that calls an LLM and returns the answer.
"""
from spark.utils.common import ask_llm, arun
from spark.nodes import Node


class AnswerNode(Node):
    def process(self, context):
        return ask_llm(context.inputs.content["question"])


async def main():
    node = AnswerNode()
    inputs = {"question": "In one sentence, why is the answer 42?"}
    out = await node.run(inputs)
    print("Question:", inputs["question"])
    print("Answer:", out)


if __name__ == "__main__":
    arun(main())