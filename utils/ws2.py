# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 thiliapr <thiliapr@tutanota.com>
# SPDX-Package: thiliapr/adv_to_renpy
# SPDX-PackageHomePage: https://github.com/thiliapr/adv_to_renpy

# 本文件是 thiliapr/adv_to_renpy 的一部分
# thiliapr/adv_to_renpy 是自由软件，你可以依照由自由软件基金会发布的 GNU Affero 通用公共许可证分发或修改它，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 thiliapr/adv_to_renpy 是希望它能有用，但是并无保障，甚至连可销售和符合某个特定的目的都不保证。请参看 GNU Affero 通用公共许可证以了解详情。
# 你应该随程序获得一份 GNU Affero 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/agpl.html>。

from functools import lru_cache
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Annotated, ClassVar, Self, TypeVar
from pydantic import BaseModel, ConfigDict, Field
from construct import Array, Bytes, CString, Const, GreedyBytes, NullTerminated, StringEncoded, StringError, Struct, Switch, Tell, Int8ul, Int16ul, Int32ul, Float32l, this


# 二进制程序的解码上下文、结果模型、操作模型
Pointer = Annotated[int, Field(ge=0)]
OperationCode = Annotated[int, Field(ge=0, le=255)]
OperationParseFunction = Callable[["ProgramDecompileContext"], "OperationDecompileResult"]
GetSchemeFunction = Callable[["ProgramDecompileEnvironment"], Struct]


class ProgramDecompileEnvironment(BaseModel):
    model_config = ConfigDict(frozen=True)

    encoding: str = Field(description="解析文本所用的编码")
    version: tuple[int, int, int, int] = Field((1, 9, 0, 0), description="程序解析器的版本")


class ProgramDecompileContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    program: memoryview = Field(description="程序内容")
    current_pointer: Pointer = Field(0, description="处理完的字节，下一次解析开始的位置")
    environment: ProgramDecompileEnvironment = Field(description="程序解释器的环境，比如解释器的版本、文本编码")


class AbstractOperation(BaseModel, ABC):
    model_config = ConfigDict(frozen=True)
    operation_code: ClassVar[OperationCode]

    @classmethod
    @abstractmethod
    def parse_from_program(cls: Self, ctx: ProgramDecompileContext) -> "OperationDecompileResult":
        ...


class OperationDecompileResult(BaseModel):
    operation: AbstractOperation | None = Field(description="解析出来的操作")
    new_pointer: Pointer = Field(description="解析后，程序的指针")


class DeclarativeOperation(AbstractOperation, ABC):
    """
    可以用 Construct 表达的、属性固定的 Operation
    """
    operation_code: ClassVar[OperationCode]

    @classmethod
    @lru_cache()
    def compiled_schema(cls, env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "operation_code" / Const(cls.operation_code, Int8ul),
            *cls.payload_schema(env).subcons,
            "size_of_operation" / Tell
        )

    @classmethod
    def parse_from_program(cls: Self, ctx: ProgramDecompileContext) -> OperationDecompileResult:
        result = cls.compiled_schema(ctx.environment).parse(ctx.program[ctx.current_pointer:])
        return OperationDecompileResult(
            operation=cls(**{key: getattr(result, key) for key in cls.model_fields}),
            new_pointer=ctx.current_pointer + result.size_of_operation
        )

    @abstractmethod
    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        ...


# Operation Code 注册
OperationClassT = TypeVar("OperationClassT", bound=AbstractOperation)
CodeToOperation: dict[OperationCode, OperationParseFunction] = {}


def register_operation_class(operation_class: OperationClassT) -> OperationClassT:
    CodeToOperation[operation_class.operation_code] = operation_class.parse_from_program
    return operation_class


