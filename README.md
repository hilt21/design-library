# Design Library

维护图片、PPT、Three.js、网页和内容创作的方法包。内容与资源存放在本库，消费项目的渠道和阶段选择配置存放在 project-router。

| 条目 | 当前方法范围 | 来源关系 |
| --- | --- | --- |
| [单色编辑海报](entries/mono-color-editorial/SKILL.md) | 配方选择、原始设计词典、提示词、正反例与验收 | adapted |
| [技术演示稿](entries/technical-deck-design/SKILL.md) | 逐页论点、视觉表达和可编辑对象规格 | reference |
| [Three.js 参考图建模](entries/threejs-reference-rebuild/SKILL.md) | 几何、枢轴和运动约束的设计规格 | reference |
| [网页设计评审](entries/web-design-review/INSTRUCTIONS.md) | 基于桌面和移动截图的问题清单 | reference |
| [渠道成稿审校](entries/channel-draft-review/INSTRUCTIONS.md) | 最小编辑、事实与语气保留 | reference |

adapted 表示保留上游具体数据并记录适配。reference 表示根据上游思路自行编写，范围以本地入口为准。宿主运行能力通过实际验收确认。

## 维护条目

[catalog.json](catalog.json) 声明唯一 ID、输入输出、领域、阶段、别名、能力、必须读取的文件和按需资源。每个条目记录完整上游提交、来源关系、保留/修改/省略项和受影响的验收用例。导出器检查路径、文件完整性、别名冲突和导入数据摘要。JSON 词典与参考文件可以存入子目录。

[exports/index.json](exports/index.json) 只提供检索摘要，每个条目的完整清单位于 exports/entries。生成文件通过下列命令维护。

```sh
python tools/export.py --write
python tools/export.py --check
python -m unittest discover -s tests -v
```

CI 只在方法、工具、测试或导出文件变更时运行，不上传构建产物。Git 记录每次适配与来源变更。

## 同步到消费仓库

project-router 的 registry/design-library.json 声明项目、允许阶段、候选 ID、显式默认项和支持的组合。从本库干净的已发布源提交运行维护命令。

```sh
python tools/export.py --sync-router ../project-router --source-sha FULL_DESIGN_LIBRARY_SHA
```

维护命令使用 POSIX 文件锁串行写入。先检查目标是否存在未处理的本地修改，再构建不可变快照，校验所有文件，最后原子替换活动索引。失败时原活动快照继续可用。重试可复用已完成快照。回滚可重新选择旧源提交并执行相同命令。同步保留旧快照，清理时只能删除未被当前指针引用且已由 Git 保存的快照。

同步完成后审阅消费仓库差异，更新其技能锁，运行完整校验并提交候选 PR。运行中的任务按原 router SHA 继续读取。

## 上游更新检查

使用已有 source.commit 为基线，比较本地上游 checkout 中的候选 ref。先通过现有 GitHub 连接器或 git fetch 取得提交，检查命令只读。

```sh
python -m tools.check_upstream --entry mono-color-editorial --checkout ../mono-color-skill --ref CANDIDATE_SHA
```

输出命中文件的变化、基线/候选提交与受影响的用例。变更通过条目适配和回归后再更新 source.commit。采集失败时命令失败，不更改当前版本。

## 验收证据

[两组独立代理的对照产物与复核](evals/agent-comparison/README.md) 已保存，实际图片和其他三类产物保留待验状态。

## 许可

自有代码和文字采用 [MIT](LICENSE)。单色海报包内的原始设计数据遵循 [Yan Liu 的 MIT 许可](entries/mono-color-editorial/references/UPSTREAM-LICENSE.txt)。原作者图像通过来源链接查阅。导入文件及其摘要见 catalog.json。
