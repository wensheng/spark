import sys

import json_repair

from spark.nodes import Node
from spark.graphs.graph import Graph
from spark.utils.common import arun, ask_llm, search_web


class DecideAction(Node):
    async def process(self, context):
        """Call the LLM to decide whether to search or answer."""
        data = context.inputs.content
        if data.get('searches') is None:
            data['searches'] = [data['question']] 
        else:
            data['searches'].append(data['question'])
        question = data['question']
        searches = data['searches']
        
        print(f"🤔 Agent deciding what to do next...")
        
        # Create a prompt to help the LLM decide what to do next with proper yaml formatting
        prompt = f"""
### CONTEXT
You are a research assistant that can search the web.
Question: {question}
Previous Research: {searches}

### ACTION SPACE
[1] search
  Description: Look up more information on the web
  Parameters:
    - query (str): What to search for

[2] answer
  Description: Answer the question with current knowledge
  Parameters:
    - answer (str): Final answer to the question

## NEXT ACTION
Decide the next action based on the context and available actions.
Return your response in this json format:

{{
    "thinking": "<your step-by-step reasoning process>",
    "action": "search OR answer",
    "reason": "<why you chose this action>",
    "answer": "<if action is answer>",
    "search_query": "<specific search query if action is search>"
}}
"""

        # Call the LLM to make a decision
        messages = [{"role": "user", "content": prompt}]
        response = ask_llm(messages)
        print('Response:', response)
 
        decision = json_repair.loads(response)
        data['decision'] = decision

        """Save the decision and determine the next step in the flow."""
        # If LLM decided to search, save the search query
        decision = data['decision']
        action = decision['action']
        data['do_search'] = action
        if action == "search":
            data["search_query"] = decision["search_query"]
            print(f"🔍 Agent decided to search for: {decision['search_query']}")
        else:
            # save the context if LLM gives the answer without searching.
            # self.ctx["searches"].append({'SEARCH': '', 'RESULTS': decision["answer"]})
            data["searches"] = decision["answer"]
            print(f"💡 Agent decided to answer the question")
        
        return data


class SearchWeb(Node):
    async def process(self, context):
        """Search the web for the given query."""
        data = context.inputs.content
        print(f"🌐 Searching the web for: {data['search_query']}")
        data['results'] = search_web(data['search_query'])
        data["searches"].append({'SEARCH': data["search_query"],  'RESULTS': data['results']})
    
        # Add the search results to the context in the shared store
        data["searches"].append({'SEARCH': data["search_query"],  'RESULTS': data['results']})
        
        print(f"📚 Found information, analyzing results...")
        
        # Always go back to the decision node after searching
        return data


class AnswerQuestion(Node):
    async def process(self, context):
        """Call the LLM to generate a final answer."""
        data = context.inputs.content
        question = data["question"]
        if isinstance(data['searches'], str):
            research = data['searches']
        else:
            research = '\n'.join([f'SEARCH:{s["SEARCH"]}\nRESULTS:{s["RESULTS"]}' for s in data['searches']['SEARCH']])
        
        print(f"✍️ Crafting final answer...")
        
        # Create a prompt for the LLM to answer the question
        prompt = f"""
### CONTEXT
Based on the following information, answer the question.
Question: {question}
Research: {research}

## YOUR ANSWER:
Provide a comprehensive answer using the research results.
"""
        # Call the LLM to generate an answer
        messages = [{"role": "user", "content": prompt}]
        answer = ask_llm(messages)
        print(f"✅ Answer generated successfully")
    
        print(f"💡 Answer: {answer}")


def create_agent_flow():
    """
    Create and connect the nodes to form a complete agent flow.
    
    The flow works like this:
    1. DecideAction node decides whether to search or answer
    2. If search, go to SearchWeb node
    3. If answer, go to AnswerQuestion node
    4. After SearchWeb completes, go back to DecideAction
    
    Returns:
        Flow: A complete research agent flow
    """
    # Create instances of each node
    decide = DecideAction()
    search = SearchWeb()
    answer = AnswerQuestion()
    
    decide.on(do_search='search') >> search
    decide.on(do_search='answer') >> answer
    search >> decide
    
    return Graph(start=decide) 


async def main():
    """Simple function to process a question."""
    # Default question
    default_question = "Who won the Nobel Prize in Physics 2025?"
    
    # Get question from command line if provided with --
    question = default_question
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            question = arg[2:]
            break
    
    # Create the agent flow
    agent_flow = create_agent_flow()
    
    # Process the question
    print(f"🤔 Processing question: {question}")
    await agent_flow.run({"question": question})

if __name__ == "__main__":
    arun(main())