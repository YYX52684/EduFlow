from typing import Any


class Signature: ...


class Module:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...


class Prediction:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...


class LM:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...


class InputField:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...


class OutputField:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...


class ChainOfThought:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


class Predict:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


def configure(*args: Any, **kwargs: Any) -> None: ...
