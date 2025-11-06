"""
Example of parallel translation using different node types.
"""
import os
import time
import sys
from asyncio import sleep
from pathlib import Path
from spark.nodes.nodes import MultipleThreadNode, MultipleProcessNode, SequentialNode
from spark.utils.common import arun, ask_llm

proj_dir = Path(__file__).parents[1]
readme_file = proj_dir / 'README.md'
output_dir = proj_dir / 'examples' / 'data' / 'translations'

FAKE_LLM = True


async def proc(item):
    text= item['text']
    language = item['language']
    
    prompt = f"""
Please translate the following markdown file into {language}. 
But keep the original markdown format, links and code blocks.
Directly return the translated text, without any other text or comments.

Original: 
{text}

Translated:"""

    filename = os.path.join(output_dir, f'spark_{language.upper()}.md')
    if FAKE_LLM:
        await sleep(2)

    else:
        result = ask_llm(prompt, model='gpt-5-nano')
        print(f'Translated {language} text')

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(result)
        
    print(f'Saved translation to {filename}')


class SerialTranslateTextNode(SequentialNode):
    async def process_item(self, item):
        await proc(item)


class ThreadTranslateTextNode(MultipleThreadNode):
    async def process_item(self, item):
        await proc(item)


class ParallelTranslateTextNode(MultipleProcessNode):
    async def process_item(self, item):
        await proc(item)



async def main(n):
    start_time = time.time()
    with open(readme_file, 'r') as f:
        text = f.read()
    os.makedirs(output_dir, exist_ok=True)
    
    data = [
        {'text': text, 'language': lang} for lang in
        ['Chinese', 'Spanish', 'Japanese', 'German', 'French', 'Korean']
    ]

    if n == 1:
        translate_node = SerialTranslateTextNode()
    elif n == 2:
        translate_node = ThreadTranslateTextNode()
    elif n == 3:
        translate_node = ParallelTranslateTextNode()
    else:
        raise ValueError(f'Invalid number of nodes: {n}')

    await translate_node.do(data)

    print('\n=== Translation Complete ===')
    print(f'Translations saved to: {output_dir}')
    print(f'Total time taken: {time.time() - start_time:.2f} seconds')
    print('============================')


if __name__ == '__main__':
    try:
        n = int(sys.argv[1])
        assert n in [1, 2, 3]
    except:
        n = 1
    arun(main(n))
