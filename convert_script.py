# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 thiliapr <thiliapr@tutanota.com>
# SPDX-Package: thiliapr/adv_to_renpy
# SPDX-PackageHomePage: https://github.com/thiliapr/adv_to_renpy

# 本文件是 thiliapr/adv_to_renpy 的一部分
# thiliapr/adv_to_renpy 是自由软件，你可以依照由自由软件基金会发布的 GNU Affero 通用公共许可证分发或修改它，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 thiliapr/adv_to_renpy 是希望它能有用，但是并无保障，甚至连可销售和符合某个特定的目的都不保证。请参看 GNU Affero 通用公共许可证以了解详情。
# 你应该随程序获得一份 GNU Affero 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/agpl.html>。

import pathlib
import argparse
from decompile import decompile_script
from utils import ast, ws2


# 转换 Operation 到 Ren'Py 指令
def convert_operation_to_ast(operation: ws2.AbstractOperation) -> ast.Sentence:
    if isinstance(operation, ws2.NextFile):
        return ast.NextFile(file=operation.file)
    if isinstance(operation, ws2.ShowChoice):
        return ast.Menu(operation=operation)
    if isinstance(operation, ws2.DisplayMessage):
        return ast.DisplayMessage(message=operation.message.removesuffix("%K%P").replace("%K", "{w}"))
    if isinstance(operation, ws2.SetDisplayName):
        return ast.SetDisplayName(character_name=operation.character_name.removeprefix("%LC"))
    if isinstance(operation, ws2.PlayMusic):
        return ast.PlayMusic(file=operation.file)
    if isinstance(operation, ws2.StopMusic):
        return ast.StopMusic(seconds=operation.seconds)
    if isinstance(operation, ws2.SoundEffect):
        return {
            False: ast.SoundEffect,
            True: ast.Voice
        }[operation.channel.startswith("char")](file=operation.file)
    if isinstance(operation, ws2.SetBackground):
        return ast.SetBackground(file=operation.file)
    if isinstance(operation, (ws2.ConditionLong, ws2.ConditionalJump, ws2.ExecuteFunction)):
        return ast.UnknownSentence(operation=operation)


# 一堆过滤器
Article = list[tuple[ws2.Pointer, ast.Sentence]]


def decide_skip_condition(article: Article) -> Article:
    new_article = []
    is_last_func_get_msg_skip = False

    for pointer, sentence in article:
        if is_last_func_get_msg_skip and isinstance(sentence, ast.UnknownSentence) and isinstance(sentence.operation, ws2.ConditionLong) and sentence.operation.config == 2 and sentence.operation.scalar_id == 999 and sentence.operation.compare_value == 1:
            # 如果分支条件是 正常模式 和 Skip 模式，那么决定正常模式
            sentence = ast.Jump(pointer=sentence.operation.pointer1)
        elif isinstance(sentence, ast.UnknownSentence) and isinstance(sentence.operation, ws2.ExecuteFunction):
            if sentence.operation.function == "GetMsgSkip":
                # 如果是 GetMsgSkip，不计入句子
                is_last_func_get_msg_skip = True
                continue
            is_last_func_get_msg_skip = False

        new_article.append((pointer, sentence))

    return new_article


def merge_message_name_display(article: Article) -> Article:
    new_article = []
    last_display_name = ""
    for pointer, sentence in article:
        if isinstance(sentence, ast.SetDisplayName):
            # 合并设定显示名称和显示消息
            last_display_name = sentence.character_name
            continue
        if isinstance(sentence, ast.DisplayMessage):
            sentence = ast.DisplayMessage(character_name=f'"{last_display_name}"' if last_display_name else "", message=sentence.message)
        new_article.append((pointer, sentence))
    return new_article


def remove_non_exist_background(article: Article, images_dir: list[str]) -> Article:
    new_article = []
    for pointer, sentence in article:
        if isinstance(sentence, ast.SetBackground) and not (images_dir / sentence.file).exists():
            continue
        new_article.append((pointer, sentence))
    return new_article


