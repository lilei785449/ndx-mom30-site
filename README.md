# NDX / MOM30 Research Site

公开展示 NDX 与 MOM30 长期研究结果的独立仓库。

## 目标

- 将 NDX / MOM30 研究与其他研究项目彻底分离。
- 用 GitHub Pages 提供公开、稳定、可访问的研究页面。
- 页面只展示由研究管线真实生成的数据，不手工伪造或补齐研究结果。
- 为后续自动更新最新结果、历史序列与统计摘要预留固定数据接口。

## 当前状态

站点骨架已建立；研究数据接口已预留，真实 NDX / MOM30 输出尚未接入本仓库。

## 目录

```text
.
├── index.html
├── README.md
├── assets/
│   ├── app.js
│   └── style.css
├── data/
│   ├── ndx_mom30_latest.json
│   └── ndx_mom30_history.csv
└── .github/
    └── workflows/
        └── pages.yml
```

## 数据接口

### `data/ndx_mom30_latest.json`

用于页面顶部的最新状态与摘要。未接入真实研究结果前，字段保持 `null`，页面明确显示“等待研究管线输出”。

### `data/ndx_mom30_history.csv`

用于后续保存历史时间序列。当前只保留表头，不填充模拟数据。

## 发布

仓库使用 GitHub Pages + GitHub Actions 发布静态网站。Pages 发布源需要在仓库 Settings → Pages 中选择 **GitHub Actions**。

## 研究原则

本网站是研究展示层，不替代原始研究与验证流程。所有公开数值应来自可复现的研究管线；任何压力测试、未来函数检查、过度拟合检查或方法变更，都应先在研究层完成，再发布到这里。

## 免责声明

本项目仅用于研究与教育展示，不构成投资建议、交易建议或收益承诺。
