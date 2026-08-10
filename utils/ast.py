# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 thiliapr <thiliapr@tutanota.com>
# SPDX-Package: thiliapr/adv_to_renpy
# SPDX-PackageHomePage: https://github.com/thiliapr/adv_to_renpy

# 本文件是 thiliapr/adv_to_renpy 的一部分
# thiliapr/adv_to_renpy 是自由软件，你可以依照由自由软件基金会发布的 GNU Affero 通用公共许可证分发或修改它，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 thiliapr/adv_to_renpy 是希望它能有用，但是并无保障，甚至连可销售和符合某个特定的目的都不保证。请参看 GNU Affero 通用公共许可证以了解详情。
# 你应该随程序获得一份 GNU Affero 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/agpl.html>。

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, TypeVar
from pydantic import BaseModel, ConfigDict, Field
from utils import ws2


# 编译环境
class ASTCompileEnvironment(BaseModel):
    model_config = ConfigDict(frozen=True)

    available_pointers: tuple[ws2.Pointer, ...]
    script_name: str


# 组件
T = TypeVar("T")


class Component[T](BaseModel, ABC):
    model_config = ConfigDict(frozen=True)

    @abstractmethod
    def compile(self, environment: ASTCompileEnvironment) -> T:
        ...


class EnvironmentConstant(Component[T]):
    name: str

    @lru_cache()
    def compile(self, environment: ASTCompileEnvironment) -> T:
        return getattr(environment, self.name)


class JumpPointer(Component[ws2.Pointer]):
    # 尽管 Jump 的 Pointer 在原来的脚本找得到，但是经过一系列剪枝（比如你看那个 ConditionShort 毛用没有，但就是有指针指这里的）
    # 程序向后运行，所以指针向后查找
    target_pointer: ws2.Pointer

    def compile(self, environment: ASTCompileEnvironment) -> ws2.Pointer:
        # available_pointers 应该按照小到大排序。可能会因为没有找到合适的 pointer 而抛 ValueError，但不应该发生
        for pointer in environment.available_pointers:
            if pointer >= self.target_pointer:
                return pointer
        else:
            raise ValueError(f"Jump 到文件末尾 pointer:{environment.available_pointers[-1]} 了都找不到目标 pointer:{self.target_pointer}")


# 句子
class Sentence(Component[str], ABC):
    @abstractmethod
    def components(self) -> list[Any]:
        return ...

    def compile(self, environment: ASTCompileEnvironment) -> str:
        return "".join(
            str(
                component.compile(environment)
                if isinstance(component, Component) else
                component
            )
            for component in self.components()
        )


class Jump(Sentence):
    pointer: ws2.Pointer

    def components(self) -> list[str | Component]:
        return [
            "jump ",
            EnvironmentConstant[str](name="script_name"),
            "__pointer_",
            JumpPointer(target_pointer=self.pointer),
        ]


class NextFile(Sentence):
    file: str

    def components(self) -> list[str | Component]:
        return [f'jump {self.file}__start']


class Menu(Sentence):
    operation: ws2.ShowChoice

    def components(self) -> list[str | Component]:
        components = [f"# {self.operation}\nmenu:\n"]
        for choice in self.operation.choices:
            components[-1] += f'    "{choice.text}":\n        '
            if isinstance(choice, ws2.ShowChoice.ChoiceFile):
                components.append(NextFile(file=choice.file))
            else:
                components.append(Jump(pointer=choice.pointer))
            components.append("\n")
        return components


class DisplayMessage(Sentence):
    character_name: str = Field("display_name", description="初始化时是变量 display_name，后来应由编译器优化")
    message: str

    def components(self) -> list[str]:
        return [
            f'"{self.message}"'
            if self.character_name in [None, "", "''", '""'] else
            f'{self.character_name} "{self.message}"'
        ]


class SetDisplayName(Sentence):
    character_name: str

    def components(self) -> list[str]:
        return [f'$display_name = "{self.character_name}"']


class PlayMusic(Sentence):
    file: str

    def components(self) -> list[str]:
        return [f'play music "bgm/{self.file}"']


class StopMusic(Sentence):
    seconds: float

    def components(self) -> list[str]:
        return ["stop music" + (f" fadeout {self.seconds}" if self.seconds else "")]


class Voice(Sentence):
    file: str

    def components(self) -> list[str]:
        return [f'voice "voice/{self.file}"']


class SoundEffect(Sentence):
    file: str

    def components(self) -> list[str]:
        return [f'play sound "se/{self.file}"']


class SetBackground(Sentence):
    file: str

    def components(self) -> list[str]:
        return [f'scene expression "images/{self.file}" at Transform(fit="contain")']


class UnknownSentence[T](Sentence):
    operation: T

    def components(self) -> list[str]:
        # 我完全搞不懂它的工作原理，让真人搞吧
        return [f'# {repr(self.operation)}\npass']
