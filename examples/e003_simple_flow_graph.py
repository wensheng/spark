"""
Text transformation loop
"""
from spark.nodes import Node, EdgeCondition
from spark.graphs.graph import Graph
from spark.utils import arun

USE_SHORTHANDS = True


class TextInputNode(Node):
    def process(self, context):
        text = input("Enter text to convert\n")
        print("\nChoose transformation:")
        print("1. Convert to UPPERCASE")
        print("2. Convert to lowercase")
        print("3. Reverse text")
        print("4. Exit")
        choice = input("\nYour choice (1-4): ")
        if USE_SHORTHANDS:
            return {'text': text, 'choice': choice, 'Continue': choice in ['1', '2', '3']}
        return {'text': text, 'choice': choice}


class TextTransformNode(Node):
    def process(self, context):
        inputs = context.inputs.content
        choice = inputs.get("choice")
        txt = inputs.get('text', '')
        if choice == "1":
            result = txt.upper()
        elif choice == "2":
            result = txt.lower()
        elif choice == "3":
            result = txt[::-1]
        elif choice == "4":
            return {'Continue': False}
        else:
            result = "Invalid option!"
            return {'Continue': True}

        print("\nResult:", result)

        if input("\nConvert another text? (y/n): ").lower() == 'y':
            return {'Continue': True}
        else:
            return {'Continue': False}


async def main():
    text_input = TextInputNode()
    text_transform = TextTransformNode()

    if USE_SHORTHANDS:
        # use shorthand edge syntax
        text_input.on(Continue=True) >> text_transform
        text_transform.on(Continue=True) >> text_input
    else:
        text_input.goto(
            text_transform,
            condition=EdgeCondition(lambda n: n.outputs.content.get('choice') in ['1', '2', '3'])
        )
        text_transform.goto(
            text_input,
            condition=EdgeCondition(lambda n: n.outputs.content and n.outputs.content.get('Continue') == True)
        )

    # Create flow
    flow = Graph(start=text_input) 

    print("\nWelcome to Text Converter!")
    print("=========================")
    
    # Run the flow
    result = await flow.run()
    print("\nThank you for using Text Converter!")
    print(f"\nFinal result: {result}")


if __name__ == "__main__":
    arun(main())