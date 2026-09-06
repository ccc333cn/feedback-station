---
name: feedback-station
description: 真机测试反馈闭环——在电脑上起一个局域网反馈站,测试者用手机逐条勾「通过 / 未通过 / 未测试」、附截图录屏、提新 Bug 与新需求,数据落本地磁盘,智能体直接读盘处理。每批交付测试版要发复验清单时、用户说"测完了 / 看反馈 / 起反馈站 / 接入反馈站"时调用。通用 Agent Skill,不绑定宿主:Claude Code、Codex、Cursor、Gemini CLI、OpenCode 等都能用。Real-device test feedback loop: start a LAN feedback site on the computer; testers mark each checklist item pass / fail / not tested on their phones, attach screenshots and recordings, file new bugs and feature requests; everything lands on local disk for the agent to read. Use when delivering a test build with a verification checklist, or when the user says "done testing", "check the feedback", "start / set up the feedback station".
license: MIT (see LICENSE)
compatibility: 需要 Python 3(仅标准库)以及能执行 shell 命令、读写文件的宿主;查看截图 / 录屏需宿主能读图,否则以文字备注为准。
---

# Feedback Station · 真机测试反馈闭环

## 是什么

一个零依赖的局域网反馈站:`server.py`(Python 3 标准库单文件服务)+ `index.html`(单页 vanilla JS),
两个文件都在本 skill 目录里。闭环三步:

1. **交付前**:智能体把这一批的真机复验清单写进 `checklist.json`(新批置顶)。
2. **测试中**:测试者手机连同一 Wi-Fi 打开站点,逐条勾「通过 / 未通过 / 未测试」,附文字、截图、录屏;
   清单以外的问题记「新 Bug」,想要的改进记「新需求」。全部自动保存到电脑磁盘。
3. **测完后**:智能体直接读盘(或跑 `summarize.py`)汇总案情,开下一批修复;修完把复验条目写进新批次。

本文约定:「智能体」= 正在读本文的你,不限于哪家产品;`<skill>` = 本 SKILL.md 所在目录;
`<root>` = 存放 `checklist.json` 与 `data/` 的目录。API 表、数据模型、记录生命周期语义见 `<skill>/docs/api.md`。

**语言**:页面界面按测试者浏览器语言自动显示(简中 / 繁中 / 英 / 日 / 韩 / 西 / 法 / 德 / 葡 / 俄),页脚可切换,
给用户的链接也可带 `?lang=en` 固定。清单条目文案、`--title`、与用户的对话一律用**用户的语言**;本文是中文,照做即可。

## 对宿主的要求(任何智能体都行)

本 skill 只依赖三件事,任何编程智能体(Claude Code、Codex、Cursor、Gemini CLI、OpenCode、Copilot……)
或能跑命令的通用智能体都满足:

- **能执行 shell 命令**:起 `python3 server.py`、跑 `summarize.py`、查内网 IP。机器上要有 Python 3,不需要任何第三方包。
- **能读写文件**:写 `checklist.json`,读 `data/*.json`。
- **可选:能看图**:截图用宿主的读图能力打开(Claude Code 的 Read、Codex / Cursor 的图片查看等);
  录屏先用 `ffmpeg -ss <秒> -i <文件> -frames:v 1 <输出>.png` 截帧再看。
  宿主看不了图就以测试者的文字备注为准,拿不准的让用户口述截图内容,别猜。

宿主沙箱不允许监听端口或起常驻后台进程时(表现为启动报权限错误、或进程一回合结束就没了),
把启动命令原样交给用户在自己终端跑,别在沙箱里反复重试;读盘、写清单不受影响。

## 首次接入一个项目(只做一次)

1. 定 `<root>`。建议放项目里、与 skill 目录分开(skill 目录只放代码),例如 `Tools/FeedbackStation/`;
   项目 `.gitignore` 加一行 `Tools/FeedbackStation/data/`(勾选、附件不入库;`checklist.json` 是交付物,入库)。
