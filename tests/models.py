from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LicenseName(StrEnum):
    MIT = "MIT"
    APACHE_2_0 = "Apache-2.0"


class CopierAnswers(BaseModel):
    """Typed convenience model for constructing valid Copier test inputs."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    distribution_name: str
    import_package_name: str | None = None
    description: str = "A modern Python package"
    author_name: str = "Example Author"
    author_email: str = "author@example.test"
    github_owner: str = "example"
    license_name: LicenseName = Field(
        default=LicenseName.MIT,
        serialization_alias="license",
    )
    publish: bool = Field(
        default=False,
        serialization_alias="publish_to_pypi",
    )

    @model_validator(mode="after")
    def derive_import_package_name(self) -> Self:
        if self.import_package_name is None:
            self.import_package_name = self.distribution_name.replace("-", "_").replace(".", "_")
        return self

    def to_copier_data(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)
