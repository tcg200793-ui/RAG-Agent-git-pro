# DESIGN.md — RAG 知识库问答智能体 实验汇报

## 5.1 全局视觉约定

### ① 画布与安全区
- 画布 1280×720，padding 上下 60 / 左右 60，内容区 1160×600
- 内容页统一母版：顶部深蓝标题条（高 68px，贯满 1280 宽，内 padding 左右 60）+ 页脚（y≈670）

### ② 配色方案（学术宝蓝 + 白底，来自 academic.md §1.2）
| 槽位 | Hex | 用途 |
| --- | --- | --- |
| 主色 | `#1E4FA8` | 顶条、编号块、关键数字、强调 |
| 辅色 | `#3D7BD9` | 第二层强调、流程节点描边 |
| 浅辅 | `#E8EFF8` | 信息横幅底、结论条底、表头底 |
| 强调 | `#D9534F` | 仅用于「问题/风险/失败案例」，全篇 ≤3% |
| 正文 | `#1A2230` / `#4A5568` / `#8B97A8` | 主/副/辅助 |
| 底色 | `#FFFFFF` | 主背景（学术默认白，≥60%） |
| 辅底 | `#F7F9FC` | 局部卡底 |
| 线 | `#D6DCE5` / `#E5E7EB` | 卡片描边、表格分隔 |

纪律：蓝族 20-40%，白底 ≥60%，红 ≤3%，金色 0。

### ③ 字体系统
- 中文：`Microsoft YaHei`（黑体族，跨平台稳）；英文/数字同族，表格数字用 Arial 观感靠右对齐
- 字号阶梯（px）：封面主标 60 / 页面主标 34（顶条白字）/ 卡片小标 24 / 正文 19-20 / KPI 巨数字 76-88 / 表格 17 / 页脚 14

### ④ 视觉母题
- **顶条**：全篇内容页统一顶部 68px 深蓝条，左「页面标题」，右「NN · CHAPTER」
- **贯通细线**：标题条下方不留装饰短线；页内分区用 1px `#D6DCE5` 横线贯通内容区宽度
- **结论条**：多数内容页底部一条 `#E8EFF8` 浅蓝底横条，一句话 takeaway

### ⑤ 配图清单
无外部生成图片。全部用 DSL 原生组件（Box 流程链 / Table / FAIcon 编号 / 手绘 Box 结构）——本项目是工程项目报告，架构图与实测数据表比摄影插图更贴合学术场景，且避免风格混用。

---

## 5.2 逐页字段

### P1 封面
- type: cover / role: hero / rhythm: peak / visual_role: atmosphere
- layout: 左侧 8 列文字 + 右侧宝蓝色块几何（无数据）
- density: 字数约 60 / 图片 0 / 留白约 45%
- description: 主标「基于 RAG 的 Git 知识库问答智能体」；副标「从 501 页 PDF 到可追溯引用的问答链路」；信息层：计算机科学与技术 · 唐成纲 2026011352 · 2026 年 11 月
- anti_pattern: 禁止封面出现任何数据指标（805 块/1024 维等一律不上封面）；禁止在封面加页脚条

### P2 目录
- type: catalog / role: supporting / rhythm: valley / visual_role: evidence
- layout: 四行编号 + 章节名 + 页码，左侧大号 CONTENTS
- density: 字数约 80 / 图片 0 / 留白约 40%
- description: 01 语料与预处理（P3–P7）｜02 向量化与检索（P8–P12）｜03 问答智能体（P13–P15）｜04 结果与反思（P16–P18）
- anti_pattern: 禁止统计装饰块（「共 4 章 19 页」）、禁止「阅读顺序」复述条、禁止主线预告行

### P3 章节页 01
- type: section / role: transition / rhythm: transition
- layout: 左侧 160px 大号「01」+ 右侧章节名与一句关键词
- description: 01 语料与预处理 —— Pro Git 中文版；结构探查；结构化切块；噪声质检
- anti_pattern: 禁止四卡片预览、禁止大段导语、禁止出现页脚

### P4 语料选型：为什么是《Pro Git》
- type: content / role: supporting / rhythm: valley / visual_role: evidence
- layout: 左侧 55% 三条判断依据（竖排，细线分隔）+ 右侧 45% 语料体检清单表
- density: 字数约 260 / 图片 0 / 留白约 20%
- description: 依据一「有唯一标准答案」：Git 命令有权威文档，答案可核验 → 便于评估幻觉；依据二「中文官方译本」：v2.1.80 PDF 501 页，术语与英文命令混排，接近真实技术问答；依据三「结构规整」：20 个字体全内嵌 + ToUnicode + 书签树，可做层级切分。右侧体检表：501 页 / 19MB / 字体嵌入 20 / 书签 L1=14 L2=101 / 代码真文本 / sha256 校验
- anti_pattern: 禁止把「为什么选这本书」写成形容词堆砌（「经典权威」），必须给可验证事实

