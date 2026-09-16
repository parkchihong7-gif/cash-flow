"""아주 작은 계산식 해석기.

모델의 매출·비용 식을 `models/*.yaml` 에 **글자로** 적어 두고,
파이썬(CLI)과 자바스크립트(대시보드)가 **같은 글자를 각자 계산한다.**

왜 이렇게 하는가. 계산식을 파이썬에 한 번, 자바스크립트에 한 번 적으면
둘이 언젠가 어긋난다. 그러면 터미널에서 본 숫자와 대시보드에서 본 숫자가
다른데 어느 쪽이 맞는지 알 수 없게 된다. 식을 한 군데만 두면 그 일이 없다.
(`tests/test_income_sim.py` 가 node 로 두 결과를 실제로 맞춰 본다.)

`eval()` 은 쓰지 않는다. 설정 파일에 적힌 글자를 그대로 실행하면
그 파일을 고칠 수 있는 사람이 무엇이든 실행할 수 있게 된다.
대신 식을 해석해서 **사칙연산·거듭제곱·min·max 만** 허용한다.
"""

from __future__ import annotations

import ast
from typing import Mapping

__all__ = ["evaluate", "check_expression", "ExpressionError", "ALLOWED_CALLS"]

#: 식 안에서 부를 수 있는 함수. 자바스크립트 쪽에도 같은 이름으로 넣어 준다.
ALLOWED_CALLS = {"min": min, "max": max}

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
_ALLOWED_UNARY = (ast.UAdd, ast.USub)


class ExpressionError(ValueError):
    """식이 규칙에 맞지 않을 때."""


def _walk(node: ast.AST, names: set[str]) -> None:
    if isinstance(node, ast.Expression):
        _walk(node.body, names)
    elif isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise ExpressionError(f"쓸 수 없는 연산입니다: {type(node.op).__name__}")
        _walk(node.left, names)
        _walk(node.right, names)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARY):
            raise ExpressionError(f"쓸 수 없는 연산입니다: {type(node.op).__name__}")
        _walk(node.operand, names)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_CALLS:
            raise ExpressionError(
                f"쓸 수 있는 함수는 {', '.join(sorted(ALLOWED_CALLS))} 뿐입니다")
        if node.keywords:
            raise ExpressionError("함수에 이름표 붙은 값은 넣을 수 없습니다")
        for argument in node.args:
            _walk(argument, names)
    elif isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
            raise ExpressionError(f"숫자만 넣을 수 있습니다: {node.value!r}")
    else:
        raise ExpressionError(f"쓸 수 없는 표현입니다: {type(node).__name__}")


def check_expression(source: str) -> set[str]:
    """식을 검사하고 그 안에 쓰인 이름들을 돌려준다."""
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"식을 읽지 못했습니다: {source!r} ({exc.msg})") from exc

    names: set[str] = set()
    _walk(tree, names)
    return names - set(ALLOWED_CALLS)


def evaluate(source: str, values: Mapping[str, float]) -> float:
    """식을 계산한다.

    0 으로 나누면 오류를 내지 않고 0 을 돌려준다. 자바스크립트는 같은 경우에
    Infinity 를 내놓기 때문에, 맞춰 두지 않으면 두 계산 결과가 갈린다.
    시뮬레이터에서 0 으로 나누는 상황은 대개 '아직 아무것도 없다' 는 뜻이라
    0 으로 보는 편이 화면에도 자연스럽다.
    """
    used = check_expression(source)
    missing = sorted(used - set(values))
    if missing:
        raise ExpressionError(
            f"식에 쓰인 값을 찾지 못했습니다: {', '.join(missing)}\n  식: {source}")

    scope = {**ALLOWED_CALLS, **{key: float(values[key]) for key in used}}
    try:
        result = eval(                                   # noqa: S307
            compile(ast.parse(source, mode="eval"), "<수식>", "eval"),
            {"__builtins__": {}}, scope,
        )
    except ZeroDivisionError:
        return 0.0
    except OverflowError as exc:
        raise ExpressionError(f"숫자가 너무 커졌습니다: {source}") from exc

    number = float(result)
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number