def register_operation_parse_function(operation_code: OperationCode, get_scheme: GetSchemeFunction):
    "解析不知道什么东西的 Operation，不会创建 Operation"
    @lru_cache()
    def compiled_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "operation_code" / Const(operation_code, Int8ul),
            *get_scheme(env).subcons,
            "size_of_operation" / Tell
        )

    def parse_function(ctx: ProgramDecompileContext) -> OperationDecompileResult:
        result = compiled_schema(ctx.environment).parse(ctx.program[ctx.current_pointer:])
        return OperationDecompileResult(
            operation=None,
            new_pointer=ctx.current_pointer + result.size_of_operation
        )

    CodeToOperation[operation_code] = parse_function


# 替换掉不靠谱的、只支持 UTF-8/16/32 的 CString。如果 CString 靠谱起来，请改用正规军的 CString
@lru_cache()
def CStringEncoding(encoding: str) -> StringEncoded:
    "尝试用原生 CString，如果不支持指定编码，就假装是 1-byte NUL 结尾字符串"
    try:
        return CString(encoding)
    except StringError:
        return StringEncoded(NullTerminated(GreedyBytes), encoding)


# From: https://github.com/DarthFly/advhd_ws2_tools/blob/master/Ws2/Opcodes
# 真正的有用 Operation
class ConditionShort(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x01
    config: int

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct("config" / Int8ul)


class ConditionLong(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x01
    config: int
    scalar_id: int = Field(description="要比较的变量的 ID")
    compare_value: float = Field(description="要和变量比较的数")
    pointer1: Pointer = Field(description="不同 config 有不同行为的指针，我也不知道它干啥的")
    pointer2: Pointer = Field(description="不同 config 有不同行为的指针，我也不知道它干啥的")

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "config" / Int8ul,
            "scalar_id" / Int16ul,
            "compare_value" / Float32l,
            "pointer1" / Int32ul,
            "pointer2" / Int32ul,
        )


def parse_condition_operation(ctx: ProgramDecompileContext) -> OperationDecompileResult:
    # 很诡异，但是代码就是这么写的
    # https://github.com/DarthFly/advhd_ws2_tools/blob/ddfd492936d9dadb3726d7bf67684ada4e413889/Ws2/Opcodes/Condition.php#L17
    # The "$configValue === 3" part is validation for mainmenu vs HOT_001 - one has IF, another doesn't.
    config = ctx.program[ctx.current_pointer + 1]
    if (config in [2, 128, 129, 130, 192]) or (config == 3 and ctx.program[ctx.current_pointer + 2] in [50, 51, 127, 128]):
        condition_class = ConditionLong
    else:
        condition_class = ConditionShort
    return condition_class.parse_from_program(ctx)


CodeToOperation[ConditionShort.operation_code] = parse_condition_operation


@register_operation_class
class Jump2(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x02
    pointer: Pointer

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct("pointer" / Int32ul)


@register_operation_class
class RunFile(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x04
    file: str

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct("file" / CStringEncoding(env.encoding))


@register_operation_class
class Jump1(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x06
    pointer: int

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct("pointer" / Int32ul)


@register_operation_class
class NextFile(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x07
    file: str

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct("file" / CStringEncoding(env.encoding))


@register_operation_class
class LayerConfig(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x09
    config: tuple[int, int, int]
    unknown: float

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "config" / Array(3, Int8ul),
            "unknown" / Float32l
        )


@register_operation_class
class SetScalar(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x0b
    scalar_id: int
    value: int

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "scalar_id" / Int16ul,
            "value" / Int8ul
        )


@register_operation_class
class ShowChoice(AbstractOperation):
    class AbstractChoice(BaseModel, ABC):
        model_config = ConfigDict(frozen=True)

        id: int
        text: str
        operations: tuple[int, int, int]

    class ChoicePointer(AbstractChoice):
        pointer: Pointer

    class ChoiceFile(AbstractChoice):
        file: str

    operation_code: ClassVar[OperationCode] = 0x0f
    choices: tuple[ChoicePointer | ChoiceFile, ...]

    @classmethod
    @lru_cache()
    def compiled_scheme(cls: Self, env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "operation_code" / Const(cls.operation_code, Int8ul),
            "choice_count" / Int8ul,
            "choices" / Array(this.choice_count, Struct(
                "id" / Int16ul,
                "text" / CStringEncoding(env.encoding),
                "operations" / Array(3, Int8ul),
                "jump_type" / Int8ul,
                "content" / Switch(this.jump_type, {
                    6: Int32ul,
                    7: CStringEncoding(env.encoding)
                })
            )),
            "size_of_operation" / Tell
        )

    def parse_from_program(cls: Self, ctx: ProgramDecompileContext) -> OperationDecompileResult:
        result = cls.compiled_scheme(ctx.environment).parse(ctx.program[ctx.current_pointer:])
        return OperationDecompileResult(operation=cls(choices=[
            {
                6: cls.ChoicePointer,
                7: cls.ChoiceFile
            }[choice.jump_type](
                id=choice.id,
                text=choice.text,
                operations=choice.operations,
                **{{6: "pointer", 7: "file"}[choice.jump_type]: choice.content}
            )
            for choice in result.choices
        ]), new_pointer=ctx.current_pointer + result.size_of_operation)


@register_operation_class
class SetTimer(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x11
    name: str
    config: int = 0
    seconds: float

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "name" / CStringEncoding(env.encoding),
            *(["config" / Int8ul] if env.version > (1, 4, 0, 0) else []),
            "seconds" / Float32l
        )


@register_operation_class
class StartTimer(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x12
    name: str
    config: tuple[int, int]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "name" / CStringEncoding(env.encoding),
            "config" / Array(2, Int8ul)
        )


@register_operation_class
class DisplayMessage(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x14
    message_id: int
    layer: str
    message: str
    type: int = 0

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "message_id" / Int32ul,
            "layer" / CStringEncoding(env.encoding),
            "message" / CStringEncoding(env.encoding),
            *(["type" / Int8ul] if env.version > (1, 0, 6, 0) else [])
        )


@register_operation_class
class SetDisplayName(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x15
    character_name: str
    config: int = 0

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "character_name" / CStringEncoding(env.encoding),
            *(["config" / Int8ul] if env.version > (1, 0, 6, 0) else [])
        )


@register_operation_class
class AddMessageToLog(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x18
    config: int
    message: str

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "config" / Int8ul,
            "message" / CStringEncoding(env.encoding)
        )


@register_operation_class
class OpenTitle(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x1a
    unknown: str

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct("unknown" / CStringEncoding(env.encoding))


@register_operation_class
class ExecuteFunction(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x1c
    function: str
    unknown: str

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "function" / CStringEncoding(env.encoding),
            "unknown" / CStringEncoding(env.encoding),
            "config" / Array(3 if env.version > (1, 0, 0, 0) else 2, Int8ul)
        )


@register_operation_class
class PlayMusic(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x1e
    channel: str
    file: str
    config: tuple[int, ...]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "file" / CStringEncoding(env.encoding),
            "config" / Array(17 if env.version > (1, 0, 6, 0) else 13, Int8ul)
        )


@register_operation_class
class StopMusic(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x1f
    channel: str
    seconds: float

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "seconds" / Float32l
        )


@register_operation_class
class SoundEffect(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x28
    channel: str
    file: str
    unknown1: float
    unknown2: float
    config: tuple[int, ...]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "file" / CStringEncoding(env.encoding),
            "unknown1" / Float32l,
            "unknown2" / Float32l,
            "config" / Array(14 if env.version > (1, 0, 6, 0) else 10, Int8ul)
        )


@register_operation_class
class CharMessageStart(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x2e

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct()


@register_operation_class
class SetBackground(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x33
    channel: str
    file: str

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "file" / CStringEncoding(env.encoding),
        )


@register_operation_class
class UsePnaPackage(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x34
    channel: str
    effect_name: str
    config: tuple[int, int]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "effect_name" / CStringEncoding(env.encoding),
            "config" / Array(2, Int8ul)
        )


@register_operation_class
class PlayMovie(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x35
    name: str
    file: str
    config: tuple[int, int, int]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "name" / CStringEncoding(env.encoding),
            "file" / CStringEncoding(env.encoding),
            "config" / Array(3, Int8ul)
        )


@register_operation_class
class ClearLayer(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x37
    channel: str

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct("channel" / CStringEncoding(env.encoding))


@register_operation_class
class DisplayCharacterImage(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x39
    channel: str
    config: tuple[int, int]
    image_ids: tuple[int, ...]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "config" / Array(2, Int8ul),
            "image_count" / Int8ul,
            "image_ids" / Array(this.image_count, Int16ul)
        )


@register_operation_class
class BackgroundMessage(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x3b
    channel: str
    message: str
    message_id: int
    unknown1: int
    unknown2: tuple[float, ...]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "message" / CStringEncoding(env.encoding),
            "message_id" / Int16ul,
            "unknown1" / Int32ul,
            "unknown2" / Array(8, Float32l)
        )


@register_operation_class
class SetMask(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x40
    channel: str
    name: str
    options: int

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "name" / CStringEncoding(env.encoding),
            "options" / Int8ul,
        )


@register_operation_class
class DragBackground(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x45
    channel: str
    config: tuple[int, int]
    unknown: tuple[float, float, float, float]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "config" / Array(2, Int8ul),
            "unknown" / Array(4, Float32l)
        )


@register_operation_class
class MoveBackground(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x46
    channel: str
    config: tuple[int, int, int]
    unknown: tuple[float, float, float, float]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "config" / Array(3, Int8ul),
            "unknown" / Array(4, Float32l)
        )


@register_operation_class
class Effect1(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x47
    channel: str
    effect_name: str
    config1: tuple[int, int, int, int]
    unknown: tuple[float, float, float, float, float, float]
    config2: tuple[int, int]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "effect_name" / CStringEncoding(env.encoding),
            "config1" / Array(4, Int8ul),
            "unknown" / Array(6, Float32l),
            "config2" / Array(2, Int8ul)
        )


@register_operation_class
class Effect2(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x48
    channel: str
    effect_name: str
    config: tuple[int, int, int, int, int]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "channel" / CStringEncoding(env.encoding),
            "effect_name" / CStringEncoding(env.encoding),
            "config" / Array(5, Int8ul),
        )


@register_operation_class
class RainStart(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x56
    id: str
    config: tuple[int, ...]
    unknown1: tuple[float, ...]
    unknown2: tuple[int, ...]
    picture1: str
    picture2: str
    picture3: str
    picture1_config: tuple[int, int]
    picture2_config: tuple[int, int, int, int]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "id" / CStringEncoding(env.encoding),
            "config" / Array(7, Int8ul),
            "unknown1" / Array(10, Float32l),
            "unknown2" / Array(5, Int32ul),
            "picture1" / CStringEncoding(env.encoding),
            "picture1_config" / Array(2, Int8ul),
            "picture2" / CStringEncoding(env.encoding),
            "picture3" / CStringEncoding(env.encoding),
            "picture2_config" / Array(4, Int8ul)
        )


@register_operation_class
class RainEnd(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x5c
    unknown: str

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct("unknown" / CStringEncoding(env.encoding))


@register_operation_class
class ShowGraphic(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x66
    file: str

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct("file" / CStringEncoding(env.encoding))


@register_operation_class
class SetVariable(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0x6e
    name: str
    value: str

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "name" / CStringEncoding(env.encoding),
            "value" / CStringEncoding(env.encoding)
        )


@register_operation_class
class ConditionalJump(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0xe6
    pointer1: int
    pointer2: int

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "pointer1" / Int32ul,
            "pointer2" / Int32ul
        )


@register_operation_class
class FileEnd(DeclarativeOperation):
    operation_code: ClassVar[OperationCode] = 0xff
    unknown: int
    config: tuple[int, int, int, int]

    def payload_schema(env: ProgramDecompileEnvironment) -> Struct:
        return Struct(
            "unknown" / Int32ul,
            "config" / Array(4, Int8ul),
        )


# 不知道干啥用的 Operation
register_operation_parse_function(0x00, lambda env: Struct())
register_operation_parse_function(0x0d, lambda env: Struct(Bytes(8)))
register_operation_parse_function(0x0e, lambda env: Struct(Bytes(5)))
register_operation_parse_function(0x08, lambda env: Struct(Bytes(1)))
register_operation_parse_function(0x16, lambda env: Struct("options" / Bytes(2 if env.version > (1, 0, 6, 0) else 1)))
register_operation_parse_function(0x17, lambda env: Struct(Bytes(1)))
register_operation_parse_function(0x19, lambda env: Struct(*([Bytes(3)] if env.version > (1, 4, 0, 0) else [])))
register_operation_parse_function(0x1b, lambda env: Struct(Bytes(1)))
register_operation_parse_function(0x20, lambda env: Struct(
    "id" / CStringEncoding(env.encoding),
    "seconds" / Float32l,
    Int16ul,
))
register_operation_parse_function(0x29, lambda env: Struct(
    "channel" / CStringEncoding(env.encoding),
    Float32l
))
register_operation_parse_function(0x2a, lambda env: Struct(
    "channel" / CStringEncoding(env.encoding),
    Float32l,
    Bytes(2)
))
register_operation_parse_function(0x32, lambda env: Struct(CStringEncoding(env.encoding)))
register_operation_parse_function(0x3a, lambda env: Struct(
    "channel" / CStringEncoding(env.encoding),
    "config" / Bytes(2),
))
register_operation_parse_function(0x3d, lambda env: Struct(Bytes(2)))
register_operation_parse_function(0x3e, lambda env: Struct())
register_operation_parse_function(0x42, lambda env: Struct(
    "channel" / CStringEncoding(env.encoding),
    "config" / Bytes(2),
))
register_operation_parse_function(0x43, lambda env: Struct(CStringEncoding(env.encoding)))
register_operation_parse_function(0x57, lambda env: Struct(
    "channel" / CStringEncoding(env.encoding),
    "config" / Bytes(2),
))
register_operation_parse_function(0x64, lambda env: Struct())
register_operation_parse_function(0x65, lambda env: Struct(
    "config1" / Bytes(3),
    Array(2, Float32l),
    "config2" / Bytes(2)
))
register_operation_parse_function(0x67, lambda env: Struct(
    "config1" / Bytes(4),
    Array(5, Float32l),
    "config2" / Int8ul
))
register_operation_parse_function(0x68, lambda env: Struct(Int8ul))

# DarthFly 在 Fadvhd_ws2_tools 没写到的、但是我遇到的 Operation
# 在《華は短し、踊れよ乙女》遇到的
register_operation_parse_function(0x22, lambda env: Struct(
    CStringEncoding(env.encoding),
    Int8ul,
))
register_operation_parse_function(0x2d, lambda env: Struct(
    CStringEncoding(env.encoding),
    Int8ul,
))
register_operation_parse_function(0x98, lambda env: Struct(
    CStringEncoding(env.encoding),
    Int32ul,
    Array(2, Float32l),
    Bytes(18),
))
register_operation_parse_function(0x99, lambda env: Struct(
    CStringEncoding(env.encoding),
    Bytes(7)
))
register_operation_parse_function(0xfb, lambda env: Struct(Bytes(1)))
register_operation_parse_function(0xfc, lambda env: Struct(Bytes(2)))
register_operation_parse_function(0xfd, lambda env: Struct())
