# Feedback Station · 真机测试反馈站

**中文** | [English](README.en.md)

一个**零依赖**的局域网反馈站,专为「编程智能体写代码 → 人在真机上验收 → 智能体读反馈继续修」这条循环设计。

- 电脑上一条命令起服务(Python 3 标准库,单文件),手机连同一 Wi-Fi 用浏览器打开。
- 测试者逐条勾「通过 / 未通过 / 未测试」,附文字、截图、录屏;清单以外的问题记「新 Bug」,想要的改进记「新需求」。
- 一切自动保存到电脑磁盘的 JSON 与文件夹里,**智能体直接读盘处理反馈**,测试者不用再截图倒腾、整理成文发回对话。
- 附带一份通用 **Agent Skill**(`SKILL.md`,遵循 [agentskills.io](https://agentskills.io) 开放格式,Claude Code、Codex、Cursor、Gemini CLI、OpenCode、Copilot,以及 Kimi Code、Qwen Code、通义灵码、Qoder、Trae、CodeBuddy / WorkBuddy、Deep Code 等都能直接加载):每批交付时怎么写复验清单、测完后怎么读盘归案、页面既有设计约定与踩坑。

它来自一个 iOS App 的开发流程:几十个 TestFlight 批次、几百条复验条目全靠它跑完。
界面语言跟随测试者浏览器(简中 / 繁中 / 英 / 日 / 韩 / 西 / 法 / 德 / 葡 / 俄),移动优先(约 393pt 宽设计,桌面居中限宽)。

## 为什么需要它

开发手机端应用时,模拟器测不了真实数据:真实账号、真实网络、推送、定位、相机相册、系统权限、手感与动效,
都只能拿真机验。于是每一批构建都得让人真机测一遍,而真机反馈这一步偏偏最费劲:

- 「你测一下新版」这种口头交代,测试者不知道这批到底改了哪、重点在哪;回来的「有点卡」「好像不对」,智能体也对不上是哪个改动。
- 测试者对着一长串清单在手机上测,测到哪了、哪条没过,只能靠记忆或另开备忘录。
- 截图、录屏要先从手机传到电脑(AirDrop / 微信 / 邮件),再拖进对话,再打字说明是哪一条的。几十条反馈就是几十次倒腾。
- 反馈散落在聊天记录里,智能体读不到原始附件,人还得二次整理成文;下一批修完再复验,又从头来一遍。

反馈站把这一步收成一条路:清单由智能体写进文件,测试者在手机浏览器里逐条勾选、就地拍照 / 录屏上传,
数据直接落在电脑磁盘,智能体读盘即可归案。截图不用传、反馈不用整理、历史不会丢。

而且两个方向都是精准的:智能体最清楚这批改了什么,清单就按改动逐条写,每条有唯一编号和原文,
测试者一眼知道该测什么、怎么算过;反馈按条目落回同一个编号,智能体拿到的是「哪一条、什么状态、什么附件」,
而不是一段要靠猜的描述。该测的不漏、不该测的不白测,复验也能精确对到上一批的哪一条。

## 快速开始(独立使用)

```bash
git clone https://github.com/ccc333cn/feedback-station.git feedback-station
cd feedback-station
cp checklist.example.json checklist.json     # 改成你的清单
python3 server.py --title "我的 App · 真机反馈"
```

终端会打印 `http://<内网 IP>:8787/`,手机连同一 Wi-Fi 打开即可。首次连不上,看电脑上有没有弹「允许 Python 接受传入连接」的防火墙提示。

参数:

| 参数 | 默认 | 说明 |
|---|---|---|
| `--root DIR` | 脚本所在目录 | 存放 `checklist.json` 与 `data/` 的目录 |
| `--port N` | `8787` | 监听端口 |
| `--host` | `0.0.0.0` | 只想本机用填 `127.0.0.1` |
| `--title` | 按浏览器语言 | 页面标题;不传则按测试者浏览器语言显示「真机反馈 / Device Test Feedback …」,传了就固定 |

运行数据全在 `<root>/data/`(`.gitignore` 已排除):

| 文件 | 内容 |
|---|---|
| `results.json` | 每条清单项的 `{status, note, files, updatedAt}`,按 itemId 记 |
| `bugs.json` | 新 Bug 数组 `{id, title, note, files, batchId, createdAt, updatedAt}` |
| `requirements.json` | 新需求数组,与 `bugs.json` 同构 |
| `uploads/` | 截图与录屏原文件 |

汇总反馈(默认只看最新批次,`--all` 全部,`--batch <id>` 指定):

```bash
python3 summarize.py --root . 
```

## 作为 Agent Skill 使用(Claude Code / Codex / Cursor / Gemini CLI / OpenCode / Copilot …)

`SKILL.md` 遵循 [Agent Skills](https://agentskills.io) 开放格式,不绑定任何一家智能体。
把整个仓库 clone 成一个 skill 目录(目录名必须叫 `feedback-station`),放到你所用宿主认的位置即可:

**国际常见宿主**

| 宿主 | 项目级(随仓库走) | 全局(本机所有项目) |
|---|---|---|
| 通用路径(Codex、Cursor、Gemini CLI、OpenCode、Copilot、Cline、Zed、Warp、Amp、Kimi、Deep Code 都认) | `.agents/skills/` | `~/.agents/skills/` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| Codex | `.agents/skills/` | `~/.agents/skills/`(早期版本为 `~/.codex/skills/`) |
| Cursor | `.cursor/skills/` | `~/.cursor/skills/` |
| Gemini CLI | `.gemini/skills/` | `~/.gemini/skills/` |
| OpenCode | `.opencode/skills/`(也认 `.claude/skills/`) | `~/.config/opencode/skills/`(也认 `~/.claude/skills/`) |
| GitHub Copilot / VS Code | `.github/skills/`(也认 `.claude/skills/`) | `~/.copilot/skills/` |
| Windsurf | `.windsurf/skills/` | `~/.codeium/windsurf/skills/` |
| Roo Code / Kilo Code | `.roo/skills/` / `.kilocode/skills/` | `~/.roo/skills/` / `~/.kilocode/skills/` |

**国内常见宿主**

| 宿主 | 项目级(随仓库走) | 全局(本机所有项目) |
|---|---|---|
| Kimi Code CLI(月之暗面) | `.kimi/skills/`(也认 `.agents/skills/`) | `~/.kimi/skills/` |
| Qwen Code(阿里) | `.qwen/skills/` | `~/.qwen/skills/` |
| 通义灵码 Lingma | `.lingma/skills/` | `~/.lingma/skills/` |
| Qoder | `.qoder/skills/` | `~/.qoder/skills/`(国内版 `~/.qoder-cn/skills/`) |
| Trae(字节) | `.trae/skills/` | `~/.trae/skills/`(国内版 `~/.trae-cn/skills/`) |
| CodeBuddy(腾讯) | `.codebuddy/skills/` | `~/.codebuddy/skills/` |
| WorkBuddy(腾讯) | — | `~/.workbuddy/skills/`(也可把 SKILL.md 直接拖进对话导入,或从 SkillHub 安装) |
| Deep Code(DeepSeek 终端智能体) | `.deepcode/skills/`(也认 `.agents/skills/`) | `~/.deepcode/skills/`(也认 `~/.agents/skills/`) |
| MiniMax Code | `.minimax/skills/` | `~/.minimax/skills/` |
| iFlow CLI(心流) | `.iflow/skills/` | `~/.iflow/skills/` |

没列到的宿主,查 [agentskills.io/clients](https://agentskills.io/clients) 和 [vercel-labs/skills](https://github.com/vercel-labs/skills) 的目录表(后者也提供 `npx skills add <repo>` 一键装进任一宿主)。
用 DeepSeek、Kimi、Qwen 这些模型但跑在 Claude Code / Cline / OpenClaw 等别家宿主上的,按宿主的路径装即可,skill 与模型无关。

例如:

```bash
git clone https://github.com/ccc333cn/feedback-station.git .agents/skills/feedback-station     # Codex / Cursor / Gemini CLI / OpenCode / Copilot / Kimi / Deep Code 通用
git clone https://github.com/ccc333cn/feedback-station.git .claude/skills/feedback-station     # Claude Code
git clone https://github.com/ccc333cn/feedback-station.git .qwen/skills/feedback-station       # Qwen Code(其他国内宿主同理换目录)
```

然后对智能体说「接入反馈站」。skill 会引导它:在项目里选一个 `<root>` 目录(建议 `Tools/FeedbackStation/`),
用 `--root` 起服务,把 URL 给你;每批交付时把复验清单写进 `checklist.json` 头部;你说「测完了」它就读盘归案。

不支持 skill 机制的智能体(或普通聊天界面)也能用:把 `SKILL.md` 全文贴进系统提示或对话当操作手册即可。
它只要求宿主能跑 shell 命令、读写文件,没有任何宿主专属的工具名(仅「已知坑」里有一条标注为 Claude Code 专属)。

skill 目录只放代码,清单与数据都在你项目的 `<root>` 里,更新 skill 不会碰到数据。

## 清单格式

`checklist.json`:

```json
{ "batches": [
  { "id": "b2", "title": "第 2 批 · 构建 12 新修", "date": "2026-09-06", "sections": [
      { "title": "一、小节标题", "items": [
          { "id": "b2-1", "label": "2-1", "text": "条目原文" } ] } ] } ] }
```

- 新批次插在 `batches` **头部**(新批置顶);旧批次永不删,测试者靠批次芯片回看历史。
- `id` 全站唯一且永不复用(结果按它记账);`label` 只是显示编号。
- `text` 是纯文本,不解析 markdown。强调用「」、emoji 前缀,分点用 ①②③。
- `date` 可选但建议必填,格式 `YYYY-MM-DD`。
- 改完不用重启,页面刷新即见。

完整示例见 [checklist.example.json](checklist.example.json)。

## 页面功能

- 顶部:标题 + 保存状态点(保存中 / 已存 / 失败点击重试);「☰ 批次」纵向多选面板(只列最近几批,下滑看更早)+ 横向滚动的批次芯片;打开页面默认只选最新批次;
  「只看:全部 / 未通过 / 未测 / 通过 / 未勾选」筛选;进度行「已测 x / y · 未通过 n · 未测 m · 新 Bug · 新需求」。
- 条目卡:编号 + 原文;三钮「通过 / 未通过 / 未测试」,再点同钮取消。「未通过 / 未测试」展开备注与附件;
  「通过」默认折叠,「＋ 补充优化建议(选填)」按需展开。
- 附件:拍照 / 相册 / 录屏多选上传,缩略图,页内灯箱查看(视频支持 Range,Safari 直接播);✕ 删除。
- 新 Bug 区与新需求区:一句话标题 + 详细描述 + 附件,按批次归属,只在自己那批的视图下显示。
- 自动保存:文字 500ms 防抖,勾选与上传即时;失败每 3s 自动重试;刷新、换设备都从服务端还原。
- 界面语言按浏览器自动识别(10 种),页脚下拉可切换,链接带 `?lang=en` 可指定;清单内容本身不翻译。

设计取舍与 API 表见 [docs/api.md](docs/api.md)。

## 目录

```
feedback-station/
├── SKILL.md                 # 通用 Agent Skill(agentskills.io 格式)
├── server.py                # 局域网服务(Python 3 标准库)
├── index.html               # 单页前端(vanilla JS)
├── summarize.py             # 三份数据 → 一份 Markdown 案情
├── checklist.example.json   # 清单示例
├── docs/api.md              # API 契约、数据模型、记录生命周期、前端设计约定
└── data/                    # 运行时生成,不入库
```

## 边界与安全

- 只绑内网 HTTP,**没有鉴权**:只在可信 Wi-Fi 下开,不要暴露到公网。
- 同一条目在两台设备**同时**编辑是「最后写入者赢」。
- 单文件上传上限 512MB;上传目录做了路径穿越防护。
- JSON 写盘走「临时文件 + `os.replace`」原子写并持锁;坏档不覆盖,改名留证后回退空数据。