### P5 结构探查：四个预判被实测推翻
- type: content / role: supporting / rhythm: valley / visual_role: evidence
- layout: 一页表格（预判 / 实测 / 对策 三列五行）+ 底部结论条
- density: 字数约 300 / 图片 0 / 留白约 15%
- description: ① 以为要正则合并硬换行 → 段落本身即 block，无需合并；② 以为书签有三级 → 只有 L1/L2，但正文有 267 个 13pt 小节标题，改用字号重建层级；③ 统计高频页眉行 → 页边 608 种文本各只出现 1–3 次，全是页码，改用「9pt+纯数字」；④ 按 span 字体判断代码 → RobotoMono 占 22 万字（正文英文也用它），改按整行全 Mono。结论：切块策略必须由实测数据推导，不能照搬通用做法
- anti_pattern: 禁止四项做成等宽四卡片（信息天然是「预判→实测」两栏对照）

### P6 结构化切块：805 块怎么来的
- type: content / role: hero / rhythm: peak / visual_role: anchor
- layout: 上方 KPI 三联数（805 块 / 718 字中位 / 550 块含代码）+ 下方四步策略链
- density: 字数约 240 / 图片 0 / 留白约 25%
- description: KPI 说明「805 块、p50=718 字、总 50.5 万字、覆盖 14 章」；四步：字号重建层级 → 按小节分组 → 组内打包 800 字 + 120 字重叠 → 块首拼「书名 > 章 > 节 > 小节」路径锚点
- anti_pattern: 禁止 KPI 数字下方不写判断；禁止把四步做成等大等高四卡片

