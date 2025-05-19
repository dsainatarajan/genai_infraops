import os
import sys
import tempfile
from typing import List, TypedDict
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Load sample Kubernetes reference snippet as context
with open('python_kubernetes_extended_ref.py') as f:
    K8S_REF = f.read()

# Langraph imports
to_install = ['langchain_core', 'langchain_openai', 'langchain_community', 'langgraph']
for pkg in to_install:
    os.system(f"pip install -U {pkg}")

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

# Chat model
ept_model = 'gpt-4o'
llm = ChatOpenAI(temperature=0, model=ept_model)

# Prompt for generating Python Kubernetes client code and validation
code_gen_prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a coding assistant expert in the Kubernetes Python SDK. "
        "Use the following reference code to guide your solutions and validation scripts:\n```python\n{context}\n```\n"
        "When the user asks for a task, generate two Python code blocks:\n"
        "1) Solution: code using kubernetes.client to perform the task.\n"
        "2) Validator: code using kubernetes.client to verify the desired state in the cluster.\n"
        "Include approach explanation, import statements, and complete code blocks for both."
    )),
    ("placeholder", "{messages}")
])

class CodeSolution(BaseModel):
    prefix: str = Field(description="Explanation of the approach")
    imports: str = Field(description="Imports for solution and validator")
    code: str = Field(description="Solution code block")
    validator: str = Field(description="Validation code block")

# Chain for code generation
code_gen_chain = code_gen_prompt | llm.with_structured_output(CodeSolution)

# Graph state definition
class GraphState(TypedDict):
    error: str
    error_part: str  # 'solution' or 'validator'
    messages: List
    generation: CodeSolution
    iterations: int
    proceed: str     # human-in-the-loop flag

# Maximum retries
max_iterations = 3

# Node: generate code solution + validator
def generate(state: GraphState):
    messages = state['messages']
    if state.get('error') == 'yes':
        messages.append(("user", f"Previous {state['error_part']} failed. Please try again and correct any errors."))
    sol = code_gen_chain.invoke({'context': K8S_REF, 'messages': messages})
    messages.append(("assistant", f"{sol.prefix}\nImports:\n{sol.imports}\nSolution:\n{sol.code}\nValidator:\n{sol.validator}"))
    return {'generation': sol, 'messages': messages, 'iterations': state['iterations'] + 1, 'error': 'none', 'error_part': '', 'proceed': ''}

# Node: validate execution of generated code and validator
def code_check(state: GraphState):
    sol = state['generation']
    msgs = state['messages']
    tmp_dir = tempfile.mkdtemp()
    sol_file = os.path.join(tmp_dir, 'k8s_solution.py')
    val_file = os.path.join(tmp_dir, 'k8s_validator.py')
    with open(sol_file, 'w') as f:
        f.write(sol.imports + '\n' + sol.code)
    with open(val_file, 'w') as f:
        f.write(sol.imports + '\n' + sol.validator)
    # Compile check
    for part, path in [('solution', sol_file), ('validator', val_file)]:
        try:
            compile(open(path).read(), path, 'exec')
        except Exception as e:
            msgs.append(("user", f"Compilation error in {part}: {e}"))
            return {**state, 'messages': msgs, 'error': 'yes', 'error_part': part}
    # Execute solution
    exit_sol = os.system(f"python {sol_file}")
    if exit_sol != 0:
        msgs.append(("user", f"Execution error in solution: exited with code {exit_sol}"))
        return {**state, 'messages': msgs, 'error': 'yes', 'error_part': 'solution'}
    # Execute validator
    exit_val = os.system(f"python {val_file}")
    if exit_val != 0:
        msgs.append(("user", f"Validation failed: validator exited with code {exit_val}"))
        return {**state, 'messages': msgs, 'error': 'yes', 'error_part': 'validator'}
    msgs.append(("assistant", "Solution executed and validated successfully."))
    return {**state, 'messages': msgs, 'error': 'no', 'error_part': ''}

# Node: human-in-the-loop review before next iteration or finish
def review(state: GraphState):
    sol = state['generation']
    print("\n--- Generated Imports ---\n", sol.imports)
    print("\n--- Solution Code ---\n", sol.code)
    print("\n--- Validator Code ---\n", sol.validator)
    print("\n--- Messages ---\n")
    for role, msg in state['messages']:
        print(f"{role}: {msg}")
    ans = input("\nReview above. Proceed to next step? (yes/no): ")
    state['proceed'] = ans.strip().lower()
    return state

# Node: reflect on failure and regenerate only failing part
def reflect(state: GraphState):
    part = state['error_part']
    msgs = state['messages']
    prompt = (
        f"The {part} code failed. Analyze the errors above and generate a corrected {part} code block only.")
    correction = llm.chat([('system', 'You are a debugging assistant.'), ('user', prompt)])
    msgs.append(('assistant', f"Reflection {part}: {correction.content}"))
    gen = state['generation']
    if part == 'solution':
        gen.code = correction.content
    else:
        gen.validator = correction.content
    return {**state, 'generation': gen, 'messages': msgs, 'error': 'none'}

# Decision node after review
def decide_after_review(state: GraphState):
    if state['proceed'] != 'yes':
        return END
    # if no error or max iterations reached, finish
    if state.get('error') == 'no' or state['iterations'] >= max_iterations:
        return END
    return 'reflect'

# Build the workflow
workflow = StateGraph(GraphState)
workflow.set_entry_point('generate')
workflow.add_node('generate', generate)
workflow.add_node('check_code', code_check)
workflow.add_node('review', review)
workflow.add_node('reflect', reflect)
workflow.add_edge('generate', 'check_code')
workflow.add_edge('check_code', 'review')
workflow.add_conditional_edges('review', decide_after_review, {'reflect': 'reflect', 'end': END})
workflow.add_edge('reflect', 'generate')
app = workflow.compile()

if __name__ == '__main__':
    app.invoke({'messages': [("user", "Please create a Deployment named dep1 using image httpd with 2 replicas."], 'iterations': 0})
