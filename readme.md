# thiliapr/adv_to_renpy
试图将 ADVPlayer 引擎的游戏转换为 Ren'Py 游戏的工具

## 许可证
![GNU AGPL Version 3 Logo](https://www.gnu.org/graphics/agplv3-with-text-162x68.png)

thiliapr/adv_to_renpy 是自由软件(Free as in Freedom)，遵循 [Affero GNU 通用公共许可证第 3 版或任何后续版本](https://www.gnu.org/licenses/agpl-3.0.html)。你享有运行、研究和修改、分发修改前后的拷贝的自由，详情请参见 [什么是自由软件？](https://www.gnu.org/philosophy/free-sw.html)

## 这个工具有什么用
把 ADVPlayer 引擎的游戏转换为 Ren'Py 游戏，这样就能用 Ren'Py 的 SDK 把它移植到 GNU/Linux / Android / iOS 上了

## 怎么使用这个项目里的脚本
### 项目里脚本的介绍
- `decompile.py`: 反编译 ADVPlayer 脚本，即`.ws2`文件
- `convert_script.py`: 将`.ws2`文件转换为 Ren'Py 脚本

### 快速使用
1. 准备一个 ADVPlayer 引擎的游戏，这里以[華は短し、踊れよ乙女](https://www.ensemble-game.com/28.hanaoto/)为例子，游戏文件夹应该呈现如此结构:  
  - hanaoto
    - AdvHD.exe
    - AdvHDLang.dll
    - Bgm.arc
    - Chip0.arc
    - Rio1.arc
    - Se.arc
    - Voice.arc
2. 用[Ren'Py SDK](https://www.renpy.org/latest.html)创建一个项目，记下它的路径，记为`project_dir`，此时文件夹应该呈现如此结构:  
   - project
     - game
       - audio
       - gui
       - images
       - script.rpy
     - .gitignore
     - log.txt
3. 将游戏文件夹的`Bgm.arc`提取到`${project_dir}/game/audio/bgm/`，将储存 CG 图片的`ChipN.arc`提取到`${project_dir}/game/images/`，将储存语音的`Voice.arc`提取到`${project_dir}/game/audio/voice/`，将储存音效的`Se.arc`提取到`${project_dir}/game/audio/se/`。我使用[GARbro](https://github.com/morkt/GARbro)提取游戏资源。
4. 创建一个专门储存脚本的文件夹，记为`script_dir`，将游戏文件夹的`RioN.arc`的脚本提取到该文件夹中。
5. 找到`script_dir`中的入口脚本文件，比如`CO_1_1`，记为`entry_script`
6. 运行`python convert_script.py $script_dir $entry_script $project_dir --encoding utf-8 -only-exist-background`
   > `--encoding utf-8`需要根据游戏编码尝试，比如日文游戏常用`cp932`，汉化脚本常用`utf-8`。如果不确定就尝试`cp932`，如果报错再尝试其他编码

## FAQ
### 未知 Operation
遇到未知的 Operation 时，调试查看 Operation 的结构，在`utils/ws2.py`模仿`register_operation_parse_function`注册一个占位符 Operation，以下是一个例子，供参考:  
1. 运行
   ```bash
   convert_script.py -e utf-8 example/zh_CN CO_1_1 hanaoto -o tmp.rpy
   ```
2. 遇到未知的 OPCode 0x99，进入调试模式
   ```
   [Info] ADVPlayer Game to Ren'Py Game - ADVPlayer 游戏到 Ren'Py 游戏转换器
   [Info] Copyright (C) 2026 thiliapr <thiliapr@tutanota.com>
   [Info] 本脚本是 thiliapr/adv_to_renpy 的一部分，是一个自由软件，遵循 GNU AGPL v3 or later 进行分发
   [Info] thiliapr/adv_to_renpy 不提供任何保障，甚至连可销售和符合某个特定的目的都不保证
   [Info] 您应该已收到一份 AGPL 副本。如果没有，请访问 https://www.gnu.org/licenses/agpl.html
   
   + - + - + - + - + - Debug Mode - + - + - + - + - +
   存在不认识的 OPCode: 0x99
   ptr=171, char='\x99', hex=0x99, op=Invaild, str=StringError("cannot use encoding 'utf-8' to decode b'\\x99effect01'"), int=1717986713,    float=272004609255837716709376.00000
   q to quit:
   ```
3. 回车进入下一个字节，发现有一个字符串
   ```
   q to quit:
   ptr=172, char='e', hex=0x65, op=Unknown, str='effect01', int=1701209701, float=68002071048283412758528.00000
   q to quit:
   ptr=173, char='f', hex=0x66, op=ShowGraphic(file='fect01'), str='ffect01', int=1667589734, float=4231682977918980456448.00000
   q to quit:
   ptr=174, char='f', hex=0x66, op=ShowGraphic(file='ect01'), str='fect01', int=1952671078, float=72064696748654244711405998571520.00000
   q to quit:
   ptr=175, char='e', hex=0x65, op=Unknown, str='ect01', int=812933989, float=0.00000
   q to quit:
   ptr=176, char='c', hex=0x63, op=Invaild, str='ct01', int=825259107, float=0.00000
   q to quit:
   ptr=177, char='t', hex=0x74, op=Invaild, str='t01', int=3223668, float=0.00000
   q to quit:
   ptr=178, char='0', hex=0x30, op=Invaild, str='01', int=12592, float=0.00000
   q to quit:
   ptr=179, char='1', hex=0x31, op=Invaild, str='1', int=49, float=0.00000
   q to quit:
   ptr=180, char='\x00', hex=0x00, op=Unknown, str='', int=33554432, float=0.00000
   q to quit:
   ```
3. 继续回车，发现在 7 个字节后(ptr=188)时遇到了一个合理的 Operation
   ```
   ptr=181, char='\x00', hex=0x00, op=Unknown, str='', int=131072, float=0.00000
   q to quit:
   ptr=182, char='\x00', hex=0x00, op=Unknown, str='', int=512, float=0.00000
   q to quit:
   ptr=183, char='\x02', hex=0x02, op=Jump2(pointer=6553600), str='\x02', int=1677721602, float=9444735217539104112640.00000
   q to quit:
   ptr=184, char='\x00', hex=0x00, op=Unknown, str='', int=6553600, float=0.00000
   q to quit:
   ptr=185, char='\x00', hex=0x00, op=Unknown, str='', int=855663616, float=0.00000
   q to quit:
   ptr=186, char='d', hex=0x64, op=Unknown, str='d', int=1932722276, float=14181961982635277892161837727744.00000
   q to quit:
   ptr=187, char='\x00', hex=0x00, op=Unknown, str='', int=1953706752, float=77072908905868490534944575062016.00000
   q to quit:
   ptr=188, char='3', hex=0x33, op=SetBackground(channel='st01', file='EF_WHITE.PNG'), str='3st01', int=812938035, float=0.00000
   ```
4. 结合上面的经历，可以认为整个 0x99 Operation 的结构就是: 一个字符串 + 7 个字节的未知数据
5. 在`utils/ws2.py`追加以下内容
   ```python
   register_operation_parse_function(0x99, lambda env: Struct(
       CStringEncoding(env.encoding),
       Bytes(7)
   ))
   ```

## 私货
- plz，看看这些文章
  - [Tivoization（硬件自锁技术）](https://www.gnu.org/philosophy/tivoization.html)
    - 臭名昭著的 [Android](https://zh.wikipedia.org/wiki/Android) 的 BootLoader 锁就是一个典型案例: 它阻止刷入任何非官方的系统镜像
  - [Android 和用户的自由](https://www.gnu.org/philosophy/android-and-users-freedom.html)
  - [Linux、GNU和自由](https://www.gnu.org/philosophy/linux-gnu-freedom.html)
  - [为什么开源错失了自由软件的重点](https://www.gnu.org/philosophy/open-source-misses-the-point.html)
  - [让软件免受专利困扰](https://www.gnu.org/philosophy/limit-patent-effect.html)
  - [对版权的误解—一系列的错误](https://www.gnu.org/philosophy/misinterpreting-copyright.html)
  - [重新审视版权制度：公众利益应居首位](https://www.gnu.org/philosophy/reevaluating-copyright.html)
  - [还在用“知识产权”这词吗？它只是看上去很美](https://www.gnu.org/philosophy/not-ipr.html)
  - [别让 “知识产权” 扭曲你的价值观](https://www.gnu.org/philosophy/no-ip-ethos.html)