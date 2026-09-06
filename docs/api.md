# Feedback Station · API 契约与数据模型

服务端 `server.py`(Python 3 标准库)+ 单页 `index.html`(vanilla JS),无框架、无路由、无构建步骤。
本文是改动前后端之前要读的契约:API 表、数据文件形状、记录生命周期语义、前端既有设计约定。

## 目录约定

| 名称 | 含义 |
|---|---|
| `<skill>` | `server.py` / `index.html` 所在目录 |
| `<root>` | `--root` 指定的目录(默认 = `<skill>`),存 `checklist.json` 与 `data/` |
| `<root>/data/` | `results.json`、`bugs.json`、`requirements.json`、`uploads/`;整目录不入库 |

`index.html` 每请求现读盘并填两个占位符:`{{TITLE}}`(`--title`,HTML 转义;为空时页面按浏览器语言填默认标题)与 `{{DATA_DIR}}`(页脚提示)。
改 `index.html` 不用重启;改 `server.py` 必须重启。

## API(全部 JSON,除上传)

| 方法与路径 | 语义 |
|---|---|
| `GET /` | `index.html`(填占位符后返回,`Cache-Control: no-store`) |
| `GET /api/state` | `{checklist, results, bugs, requirements}` 一次拉全 |
| `POST /api/result` | `{itemId, status, note?}`;`status ∈ "pass" \| "fail" \| "blocked" \| null`(null = 清除);upsert 进 `results.json`,服务端补 `updatedAt`;返回 `{itemId, record}` |
| `POST /api/bug` | `{id?, title?, note?, batchId?}`;无 `id` 新建(服务端发 id、`createdAt`、`batchId`),有 `id` 更新;返回 `{entry, bug}`(`bug` 是旧字段别名) |
| `POST /api/bug/delete` | `{id}` 删除该条,连带删它的上传文件;返回 `{deleted}` |
| `POST /api/requirement` | 同 `/api/bug`,落 `requirements.json`;返回 `{entry}` |
| `POST /api/requirement/delete` | 同 `/api/bug/delete` |
| `POST /api/upload?kind=item&id=<itemId>`(或 `kind=bug` / `kind=req`) | `multipart/form-data` 单文件(取第一个带 filename 的部件);存 `data/uploads/<kind>-<id>-<时间戳>.<ext>`;把 `uploads/<name>` 追进对应记录的 `files`;返回 `{path, files}` |
| `POST /api/upload/delete` | `{kind, id, path}` 从记录摘除并删文件 |
| `GET /uploads/<name>` | 回放上传的图 / 视频;支持 `Range`(Safari 播视频必需);仅限 `data/uploads/` 内,路径穿越一律 404 |

错误一律 `{"error": "..."}`;请求体没读干净的错误会断开连接(避免 keep-alive 串包)。
限制:JSON 体 2MB、上传 512MB、文本字段 20000 字、id 128 字。

## 数据文件

`checklist.json`(交付物,入库):

```json
{ "batches": [
  { "id": "b2", "title": "第 2 批 · 构建 12 新修", "date": "2026-09-06", "sections": [
      { "title": "一、小节标题", "items": [
          { "id": "b2-1", "label": "2-1", "text": "条目原文" } ] } ] } ] }
```

- `batches[0]` 是最新批次(新批插头部)。`date` 可选,`YYYY-MM-DD`。
- `items[].id` 全站唯一且永不复用;`label` 只是显示编号;`text` 纯文本。

`results.json`(按 itemId 记):

```json
{ "b2-1": { "status": "fail", "note": "……", "files": ["uploads/item-b2-1-20260906-101500-123.png"], "updatedAt": "2026-09-06T10:15:00+08:00" } }
```

`bugs.json` / `requirements.json`(同构数组):

```json
[ { "id": "bug-20260906-101500-123-a1b2", "title": "一句话标题", "note": "详细描述", "files": [],
    "batchId": "b2", "createdAt": "2026-09-06T10:15:00+08:00", "updatedAt": "2026-09-06T10:16:30+08:00" } ]
```

## 记录生命周期语义

- **三态**:`pass` / `fail` / `blocked`(显示「未测试」= 留待补测);`blocked` 不计入进度行的「已测」。
- **清除**:`status: null` 且 `note` 空且 `files` 空 ⇒ 整条记录从 `results.json` 删除;三样有一样非空就保留(状态为 null 的残条也保留,备注不丢)。
- **note 保留**:`POST /api/result` 不带 `note` 字段时不改备注;带了就整体覆盖(前端总是带)。
- **归属**:新 Bug / 新需求新建时取前端传的 `batchId`,没传就用清单最新批次;更新时**不带** `batchId` 不改归属(防旧页面把归属冲掉)。
  读盘时缺 `batchId` 的旧记录一律补成清单最新批次(清单为空时补 `legacy`)。
