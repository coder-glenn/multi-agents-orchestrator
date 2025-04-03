import asyncio

from typing import Any, Dict, Set
from autogen_core import (
    RoutedAgent,
    TopicId,
    message_handler,
    type_subscription, AgentId,
)

from llm_client import LLMClient
from message import EvaluationResultMessage, UserRequestMessage, AgentResultMessage, AgentTaskMessage
from register import Register

llm_client = LLMClient()
@type_subscription(topic_type="Orchestrator")
class Orchestrator(RoutedAgent):
    instance = None

    def __init__(self) -> None:
        super().__init__("Orchestrator")
        self.contexts: Dict[str, Dict[str, Any]] = {}

    @message_handler
    async def handle_user_request(self, message: UserRequestMessage, ctx) -> None:
        user_question = message.payload['content']
        print(f"[Orchestrator] Received user request: {user_question}")
        correlation_id = message.header.message_id
        self.contexts[correlation_id] = {
            "original_request": user_question,
            "subtasks": [],
            "agent_results": [],
            "prev_result": None
        }

        subtasks, execution_mode = llm_client.breakdown_task(user_question, self.contexts[correlation_id])
        print(f"[Orchestrator] Breakdown results: {subtasks}, mode: {execution_mode}")
        current_context = self.contexts[correlation_id]
        if execution_mode.strip() == "serial":

            for subtask in subtasks:
                agent_result = await self.delegate_task(correlation_id, subtask, current_context)
                current_context["subtasks"].append({"task": subtask, "is_completed": True})
                current_context["prev_result"] = agent_result.payload["result"]
                current_context["agent_results"].append(agent_result)

        elif execution_mode == "parallel":
            tasks = []

            for subtask in subtasks:
                current_context["subtasks"].append({"task": subtask, "is_completed": False})
                tasks.append(self.delegate_task(correlation_id, subtask, current_context))

            results = await asyncio.gather(*tasks)
            current_context["agent_results"].append(results)
            for result in results:
                print(result)

            final_result = "\n".join(results)
            print(f"[Orchestrator] Parallel subtask results: {final_result}")

        else:

            response = await self.delegate_task(correlation_id, user_question, current_context)
            current_context["subtasks"].append({"task": user_question, "is_completed": True})
            current_context["agent_results"].append(response)

        final_result = self.contexts[correlation_id]["final_result"]
        print(f"[Orchestrator] All subtasks executed for correlation_id {correlation_id}. Final result: {final_result}")
        # Broadcast final aggregated result to Evaluator for final evaluation
        evaluate_result = await self.send_message(AgentResultMessage.create(
            sender="Orchestrator",
            correlation_id=correlation_id,
            result=final_result,
            success=True
        ), recipient=AgentId("Evaluator", "Orchestrator"))

    async def delegate_task(self, correlation_id: str, task_content: str, context: Dict[str, Any]) -> AgentResultMessage:
        agents = Register.get_agents_desc()
        descriptions = "\n".join([f"AgentName: {name}, Description: {info['description']}" for name, info in agents.items()])
        selected_agent = llm_client.select_agent(descriptions, task_content)
        print(f"[Orchestrator] LLM selected agent: {selected_agent}")
        if selected_agent not in agents.keys():
            selected_agent = "GenericAgent"
            print(f"[Orchestrator] Using GenericAgent as fallback")
        task_msg = AgentTaskMessage.create(sender="Orchestrator",
                                           recipient=selected_agent,
                                           task_content=task_content,
                                           correlation_id=correlation_id,
                                           context=context)

        return await self.send_message(task_msg, recipient=AgentId(type=selected_agent, key="default"))

    @message_handler
    async def handle_evaluation_result(self, message: EvaluationResultMessage, ctx) -> None:
        correlation_id = message.header.correlation_id
        self.contexts[correlation_id] = message.payload["context"]
        completed = message.payload["completed"]
        final_result = message.payload.get("final_result")
        if not final_result and correlation_id in self.contexts:
            final_result = "\n".join(self.contexts[correlation_id].get("agent_results", []))
        if completed:
            print(f"[Orchestrator] Final result returned to user: {final_result}")
            # Clear context and related states
            self.contexts[correlation_id].get("subtasks")[0]["is_completed"] = True

            user_msg = UserRequestMessage.create(sender="User", request_content=self.contexts[correlation_id].get("subtasks")[1],
                                                 correlation_id=correlation_id)
            await self.handle_user_request(user_msg, ctx)
            # self.tried_topics.pop(correlation_id, None)
            # self.contexts.pop(correlation_id, None)
            # if correlation_id in self.result_futures:
            #     self.result_futures.pop(correlation_id, None)
        else:
            print(f"[Orchestrator] Evaluation indicates task not completed. Retrying.")
            original_request = self.contexts.get(correlation_id, {}).get("original_request", "")
            user_msg = UserRequestMessage.create(sender="User", request_content=original_request, correlation_id=correlation_id)
            await self.handle_user_request(user_msg, ctx)
