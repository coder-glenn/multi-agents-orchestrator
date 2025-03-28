import asyncio

from autogen_core import SingleThreadedAgentRuntime, RoutedAgent, message_handler, TopicId, TypeSubscription

from typing import Any, Dict, Optional
from agent_core.agents import Agent

from base_agent import BaseAgent
from evaluator import Evaluator
from llm_client import LLMClient
from message import ErrorNotificationMessage, AgentTaskMessage, AgentResultMessage, UserRequestMessage
from orchestrator import Orchestrator
from register import DEFAULT_TOPIC, Register

llm_client = LLMClient()

class ExternalAgentWrapper(RoutedAgent):
    def __init__(self, name: str, description: str, topic: Optional[str], external_agent: Any) -> None:
        super().__init__(description)
        self.name = name
        self.description = description
        self.topic = topic if topic is not None else DEFAULT_TOPIC
        self.external_agent = external_agent
        Register.register_external_agent(external_agent, self.name, self.description, self.topic)

    @message_handler
    async def handle_task(self, message: AgentTaskMessage, ctx) -> None:
        print(f"[ExternalAgentWrapper {self.name}] Received task: {message.payload['task']}")
        try:
            result = self.external_agent.execute(message.payload['task'], message.payload.get("context", {}))
        except Exception as e:
            error_msg = ErrorNotificationMessage.create(sender=self.name, error_info=str(e), correlation_id=message.header.correlation_id)
            await self.publish_message(error_msg, topic_id=TopicId("Error", source=self.name))
            result = f"Execution error: {str(e)}"
        success = "success" in result.lower()
        agent_result = AgentResultMessage.create(sender=self.name,
                                                 correlation_id=message.header.correlation_id,
                                                 result=result,
                                                 success=success)
        await self.publish_message(agent_result, topic_id=TopicId("Orchestrator", source=self.name))
        print(f"[ExternalAgentWrapper {self.name}] Published result: {result}")


class AgentController:
    def __init__(self):
        self.runtime = SingleThreadedAgentRuntime()
        self.agents: Dict[str, Any] = {}
        self.evaluator: Optional[Evaluator] = None
        self.orchestrator: Optional[Orchestrator] = None

    async def register_components(self):
        self.evaluator = await Evaluator.register(self.runtime, type="Evaluator", factory=lambda: Evaluator())
        self.orchestrator = await Orchestrator.register(self.runtime, type="Orchestrator", factory=lambda: Orchestrator())
        await self.runtime.add_subscription(TypeSubscription(topic_type="AgentResult", agent_type="*"))
        # 注册一个 GenericAgent，用于当 LLM 选择失败时的兜底方案
        await BaseAgent.register(self.runtime, type="GenericAgent", factory=lambda: BaseAgent("GenericAgent", "Generic agent for common tasks", "GenericAgent", Agent()))
        await self.runtime.add_subscription(TypeSubscription(topic_type="GenericAgent", agent_type="GenericAgent"))

    async def register_user_agent(self, agent_name: str, description: str, topic: Optional[str], source_agent: Agent):
        agent = await BaseAgent.register(self.runtime, type=agent_name, factory=lambda: BaseAgent(agent_name, description, topic, source_agent))
        await self.runtime.add_subscription(TypeSubscription(topic_type=agent_name, agent_type=agent_name))
        Register.register_agent(agent_name, description, topic)
        self.agents[agent_name] = agent

    async def register_custom_agent(self, external_agent: Any, name: str, description: str, topic: Optional[str]):
        wrapper = ExternalAgentWrapper(name, description, topic, external_agent)
        await wrapper.register(self.runtime, type=wrapper.name)
        await self.runtime.add_subscription(TypeSubscription(topic_type=wrapper.topic, agent_type=wrapper.name))
        self.agents[name] = wrapper

    async def remove_agent(self, agent_name: str):
        Register.remove_agent(agent_name)
        if agent_name in self.agents:
            del self.agents[agent_name]

    async def start(self):
        self.runtime.start()

    async def stop(self):
        await self.runtime.stop_when_idle()


async def main():

    manager = AgentController()
    await manager.register_components()


    dev_agent = Agent()
    dev_agent.background = "You are a professional software developer with expertise in coding. Provide a complete, well-structured code solution."
    await manager.register_user_agent("DevAgent", "DevAgent generates the code implementation for the software system. It produces complete, runnable code that follows best practices, includes error handling, and is easy to maintain.", "DevAgent", dev_agent)

    review_agent = Agent()
    review_agent.background = "You are a senior code reviewer. Your review should be precise and constructive."
    await manager.register_user_agent("ReviewAgent", "ReviewAgent specialized in code review", "ReviewAgent", review_agent)

    test_agent = Agent()
    test_agent.background = "You are an expert in testing software system. Ensure comprehensive and maintainable tests."
    await manager.register_user_agent("TestAgent", "TestAgent creates unit tests for the software system. It writes tests covering successful logins, failure cases, and edge conditions using a popular Python testing framework.", "TestAgent", test_agent)


    doc_agent = Agent()
    doc_agent.background = "You are an expert in testing software system. Ensure comprehensive and maintainable tests."
    await manager.register_user_agent("DocAgent",
                                      "DocAgent produces clear documentation for the software system. It includes an overview, setup instructions, key code explanations, and usage examples.",
                                      "DocAgent", doc_agent)

    await manager.start()

    user_input = "Implement a sorting algorithm in Java, perform code review and test process, and create doc once at last"
    user_msg = UserRequestMessage.create(sender="User", request_content=user_input)
    await manager.runtime.publish_message(user_msg, topic_id=TopicId("Orchestrator", source="User"))

    await manager.runtime.stop_when_idle()
    await manager.stop()

if __name__ == "__main__":
    asyncio.run(main())
