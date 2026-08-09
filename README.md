# NDX-MOM30

公开、可复现的 Nasdaq-100 当前横截面动量榜单。

## 冻结规则

1. 使用 Nasdaq 官方 NDX 成分快照作为当前股票池。
2. 找到**当前这组成分股集合首次生效的交易日**。
3. 所有当前成分股统一使用该交易日的开盘价作为 0% 起点。
4. 每次更新计算：`最新收盘价 / 本轮统一起点开盘价 - 1`。
5. 按累计涨幅从高到低排序，输出前 30 名。
6. 只要 Nasdaq 官方成分集合变化，所有股票重新寻找新集合首次生效交易日并统一归零。
7. 不加入基本面，不调窗口，不根据榜单结果修改规则。

这是一套**当前实盘横截面筛选**，不是拿今天的 Nasdaq-100 成分股回填历史的回测。

## 自动更新

`.github/workflows/update-mom30.yml` 在美股工作日收盘后自动运行，也支持手动运行。

流程：

```text
Nasdaq 官方 NDX 成分快照
        ↓
识别当前成分集合及本轮统一起点
        ↓
yfinance adjusted OHLC
        ↓
计算本轮累计涨幅
        ↓
Top30 + 全部排名 + 每日摘要
        ↓
提交 data/ 结果
        ↓
GitHub Pages 自动重新部署
```

## 公开数据

- `data/ndx_mom30_latest.json`：网页读取的最新摘要与 Top30。
- `data/ndx_mom30_top30.csv`：当前 Top30 明细。
- `data/ndx_mom30_all.csv`：全部当前 NDX 成分排名。
- `data/ndx_mom30_history.csv`：每日摘要历史。
- `data/ndx_mom30_state.json`：当前成分集合与本轮统一起点，用于下一次更新续跑。

## 代码

- `scripts/update_mom30.py`：完整、可复现的 NDX-MOM30 v1.0 更新程序。
- `.github/workflows/update-mom30.yml`：每日排名更新。
- `.github/workflows/pages.yml`：GitHub Pages 部署。

## 网站

GitHub Pages 发布地址：

`https://lilei785449.github.io/ndx-mom30-site/`

## 数据边界

- 股票池：Nasdaq 官方 NDX 成分快照。
- 价格：yfinance，`auto_adjust=True`，用于当前榜单计算。
- 页面不会手工补造榜单或收益数据；更新失败时保留最近一次已成功发布的数据。

## 免责声明

本项目仅用于研究与教育展示，不构成投资建议、交易建议或收益承诺。
