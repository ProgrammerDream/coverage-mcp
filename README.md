# coverage-mcp

把 `tool/` 那套 Bash + 内嵌 Python 的 JaCoCo 分支覆盖率能力，抽成 **Python 全栈内核 + MCP server**，
定位「Java 分支级、按测试类、能指到未覆盖行的 agent 覆盖率反馈器」，填补现有 MCP
（test-coverage-mcp 只给%、se333 instruction/方法/全量）的精确缺口。

## 进度

- **M0 解析层** ✅ csv/xml/surefire + 未覆盖分支行，搬成可单测纯函数（对 optaplanner 真实报告快照锁定）。
- **M1 端到端** ✅ runner 复刻 maven 覆盖率链路；与 bash `run-module-test.sh` 对同一 case 逐字段一致（含未覆盖行）。
- **M2 MCP 壳** ✅ FastMCP 暴露 `coverage_check`，返回紧凑 JSON。
- **M3 按包自动收集 + JSON 瘦身** ✅ `--package fanya/schedule` 一条测整包；uncovered 的 file 相对模块路径省 token。
- M4 抽独立仓 + 编排迁 mvnw/just —— 后续。

## 结构

```
src/jacov/
  model.py    数据模型 + 阈值兼容（80 / 0.8）
  jacoco.py   解析 jacoco.csv / jacoco.xml / surefire（对齐 run-module-test.sh 三段）
  runner.py   复刻 maven 覆盖率链路（复用 tool/env.sh 的 Maven 环境）
  check.py    编排 + 人读输出 + 结构化组装（check_coverage / build_result）
  server.py   FastMCP server（coverage_check 工具）
tests/        14 个用例（解析层 11 + 组装层 3），fixture 取自 optaplanner 真实报告
```

## 跑测试

```bash
cd coverage-mcp
python -m pytest -q          # 免安装（pyproject 配 pythonpath=src）
```

## 命令行用（人类用法）

> 适用于 PowerShell / CMD / Git Bash。命令**一行写完**最省事，不要用 bash 的 `\` 换行。

### 第 0 步：装一次（只做一次）

```
pip install -e coverage-mcp
```

装完后 `python -m jacov.check` 在**任何目录**都能用——不用设 `PYTHONPATH`，也不用 `cd` 进 coverage-mcp。

### 最常用：测一个业务包（自动收集该包的测试类 + 业务类）

在项目根目录执行：

```
python -m jacov.check --module-dir fanyajwproject-course-v2\fanyajwproject-course-v2 --package fanya/schedule --min-branch 80
```

`--package fanya/schedule` 会自动找该包下所有 `*Test.java` 当测试、所有 `.java` 当业务类，不用手列一长串。

### 或者：手动指定测试类 / 业务类

```
python -m jacov.check --module-dir optaplanner-jxjy\optaplanner-jxjy --tests TeacherDayOfWeekParseStrategyTest --cover CommonMethods --min-branch 80
```

### 参数

| 参数 | 必填 | 含义 |
| --- | --- | --- |
| `--module-dir` | 是 | 模块目录（含 `pom.xml`）；相对当前目录或绝对路径都行 |
| `--package` | 与 `--tests` 二选一 | 业务包（如 `fanya/schedule`），自动收集测试类 + 业务类 |
| `--tests` | 与 `--package` 二选一 | 测试类，逗号分隔（如 `FooTest,BarTest`） |
| `--cover` | 否 | 卡覆盖率的业务类，逗号分隔；不填 = 整模块汇总 |
| `--min-branch` | 否 | 最低分支覆盖率，写 `80` 或 `0.8`；默认 0（只看不卡） |
| `--no-compile` | 否 | 跳过编译（代码已编译时更快） |
| `--no-reuse` | 否 | 每个测试类用独立 JVM（严格隔离，多测试类时慢） |

### 看懂输出

```
测试结果汇总     → 总数 / 通过 / 失败
分支覆盖率汇总   → 每个业务类 [PASS/FAIL] 分支总数 / 已覆盖 / 未覆盖 / 覆盖率
未完全覆盖分支   → 文件:行号 + MISS（全没覆盖）/ PARTIAL（只覆盖一半）+ 源码
```

退出码：全通过且达标 = `0`，否则 = `1`（可用于 CI / 脚本判断成败）。

### ⚠️ PowerShell 用户注意

- **别**抄 bash 写法：`PYTHONPATH=src python ...`（PS 不支持这种前缀赋值）和行尾 `\` 换行（PS 续行符是反引号 `` ` ``）——都会报 `Missing expression after unary operator '--'`。
- 装好包后**一行命令**最干净，什么前缀都不用加。

## 全量纯测试（像 Jenkins，不跑覆盖率）

只想跑测试看通过/失败、不要覆盖率（更快），用 `jacov.runtests`：

```
# 全量：模块下所有 *Test.java（相当于 mvn test）
python -m jacov.runtests --module-dir fanyajwproject-course-v2\fanyajwproject-course-v2

# 只测某个包 / 某几个类
python -m jacov.runtests --module-dir fanyajwproject-course-v2\fanyajwproject-course-v2 --package fanya/schedule
python -m jacov.runtests --module-dir fanyajwproject-course-v2\fanyajwproject-course-v2 --tests FooTest,BarTest
```

- 跑的过程**实时显示**编译（`Building`/`Compiling`）和每个测试类（`Running XxxTest` / `Tests run: N`），不会静默——能看到跑到哪、卡在哪。
- 结尾 Jenkins 式汇总：套件 / 用例 / 通过 / 失败 / 错误 / 跳过 + 失败套件清单；退出码 0（全过）/ 1（有失败）。
- ⚠️ 全量可能慢（course-v2 ~1900 用例、~3 分钟，大头是少数连外部/DB 的集成测试）；只验证某块用 `--package` 秒级。

## 性能与开关

覆盖率合并成**单条 maven 命令**（prepare-agent → 测试 → report），避免多次 JVM 冷启动；多测试类默认复用 fork JVM。

| 开关（CLI 反向） | 默认 | 说明 |
| --- | --- | --- |
| `compile_first`（`--no-compile`） | True | True 含增量编译（测最新代码）；False 用 `surefire:test` 跳过编译 |
| `reuse_forks`（`--no-reuse`） | True | True 多测试类复用同一 fork JVM（快 ~4x）；False 每类独立 JVM（严格隔离） |

实测 course-v2 schedule 包 21 测试：拆 3 次 maven + 独立 JVM 会超时 → 合并 1 条 + 复用 fork **12s**（覆盖率逐字段一致）。
若怀疑测试间静态状态污染导致覆盖率异常，用 `--no-reuse` 切独立 JVM 对照。

## 接入 Claude Code（MCP）

1. 装包：`pip install -e coverage-mcp`（带 mcp 依赖）。
2. 在项目 `.mcp.json` 的 `mcpServers` 里加一个 `jacov` 条目（command 用本机 python.exe 绝对路径，与装包的解释器一致；已有别的 server 就并列加）：
   ```json
   {
     "mcpServers": {
       "jacov": {
         "command": "<python.exe 绝对路径>",
         "args": ["-m", "jacov.server"]
       }
     }
   }
   ```
3. 重启 Claude Code（或 `/mcp` 重连）。之后可调 `coverage_check(module_dir, tests, cover, min_branch)`。

> 注：`coverage_check` 首次调用会真跑 maven（编译 + 测试 + JaCoCo），耗时分钟级。
> 返回紧凑 JSON：`status / tests / coverage / uncovered（行号+MISS·PARTIAL+源码） / reports`。
