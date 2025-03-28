
from autogen_core import (
    RoutedAgent,
    TopicId,
    message_handler,
    type_subscription,
)

from llm_client import LLMClient
from message import AgentResultMessage, EvaluationResultMessage


@type_subscription(topic_type="Evaluator")
class Evaluator(RoutedAgent):
    def __init__(self) -> None:
        super().__init__("Evaluator")

    @message_handler
    async def handle_agent_result(self, message: AgentResultMessage, ctx) -> None:
        print(f"[Evaluator] Received agent result from: {message.header.sender}")
        correlation_id = message.header.correlation_id

        original_request = message.payload["context"].get("original_request", "No original request")
        completed = LLMClient().evaluate_result(original_request, message.payload["result"])

        final_result = message.payload["result"] if completed else None
        eval_msg = EvaluationResultMessage.create(sender="Evaluator",
                                                   correlation_id=correlation_id,
                                                   final_result=final_result,
                                                   completed=completed,
                                                   context=message.payload["context"])
        await self.publish_message(eval_msg, topic_id=TopicId("Orchestrator", source="Evaluator"))
        print(f"[Evaluator] Evaluation for correlation_id {correlation_id} completed: {completed}")
