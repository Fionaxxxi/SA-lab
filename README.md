# 公务员模拟面试语音作答分析

本项目实现考生端语音作答分析与反馈。考生在 Android 手机选题、录音作答，应用显示转写、参考要点覆盖和匹配证据。实验围绕两台 Android 手机与同一台 Windows 电脑，验证手机离线运行、端云计算切分和运行时调整。

当前进度为仓库骨架。S0 从固定音频、模型金样例和模块协议开始验证。可构建的 Android 工程、可运行的模型模块及服务入口分别在后续阶段交付。

| 目录 | 内容 | 技术责任区 |
| --- | --- | --- |
| `mobile/` | Android 应用、采集与展示、端侧推理、任务协调及网络 | Android、语音语义、端云执行分别负责对应模块 |
| `server/` | Python 局域网网关及 M1–M4 算法适配 | 网关由端云执行维护，算法由对应模块维护 |
| `contracts/` | 模块协议、执行计划和联调样例 | 提供方与调用方共同验收 |
| `planner/` | 成本表、最小割复算和枚举对照 | 端云执行与切分 |
| `models/` | 模型清单与下载位置说明 | 语音与语义 |
| `experiments/` | 样本清单、实验配置、统计脚本和结果索引 | 设备记录、统计结果和成本配置分别维护 |
| `docs/` | 架构视图、决策和演示材料 | 按模块分工共同维护 |

三人的第一批交接件是标准 WAV 与分段样例、同一输入的预期转写和匹配结果、可调用的服务回包与错误样例。使用同一个样本编号和版本记录联调。Windows 服务与实验脚本使用项目专用 Conda 环境，依赖版本通过 S0 验证后锁定。

首次提交前检查暂存清单。课程原件、内部实施计划、过程证据、模型权重、原始录音与本机凭据留在本地。复用代码纳入仓库前登记实际来源、版本、许可证和版权声明。

准备好空的 GitHub 仓库后，在项目根目录执行下面的命令。检查暂存清单后再提交。添加 origin 时，将占位文本换成仓库实际地址。

```powershell
git init -b main
git add -- .gitignore .gitattributes README.md THIRD_PARTY_NOTICES.md environment.yml mobile server contracts planner models experiments docs
git diff --cached --name-only
git commit -m "chore: scaffold interview feedback project"
git remote add origin '<GitHub 仓库 HTTPS 地址>'
git push -u origin main
```

已有历史的 GitHub 仓库需要先查看远端分支，再确定如何合并首次提交。
