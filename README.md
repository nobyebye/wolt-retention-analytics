# 用户留存与复购分析系统

**MySQL 8 · Python · Streamlit · Data quality · Cohort analysis**

A customer retention analytics system by nobyebye, covering data reconciliation, MySQL modeling, cohort metrics and interactive reporting.

面向餐饮与零售业务的个人数据分析项目，完成从 CSV 数据校验、对账、MySQL 建模到用户留存看板的完整流程，重点分析用户留存、30 天复购和跨业务线购买。

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

## 业务问题

1. 首购来自餐饮和零售的用户，后续月份的留存有什么差异？
2. 用户留在首购业务线，还是转向另一条业务线？
3. 完整观察 30 天的新用户中，有多少发生复购与跨线购买？
4. 数据缺失、未知用户和观察窗口会如何扭曲指标？

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
docs/                 指标口径、架构、分析结论、简历与面试材料
data/raw/             运行时下载，Git 忽略
artifacts/            运行结果和 CSV，Git 忽略
.github/workflows/    MySQL 集成测试 CI
```

## 工程范围

支持哈希溯源、原始 JSON 保存、隔离异常记录、批量导入、幂等全量刷新、并发互斥、质量闸门、失败回滚和 CSV 导出。
当前规模适合单机批处理，尚未实现实时 CDC、调度平台或多租户权限系统。
[架构与故障处理](docs/architecture.md) · [简历和面试说明](docs/resume-zh.md)

## 数据与许可

数据与题目来自 [woltapp/analytics-summer-intern-2022](https://github.com/woltapp/analytics-summer-intern-2022)。
源文件为人工合成数据，版权及使用条件归原作者；本库不重新分发原始 CSV。
MIT 许可仅适用于本项目原创代码和文档。Wolt 名称仅用于来源说明，不表示官方关联。
