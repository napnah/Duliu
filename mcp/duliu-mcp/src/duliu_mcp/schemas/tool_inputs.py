from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class GetProblemInput(_StrictModel):
    problem_id: str = Field(..., description="Duliu problem UUID")


class ListArtifactsInput(_StrictModel):
    problem_id: str = Field(..., description="Duliu problem UUID")


class GetArtifactInput(_StrictModel):
    problem_id: str = Field(..., description="Duliu problem UUID")
    kind: str = Field(
        ...,
        description="Artifact kind: statement, std, gen, validator, checker, report, ...",
        min_length=1,
    )


class ExportTestDataInput(_StrictModel):
    problem_id: str = Field(..., description="Duliu problem UUID")
    output_dir: Path | None = Field(
        default=None,
        description="Target directory; defaults to DULIU_EXPORT_DIR/{problem_id}/tests",
    )
    format: Literal["files", "zip"] = Field(
        default="files",
        description="Export as loose .in/.out files or a single zip archive",
    )
    include_samples_only: bool = Field(
        default=False,
        description="If true, export only sample tests from spec_json",
    )


class ExportPolygonPackageInput(_StrictModel):
    problem_id: str = Field(..., description="Duliu problem UUID")
    output_dir: Path | None = Field(
        default=None,
        description="Target directory; defaults to DULIU_EXPORT_DIR/{problem_id}/polygon_package",
    )
    language: Literal["chinese", "english", "both"] = Field(
        default="chinese",
        description="Statement language(s) to include in the package",
    )
