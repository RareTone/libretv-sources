# LibreTV Sources

使用 GitHub Pages 托管两份 LibreTV-SourceList v2 JSON 订阅。无需前端、Node.js 构建或额外服务器。

## 订阅地址

以下是 `RareTone/libretv-sources` 的预定 Pages 地址；首次发布需在 Actions 中确认 **Deploy GitHub Pages** 成功后使用。

| 文件 | HTTPS 订阅地址 | 初始点播源数量 | 用途 |
| --- | --- | ---: | --- |
| `sources/stable.json` | <https://raretone.github.io/libretv-sources/sources/stable.json> | 5 | 原始配置中标记启用的源，日常订阅优先选择 |
| `sources/all.json` | <https://raretone.github.io/libretv-sources/sources/all.json> | 37 | 全部去重源，用于自行筛选与测试 |

两份配置的 `liveSources` 均为 `[]`。上述数量是初始导入数量，后续以 JSON 和 Actions 校验输出为准。

`stable` 仅指原配置启用的子集，不代表已验证可播放；`all` 包含该子集，通常选择一个地址即可。订阅 `all` 后，LibreTV 会按自己的规则启用导入的源，原配置中未启用的状态没有保存在这份 SourceList 中。

初始文件分别来自 `LibreTV_启用源_5条.json` 和 `LibreTV_全部源_去重.json`，内容原样保留。原文件已符合格式且没有重复 URL，因此无需删除字段或重写地址。两份文件中的列表名称、源名称、URL 和 `isAdult` 均沿用原值。没有依据源名称重新推断成人内容标记。

## LibreTV v2.21.1 导入与同步

1. 打开自己部署的 LibreTV 并登录。
2. 进入 **设置 → 源管理 → 数据源订阅**。
3. 粘贴上表中的完整 HTTPS 地址，点击 **订阅**。日常使用可先选择 `stable.json`。
4. 查看订阅条目的点播数量。远端更新后，点击该条目的 **⟳** 手动同步。
5. 需要自动刷新时，在该订阅的周期下拉框选择天数。v2.21.1 默认关闭自动刷新；设置后，打开站点时才会检查是否到期。

同步以远端列表为准：在 LibreTV 内单独编辑或删除订阅源可能被下一次同步覆盖；长期调整应修改本仓库的 JSON。

此处填写的是直接返回 JSON 的 Pages 地址。不要填写 GitHub 的 `blob/main/...` 文件浏览页面，也不要从完整设置备份入口导入。订阅由 LibreTV 服务端拉取，无需额外配置 CORS。操作与格式依据：[LibreTV v2.21.1 官方说明](https://github.com/LibreSpark/LibreTV/blob/v2.21.1/README.md#数据源订阅--分享)。

## 修改源

- **添加**：在 `sources` 数组追加对象，至少包含非空的 `name` 和 HTTP/HTTPS `url`；可选字段为布尔值 `isAdult`、HTTP/HTTPS 详情页根地址 `detail`。
- **删除**：移除对应对象并检查 JSON 逗号。
- **更新**：修改相应字段，保留真实 API 路径；不要仅为了校验通过而替换接口。
- **维护启用子集**：若希望某源同时存在于 `stable` 和 `all`，两份文件都需要修改；它们不会自动相互生成。
- 顶层保留 `name`、整数 `version: 2`、数组 `sources` 和数组 `liveSources`。不要混入完整设置、TVBOX、`enabled` 或自定义请求头等字段。
- 若以后增加直播源，`liveSources` 的每项使用 `name`、`url`，可选 HTTP/HTTPS `epg`。

每个文件的点播源和直播源分别按 URL 检查重复。比较时忽略主机名大小写、默认端口和末尾斜杠，但校验器不会修改文件；路径与查询参数仍区分不同接口。两份订阅之间允许重叠。点播最多 100 条、直播最多 50 条，防止 LibreTV 静默截断。

在仓库根目录使用 Python 3.12 或以上版本执行（只用标准库，无需安装依赖）：

```powershell
python scripts/validate.py
python -m unittest discover -s tests -p test_validate.py -v
git diff --check
git add sources/stable.json sources/all.json
git commit -m "chore(sources): 更新订阅源并通过格式校验"
git push origin main
```

如果 Windows 的 Python 未加入 PATH，可将 `python` 替换为 `py -3.12`，或用 `& '实际的python.exe完整路径'` 调用。

也可直接在 GitHub 网页编辑 JSON 并提交。Actions 会自动校验并部署；校验失败时停止本次部署，已发布版本保持不变。修正后重新提交即可；回滚可在 GitHub 撤销相应提交或本地 `git revert <提交SHA>` 后推送。Pages 更新和客户端缓存可能存在短暂延迟，部署成功后再同步订阅。

## 自动校验与 Pages

- `scripts/validate.py`：严格解析 JSON，拒绝重复对象键、NaN/Infinity、错误字段类型、不兼容字段、非 HTTP(S) 地址和重复 URL；输出两份文件各自的点播/直播数量。
- 校验器还拒绝明显凭证、带账号密码的 URL、敏感查询参数、内网/保留 IP 和本地主机名；不会执行 DNS 查询，不能代替人工审查共享权限或检查任意形式的秘密。
- `tests/test_validate.py`：覆盖有效配置、错误结构、重复 URL、兼容字段、数量限制、敏感地址和命令行失败退出码。
- `validate.yml`：每次 push、Pull Request 自动校验，也可被部署工作流复用。
- `pages.yml`：仅 `main` push 或在 `main` 手动触发时部署；通过 `needs: validate` 等待同一提交校验成功，再将两份 JSON 复制到 `_site/sources/` 并发布。

Pages 的网站产物仅含两份 JSON；公开 GitHub 仓库中的 README、脚本和测试同样公开可读。接口探测不作为 CI 门槛，临时网络故障不应阻断配置发布。JSON 格式正确、HTTP 返回成功，均不等于影片可搜索或可播放。

首次发布时，仓库管理员需创建公开仓库并推送 `main`，在 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。若首次运行早于 Pages 启用，可在 Actions 手动运行 **Deploy GitHub Pages**。工作流使用 GitHub 自动提供的令牌及 `pages: write`、`id-token: write` 权限，无需保存个人 Token。参考：[GitHub Pages 自定义工作流文档](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)。

## 公开共享检查

提交前确认源配置允许公开共享，不包含密码、Token、Cookie、私有地址或个人信息。初始静态检查未发现这些内容，但源文件没有附带分发授权说明，公开分享权限应由提供者确认。不要提交本机完整设置备份、网络配置或凭证。此仓库只托管配置，不托管影视文件。