### P7 切块质检：三个真实坑
- type: content / role: supporting / rhythm: valley / visual_role: evidence
- layout: 三行「坑 / 现象 / 修法」，行间 1px 细线；右侧窄栏放质检结果（噪声复检 0）
- density: 字数约 280 / 图片 0 / 留白约 20%
- description: 坑一 GitHub Markdown 一节原文含 ``` → 围栏长度取最长连续反引号 +1；坑二 连续多代码块时「代码不触发切分」失效，单块堆到 2556 字 → 允许代码块触发 flush；坑三 Figure 图注无对应图片纯噪声 → 正则剔除。质检结果：页码 0、目录点线 0、图注 0
- anti_pattern: 禁止把三个坑写成平级 checklist 而无「修法」

### P8 章节页 02
- type: section / role: transition / rhythm: transition
- layout: 同 P3
- description: 02 向量化与检索 —— 805×1024；内积即余弦；BM25 基线；实测对比

### P9 向量索引：805×1024 的一次性投入
- type: content / role: supporting / rhythm: valley / visual_role: evidence
- layout: 左侧流程链（4 节点纵向）+ 右侧三条工程决策
- density: 字数约 250 / 图片 0 / 留白约 20%
- description: 流程：文本块 → 批量 10 条/次调 text-embedding-v4 → 1024 维向量 → L2 归一化 → embeddings.npy（3.1MB）。决策：①批上限 10 条（非 OpenAI 惯例 32，实测 400 报错）；②4xx 不重试 5xx 退避重试；③归一化后内积等价余弦，检索端少算一次除法
- anti_pattern: 禁止只写「调用 API 生成向量」而不写踩坑与决策

### P10 语义检索：为什么不用向量数据库
- type: content / role: supporting / rhythm: valley / visual_role: evidence
- layout: 左右 5:5，左「选型判断」三问三答，右「实测开销」小表
- density: 字数约 240 / 图片 0 / 留白约 22%
- description: 规模 805 块 → 暴力内积 0.01 ms/次，精确最近邻无召回损失；faiss/hnswlib 的收益要百万级才显现；引入近似索引反而带来「调参 + 召回转人工核查」的成本。右表：矩阵 805×1024 float32 = 3.1MB 常驻内存；单次检索 0.01ms；BM25 0.54ms
- anti_pattern: 禁止把「不用向量库」写成技术保守，要写清规模判据

### P11 BM25 基线：零依赖的另一条腿
- type: content / role: supporting / rhythm: valley / visual_role: evidence
- layout: 左侧实现要点（三条）+ 右侧与向量检索的互补关系（两栏对照）
- density: 字数约 250 / 图片 0 / 留白约 20%
- description: 要点：不装 jieba，中文按二字组切片、英文按符号切整词；标准库实现（Counter + math）；命令名（git rebase / cherry-pick）天然精确匹配。互补：BM25 强在术语精确、弱在同义改写；向量强在语义、弱在罕见命令名
- anti_pattern: 禁止两个方法都写成「各有优缺点」的中性对称表述，必须给出适用边界

### P12 实测对比：三个查询谁命中
- type: content / role: hero / rhythm: peak / visual_role: anchor
- layout: 表格（查询 / BM25 top1 / 向量 top1 相似度 / 判定）+ 底部结论条
- density: 字数约 300 / 图片 0 / 留白约 15%
- description: Q1「如何撤销已推送的提交」→ BM25 命中「git push」附录（错），向量命中「撤消操作」（对但只覆盖本地）；两者都未命中「已推送」的关键差异 → 暴露语料覆盖 + 检索粒度问题。Q2「rebase 与 merge 区别」→ 向量 top1 变基 0.767、top2 变基 vs. 合并 0.764，双命中；BM25 top1 命中变基章但对比较弱。Q3「git stash 有什么用」→ 向量 0.832 命中附录 C 命令条，BM25 命中贮藏工作节，两者都好
- anti_pattern: 禁止只报喜不报忧，必须保留 Q1 这个失败案例

### P13 章节页 03
- type: section / role: transition / rhythm: transition
- layout: 同 P3
- description: 03 问答智能体 —— 提示词约束；工具调用主循环；防幻觉兜底

### P14 提示词工程：把「不许编」写成可执行规则
- type: content / role: supporting / rhythm: valley / visual_role: evidence
- layout: 四条规则纵向排列 + 右侧一条「反例 → 正例」对照
- density: 字数约 300 / 图片 0 / 留白约 18%
- description: 规则一 知识来源只有检索原文，检索不到就说「知识库里没有」；规则二 引用格式「（Git 分支 > 变基，p99）」，一次回答不超 4 处；规则三 命令必须给完整可执行写法并说明副作用（可逆性、是否改写已推送历史）；规则四 相似度分档判断（>0.75 对题 / 0.5–0.75 需读原文确认 / <0.5 换词重试或说没找到）
- anti_pattern: 禁止罗列提示词原文，要写成「问题 → 规则」的因果

### P15 主循环：检索次数交给模型决定
- type: content / role: hero / rhythm: peak / visual_role: anchor
- layout: 横向流程链（5 节点）+ 下方两个「与一次性 RAG 的差别」说明 + 结论条
- density: 字数约 260 / 图片 0 / 留白约 20%
- description: 用户问题 → 模型判断是否检索 → 调 search_git_docs(query, top_k) → 结果以「[章节路径|页码|相似度] 原文」回填 → 模型作答或换词再检（上限 4 轮）。差别：一次性 RAG 检索词写死在代码里；这里模型可改写查询、可调 top_k、答非所问时能自救
- anti_pattern: 禁止流程图节点里塞长句；禁止把「4 轮上限」放在图里不解释

### P16 防幻觉：软约束之外的硬兜底
- type: content / role: supporting / rhythm: valley / visual_role: evidence
- layout: 2×2 四格矩阵（四道防线），每格编号 + 一行机制 + 一行防的是什么
- density: 字数约 280 / 图片 0 / 留白约 18%
- description: ①提示词「参数边界」：书中没有的新参数（如 --force-with-lease）不得补充；②代码审计 _audit：答案里每个长选项正则抽出，逐个比对本轮检索原文，缺失就黄字告警；③轮次与 top_k 硬上限：MAX_TOOL_ROUNDS=4、MAX_TOP_K=8，防检索不收敛与上下文撑爆；④历史裁剪对齐 user 边界，防 tool 消息成孤儿被接口拒绝。核心判断：提示词是软的，能被绕过；代码是硬的，挡得住
- anti_pattern: 禁止四格做成等宽等高三卡片；禁止只列机制不写「防的是什么」

### P17 章节页 04
- type: section / role: transition / rhythm: transition
- layout: 同 P3
- description: 04 结果与反思 —— 端到端实测；局限；下一步

### P18 端到端实测：一个成功案例与一个失败案例
- type: content / role: hero / rhythm: peak / visual_role: evidence
- layout: 左右 6:4，左成功案例（书中覆盖度高）结构化摘录，右失败案例（语料无覆盖）+ 审计告警
- density: 字数约 320 / 图片 0 / 留白约 12%
- description: 成功：「rebase 与 merge 区别」→ 命中 p99/p100/p108/p495，输出分「本质区别 / 历史形态对比 / 关键约束」三段并带章节页码引用，同时正确指出 rebase 不可用于已推送提交。失败：「如何撤销已推送提交」→ 模型判定知识库无覆盖并说明最接近章节（p247 重写历史），但审计器抓到 --force、--hard 两个参数未在本轮原文出现 —— 说明审计器真的在工作
- anti_pattern: 禁止只放成功案例；失败案例不得淡化处理

### P19 局限与下一步
- type: content / role: supporting / rhythm: valley / visual_role: evidence
- layout: 左右两栏（已知局限 4 条 / 下一步 3 条），中间 1px 竖线
- density: 字数约 300 / 图片 0 / 留白约 18%
- description: 局限：①无自动评测集，效果靠人工判读，不能量化；②语料只覆盖 Git 2.x 早期，revert/force-with-lease 等未涵盖；③混合检索未融合（BM25 与向量各跑各的）；④切块按字数而非 token，长代码块仍可能超模型窗口。下一步：RRF 融合召回、建 30 题人工标注评测集、语料更新到 Pro Git 第 2 版最新修订
- anti_pattern: 禁止局限写成「仍有提升空间」这类空话，每条必须具体到机制

### P20 结束页
- type: ending / role: hero / rhythm: peak / visual_role: atmosphere
- layout: 居中「谢谢，请指正」+ 一行项目信息
- description: 结束页，含姓名学号
- anti_pattern: 禁止在内容页塞致谢；结束页禁止出现页脚与数据
