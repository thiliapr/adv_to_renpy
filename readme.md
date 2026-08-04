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
1. 准备一个 ADVPlayer 引擎的游戏，这里以[華は短し、踊れよ乙女](https://www.ensemble-game.com/28.hanaoto/)为例子，将游戏路径记为`game_path`，此时`game_path`应该呈现如此文件结构:  
  - game_name
    - AdvHD.exe
    - AdvHDLang.dll
    - Bgm.arc
    - Chip0.arc
    - Rio1.arc
    - Se.arc
    - Voice.arc
2. 用[Ren'Py SDK](https://www.renpy.org/latest.html)创建一个项目，记下它的路径，记为`project_path`，此时`project_path`应该呈现如此文件结构:  
   - project_name
     - game
       - audio
       - gui
       - images
       - script.rpy
     - .gitignore
     - log.txt
3. 将`Bgm.arc`提取到`${project_path}/game/audio/bgm/`，将储存 CG 图片的`ChipN.arc`提取到`${project_path}/game/images/`，将储存语音的`Voice.arc`提取到`${project_path}/game/audio/voice/`，将储存音效的`Se.arc`提取到`${project_path}/game/audio/se/`。我使用[GARbro](https://github.com/morkt/GARbro)提取游戏资源。
4. 创建文件夹`ws2_script`，将`RioN.arc`的脚本提取到该文件夹中。
5. 找到`ws2_script`文件夹中的入口脚本文件，比如`CO_1_1`，记为`entry_script`
6. 运行`python convert_script.py $game_dir $entry_script $project_path --encoding utf-8 -only-exist-background`

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