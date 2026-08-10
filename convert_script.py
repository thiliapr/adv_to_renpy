# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 thiliapr <thiliapr@tutanota.com>
# SPDX-Package: thiliapr/adv_to_renpy
# SPDX-PackageHomePage: https://github.com/thiliapr/adv_to_renpy

# 本文件是 thiliapr/adv_to_renpy 的一部分
# thiliapr/adv_to_renpy 是自由软件，你可以依照由自由软件基金会发布的 GNU Affero 通用公共许可证分发或修改它，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 thiliapr/adv_to_renpy 是希望它能有用，但是并无保障，甚至连可销售和符合某个特定的目的都不保证。请参看 GNU Affero 通用公共许可证以了解详情。
# 你应该随程序获得一份 GNU Affero 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/agpl.html>。

import re
import pathlib
import argparse
from functools import lru_cache
from pydantic import BaseModel
from tqdm import tqdm
from decompile import decompile_script
from utils import ast, ws2


# 脚本常量
SCRIPT_START = """
define config.old_substitutions = False
define config.safe_text = True

init python:
    style.default.ruby_style.yoffset = -28

    def dot_tag(tag, argument, contents):
        rv = []
        for kind, text in contents:
            if kind != renpy.TEXT_TEXT:
                rv.append((kind, text))
                continue
            for char in text:
                rv.extend([(renpy.TEXT_TAG, "rb"), (renpy.TEXT_TEXT, char), (renpy.TEXT_TAG, "/rb"), (renpy.TEXT_TAG, "rt"), (renpy.TEXT_TEXT, "•"), (renpy.TEXT_TAG, "/rt")])
        return rv
    config.custom_text_tags["dot"] = dot_tag

label start:
    jump {entry_script}__start
""".strip() + "\n\n"
SCRIPT_BLOCK = """
label {current_script}__start:
    jump {current_script}__pointer_{start_pointer}
""".strip() + "\n\n"
HIGHLIGHT_TEXT_EXPRESSION = re.compile(r"%XS\d\d(.+)?%XE")
DOT_TEXT_EXPRESSION = re.compile(r"{(.+)?;・}")


# 转换 Operation 到 Ren'Py 指令
def convert_operation_to_ast(operation: ws2.AbstractOperation) -> ast.Sentence:
    if isinstance(operation, (ws2.Jump1, ws2.Jump2)):
        return ast.Jump(pointer=operation.pointer)
    if isinstance(operation, ws2.NextFile):
        return ast.NextFile(file=operation.file)
    if isinstance(operation, ws2.ShowChoice):
        return ast.Menu(operation=operation)
    if isinstance(operation, ws2.DisplayMessage):
        if not (message := operation.message.removesuffix("%K%P").replace("%P", "").replace("%K", "{w}")):
            return
        message = re.sub(HIGHLIGHT_TEXT_EXPRESSION, r"{size=*1.5}\1{/size}", message)
        message = re.sub(DOT_TEXT_EXPRESSION, r"{dot}\1{/dot}", message)
        return ast.DisplayMessage(message=message)
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


# 辅助工具
SentenceArticle = tuple[tuple[ws2.Pointer, ast.Sentence], ...]
ParagraphArticle = tuple[tuple[ws2.Pointer, list[ast.Sentence]], ...]

