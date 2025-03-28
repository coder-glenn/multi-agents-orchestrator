import asyncio

from typing import Any, Dict, Optional, List, Set, Tuple
from autogen_core import (
    RoutedAgent,
    TopicId,
    message_handler,
    type_subscription,
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
        self.tried_topics: Dict[str, Set[str]] = {}
        # Context includes original_request, subtasks (list of dicts), agent_results, last_result, final_result
        self.contexts: Dict[str, Dict[str, Any]] = {}
        self.result_futures: Dict[str, asyncio.Future] = {}
        Orchestrator.instance = self

    @message_handler
    async def handle_user_request(self, message: UserRequestMessage, ctx) -> None:
        print(f"[Orchestrator] Received user request: {message.payload['content']}")
        correlation_id = message.header.message_id
        # Initialize context; subtasks is now a list of dictionaries with keys "task" and "is_completed"
        self.contexts[correlation_id] = {
            "original_request": message.payload["content"],
            "subtasks": [],
            "agent_results": [],
            "last_result": None,
            "final_result": None
        }
        self.tried_topics[correlation_id] = set()
        # Create a new future for waiting on subtask results
        self.result_futures[correlation_id] = asyncio.get_event_loop().create_future()

        # Breakdown the task into subtasks using LLM
        subtasks, execution_mode = llm_client.breakdown_task(message.payload["content"], self.contexts[correlation_id])
        print(f"[Orchestrator] Breakdown results: {subtasks}, mode: {execution_mode}")
        if not subtasks:
            subtasks = [message.payload["content"]]

        if execution_mode.strip() == "serial":
            current_context = self.contexts[correlation_id]

            for subtask in subtasks:
                current_context["subtasks"].append({"task": subtask, "is_completed": False})

                if current_context["last_result"]:
                    current_context["prev_result"] = current_context["last_result"]
                print(f"[Orchestrator] Delegating subtask: {subtask} with context: {current_context}")

                # print(f"[Orchestrator] Received result for subtask '{subtask}': {result}")
                # current_context["last_result"] = result
            if not current_context.get("subtasks", [])[0]["is_completed"]:
                await self.delegate_task(correlation_id, subtasks[0], current_context)
            else:
                await self.delegate_task(correlation_id, message.payload["content"], current_context)
        elif execution_mode == "parallel":
            tasks = []

            for subtask in subtasks:
                self.contexts[correlation_id]["subtasks"].append({"task": subtask, "is_completed": False})
                tasks.append(self.delegate_task(correlation_id, subtask, self.contexts[correlation_id]))
            results = await asyncio.gather(*tasks)

            for item in self.contexts[correlation_id]["subtasks"]:
                item["is_completed"] = True
            self.contexts[correlation_id]["agent_results"].extend(results)
            final_result = "\n".join(results)
            print(f"[Orchestrator] Parallel subtask results: {results}")
        else:

            current_context = self.contexts[correlation_id]

            for subtask in subtasks:
                current_context["subtasks"].append({"task": subtask, "is_completed": False})

                if current_context["last_result"]:
                    current_context["prev_result"] = current_context["last_result"]
                print(f"[Orchestrator] Delegating subtask: {subtask} with context: {current_context}")

                # print(f"[Orchestrator] Received result for subtask '{subtask}': {result}")
                # current_context["last_result"] = result
            if not current_context.get("subtasks", [])[0]["is_completed"]:
                await self.delegate_task(correlation_id, subtasks[0], current_context)
            else:
                await self.delegate_task(correlation_id, message.payload["content"], current_context)

        self.contexts[correlation_id]["final_result"] = final_result
        print(f"[Orchestrator] All subtasks executed for correlation_id {correlation_id}. Final result: {final_result}")
        # Broadcast final aggregated result to Evaluator for final evaluation
        await self.publish_message(AgentResultMessage.create(
            sender="Orchestrator",
            correlation_id=correlation_id,
            result=final_result,
            success=True
        ), topic_id=TopicId("Evaluator", source="Orchestrator"))

    async def delegate_task(self, correlation_id: str, task_content: str, context: Dict[str, Any]) -> str:
        agents = Register.get_agents_desc()
        descriptions = "\n".join([f"AgentName: {name}, Description: {info['description']}" for name, info in agents.items()])
        selected_agent = llm_client.select_agent(descriptions, task_content, self.tried_topics[correlation_id])
        print(f"[Orchestrator] LLM selected agent: {selected_agent} (tried: {self.tried_topics[correlation_id]})")
        if selected_agent not in agents.keys():
            selected_agent = "GenericAgent"
            print(f"[Orchestrator] Using GenericAgent as fallback")
        self.tried_topics[correlation_id].add(selected_agent)
        task_msg = AgentTaskMessage.create(sender="Orchestrator",
                                           recipient=selected_agent,
                                           task_content=task_content,
                                           correlation_id=correlation_id,
                                           context=context)
        # Send the task message directly to the selected agent
        await self.publish_message(task_msg, topic_id=TopicId(selected_agent, source="Orchestrator"))
        # Wait for the result from the agent
        result = await self.wait_for_result(correlation_id)
        return result

    async def wait_for_result(self, correlation_id: str) -> str:
        if correlation_id in self.result_futures:
            result = await self.result_futures[correlation_id]
            print(f"[Orchestrator] wait_for_result received: {result}")
            # Reset the future for the next subtask (for serial processing)
            self.result_futures[correlation_id] = asyncio.get_event_loop().create_future()
            return result
        return f"No result received (correlation_id={correlation_id})"

    @message_handler
    async def handle_agent_result(self, message: AgentResultMessage, ctx) -> None:
        correlation_id = message.header.correlation_id
        self.contexts[correlation_id] = message.payload["context"]
        if correlation_id in self.contexts:
            self.contexts[correlation_id].setdefault("agent_results", []).append(message.payload["result"])
        print(f"[Orchestrator] Received agent result from {message.header.sender}: {message.payload['result']}")
        # Set result for the waiting future (for serial tasks)
        if correlation_id in self.result_futures and not self.result_futures[correlation_id].done():
            self.result_futures[correlation_id].set_result(message.payload["result"])
        await self.publish_message(message, topic_id=TopicId("Evaluator", source="Orchestrator"))

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
