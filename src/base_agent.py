
from typing import Any, Dict, Optional, List, Set, Tuple

from agent_core.agents import Agent

from autogen_core import (
    RoutedAgent,
    TopicId,
    message_handler
)

from message import AgentTaskMessage, ErrorNotificationMessage, AgentResultMessage
from register import DEFAULT_TOPIC, Register


class BaseAgent(RoutedAgent):
    def __init__(self, name: str, description: str, topic: Optional[str], source_agent: Agent) -> None:
        super().__init__(description)
        self.name = name
        self.description = description
        self.topic = topic if topic is not None else DEFAULT_TOPIC
        self.source_agent = source_agent
        Register.register_agent(self.name, self.description, self.topic)

    @message_handler
    async def handle_task(self, message: AgentTaskMessage, ctx) -> None:
        print(f"[BaseAgent {self.name}] Received task: {message.payload['task']}")
        try:
            task_content = message.payload["task"]
            # 保留原始上下文，便于后续agent使用
            context = message.payload.get("context", {})
            result = self.source_agent.execute(task_content)
        except Exception as e:
            error_msg = ErrorNotificationMessage.create(sender=self.name, error_info=str(e), correlation_id=message.header.correlation_id)
            await self.publish_message(error_msg, topic_id=TopicId("Error", source=self.name))
            result = f"Execution error: {str(e)}"
        success = "success" in result.lower()
        # 直接返回处理结果给编排器
        agent_result = AgentResultMessage.create(sender=self.name,
                                                 correlation_id=message.header.correlation_id,
                                                 result=result,
                                                 success=success,
                                                 context=context)
        await self.publish_message(agent_result, topic_id=TopicId("Orchestrator", source=self.name))
        print(f"[BaseAgent {self.name}] Processed task '{task_content}' with result: {result}")