class ArticleFilter:
    @staticmethod
    @lru_cache()
    def get_real_pointer(article: SentenceArticle, pointer: ws2.Pointer) -> ws2.Pointer:
        return ast.JumpPointer(target_pointer=pointer).compile(ast.ASTCompileEnvironment(available_pointers=list(zip(*article))[0], script_name="thread_jump"))

    @staticmethod
    def decide_skip_condition(article: SentenceArticle) -> SentenceArticle:
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

        return tuple(new_article)

    @staticmethod
    def remove_non_exist_background(article: SentenceArticle, images_dir: list[str]) -> SentenceArticle:
        new_article = []
        for pointer, sentence in article:
            if isinstance(sentence, ast.SetBackground) and not (images_dir / sentence.file).exists():
                continue
            new_article.append((pointer, sentence))
        return tuple(new_article)

    @staticmethod
    def remove_jump_to_next_pointer(article: SentenceArticle) -> SentenceArticle:
        """
        删除类似:
        #0 jump 1
        #1 func
        这种无意义的跳转，因为程序会自动顺序执行下一条指令
        """
        new_article = []
        for index, (pointer, sentence) in enumerate(article):
            if isinstance(sentence, ast.Jump) and index + 1 < len(article) and article[index + 1][0] == ArticleFilter.get_real_pointer(article, sentence.pointer):
                continue
            new_article.append((pointer, sentence))
        return tuple(new_article)

    @staticmethod
    def clean_useless_code(article: SentenceArticle) -> SentenceArticle:
        class WalkContext(BaseModel):
            current_pointer: ws2.Pointer
            last_set_message_name: ws2.Pointer | None = None
            last_background_file: str = "not_a_file"

        class WalkResult(BaseModel):
            walked_pointer: set[ws2.Pointer] = set()
            message_content_to_name: dict[ws2.Pointer, dict[str, set[ws2.Pointer]]] = {}
            last_background_before_setting: dict[ws2.Pointer, set[str]] = {}

        pointer_to_index = {pointer: index for index, (pointer, _) in enumerate(article)}
        def walk(context: WalkContext, result: WalkResult):
            # 走过了地区不要再走一遍
            try:
                context.current_pointer = ArticleFilter.get_real_pointer(article, context.current_pointer)
                if context.current_pointer in result.walked_pointer:
                    return
            except ValueError:
                return

            # 按照指令跑一下程序
            index = pointer_to_index[context.current_pointer]
            while index < len(article):
                pointer, sentence = article[index]
                result.walked_pointer.add(pointer)

                # 记录消息的角色名称设定、内容显示
                if isinstance(sentence, ast.SetDisplayName):
                    context.last_set_message_name = pointer
                elif isinstance(sentence, ast.DisplayMessage):
                    result.message_content_to_name.setdefault(pointer, {})
                    if context.last_set_message_name:
                        result.message_content_to_name[pointer].setdefault(article[pointer_to_index[context.last_set_message_name]][1].character_name, set()).add(context.last_set_message_name)

                # 记录背景图形的设定
                elif isinstance(sentence, ast.SetBackground):
                    result.last_background_before_setting.setdefault(pointer, set()).add(context.last_background_file)
                    context.last_background_file = sentence.file

                # 如果是无条件跳转，跳转到指定位置
                elif isinstance(sentence, ast.Jump):
                    index = pointer_to_index[ArticleFilter.get_real_pointer(article, sentence.pointer)]
                    continue
                if isinstance(sentence, ast.NextFile):
                    break

                # 有条件跳转时，分叉出 3 条路——pointer1、pointer2、原指针下继续
                if isinstance(sentence, ast.UnknownSentence) and isinstance(sentence.operation, (ws2.ConditionLong, ws2.ConditionalJump)):
                    for pointer in [sentence.operation.pointer1, sentence.operation.pointer2]:
                        walk(context.model_copy(update={"current_pointer": pointer}), result)

                # 如果是菜单，分叉出 N 条路。ShowChoice 肯定跳到不知到哪里去，现在别走了
                if isinstance(sentence, ast.Menu):
                    for choice in sentence.operation.choices:
                        if isinstance(choice, ws2.ShowChoice.ChoicePointer):
                            walk(context.model_copy(update={"current_pointer": choice.pointer}), result)
                    break

                # 下一条指令
                index += 1

        # 按照控制流跑一遍程序
        result = WalkResult()
        walk(WalkContext(current_pointer=article[0][0]), result)

        # 处理收集到的数据、整理出有用的 SetDisplayName
        useful_name_setting = set(
            name_setting
            for name_setting_per_content in result.message_content_to_name.values() if len(name_setting_per_content) > 1
            for name_setting_per_name in name_setting_per_content.values()
            for name_setting in name_setting_per_name
        )

        # 过滤掉死代码（没有跑过的指针）、没用的背景切换
        new_article = []
        for pointer, sentence in article:
            if pointer not in result.walked_pointer:
                continue

            # 合并消息的名称和内容、过滤掉无用的 SetDisplayName
            if pointer in result.message_content_to_name and len(character_name := result.message_content_to_name[pointer]) <= 1:
                # 因为 Ren'Py 支持变量角色名，所以要用 "" 包括表示这是一个字面量
                new_article.append((pointer, sentence.model_copy(update={"character_name": f'"{list(character_name.keys())[0]}"' if character_name else ""})))
                continue
            if isinstance(sentence, ast.SetDisplayName) and pointer not in useful_name_setting:
                continue

            # 删除没变化的背景变化指令
            if isinstance(sentence, ast.SetBackground) and result.last_background_before_setting[pointer] == {sentence.file}:
                continue

            # 一般指令
            new_article.append((pointer, sentence))
        return tuple(new_article)

    def remove_repetitive_sound_effect(article: SentenceArticle):
        new_article = []
        last_sound_effect = None
        for pointer, sentence in article:
            # 跳过同一时间出现的相同音效
            if isinstance(sentence, ast.SoundEffect):
                if sentence == last_sound_effect:
                    continue
                last_sound_effect = sentence

            # 显示消息需要时间，可以出现和上次相同的音效了
            if isinstance(sentence, ast.DisplayMessage):
                last_sound_effect = None

            # 加入指令列表
            new_article.append((pointer, sentence))
        return tuple(new_article)


