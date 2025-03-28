

DEFAULT_TOPIC = "DefaultTopic"

from typing import Any, Dict, Optional, List, Set, Tuple


class Register:
    _agents: Dict[str, Dict] = {}
    _external_agents: List[Any] = []

    @classmethod
    def register_agent(cls, agent_name: str, description: str, topic: Optional[str] = None):
        topic = topic if topic is not None else DEFAULT_TOPIC
        cls._agents[agent_name] = {"description": description, "topic": topic}
        # print(f"[Register] Registered agent {agent_name}, description: {description}, topic: {topic}")

    @classmethod
    def remove_agent(cls, agent_name: str):
        if agent_name in cls._agents:
            del cls._agents[agent_name]
            print(f"[Register] Removed agent {agent_name}")
        else:
            print(f"[Register] Agent {agent_name} not found")

    @classmethod
    def register_external_agent(cls, agent: Any, name: str, description: str, topic: Optional[str] = None):
        topic = topic if topic is not None else DEFAULT_TOPIC
        cls._external_agents.append(agent)
        cls.register_agent(name, description, topic)
        print(f"[Register] Custom agent registered: {name}")

    @classmethod
    def get_agents_desc(cls) -> Dict[str, Dict]:
        return cls._agents

    @classmethod
    def get_agent_list(cls) -> List[Any]:
        return cls._external_agents