2. 起服务(首次会自建空 `checklist.json` 与 `data/`):

```bash
python3 <skill>/server.py --root Tools/FeedbackStation --title "<项目名> · 真机反馈"
```

3. 把终端打印的 `http://<内网 IP>:8787/` 给用户(`--title` 不传时标题按浏览器语言显示;传了就固定)。手机首连失败,提醒用户看电脑上的防火墙弹窗
   「允许 Python 接受传入连接」(智能体碰不了系统弹窗)。
4. 把启动命令(含 `--root` / `--title`)记进项目的智能体说明文件——宿主认哪个就写哪个
   (`AGENTS.md` / `CLAUDE.md` / `GEMINI.md` / `.cursor/rules` 等)或项目内 skill,下次直接用。

## 运维速查

- 起 / 重启(常驻用 nohup;重启电脑后要重起):

```bash
lsof -ti:8787 | xargs kill 2>/dev/null; nohup python3 <skill>/server.py --root <root> --title "<项目名> · 真机反馈" >> <root>/data/server.log 2>&1 &
```

- 内网 IP 用 `ipconfig getifaddr en0`(macOS)/ `hostname -I`(Linux)**现查**,会变,别写死进文档。
- **改 `index.html` 不用重启**(每请求现读盘);**改 `server.py` 必须重启**。页面端改动让用户下拉刷新即生效;
  填到一半的数据在服务端不受影响(保存失败自动每 3s 重试,扛得住重启窗口)。
- 数据在 `<root>/data/`:`results.json` 按 itemId 记 `{status, note, files, updatedAt}`;
  `bugs.json` 与 `requirements.json` 是两个同构数组 `{id, title, note, files, batchId, createdAt, updatedAt}`;
  附件在 `uploads/`。**永不清库**——历史批次与反馈就是档案,用户要回看。
- 端口换了就把命令里的 `8787` 一起换(`--port`)。

## 每批交付时(发出测试版之后)

1. 真机复验清单**不只发文字**:写进 `<root>/checklist.json` 的 `batches` **头部**(新批置顶):

```json
{ "id": "b12", "title": "第 12 批 · 构建 30 新修", "date": "2026-09-06", "sections": [
    { "title": "一、小节标题", "items": [
        { "id": "b12-1", "label": "12-1", "text": "条目原文" } ] } ] }
```

   逐条硬约束:
   - `id` 全站唯一且**永不复用 / 改写**(`results.json` 按它记账);`label` 是显示编号,
     **同一批内要一眼可辨**——多份来源各带一套编号时先做映射再落库,别让两个「C1」撞在一起。
   - ⚠️ **条目文案是纯文本,不解析 markdown**(前端用 `textContent`):写 `**加粗**` 或反引号会原样显示成星号 / 反引号。
     强调用「」引号、⚠️ / 🔶 / 📏 这类 emoji 前缀,分点用 ①②③。
   - `date` 必填(`"YYYY-MM-DD"`,写当天):批次芯片第二行小字与列表批次标题都靠它;缺了只是不显示,但新批别漏。
   - 旧批次**永不删除**(用户靠批次芯片回看历史);上一批未通过项的复验条目写进新批。
   - 一批有多份契约 / 多个来源时,**每份各占一节**,逐份核对,别只挂其中一份。
   - 改完无需重启,用户刷新即见。
2. **分流**:建批次前先把条目分两堆——**用户必测** = 手感 / 动效 / 真机专属(系统语言、推送、真机报的 Bug 复验)/ 需要用户裁定的;
   **智能体可测** = 模拟器 / 自动化可达的布局、文案、状态机、数据正确性。智能体可测的条目**不删**、照常进清单留档,
   文案前缀「🤖 智能体已在模拟器测过,你不用测 · 」;智能体的结果写进实施记录。用户只测必须由人测的。
3. 通知用户:构建号 + 「反馈站新批次已上线」。

