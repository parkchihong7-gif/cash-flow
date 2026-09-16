"""템플릿 기획서(spec.yaml) 규격과 검사.

**검사가 이 상품의 뼈대입니다.** 노션 템플릿은 관계·롤업이 한 군데만 어긋나도
복제한 구매자 화면에서 빈칸이 뜹니다. 그런데 그 어긋남은 만들 때는 안 보이고
구매자가 열었을 때 보입니다. 그래서 만들기 전에 잡습니다.

여기서 잡는 것

    타입      노션 API 가 아는 타입만
    제목      데이터베이스마다 title 속성이 정확히 하나
    관계      relation_to 가 실제로 있는 데이터베이스를 가리키는가
    롤업      가리키는 관계 속성이 같은 DB 에 있고, 대상 속성이 저쪽에 있는가
    선택지    select·multi_select·status 에 선택지가 있는가
    예시      5행이고, 없는 속성을 쓰지 않는가
    뷰        아는 종류인가, 쓰는 속성이 실제로 있는가
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from notion_kit.notion_types import (
    ALL_TYPES, NEEDS_OPTIONS, ROLLUP_FUNCTIONS, VIEW_TYPES,
)

__all__ = ["PropertySpec", "ViewSpec", "DatabaseSpec", "PageNode", "ButtonSpec",
           "TemplateSpec", "slugify", "SAMPLE_ROWS"]

#: 예시 데이터는 정확히 이만큼. 적으면 비어 보이고, 많으면 구매자가 지우는 데 시간을 쓴다.
SAMPLE_ROWS = 5


def slugify(text: str) -> str:
    """폴더 이름에 쓸 수 있게 다듬는다. 한글은 그대로 둔다."""
    text = unicodedata.normalize("NFC", str(text)).strip()
    text = re.sub(r"[\\/:*?\"<>|]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text.strip("-") or "템플릿"


class PropertySpec(BaseModel):
    """데이터베이스 속성 하나."""

    name: str = Field(min_length=1)
    type: str
    description: str = ""

    #: select / multi_select / status 의 선택지
    options: list[str] = Field(default_factory=list)

    #: number 의 표시 형식 (number, won, percent 등)
    number_format: str = ""

    #: formula 수식. 노션 문법 그대로 적는다
    formula: str = ""

    #: relation 이 가리킬 데이터베이스의 key
    relation_to: str = ""

    #: rollup 이 타고 갈 관계 속성 이름 (같은 DB 안)
    rollup_relation: str = ""

    #: rollup 이 대상 DB 에서 볼 속성 이름
    rollup_property: str = ""

    #: rollup 계산 방식
    rollup_function: str = "count"

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in ALL_TYPES:
            raise ValueError(
                f"노션이 모르는 속성 타입입니다: {value}\n"
                f"  쓸 수 있는 타입: {', '.join(sorted(ALL_TYPES))}")
        return value

    @model_validator(mode="after")
    def _check(self) -> "PropertySpec":
        if self.type in NEEDS_OPTIONS and not self.options:
            raise ValueError(f"{self.name}: {self.type} 은 선택지가 있어야 합니다")
        if self.type not in NEEDS_OPTIONS and self.options:
            raise ValueError(f"{self.name}: {self.type} 에는 선택지를 넣을 수 없습니다")
        if self.type == "relation" and not self.relation_to:
            raise ValueError(f"{self.name}: relation 은 relation_to 가 있어야 합니다")
        if self.type == "formula" and not self.formula:
            raise ValueError(f"{self.name}: formula 는 수식이 있어야 합니다")
        if self.type == "rollup":
            if not (self.rollup_relation and self.rollup_property):
                raise ValueError(
                    f"{self.name}: rollup 은 rollup_relation 과 rollup_property 가 "
                    "모두 있어야 합니다")
            if self.rollup_function not in ROLLUP_FUNCTIONS:
                raise ValueError(
                    f"{self.name}: 모르는 롤업 계산입니다: {self.rollup_function}\n"
                    f"  쓸 수 있는 것: {', '.join(sorted(ROLLUP_FUNCTIONS))}")
        if len(self.options) != len(set(self.options)):
            raise ValueError(f"{self.name}: 선택지가 겹칩니다")
        return self


class ViewSpec(BaseModel):
    """데이터베이스 뷰 하나.

    ⚠️ 공개 API 로는 뷰를 만들지 못합니다. 설계서에만 적히고
    `build_guide.md` 가 손으로 만드는 법을 알려 줍니다.
    """

    name: str = Field(min_length=1)
    type: Literal["table", "board", "calendar", "list", "gallery", "timeline"]
    purpose: str = ""

    #: board 는 무엇으로 묶을지, calendar·timeline 은 어느 날짜를 쓸지
    group_by: str = ""
    date_property: str = ""
    filter_note: str = ""
    sort_note: str = ""

    @model_validator(mode="after")
    def _needs_its_key_property(self) -> "ViewSpec":
        if self.type == "board" and not self.group_by:
            raise ValueError(f"{self.name}: 보드 뷰는 group_by 가 있어야 합니다")
        if self.type in ("calendar", "timeline") and not self.date_property:
            raise ValueError(f"{self.name}: {self.type} 뷰는 date_property 가 있어야 합니다")
        return self


class DatabaseSpec(BaseModel):
    """데이터베이스 하나."""

    key: str = Field(min_length=1, description="다른 곳에서 가리킬 때 쓰는 이름")
    name: str = Field(min_length=1)
    description: str = ""
    icon: str = ""
    parent_page: str = Field(default="", description="어느 페이지 아래에 둘지")
    properties: list[PropertySpec] = Field(min_length=1)
    views: list[ViewSpec] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def property_map(self) -> dict[str, PropertySpec]:
        return {p.name: p for p in self.properties}

    @property
    def title_property(self) -> PropertySpec | None:
        for spec in self.properties:
            if spec.type == "title":
                return spec
        return None

    @model_validator(mode="after")
    def _check(self) -> "DatabaseSpec":
        names = [p.name for p in self.properties]
        if len(names) != len(set(names)):
            repeated = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"{self.name}: 속성 이름이 겹칩니다 — {', '.join(repeated)}")

        titles = [p for p in self.properties if p.type == "title"]
        if len(titles) != 1:
            raise ValueError(
                f"{self.name}: title 속성이 정확히 하나여야 합니다 (지금 {len(titles)}개). "
                "노션 데이터베이스는 제목 칸이 반드시 하나입니다")

        known = set(names)
        for view in self.views:
            for label, value in (("group_by", view.group_by),
                                 ("date_property", view.date_property)):
                if value and value not in known:
                    raise ValueError(
                        f"{self.name} / {view.name} 뷰의 {label} 가 없는 속성입니다: {value}")

        for index, row in enumerate(self.sample_rows, start=1):
            unknown = sorted(set(row) - known)
            if unknown:
                raise ValueError(
                    f"{self.name}: 예시 {index}행이 없는 속성을 씁니다: {', '.join(unknown)}")
        return self


class PageNode(BaseModel):
    """페이지 트리의 마디 하나."""

    title: str = Field(min_length=1)
    icon: str = ""
    purpose: str = ""
    children: list["PageNode"] = Field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


class ButtonSpec(BaseModel):
    """템플릿 버튼. 구매자가 눌러 새 항목을 만드는 단추."""

    name: str = Field(min_length=1)
    where: str = Field(default="", description="어느 페이지에 둘지")
    creates: str = Field(default="", description="어느 데이터베이스에 만들지 (key)")
    prefill: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class TemplateSpec(BaseModel):
    """템플릿 하나의 설계 전부."""

    name: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    summary: str = ""
    icon: str = "📋"
    slug: str = ""
    pages: list[PageNode] = Field(min_length=1)
    databases: list[DatabaseSpec] = Field(min_length=1)
    buttons: list[ButtonSpec] = Field(default_factory=list)

    #: 이 템플릿이 풀어 주는 문제. 판매 문구의 재료가 된다
    problems: list[str] = Field(default_factory=list)

    @property
    def database_map(self) -> dict[str, DatabaseSpec]:
        return {db.key: db for db in self.databases}

    @property
    def page_titles(self) -> set[str]:
        return {node.title for page in self.pages for node in page.walk()}

    @model_validator(mode="after")
    def _check(self) -> "TemplateSpec":
        if not self.slug:
            object.__setattr__(self, "slug", slugify(self.topic))

        keys = [db.key for db in self.databases]
        if len(keys) != len(set(keys)):
            raise ValueError("데이터베이스 key 가 겹칩니다")

        known_pages = self.page_titles
        by_key = self.database_map

        for db in self.databases:
            if db.parent_page and db.parent_page not in known_pages:
                raise ValueError(
                    f"{db.name}: parent_page 가 없는 페이지입니다: {db.parent_page}\n"
                    f"  있는 페이지: {', '.join(sorted(known_pages))}")

            for spec in db.properties:
                if spec.type == "relation" and spec.relation_to not in by_key:
                    raise ValueError(
                        f"{db.name} / {spec.name}: relation_to 가 없는 데이터베이스입니다: "
                        f"{spec.relation_to}\n  있는 key: {', '.join(sorted(by_key))}")

                if spec.type == "rollup":
                    through = db.property_map.get(spec.rollup_relation)
                    if through is None or through.type != "relation":
                        raise ValueError(
                            f"{db.name} / {spec.name}: rollup_relation 은 같은 "
                            f"데이터베이스의 relation 속성이어야 합니다 "
                            f"({spec.rollup_relation})")
                    target = by_key.get(through.relation_to)
                    if target and spec.rollup_property not in target.property_map:
                        raise ValueError(
                            f"{db.name} / {spec.name}: rollup_property 가 "
                            f"{target.name} 에 없습니다: {spec.rollup_property}")

        for button in self.buttons:
            if button.where and button.where not in known_pages:
                raise ValueError(f"버튼 {button.name}: 없는 페이지입니다: {button.where}")
            if button.creates and button.creates not in by_key:
                raise ValueError(f"버튼 {button.name}: 없는 데이터베이스입니다: {button.creates}")
            target = by_key.get(button.creates)
            if target:
                unknown = sorted(set(button.prefill) - set(target.property_map))
                if unknown:
                    raise ValueError(
                        f"버튼 {button.name}: 없는 속성을 미리 채웁니다: {', '.join(unknown)}")
        return self

    def relation_properties(self) -> list[tuple[DatabaseSpec, PropertySpec]]:
        """관계·롤업 속성만 모아 준다. deploy 가 2단계로 나눠 만들 때 쓴다."""
        found = []
        for db in self.databases:
            for spec in db.properties:
                if spec.type in ("relation", "rollup"):
                    found.append((db, spec))
        return found


PageNode.model_rebuild()
