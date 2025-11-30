"""
Demonstrate how to use a node to stream data.
This is mostly useful for audio or video applications.
Spark Agents almost never need to stream data.
"""
import asyncio
import time
import threading

from spark.nodes import Node, ChannelMessage
from examples.fake_llm import fake_stream_llm


class StreamNode(Node):
    """
    node's go() method take data from node's mailbox and package it to ExecutionContext
    """
    async def process(self, context):
        """
        Here we just make the text UPPERCASE and print it out
        """
        print(context.inputs.content['text'].upper(), end="", flush=True)


def send_data_to_node(loop, node):
    should_run = True
    chunks = fake_stream_llm("What's the meaning of life?")
    try:
        for chunk in chunks:
            if not should_run:
                break
            if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content is not None:
                chunk_content = chunk.choices[0].delta.content
                # put the data to node's mailbox
                future = asyncio.run_coroutine_threadsafe(node.mailbox.send(ChannelMessage({'text': chunk_content})), loop)
                future.result()
                time.sleep(0.1)  # simulate latency
    except KeyboardInterrupt:
        print("User interrupted streaming.")
        should_run = False


async def main():
    node = StreamNode()

    loop = asyncio.get_running_loop()
    consumer_task = asyncio.create_task(node.go())

    producer_thread = threading.Thread(target=send_data_to_node, args=(loop, node), daemon=True)
    producer_thread.start()
    # Do not block the event loop while waiting for the producer to finish
    await asyncio.to_thread(producer_thread.join)

    # Producer is done; stop the consumer
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass


if __name__ == '__main__':
    asyncio.run(main())