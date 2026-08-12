# A股顶部风险看板：集中度增强版

在原网页看板外增加一层独立增强器，不修改原B/C评分：

- 确认门：B/C预警后最多等待10个A股交易日；40日C50升幅在此前252日的历史分位达到50%即确认，否则过滤。
- 20日补充：20日C50升幅在此前504日的历史分位达到90%，连续3个交易日确认；补充信号冷却45个交易日。
- 最终增强信号：确认后的B/C信号与20日集中度补充信号取并集。

当前网页B/C版本重新回测（不是此前31次基线）：40次成熟增强信号，29次命中，精确率72.5%；覆盖29/34个顶部，召回率85.3%，F1约78.4%。

## 自动更新

GitHub Actions 工作流 `update-a-share-monitor.yml` 在合并到默认分支后，每个交易日北京时间19:30运行：

1. 读取上游B/C `dashboard.json`；上游暂不可用时使用仓库缓存。
2. 下载通达信官方 `hsjday.zip`。
3. 重算沪深普通A股每日前50成交集中度、20/40日变化和历史分位。
4. 重算确认门、20日补充和增强回测。
5. 写入 `site/data/dashboard.json` 和 `site/data/concentration.csv`。
6. 上传完整站点Artifact，并提交数据更新。
7. 如仓库配置 `NETLIFY_AUTH_TOKEN` 与 `NETLIFY_SITE_ID`，自动发布到Netlify。

可选仓库变量 `UPSTREAM_DASHBOARD_URL` 可覆盖原B/C数据源地址。

## 部署方式

- GitHub Actions 每个交易日北京时间19:30刷新B/C上游快照和通达信C50数据。
- 若Netlify项目连接本仓库，数据提交后由 `netlify.toml` 自动重建静态壳并发布。
- 若使用手工Netlify部署，可在仓库Secrets中配置 `NETLIFY_AUTH_TOKEN` 与 `NETLIFY_SITE_ID`；不要把密钥写入代码。
- 当前原预览站点不在本对话已连接的Netlify账号中，因此首次切换到增强版需要一次站点连接/授权。

<!-- refresh: 2026-08-12 -->
