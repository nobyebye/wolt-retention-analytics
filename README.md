# Wolt 用户留存与复购分析系统

**MySQL 8 · Python · Streamlit · Data quality · Cohort analysis**

A customer retention analytics system for the Wolt restaurant and retail business scenario, covering data reconciliation, cohort metrics and repeat-purchase reporting.

以芬兰创立的 Wolt 公司餐饮与零售业务场景为背景，解决首购与购买数据难以对账、留存指标口径不统一，以及复购和跨业务线购买缺少统一分析视图的问题。项目通过 Python 数据处理、MySQL 分层建模和交互看板，建立可重复运行的用户行为分析流程。

初次了解项目，先读 [中文项目讲解](docs/walkthrough.md)，再看 [业务问题与方案](docs/project-overview.md)。

## 已验证结果

| 项目 | 当前公开数据快照 |
|---|---:|
| 首购记录 / 用户 | 71,257 |
| 购买文件记录 | 227,457 |
| 合并、对账后购买事件（含首购） | 288,569 |
| 未知首购用户的隔离事件 | 10,145 |
| 隔离事件涉及用户 | 3,311 |
| MySQL 数据质量检查 | 7 项 |

13 项单元及 MySQL 集成测试已在 MySQL 8.0.42 上通过；Streamlit 加载和两种业务线/指标筛选已实测。
完整运行记录见 [验证记录](docs/validation.md)，结果与边界见 [分析报告](docs/analysis-report.md)。

## 解决的问题

| 问题 | 解决方式 | 项目结果 |
|---|---|---|
| 首购与购买记录无法直接对账 | 建立首购锚点，核对用户及订单关系，隔离无法归属的记录 | 隔离 10,145 条记录，形成可追溯的数据集 |
| 不同业务线的留存缺少统一口径 | 按首购月份与业务线建立同期群，区分平台留存和同业务线留存 | 支持餐饮、零售用户留存对比 |
| 观察时间不足容易造成指标偏差 | 完整月份才计算月度留存，满 30 天观察期才纳入复购分母 | 区分未观察到与真实零返回 |
| 复购及交叉购买缺少统一视图 | 汇总 30 天复购与跨线购买，提供筛选看板和 CSV 导出 | 可比较用户回访和跨业务线购买行为 |
| 重复执行及中途失败影响数据可靠性 | 事务刷新、并发互斥、质量检查和自动测试 | 可重复执行，失败时保留上次数据库快照 |

完整背景与实现见 [项目说明](docs/project-overview.md)。

具体口径见 [metric-contract.md](docs/metric-contract.md)。没有金额、成本或实验数据，不计算收入、利润或因果提升。

## 快速启动：Docker Compose

前提：Git、Docker Engine / Docker Desktop（Linux containers）和 Compose v2，能访问 GitHub 原始文件。

```bash
git clone https://github.com/nobyebye/wolt-retention-analytics.git
cd wolt-retention-analytics
docker compose up -d mysql
docker compose run --rm pipeline
docker compose up -d dashboard
```

打开 http://localhost:8501 。首次构建会安装依赖，首次运行会下载两份 CSV。
示例密码仅用于绑定 127.0.0.1 的本地演示；可以复制 `.env.example` 为 `.env` 后修改，Compose 会自动读取。
重复执行 `docker compose run --rm pipeline` 会以事务刷新同一快照，不追加重复事实记录。
停止：`docker compose stop`，数据卷保留。

Docker 配置已提供；当前开发机使用原生 MySQL 验证，未在本机实际运行 Docker 容器。

## 本地 Python + MySQL

前提：Python 3.11+、MySQL 8.0.42（或兼容 MySQL 8），新建专用数据库与有该库读写权限的用户。

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-lock.txt
pip install --no-deps -e .
```

PowerShell 配置（按实际连接修改；Python 不自动读取 .env）：

```powershell
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_PORT="3307"
$env:MYSQL_DATABASE="wolt_analytics"
$env:MYSQL_USER="wolt"
$env:MYSQL_PASSWORD="local-demo-only"
wolt-analytics run --download --observation-start 2020-04-21 --as-of 2020-10-31
wolt-analytics check
streamlit run dashboard/app.py
```

macOS/Linux 用 `export MYSQL_PORT=3307` 等方式设置同名环境变量，再运行相同命令。
如果手动下载了 CSV 放在 data/raw，去掉 `--download`；命令应在仓库根目录执行。

## 测试与性能复现

```bash
pytest -q
```

默认运行单元测试，MySQL 集成测试跳过。创建独立 `wolt_test` 库并授权后：

```powershell
$env:MYSQL_DATABASE="wolt_test"
$env:RUN_MYSQL_TESTS="1"
pytest -q
$env:MYSQL_DATABASE="wolt_analytics"
python scripts/benchmark.py
```

集成测试会刷新专用测试库表，只接受 `_test` 结尾的数据库名。GitHub Actions 使用容器 MySQL 和小规模手算 fixture。
性能脚本对同一用户/日期查询比较扫描与复合索引，核对结果相同，输出 7 次计时与 EXPLAIN ANALYZE；结果只代表该机器、数据规模和缓存条件。

## 仓库结构

```text
src/wolt_analytics/    CSV 契约、对账、参数化导入、事务与日志
sql/                  MySQL 表结构、留存/复购/事件汇总模型
dashboard/            Streamlit 只读交互看板
tests/                单元测试、真实 MySQL 业务边界测试
scripts/              可重复查询性能实验
docs/                 业务背景、问题与方案、指标口径、架构及分析结论
data/raw/             运行时下载，Git 忽略
artifacts/            运行结果和 CSV，Git 忽略
.github/workflows/    MySQL 集成测试 CI
```

## 工程范围

支持哈希溯源、原始 JSON 保存、隔离异常记录、批量导入、幂等全量刷新、并发互斥、质量闸门、失败回滚和 CSV 导出。
当前规模适合单机批处理，尚未实现实时 CDC、调度平台或多租户权限系统。
[架构与故障处理](docs/architecture.md) · [项目说明](docs/project-overview.md)

## 数据与许可

数据与题目来自 [woltapp/analytics-summer-intern-2022](https://github.com/woltapp/analytics-summer-intern-2022)。
源文件为人工合成数据；本库不重新分发原始 CSV。
MIT 许可仅适用于本项目原创代码和文档。Wolt 名称仅用于来源说明，不表示官方关联。
