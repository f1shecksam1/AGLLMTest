from pydantic import BaseModel, Field
from typing import Any


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    x_sql_file: str = Field(alias="x_sql_file")

    sql_text: str | None = None  # runtime'da dolduracağız

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
