import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

def current_timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"

def generate_id() -> str:
    return str(uuid.uuid4())

class MessageHeader(BaseModel):
    message_id: str = Field(default_factory=generate_id)
    sender: str
    recipient: Optional[str] = None
    timestamp: str = Field(default_factory=current_timestamp)
    correlation_id: Optional[str] = None
    message_type: str

class BaseMessage(BaseModel):
    header: MessageHeader
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = {}

class UserRequestMessage(BaseMessage):
    @classmethod
    def create(cls, sender: str, request_content: str, correlation_id: Optional[str] = None) -> "UserRequestMessage":
        header = MessageHeader(
            sender=sender,
            recipient="Orchestrator",
            message_type="UserRequest",
            correlation_id=correlation_id
        )
        return cls(header=header, payload={"content": request_content})


class AgentTaskMessage(BaseMessage):
    @classmethod
    def create(cls, sender: str, recipient: str, task_content: str, correlation_id: str, context: Dict[str, Any], retry: int = 0) -> "AgentTaskMessage":
        header = MessageHeader(
            sender=sender,
            recipient=recipient,
            message_type="AgentTask",
            correlation_id=correlation_id
        )
        return cls(header=header, payload={"task": task_content, "retry": retry, "context": context})


class AgentResultMessage(BaseMessage):
    @classmethod
    def create(cls, sender: str, correlation_id: str, result: str, context: Dict[str, Any], success: bool) -> "AgentResultMessage":
        header = MessageHeader(
            sender=sender,
            recipient="Orchestrator",
            message_type="AgentResult",
            correlation_id=correlation_id
        )
        return cls(header=header, payload={"result": result, "context": context, "success": success})

class EvaluationResultMessage(BaseMessage):
    @classmethod
    def create(cls, sender: str, correlation_id: str, final_result: Optional[str], context: Dict[str, Any], completed: bool) -> "EvaluationResultMessage":
        header = MessageHeader(
            sender=sender,
            recipient="Orchestrator",
            message_type="EvaluationResult",
            correlation_id=correlation_id
        )
        return cls(header=header, payload={"final_result": final_result, "context": context, "completed": completed})


class ErrorNotificationMessage(BaseMessage):
    @classmethod
    def create(cls, sender: str, error_info: str, correlation_id: Optional[str] = None) -> "ErrorNotificationMessage":
        header = MessageHeader(
            sender=sender,
            recipient="Orchestrator",
            message_type="ErrorNotification",
            correlation_id=correlation_id
        )
        return cls(header=header, payload={"error": error_info})
