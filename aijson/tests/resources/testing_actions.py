import asyncio
from typing_extensions import AsyncIterator, assert_never

from aijson.models.config.action import (
    Action,
    StreamingAction,
)
from aijson.models.func import (
    register_action,
)
from aijson.models.io import (
    FinalInvocationInputs,
    BlobRepoInputs,
    BaseModel,
)
from aijson_ml.utils.prompt_context import (
    PromptElement,
    RoleElement,
    ContextElement,
    TextElement,
)
from aijson.models.blob import Blob
from aijson_ml.actions.llm import Inputs as PromptInputs

# Add


class AddInputs(BaseModel):
    a: int
    b: int


class AddOutputs(BaseModel):
    result: int


class Add(Action[AddInputs, AddOutputs]):
    name = "test_add"

    async def run(self, inputs: AddInputs) -> AddOutputs:
        return AddOutputs(result=inputs.a + inputs.b)


# Nested add


class NestedAddInputs(BaseModel):
    nested: AddInputs


class NestedAddOutputs(BaseModel):
    nested: AddOutputs


class AddNested(Action[NestedAddInputs, NestedAddOutputs]):
    name = "test_nested_add"

    async def run(self, inputs: NestedAddInputs) -> NestedAddOutputs:
        return NestedAddOutputs(
            nested=AddOutputs(result=inputs.nested.a + inputs.nested.b),
        )


# optional nested add


class OptionalNestedAddInputs(BaseModel):
    nested: AddInputs | None


class OptionalNestedAddOutputs(BaseModel):
    nested: AddOutputs | None


class OptionalAddNested(Action[OptionalNestedAddInputs, OptionalNestedAddOutputs]):
    name = "test_optional_nested_add"

    async def run(self, inputs: OptionalNestedAddInputs) -> OptionalNestedAddOutputs:
        if inputs.nested is None:
            return OptionalNestedAddOutputs(nested=None)
        return OptionalNestedAddOutputs(
            nested=AddOutputs(result=inputs.nested.a + inputs.nested.b),
        )


# Double add


class DoubleAdd(StreamingAction[AddInputs, AddOutputs]):
    name = "test_double_add"

    async def run(self, inputs: AddInputs) -> AsyncIterator[AddOutputs]:
        yield AddOutputs(result=inputs.a + inputs.b)
        yield AddOutputs(result=2 * (inputs.a + inputs.b))


# Waiting add


class WaitingAdd(Action[AddInputs, AddOutputs]):
    name = "test_waiting_add"

    async def run(self, inputs: AddInputs) -> AddOutputs:
        await asyncio.sleep(0.05)
        return AddOutputs(result=inputs.a + inputs.b)


# Error


class ErrorAction(Action[None, None]):
    name = "test_error"

    async def run(self, inputs: None) -> None:
        raise RuntimeError("This action always fails")


# Create blob


class CreateBlobOutputs(BaseModel):
    blob: Blob


class CreateBlob(Action[BlobRepoInputs, CreateBlobOutputs]):
    name = "test_create_blob"

    async def run(self, inputs: BlobRepoInputs) -> CreateBlobOutputs:
        blob = await inputs._blob_repo.save(self.log, b"testy_blob")
        return CreateBlobOutputs(blob=blob)


# Get blob


class GetBlobInputs(BlobRepoInputs):
    blob: Blob


class GetBlob(Action[GetBlobInputs, None]):
    name = "test_get_blob"

    async def run(self, inputs: GetBlobInputs) -> None:
        await inputs._blob_repo.retrieve(self.log, inputs.blob)


# Transforming prompt


class NestedPromptContext(BaseModel):
    context: list[PromptElement]


class TransformingPromptInputs(BaseModel):
    context: list[PromptElement]
    nested: NestedPromptContext


class TransformingPromptOutputs(BaseModel):
    context_value: str
    nested_context_value: str


