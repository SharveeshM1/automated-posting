from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.links import validate_message


class PostingRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Check out our latest business platform and grow your online visibility. https://example.com"
            }
        }
    )

    message: str

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        return validate_message(value)


class PlatformResult(BaseModel):
    platform: str
    status: Literal["success", "failed"]
    posted_url: Optional[str] = None
    public_access: bool = False
    date: Optional[str] = None
    time: Optional[str] = None
    error: Optional[str] = None


class PostingResponse(BaseModel):
    success: bool  # True when at least one platform succeeded
    results: List[PlatformResult]


class ValidationErrorItem(BaseModel):
    field: str
    error: str


class ValidationErrorResponse(BaseModel):
    success: bool = False
    errors: List[ValidationErrorItem]