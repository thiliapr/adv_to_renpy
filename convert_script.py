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
    if isinstance(operation, (ws2.Jump1, ws2.Jump2)):
        return ast.Jump(pointer=operation.pointer)
    if isinstance(operation, ws2.NextFile):
        return ast.NextFile(file=operation.file)
    if isinstance(operation, ws2.ShowChoice):
        return ast.Menu(operation=operation)
    if isinstance(operation, ws2.DisplayMessage) and (message := operation.message.removesuffix("%K%P").replace("%P", "").replace("%K", "{w}")):
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
SentenceArticle = list[tuple[ws2.Pointer, ast.Sentence]]
ParagraphArticle = list[tuple[ws2.Pointer, list[ast.Sentence]]]

class ArticleFilter:
    @staticmethod
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

        return new_article

    @staticmethod
    def merge_message_name_display(article: SentenceArticle) -> SentenceArticle:
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

    @staticmethod
    def remove_non_exist_background(article: SentenceArticle, images_dir: list[str]) -> SentenceArticle:
        new_article = []
        for pointer, sentence in article:
            if isinstance(sentence, ast.SetBackground) and not (images_dir / sentence.file).exists():
                continue
            new_article.append((pointer, sentence))
        return new_article

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
        return new_article

    @staticmethod
    def clean_dead_code(article: SentenceArticle) -> SentenceArticle:
        pointer_to_index = {pointer: index for index, (pointer, _) in enumerate(article)}
        def walk(pointer: ws2.Pointer, walked_pointer: set[ws2.Pointer]):
            """
            按照控制流跑一遍程序

            Args:
                从哪里开始跑、走过的指针
            """
            try:
                if (pointer := ArticleFilter.get_real_pointer(article, pointer)) in walked_pointer:
                    return
            except ValueError:
                return

            # 按照指令跑一下程序
            index = pointer_to_index[pointer]
            while index < len(article):
                pointer, sentence = article[index]
                walked_pointer.add(pointer)

                # 如果是无条件跳转，跳转到指定位置
                if isinstance(sentence, ast.Jump):
                    index = pointer_to_index[ArticleFilter.get_real_pointer(article, sentence.pointer)]
                    continue
                if isinstance(sentence, ast.NextFile):
                    break

                # 有条件跳转时，分出 3 条路。ConditionLong 有可能不跳转，所以现在继续走吧
                if isinstance(sentence, ast.UnknownSentence) and isinstance(sentence.operation, (ws2.ConditionLong, ws2.ConditionalJump)):
                    walk(sentence.operation.pointer1, walked_pointer)
                    walk(sentence.operation.pointer2, walked_pointer)

                # 如果是菜单，分出 N 条路。ShowChoice 肯定跳到不知到哪里去，现在别走了
                if isinstance(sentence, ast.Menu):
                    for choice in sentence.operation.choices:
                        if isinstance(choice, ws2.ShowChoice.ChoicePointer):
                            walk(choice.pointer, walked_pointer)
                    break

                # 下一条指令
                index += 1

        # 按照控制流跑一遍程序
        walked_pointer = set()
        walk(article[0][0], walked_pointer)

        # 过滤掉死代码（没有跑过的指针）
        new_article = []
        for pointer, sentence in article:
            if pointer not in walked_pointer:
                continue
            new_article.append((pointer, sentence))
        return new_article


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
    new_article: ParagraphArticle = []
    for pointer, sentence in article:
        if pointer in pointers_may_jump_to:
            new_article.append((pointer, [sentence]))
            continue
        new_article[-1][1].append(sentence)

    # 编译句子
    environment = ast.ASTCompileEnvironment(
        available_pointers=list(zip(*article))[0],
        script_name=current_script
    )
    new_article = [(pointer, [sentence.compile(environment) for sentence in sentences]) for pointer, sentences in new_article]

    # 写成 Ren'Py 脚本
    script = f"label {current_script}__start:\n    jump {current_script}__pointer_{article[0][0]}\n\n"
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
    renpy_script_path.write_text(f"define config.old_substitutions = False\ndefine config.safe_text = True\n\nlabel start:\n    jump {args.entry_script}__start\n\n", encoding="utf-8")

    # 从入口脚本开始读取脚本
    scripts_to_convert: set[str] = {args.entry_script}
    converted_scripts: set[str] = set()

    while (remaining_scripts := scripts_to_convert - converted_scripts):
        # 获取当前要处理的脚本
        current_script = remaining_scripts.pop()
        script_path = args.script_dir / f"{current_script}.ws2"
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
        article = ArticleFilter.decide_skip_condition(article)

        # 合并显示名称和消息
        article = ArticleFilter.merge_message_name_display(article)

        # 删除不存在的背景切换指令
        article = ArticleFilter.remove_non_exist_background(article, args.project_dir / "game/images")

        # 删除死代码
        article = ArticleFilter.clean_dead_code(article)

        # 删除无意义的跳转
        article = ArticleFilter.remove_jump_to_next_pointer(article)

        # 添加涉及到的脚本到待解析列表
        for _, sentence in article:
            if isinstance(sentence, ast.NextFile):
                scripts_to_convert.add(sentence.file)
            elif isinstance(sentence, ast.Menu):
                for choice in sentence.operation.choices:
                    if isinstance(choice, ws2.ShowChoice.ChoiceFile):
                        scripts_to_convert.add(choice.file)

        # 将句子组成段落并编译成 Ren'Py 脚本，写入文件
        script = convert_ast_to_renpy(current_script, article)
        with open(renpy_script_path, "a", encoding="utf-8") as f:
            f.write(script)

        # 添加到已转换脚本集合
        converted_scripts.add(current_script)


if __name__ == "__main__":
    main(parse_args())
