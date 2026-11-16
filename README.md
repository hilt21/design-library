# Design Library

为图片、PPT、Three.js、网页设计和内容创作维护可复用的设计方法。用 Git 提交固定版本。每个主条目有来源、适用阶段和明确的输出。

| 条目 | 用途 | 接入范围 |
| --- | --- | --- |
| [单色编辑海报](entries/mono-color-editorial/SKILL.md) | 视觉配方、提示词和验收 | content-studio 候选 |
| [技术演示稿](entries/technical-deck-design/SKILL.md) | 逐页论点、表达形式与可编辑对象 | 设计库 |
| [Three.js 参考图建模](entries/threejs-reference-rebuild/SKILL.md) | 程序化建模与几何、运动核验 | 设计库 |
| [网页设计评审](entries/web-design-review/INSTRUCTIONS.md) | 基于桌面和移动截图的可定位问题清单 | 设计库 |
| [渠道成稿审校](entries/channel-draft-review/INSTRUCTIONS.md) | 最小改动，保留事实与作者语气 | content-studio 候选 |

[catalog.json](catalog.json) 是人工维护的目录，包含上游仓库、固定提交、入口和许可。Kami、Anatomy 和 Taste Skill 作为参考登记。条目内的文字是为本库编写的适配方法。上游图片和脚本通过来源查阅。

## 维护

新增条目时为它分配唯一 ID，在 `entries/<id>/` 写入口和本条目所需的叶文件，再登记适用阶段、别名和来源。声明 `content-studio` 将条目标记为此次同步目标。视觉、校稿和首次接入分别保留真实验收结果。

```sh
python tools/export.py --write
python tools/export.py --check
python -m unittest discover -s tests -v
```

[exports/index.json](exports/index.json) 是生成文件。校验检查 ID、别名冲突、未声明或缺失的文件、自引用和文件摘要。当前依赖只支持条目目录内的叶文件。

## 同步到 project-router

在新发布的设计库提交上建立干净的 checkout。在 `project-router` 的候选分支执行同步，再审阅差异、更新现有锁文件并跑该仓库的测试。

```sh
python tools/export.py --sync-router ../project-router --source-sha FULL_DESIGN_LIBRARY_SHA
```

同步只复制明确绑定到 `content-studio` 的材料。同步文件由 Git 跟踪。该命令不发布或晋升路由快照。下一次更新通过 Git 提交修改目录和文件，重新生成、校验和同步。

## 许可

本库自有代码和文字采用 [MIT](LICENSE)。目录中的许可证字段记录对应上游来源。