## 用户测完后(用户会明说"测完了")

1. 先跑汇总(默认只汇总最新批次;`--all` 全部;`--batch <id>` 指定):

```bash
python3 <skill>/summarize.py --root <root>
```

   需要细看时直接读 `data/results.json` / `bugs.json` / `requirements.json`,附件按「对宿主的要求」一节看图 / 截帧;
   条目文案对照 `checklist.json` 反查 id → 原文;新 Bug / 新需求看 `batchId` 知道是哪一批测出来的。
2. 汇总成案情:**未通过 + 未测原因 + 新 Bug + 新需求 + 通过项的选填优化建议**都要看,按项目既有流程开下一批。
3. 处理过的反馈**留在原地不动**(历史档案);修复后的复验以新批次条目形式出现。

## 页面既有设计约定(改前端前先读,别回退)

- 三态 `pass / fail / blocked`,`blocked` 显示名「未测试」= 留待补测,**不计入「已测」**。
- 「通过」的备注面板**默认折叠**,「＋ 补充优化建议(选填)」按需展开;已有内容的通过项直接展开;
  「未通过 / 未测试」恒展开。收起不清空,误点切回不丢。
- 筛选行「只看:全部 / 未通过 / 未测 / 通过 / 未勾选」是复查用的;**改态不当场隐藏卡片**(避免手一点卡片就消失),切筛选时才生效。
- 输入框字号 **16px 是 iOS Safari 不触发聚焦自动放大的下限**,别调小。
- 附件点开走页内灯箱(✕ / 点空白 / 点图关闭),别改回 `window.open`(iOS 主屏 Web App 模式回不来)。
- 跨设备同时编辑同一条 = 最后写入者赢(已知边界,单人单机无碍)。
- **新需求区**在新 Bug 区**下方**,与它完全同构,落 `requirements.json` / 端点 `/api/requirement`。别把两个区合并,也别调换上下顺序。
- **新 Bug 与新需求按批次归属**:新建时取**当前选中的最新批次**(清单新批置顶 ⇒ 第一个选中的);
  列表只在自己那一批的视图下显示;没选批次时「＋ 添加」置灰;多选批次才露出卡片左上角的批次角标。别改回全局显示。
- 批次筛选:「☰ 批次」钮打开**纵向面板**(全部批次多选 + 只看最新 / 全选 / 清空);芯片行保留且**横向滚动**
  (`nowrap`,别改回 `flex-wrap: wrap`——批次变多会把芯片挤压变形),桌面端滚轮竖转横 + 鼠标拖动。
  页面本身不许横向滚。批次选择的唯一写点 = `toggleBatch()` / `setSelection()`,改选中逻辑只改那里。
- **批次多了也不铺开**:面板限高内滚,打开只列最近几批,滚到底再追加更早的;每次打开页面默认只选最新批次(不持久化,刷新即回到最新)。
  别改回全部铺开 / 默认全选。

## 已知坑

- **(仅 Claude Code)** 用它的 Browser pane 验本站:`computer` 的点击 / 拖拽可能 30s 超时(截图、`read_page`、`javascript_tool` 正常)。
  绕法 = `javascript_tool` 直接 `element.click()` / `dispatchEvent(new Event('input'))` 驱动(同一套事件处理器,功能验证等价),
  再用 `screenshot` 验视觉;`window.confirm` 用 `window.confirm=function(){return true;}` 打桩。
- **其他宿主验本站**:没有浏览器工具就用 curl 打 API(`<skill>/docs/api.md` 末尾有手工验收清单),视觉走查让用户在手机 / 桌面浏览器上做。
- 手机相册上传时 iOS 会把 HEIC 转 JPEG;录屏是 `.mov`(服务端已支持 Range,Safari 可直接播放);单文件上限 512MB。
- 端口被占:`lsof -ti:8787 | xargs kill`。服务只绑内网 HTTP,没有鉴权——只在可信 Wi-Fi 下开,别暴露到公网。
