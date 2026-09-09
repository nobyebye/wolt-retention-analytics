# 验证记录

验证日期：2026-09-09。环境：Windows、Python 3.12、原生独立 MySQL 8.0.42。
依赖快照见 requirements-lock.txt。

| 验证项 | 结果 |
|---|---|
| 全量官方模拟数据导入和分析 | 成功，71,257 用户 / 288,569 合并事件 |
| SQL 数据质量闸门 | 7 项通过 |
| 单元与真实 MySQL 集成测试 | 13 passed，第二次验证耗时 1.51 秒 |
| 重跑幂等与失败回滚 | 手算 fixture 集成测试通过 |
| Streamlit AppTest | 看板加载、Retail store 切换、平台留存切换均无异常 |
| Docker Compose 配置校验 | `docker compose config --quiet` 通过 |
| Docker 容器实际启动 | 本机 Docker daemon 未启动，未验证 |
| 查询结果一致性 | 索引与扫描版本均返回 203 条匹配事件 |

## 性能实验

对 288,569 行 fact_purchase 执行同一用户及日期范围计数。每个版本预热 1 次，再测 7 次客户端墙钟时间。

| 执行方式 | 中位耗时 | EXPLAIN ANALYZE |
|---|---:|---|
| 忽略二级索引 | 40.603 ms | 全表扫描 288,569 行 |
| 使用 user/date/line 索引 | 0.347 ms | 覆盖索引范围扫描 203 行 |

这是刻意隔离索引效果的本机热缓存微基准；不代表原始应用曾经缺少索引，也不代表整体报表性能提升。
完整运行次数、执行计划见 [benchmark.json](benchmark.json)，数据哈希、质量结果和复购结果见 [run-summary.json](run-summary.json)。

## 复现

```powershell
$env:MYSQL_DATABASE="wolt_test"
$env:RUN_MYSQL_TESTS="1"
pytest -q
$env:MYSQL_DATABASE="wolt_analytics"
wolt-analytics run --download --observation-start 2020-04-21 --as-of 2020-10-31
wolt-analytics check
python scripts/benchmark.py
```

以上需先配置 MYSQL_HOST / PORT / USER / PASSWORD 和专用数据库。运行从仓库根目录发起。