# 主程序
def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("game_dir", type=pathlib.Path, help="游戏主目录，脚本放置在 ${game_dir}/script 下")
    parser.add_argument("entry_script", help="入口脚本，比如 CO_1_1")
    parser.add_argument("project_dir", type=pathlib.Path, help="输出 Ren'Py 游戏文件夹")
    parser.add_argument("-e", "--encoding", default="cp932", help="WS2 脚本使用的文本编码，默认为 %(default)s")
    parser.add_argument("-v", "--version", type=int, nargs=4, default=(1, 9, 9, 9), metavar=("MAJOR", "MINOR", "PATCH", "BUILD"), help="程序解译环境的版本号，默认为 %(default)s")
    parser.add_argument("-b", "--only-exist-background", action="store_true", help="只使用游戏目录存在的背景")
    return parser.parse_args(args)


def main(args: argparse.Namespace):
    # 显示版权声明、无担保说明、许可证信息和查看方式
    print("[Info] ADVPlayer Game to Ren'Py Game - ADVPlayer 游戏到 Ren'Py 游戏转换器")
    print("[Info] Copyright (C) 2026 thiliapr <thiliapr@tutanota.com>")
    print("[Info] 本脚本是 thiliapr/adv_to_renpy 的一部分，是一个自由软件，遵循 GNU AGPL v3 or later 进行分发")
    print("[Info] thiliapr/adv_to_renpy 不提供任何保障，甚至连可销售和符合某个特定的目的都不保证")
    print("[Info] 您应该已收到一份 AGPL 副本。如果没有，请访问 https://www.gnu.org/licenses/agpl.html")
    print()

    # 初始化游戏脚本
    renpy_script_path = args.project_dir / "game/script.rpy"
    renpy_script_path.write_text("define config.old_substitutions = False\ndefine config.safe_text = True\n", encoding="utf-8")

    # 从入口脚本开始读取脚本
    scripts_to_convert: set[str] = {args.entry_script}
    converted_scripts: set[str] = set()

    while (remaining_scripts := scripts_to_convert - converted_scripts):
        # 获取当前要处理的脚本
        current_script = remaining_scripts.pop()
        script_path = args.game_dir / f"script/{current_script}.ws2"
        if not script_path.exists():
            print(f"[Warning] 未找到脚本: {script_path}")
            converted_scripts.add(current_script)
            continue

        # 将脚本解析成一系列操作
        instructions = decompile_script(script_path.read_bytes(), ws2.ProgramDecompileEnvironment(encoding=args.encoding, version=args.version))
        instructions = list(instructions)

        # 写成一系列 Ren'Py 语句 
        article = [
            (pointer, sentence)
            for pointer, sentence in [
                (pointer, convert_operation_to_ast(operation))
                for pointer, _, operation in instructions
            ]
            if sentence is not None
        ]

        # 处理在 skip 和正常模式下的分支，采用正常模式
        article = decide_skip_condition(article)

        # 合并显示名称和消息
        article = merge_message_name_display(article)

        # 删除不存在的背景切换指令
        article = remove_non_exist_background(article, args.project_dir / "game/images")

        # 添加涉及到的脚本到待解析列表
        for _, sentence in article:
            if isinstance(sentence, ast.NextFile):
                scripts_to_convert.add(sentence.file)
            elif isinstance(sentence, ast.Menu):
                for choice in sentence.operation.choices:
                    if isinstance(choice, ws2.ShowChoice.ChoiceFile):
                        scripts_to_convert.add(choice.file)

        # 编译句子
        environment = ast.ASTCompileEnvironment(
            available_pointers=list(zip(*article))[0],
            script_name=current_script
        )
        article = [(pointer, sentence.compile(environment)) for pointer, sentence in article]

        # 写入文件
        append_content = []
        if current_script == args.entry_script:
            append_content.append(f"label start:\n    jump {current_script}__start\n")
        append_content.append(f"label {current_script}__start:\n    jump {current_script}__pointer_{article[0][0]}\n")
        append_content.extend(
            f"label {current_script}__pointer_{pointer}:\n" + "\n".join(f"    {line}" for line in sentence.splitlines()) + "\n"
            for pointer, sentence in article
        )
        append_content = "".join(append_content)

        with open(renpy_script_path, "a", encoding="utf-8") as f:
            f.write(append_content)

        # 添加到已转换脚本集合
        converted_scripts.add(current_script)


if __name__ == "__main__":
    main(parse_args())
