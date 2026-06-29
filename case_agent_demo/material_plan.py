from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePath

from case_agent_demo.models import Material, MaterialType


@dataclass(frozen=True)
class MaterialTask:
    task_id: str
    material_type: str
    material_ids: list[str]
    source_paths: list[str]
    group_id: str = ""
    requires_vision: bool = False


ImageGroupTask = MaterialTask


@dataclass(frozen=True)
class MaterialPlan:
    statement_tasks: list[MaterialTask] = field(default_factory=list)
    evidence_image_tasks: list[ImageGroupTask] = field(default_factory=list)
    report_image_tasks: list[ImageGroupTask] = field(default_factory=list)

    @classmethod
    def from_materials(cls, materials: list[Material]) -> "MaterialPlan":
        statement_tasks: list[MaterialTask] = []
        evidence_groups: dict[str, list[Material]] = {}
        report_groups: dict[str, list[Material]] = {}

        for material in materials:
            if material.material_type == MaterialType.STATEMENT:
                statement_tasks.append(
                    MaterialTask(
                        task_id=f"statement:{material.material_id}",
                        material_type=material.material_type.value,
                        material_ids=[material.material_id],
                        source_paths=[material.source_path],
                    )
                )
            elif material.material_type == MaterialType.EVIDENCE_IMAGE:
                evidence_groups.setdefault(_image_group_id(material), []).append(material)
            elif material.material_type == MaterialType.REPORT_IMAGE:
                report_groups.setdefault(_image_group_id(material), []).append(material)

        return cls(
            statement_tasks=statement_tasks,
            evidence_image_tasks=_groups_to_tasks(MaterialType.EVIDENCE_IMAGE, evidence_groups),
            report_image_tasks=_groups_to_tasks(MaterialType.REPORT_IMAGE, report_groups),
        )

    @property
    def image_tasks(self) -> list[ImageGroupTask]:
        return [*self.evidence_image_tasks, *self.report_image_tasks]

    @property
    def statement_count(self) -> int:
        return len(self.statement_tasks)

    @property
    def evidence_image_group_count(self) -> int:
        return len(self.evidence_image_tasks)

    @property
    def report_image_group_count(self) -> int:
        return len(self.report_image_tasks)

    @property
    def total_materials(self) -> int:
        return sum(len(task.material_ids) for task in [*self.statement_tasks, *self.image_tasks])


def _groups_to_tasks(material_type: MaterialType, groups: dict[str, list[Material]]) -> list[ImageGroupTask]:
    tasks: list[ImageGroupTask] = []
    for group_id in sorted(groups):
        group = sorted(groups[group_id], key=lambda item: item.source_path or item.material_id)
        tasks.append(
            ImageGroupTask(
                task_id=f"{material_type.value}:{group_id}",
                material_type=material_type.value,
                material_ids=[item.material_id for item in group],
                source_paths=[item.source_path for item in group],
                group_id=group_id,
                requires_vision=True,
            )
        )
    return tasks


def _image_group_id(material: Material) -> str:
    if not material.source_path:
        return material.material_id
    path = PurePath(material.source_path)
    parent = path.parent.name
    if parent in {"identification_images", "report_images", ""}:
        return path.stem
    return parent