- **附件**:删记录连带删文件;删文件同时从记录摘除;`GET /uploads/` 之外没有任何列目录接口。
- **并发**:所有读写持一把进程内 RLock,JSON 用「临时文件 + `os.replace`」原子写;两台设备同时改同一条 = 最后写入者赢。
- **坏档**:JSON 解析失败不覆盖,改名 `*.corrupt-<时间戳>` 留证,回退空数据。

## 前端设计约定(改之前先读,别回退)

这些都是真实测试者用出来的取舍,每条背后都有一次返工:

1. **「通过」默认折叠备注**,「＋ 补充优化建议(选填)」按需展开;已有内容的通过项直接展开;「未通过 / 未测试」恒展开。收起不清空。
2. **筛选不当场隐藏卡片**:改态后卡片留在原地(避免手一点卡片就消失),切筛选时才生效。`card.dataset.status` 是筛选依据。
3. **输入框 16px**:iOS Safari 不触发聚焦自动放大的下限,别调小。
4. **附件页内灯箱**(✕ / 点空白 / 点图关闭),不用 `window.open`——iOS 主屏 Web App 模式打开新页回不来。视频节点移除即停播释放。
5. **新需求区独立**:在新 Bug 区下方、同构、独立文件与端点(`ENTRY_KINDS` 分发)。别合并、别调换顺序。
6. **按批次归属**:新记录归当前选中的最新批次;列表只在自己批次视图下显示;没选批次「＋ 添加」置灰;多选批次才露角标(`body.multi-batch`)。
7. **批次选择两个入口一个写点**:「☰ 批次」纵向面板(只看最新 / 全选 / 清空 + 逐条多选)与横向滚动芯片行共用 `toggleBatch()` / `setSelection()`;
   芯片行 `nowrap` + 横向滚动(别改 `wrap`,批次变多会挤压变形),桌面端滚轮竖转横 + 鼠标拖动(拖动中 `.dragging` 吞点击);页面本身不许横向滚。
   面板限高 320px 内部滚动,打开时只列最近 `BP_PAGE`(6)条,滚到底或点底部提示再追加更早的;改选中只原地同步勾号(`paintBatchPanel()`),不重建、不丢滚动位置。
8. **批次选择不持久化**:每次打开页面默认只选最新批次(`batches[0]`);多选是临时复查动作,刷新即回到最新——这样新批次上线后刷新一定看得到,页面也不会一打开就铺开几十批。
9. **自动保存**:文字 500ms 防抖,勾选 / 上传 / 删除即时;失败入队每 3s 重试,状态点可点手动重试。
10. **界面多语言**:文案全部走 `t(key)`,字典 `I18N` 内置 10 种语言(zh-CN / zh-TW / en / ja / ko / es / fr / de / pt / ru);
    语言取 `?lang=` → localStorage `feedback-station.lang` → `navigator.languages` → `en`,页脚下拉切换后 reload。
    新增文案十种都要补(`t()` 缺键回退英文);清单内容(批次标题、条目)是谁写的就什么语言,不翻译。
11. 视觉:暖黑底 `#12100E`、卡 `#1C1815` 圆角 16、琥珀 `#E8B463` 强调、米白 `#F2EDE3` 正文、次要字 `#8A7F70`、通过绿 `#7FA86A`、未通过红 `#C24A33`;系统字体栈;移动优先,桌面居中限宽 560px。

## 手工验收清单(改完服务端跑一遍)

1. 冷启动零报错,打印含内网 IP 的 URL;`--root` 指向空目录时自建三份数据文件与空清单。
2. curl 全 API:state 拉取;result 四态(pass / fail / blocked / null)upsert 与清除;bug / requirement 建 / 改 / 删;
   multipart 真文件上传 → `uploads/` 落盘、记录 `files` 追加、`GET /uploads/…` 原样回放且 `Range` 返回 206;
   upload/delete 摘除且文件消失;`/uploads/../server.py` 必须 404。
3. 杀掉服务重启 → state 数据原样。
4. 浏览器(手机宽 + 桌面)走查:批次面板与芯片切换、三态高亮、未通过展开、文字防抖保存、刷新还原、新 Bug / 新需求增删、进度行数字。
