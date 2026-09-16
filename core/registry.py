"""프로그램 레지스트리 — products/ 를 훑어 program.yaml 을 모은다.

대시보드는 이 모듈만 통해 프로그램을 본다. 새 프로그램이 추가돼도
대시보드 코드는 바뀌지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.manifest import MANIFEST_FILENAME, ProgramManifest, load_manifest
from shared.config import PRODUCTS_DIR

__all__ = ["Registry", "LoadError", "get_registry"]


@dataclass
class LoadError:
    """program.yaml 을 읽지 못한 폴더. 대시보드에 그대로 노출한다."""

    directory: Path
    message: str

    @property
    def name(self) -> str:
        return self.directory.name


class Registry:
    """products/ 아래 프로그램 목록.

    Args:
        products_dir: 훑을 폴더. 기본은 저장소의 `products/`.
    """

    def __init__(self, products_dir: Path | str = PRODUCTS_DIR) -> None:
        self.products_dir = Path(products_dir)
        self.programs: list[ProgramManifest] = []
        self.errors: list[LoadError] = []
        self.reload()

    def reload(self) -> None:
        """디스크를 다시 읽는다. 대시보드의 '새로고침'이 이걸 부른다."""
        self.programs = []
        self.errors = []
        if not self.products_dir.is_dir():
            return

        for directory in sorted(self.products_dir.iterdir()):
            if not directory.is_dir() or not (directory / MANIFEST_FILENAME).is_file():
                continue
            try:
                self.programs.append(load_manifest(directory))
            except Exception as exc:  # 한 개가 깨져도 나머지는 보여준다
                self.errors.append(LoadError(directory=directory, message=str(exc)))

        self.programs.sort(key=lambda p: (p.number, p.id))

    def get(self, program_id: str) -> ProgramManifest | None:
        return next((p for p in self.programs if p.id == program_id), None)

    def require(self, program_id: str) -> ProgramManifest:
        program = self.get(program_id)
        if program is None:
            raise KeyError(f"등록되지 않은 프로그램입니다: {program_id}")
        return program

    def __len__(self) -> int:
        return len(self.programs)

    def __iter__(self):
        return iter(self.programs)


_registry: Registry | None = None


def get_registry(reload: bool = False) -> Registry:
    """프로세스당 하나의 레지스트리를 재사용한다."""
    global _registry
    if _registry is None:
        _registry = Registry()
    elif reload:
        _registry.reload()
    return _registry