# 写成 Ren'Py 脚本
def convert_ast_to_renpy(current_script: str, article: SentenceArticle) -> str:
    # 记录可能会被跳转到的指针
    pointers_may_jump_to = {article[0][0]}  # 第一个指针是这个脚本的入口，script__start 会跳转到这个入口
    for pointer, sentence in article:
        if isinstance(sentence, ast.Jump):
            pointers_may_jump_to.add(sentence.pointer)
        elif isinstance(sentence, ast.Menu):
            for choice in sentence.operation.choices:
                if isinstance(choice, ws2.ShowChoice.ChoicePointer):
                    pointers_may_jump_to.add(choice.pointer)
        elif isinstance(sentence, ast.UnknownSentence):
            if isinstance(sentence.operation, (ws2.Jump1, ws2.Jump2)):
                pointers_may_jump_to.add(sentence.operation.pointer)
            elif isinstance(sentence.operation, (ws2.ConditionLong, ws2.ConditionalJump)):
                pointers_may_jump_to.add(sentence.operation.pointer1)
                pointers_may_jump_to.add(sentence.operation.pointer2)

    # 合并没有被跳转到的单行指令成为一个连续的段落
    new_article = []
    for pointer, sentence in article:
        if pointer in pointers_may_jump_to:
            new_article.append((pointer, [sentence]))
            continue
        new_article[-1][1].append(sentence)
    new_article: ParagraphArticle = tuple(new_article)

    # 编译句子
    environment = ast.ASTCompileEnvironment(
        available_pointers=list(zip(*article))[0],
        script_name=current_script
    )
    new_article = [(pointer, [sentence.compile(environment) for sentence in sentences]) for pointer, sentences in new_article]

    # 写成 Ren'Py 脚本
    script = SCRIPT_BLOCK.format(current_script=current_script, start_pointer=article[0][0])
    for pointer, sentences in new_article:
        script += f"label {current_script}__pointer_{pointer}:\n"
        for sentence in sentences:
            script += "\n".join(f"    {line}" for line in sentence.splitlines()) + "\n"
        script += "\n"
    return script


# 主程序
def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("script_dir", type=pathlib.Path, help="游戏脚本目录，里面储存着一堆 .ws2 脚本")
    parser.add_argument("entry_script", help="入口脚本，比如 CO_1_1")
    parser.add_argument("project_dir", type=pathlib.Path, help="输出 Ren'Py 游戏文件夹")
    parser.add_argument("-e", "--encoding", default="cp932", help="WS2 脚本使用的文本编码，默认为 %(default)s")
    parser.add_argument("-v", "--version", type=int, nargs=4, default=(1, 9, 9, 9), metavar=("MAJOR", "MINOR", "PATCH", "BUILD"), help="程序解译环境的版本号，默认为 %(default)s")
    parser.add_argument("-b", "--only-exist-background", action="store_true", help="只使用游戏目录存在的背景")
    parser.add_argument("-o", "--output-script-path", type=pathlib.Path, help="如果指定，则将脚本输出到指定路径，而不是默认的 ${project_dir}/game/script.rpy")
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
    renpy_script_path = args.output_script_path or (args.project_dir / "game/script.rpy")
    renpy_script_path.write_text(SCRIPT_START.format(entry_script=args.entry_script), encoding="utf-8")

    # 从入口脚本开始读取脚本
    scripts_to_convert: set[str] = {args.entry_script}
    converted_scripts: set[str] = set()
    missing_scripts: set[str] = set()
    progress_bar = tqdm(total=1)

    while (remaining_scripts := scripts_to_convert - missing_scripts - converted_scripts):
        # 获取当前要处理的脚本
        current_script = remaining_scripts.pop()
        script_path = args.script_dir / f"{current_script}.ws2"

        # 如果脚本不存在，则跳过并更新进度条
        if not script_path.exists():
            missing_scripts.add(current_script)
            progress_bar.total = len(scripts_to_convert - missing_scripts)
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
        article = ArticleFilter.decide_skip_condition(article)

        # 删除不存在的背景切换指令
        article = ArticleFilter.remove_non_exist_background(article, args.project_dir / "game/images")

        # 删除无用代码
        article = ArticleFilter.clean_useless_code(article)

        # 删除重复音效
        article = ArticleFilter.remove_repetitive_sound_effect(article)

        # 删除无意义的跳转
        article = ArticleFilter.remove_jump_to_next_pointer(article)

        # 添加涉及到的脚本到待解析列表，并更新进度条
        for _, sentence in article:
            if isinstance(sentence, ast.NextFile):
                scripts_to_convert.add(sentence.file)
            elif isinstance(sentence, ast.Menu):
                for choice in sentence.operation.choices:
                    if isinstance(choice, ws2.ShowChoice.ChoiceFile):
                        scripts_to_convert.add(choice.file)
        progress_bar.total = len(scripts_to_convert - missing_scripts)

        # 将句子组成段落并编译成 Ren'Py 脚本，写入文件
        script = convert_ast_to_renpy(current_script, article)
        with open(renpy_script_path, "a", encoding="utf-8") as f:
            f.write(script)

        # 添加到已转换脚本集合，并更新进度条
        converted_scripts.add(current_script)
        progress_bar.update()
    progress_bar.close()

    if missing_scripts:
        print(f"[Warning] 未找到脚本: {', '.join(missing_scripts)}")


if __name__ == "__main__":
    main(parse_args())