class TransformingInput(Action[TransformingPromptInputs, TransformingPromptOutputs]):
    name = "test_transforming_prompt"

    async def run(self, inputs: TransformingPromptInputs) -> TransformingPromptOutputs:
        first_element = inputs.context[0]

        if isinstance(first_element, str):
            text = first_element
        elif isinstance(first_element, RoleElement):
            text = ""
        elif isinstance(first_element, ContextElement):
            text = first_element.value
        elif isinstance(first_element, TextElement):
            text = first_element.text
        else:
            assert_never(first_element)

        return TransformingPromptOutputs(
            context_value=text,
            nested_context_value=text,
        )


class PromptTransformingInput(Action[PromptInputs, PromptInputs]):
    name = "test_passing_prompt"

    async def run(self, inputs: PromptInputs) -> PromptInputs:
        return inputs


class RangeStreamInput(BaseModel):
    range: int


class RangeStreamOutput(BaseModel):
    value: int


class RangeStream(StreamingAction[RangeStreamInput, RangeStreamOutput]):
    name = "test_range_stream"

    async def run(self, inputs: RangeStreamInput) -> AsyncIterator[RangeStreamOutput]:
        for i in range(inputs.range):
            yield RangeStreamOutput(value=i)


class StringifierInput(BaseModel):
    value: int


class StringifierOutput(BaseModel):
    string: str


class Stringifier(Action[StringifierInput, StringifierOutput]):
    name = "test_stringifier"

    async def run(self, inputs: StringifierInput) -> StringifierOutput:
        return StringifierOutput(string=str(inputs.value))


# Non-caching action


class NonCacheAdderInputs(BaseModel):
    a: int
    b: int


class NonCacheAdderOutputs(BaseModel):
    result: int


class NonCachingAdder(Action[NonCacheAdderInputs, NonCacheAdderOutputs]):
    name = "test_non_caching_adder"
    cache = False

    async def run(self, inputs: NonCacheAdderInputs) -> NonCacheAdderOutputs:
        return NonCacheAdderOutputs(result=inputs.a + inputs.b)


# finish action


class FinishInputs(FinalInvocationInputs):
    pass


class FinishOutputs(BaseModel):
    finish_history: list[bool]


class FinishAction(Action[FinishInputs, FinishOutputs]):
    name = "test_finish"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = []

    async def run(self, inputs: FinishInputs) -> FinishOutputs:
        self.history.append(inputs._finished)
        return FinishOutputs(finish_history=self.history[:])


class Dummy:
    def __init__(self, a):
        self.a = a


class UncacheableIO(BaseModel):
    a: Dummy


class UncacheableOutputAction(Action[None, UncacheableIO]):
    name = "uncacheable"

    async def run(self, inputs: None) -> UncacheableIO:
        return UncacheableIO(a=Dummy(1))


class UncacheableInputAction(Action[UncacheableIO, None]):
    name = "uncacheable_input"

    async def run(self, inputs: UncacheableIO) -> None:
        assert inputs.a.a == 1


class IntAdd(Action[AddInputs, int]):
    name = "int_add"

    async def run(self, inputs: AddInputs) -> int:
        return inputs.a + inputs.b


class NonModelUncacheableAction(Action[None, Dummy]):
    name = "uncacheable_non_model_output"

    async def run(self, inputs: None) -> Dummy:
        return Dummy(a=1)


@register_action
def bare_func():
    return 1


@register_action(
    name="custom_func",
)
def custom_info_func():
    return 1


@register_action
async def bare_adder_func(a, b):
    return a + b


@register_action()
def annotated_adder_func(a: int, b: int) -> int:
    return a + b


@register_action
async def default_adder_func(a: int, b: int = 2) -> int:
    return a + b


@register_action
async def bare_adder_generator_func(a, b):
    for i in range(a + b):
        yield i


@register_action
async def adder_generator_func(a: int, b: int) -> AsyncIterator[int]:
    for i in range(a + b):
        yield i
