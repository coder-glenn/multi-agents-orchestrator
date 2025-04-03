from typing import Any, Dict, Optional, List, Set, Tuple

from agent_core.utils.llm_chat import LLMChat

class LLMClient:

    def select_agent(self, agent_descriptions: str, question: str, exclude: Set[str] = None) -> str:
        if exclude is None:
            exclude = set()
        prompt = (
            f"Analyze the question: '{question}' and the following agent descriptions: {agent_descriptions}.\n"
            f"Exclude: {','.join(exclude) if exclude else 'none'}.\n"
            "Return only the agent name, return no_agent if none selected"
        )
        response = LLMChat().process(prompt)
        selected = response.strip()
        print(f"[LLMClient] select_agent prompt:\n{prompt}\nResponse: {selected}")
        return selected

    def evaluate_result(self, original_request: str, agent_result: str) -> bool:
        prompt = (
            f"Given the original request: '{original_request}' and the agent result: '{agent_result}',\n"
            "determine if the task was successfully completed. Return True if successful, else False."
        )
        response = LLMChat().process(prompt)
        result = response.strip().lower()
        print(f"[LLMClient] evaluate_result prompt:\n{prompt}\nResponse: {result}")
        return True

    def breakdown_task(self, request_content: str, context: Dict[str, Any]) -> Tuple[List[str], str]:
        prompt = (
            f"Break down the task: '{request_content}' with context: {context}.\n"
            "Return subtasks separated by semicolons and execution mode serial or parallel separated by a pipe symbol.\n"
            "Example: task1; task2 | serial"
        )
        response = LLMChat().process(prompt)
        response = response.strip()
        print(f"[LLMClient] breakdown_task prompt:\n{prompt}\nResponse: {response}")
        try:
            tasks_part, mode = response.split("|")
            subtasks = [s.strip() for s in tasks_part.split(";") if s.strip()]
        except Exception as e:
            subtasks = [request_content]
            mode = "serial"
        return subtasks, "serial"