# 快照与实验清单

模块：`tidewatch/snapshot.py`。固定一次实验"用了哪份数据、做了哪些尝试"，让旧实验在补数或改参数之后仍能重读原输入、逐项对照。目录 `root` 由调用方传入（将来由 CLI 决定），快照在 `root/snapshots/`，清单在 `root/experiments/`。

状态：已实现（任务 snapshot）。

可复现与无未来信息是两项独立的验收：快照只回答"用的是哪份数据"，"当时能否使用"由 [time-conventions.md](time-conventions.md) 的时点约定和历史回放假设回答。ClickHouse 里的数据会被补数或重导覆盖，所以研究不直接以库为输入，而以快照为输入。

## 需求

### 快照按内容寻址且不可变

`save(frame, root)` 把 DataFrame 写成 parquet，文件名即快照 id，为文件字节的 sha256。写入先落同目录临时文件再原子改名，失败时目标与临时文件都不留下。同名文件已存在时不覆盖，但先校验其哈希，不一致报 `ValueError`，不把坏文件当作保存成功。数据有任何变化（例如补数）都得到新 id，旧快照不受影响。读回后的列类型（包括 UTC 时区）与写入前一致。

- 场景：同一份数据保存两次得到同一 id、不新增文件；改一个价格得到新 id，旧 id 仍读回原数据。
- 场景：同名文件已被篡改时 `save` 报错且不改写；改名一步失败时目录里什么都不留。
- 测试：`test_snapshot_round_trips_and_is_content_addressed`、`test_existing_snapshot_is_not_overwritten_and_is_verified`、`test_failed_write_leaves_nothing_behind`

### 读取时校验哈希

`load(snapshot_id, root)` 重新计算文件 sha256，与 id 不一致时报 `ValueError`，文件不存在时报 `FileNotFoundError`，不返回可疑数据。id 必须是 64 位小写十六进制，否则报 `ValueError`，这也挡住了路径穿越。

- 场景：文件末尾多一个字节、id 为 `../x`、大写或截短时报错。
- 测试：`test_snapshot_load_rejects_tampered_missing_or_bad_id`

### 实验清单记录全部尝试且不可变

`record_experiment(manifest, root)` 登记一份实验清单，返回清单 id（规范化 JSON 的 sha256，键顺序无关）。清单必须包含：

- `snapshot`：输入快照 id，快照必须存在且哈希完好；
- `definition`：因子或规则定义（代码版本、参数、预热、缺失规则）；
- `time_policy`：时间策略，如 `lag`；
- `execution`：成交假设，如费率与滑点；
- `trials`：全部尝试过的参数或候选，包括落选的，非空列表。只留胜出者会掩盖选择偏差，留痕本身不消除偏差，但让偏差可以被检查。

缺字段、`trials` 为空或不是列表、值里有 NaN 或无穷大（不是标准 JSON）、快照已损坏时报 `ValueError`，快照不存在时报 `FileNotFoundError`。同一清单重复登记得到同一 id；修订任一字段（换快照或改费用）得到新 id，旧清单不变。`load_experiment` 读取时同样校验哈希。

- 场景：E1 用快照 S1；补数得到 S2，只换输入得到 E2；只改费用得到 E3。三者 id 互不相同，E1 读回原样。
- 场景：清单含 NaN 时报错；清单文件被改动后读取报错；引用坏快照时报错。
- 测试：`test_experiment_manifest_is_immutable_and_revisions_get_new_ids`、`test_experiment_manifest_rejects_incomplete_input`

## 已知限制

- 快照 id 依赖 parquet 字节：同样的数据由不同版本的 polars 写出可能得到不同 id。这只会多出一份快照，不会让两份不同的数据共用一个 id。
- 清单按 JSON 语义取 id：`5` 与 `5.0` 得到不同 id；tuple 读回变成 list；非字符串键被转成字符串，混合类型键、日期等不可序列化的值报 `TypeError`。调用方用基本类型写清单即可避免。
- 清单字段的取值是任意 JSON，结构（例如 `definition` 必须带哪些键）由因子评测和回测任务约定。
- 并发写同一 id 时，后写者可能用相同字节替换先写者的文件，内容相同，结果无害。
- 不做清理：快照只增不删，需要回收空间时人工处理。
