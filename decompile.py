# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 thiliapr <thiliapr@tutanota.com>
# SPDX-Package: thiliapr/adv_to_renpy
# SPDX-PackageHomePage: https://github.com/thiliapr/adv_to_renpy

# 本文件是 thiliapr/adv_to_renpy 的一部分
# thiliapr/adv_to_renpy 是自由软件，你可以依照由自由软件基金会发布的 GNU Affero 通用公共许可证分发或修改它，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 thiliapr/adv_to_renpy 是希望它能有用，但是并无保障，甚至连可销售和符合某个特定的目的都不保证。请参看 GNU Affero 通用公共许可证以了解详情。
# 你应该随程序获得一份 GNU Affero 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/agpl.html>。

import sys
import pathlib
import argparse
from collections.abc import Iterator
from construct import StringError, Float32l, Int32ul
from utils.ws2 import AbstractOperation, CStringEncoding, OperationCode, Pointer, ProgramDecompileContext, ProgramDecompileEnvironment, CodeToOperation


def debug_program(context: ProgramDecompileContext):
    info = {"ptr": context.current_pointer}

    # 基本信息: 什么字符、哈希值
    char = context.program[context.current_pointer]
    info["char"] = repr(chr(char))
    info["hex"] = f"0x{char:02x}"

    # 从这里开始解析，会解析出什么 Operation
    operation = "Invaild"
    if char in CodeToOperation:
        try:
            operation = CodeToOperation[char](context).operation
            if operation is None:
                operation = "Unknown"
            else:
                operation = repr(operation)
        except Exception as e:
            operation = e
    info["op"] = operation

    # 从这里开始解析各种类型，会解析出来什么
    content = context.program[context.current_pointer:]
    for type_name, type_cls in [
        ("str", CStringEncoding(context.environment.encoding)),
        ("int", Int32ul),
        ("float", Float32l)
    ]:
        try:
            value = type_cls.parse(content)
        except StringError as e:
            value = e

        if type_name == "float":
            value = f"{value:.5f}"
        elif type_name == "str":
            value = repr(value)

        info[type_name] = value

    # 显示所有可能
    print(", ".join(f"{k}={v}" for k, v in info.items()))


def decompile_script(script: bytes, environment: ProgramDecompileEnvironment) -> Iterator[tuple[Pointer, OperationCode, AbstractOperation | None]]:
    # 初始化反编译上下文
    context = ProgramDecompileContext(
        program=memoryview(script),
        environment=environment
    )

    # 逐条解析
    while context.current_pointer < len(context.program):
        operation_code = context.program[context.current_pointer]
        if operation_code not in CodeToOperation:
            print("+ - " * 5 + "Debug Mode" + " - +" * 5, file=sys.stderr)
            while input("q to quit: ") != "q":
                debug_program(context)
                context.current_pointer += 1
            raise RuntimeError(f"存在不认识的 OPCode: {hex(operation_code)}")

        result = CodeToOperation[operation_code](context)
        new_pointer = (yield context.current_pointer, operation_code, result.operation) or result.new_pointer
        context.current_pointer = new_pointer


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("script_path", type=pathlib.Path, help="要反编译的 .ws2 脚本文件")
    parser.add_argument("-e", "--encoding", default="cp932", help="WS2 脚本使用的文本编码，默认为 %(default)s")
    parser.add_argument("-v", "--version", type=int, nargs=4, default=(1, 9, 9, 9), metavar=("MAJOR", "MINOR", "PATCH", "BUILD"), help="程序解译环境的版本号，默认为 %(default)s")
    return parser.parse_args(args)


def main(args: argparse.Namespace):
    # 显示版权声明、无担保说明、许可证信息和查看方式
    print("[Info] Script Decompiler - ADVPlayer .ws2 脚本文件反编译工具")
    print("[Info] Copyright (C) 2026 thiliapr <thiliapr@tutanota.com>")
    print("[Info] 本脚本是 thiliapr/adv_to_renpy 的一部分，是一个自由软件，遵循 GNU AGPL v3 or later 进行分发")
    print("[Info] thiliapr/adv_to_renpy 不提供任何保障，甚至连可销售和符合某个特定的目的都不保证")
    print("[Info] 您应该已收到一份 AGPL 副本。如果没有，请访问 https://www.gnu.org/licenses/agpl.html")
    print()

    # 逐条解析
    for pointer, operation_code, operation in decompile_script(args.script_path.read_bytes(), ProgramDecompileEnvironment(encoding=args.encoding, version=args.version)):
        print(f"#{pointer:06}: opcode=0x{operation_code:02x}, {'UnknownOperation' if operation is None else repr(operation)}")


if __name__ == "__main__":
    main(parse_args())
