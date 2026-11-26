# NSHST

独立分支，仅包含 NSHST 的只读探针。

- 面板：`https://dash.nshst.com/`
- API 凭据：GitHub Actions Secret `NSHST_API_KEY`；不要提交到公开仓库。
- `nshst_probe.py`：列出名下服务器，并通过 `/api/client/servers/{id}/resources` 核对运行状态；不启动、不停止、不续期。
- 当前凭据可访问 `/api/client`；`/api/application/servers` 返回 403，不代表客户端 API 不可用。
- 当前未找到并验证续期接口；没有部署续期或启动任务。

运行：

```bash
python nshst_probe.py
```

设置环境变量 `NSHST_API_KEY` 后运行。工作流在 main：`.github/workflows/nshst_probe.yml`，仅手动触发。


## 续期与启动

用户要求仅在续期成功并核实后检查、必要时启动，不设置独立定时启动检查。
官方 FAQ 表示免费计划至少每 7 天登录面板，忘记后有 72 小时缓冲；当前 API 未提供到期信息，API 调用是否算作面板登录未验证。
自动续期尚未实现；请定期手动登录面板，直到验证可用的续期方式。
