"""Input validation using Pydantic."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator, ValidationError as PydanticValidationError
from backend.utils.exceptions import ValidationError


class LogActionRequest(BaseModel):
    """Validation schema for log-action endpoint."""
    source: str = Field(..., description="Source of the action")
    action_type: str = Field(..., description="Type of action")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Action context")
    context_json: Optional[Dict[str, Any]] = Field(None, description="Alternative context field")
    session_id: Optional[str] = Field(None, description="Session ID")
    
    @validator('source')
    def validate_source(cls, v):
        allowed_sources = ['chrome', 'vscode', 'system']
        if v not in allowed_sources:
            raise ValueError(f'source must be one of {allowed_sources}')
        return v
    
    @validator('action_type')
    def validate_action_type(cls, v):
        if not v or len(v) > 100:
            raise ValueError('action_type must be non-empty and less than 100 characters')
        return v
    
    @validator('context', 'context_json')
    def validate_context(cls, v):
        if v is not None and not isinstance(v, dict):
            raise ValueError('context must be a dictionary')
        return v
    
    class Config:
        extra = 'forbid'  # Reject extra fields


class TrainingRequest(BaseModel):
    """Validation schema for training endpoint."""
    num_epochs: int = Field(default=50, ge=1, le=1000, description="Number of training epochs")
    learning_rate: float = Field(default=0.001, ge=0.0001, le=0.1, description="Learning rate")
    batch_size: int = Field(default=64, ge=1, le=512, description="Batch size")
    
    class Config:
        extra = 'forbid'


class ChatRequest(BaseModel):
    """Validation schema for LLM chat endpoint."""
    message: str = Field(..., min_length=1, max_length=5000, description="Chat message")
    intent: Optional[str] = Field(None, max_length=50, description="Detected intent")
    search_results: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Search results for context")
    
    class Config:
        extra = 'forbid'


def validate_request(data: Dict[str, Any], schema: type[BaseModel]) -> BaseModel:
    """
    Validate request data against a Pydantic schema.
    
    Args:
        data: Request data dictionary
        schema: Pydantic model class
        
    Returns:
        Validated model instance
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        return schema(**data)
    except PydanticValidationError as e:
        errors = []
        for error in e.errors():
            field = '.'.join(str(x) for x in error['loc'])
            errors.append(f"{field}: {error['msg']}")
        raise ValidationError(
            message="Validation failed",
            error_code="VALIDATION_ERROR",
            details={"errors": errors, "raw_errors": e.errors()}
        )

