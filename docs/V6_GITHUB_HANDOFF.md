# V6 GitHub同步与待确认推送步骤

仓库https://github.com/Eli-Mao/baidumoufa，独立分支codex/v6-deep-optimization。原D:/SatelliteProject_GitHub存在显式Deny ACL及大量未提交修改，本轮只读核对，未修改权限、清理或覆盖工作区。全部新修改在安全独立克隆完成。

已通过Git OpenSSL后端读取并fetch远程：main=d4c9ccb0daeb0fc4401ff405d584bfc49a5f1db4，Iceswing与delivery/overhead-fix=677d7d93719c6676c799679e385e20ca6462b58c，楼心荡=9ac04628edfa7db2646dd61a518699a5fdc21d06。楼心荡的赛题二分支仅核对，没有自动合入。远程main相对公共祖先只移除旧delivery目录，本轮将该清理合入V6分支；相对当前main的PR不删除任何队友文件。旧代码仍在历史与Iceswing分支可恢复。

Schannel在当前沙箱报SEC_E_NO_CREDENTIALS；单次/本地Git设置http.sslBackend=openssl可正常访问，证书验证保持开启，没有sslVerify=false。Git Credential Manager2.9.1已安装，但沙箱没有可用的非交互GitHub令牌。匿名读取公共仓库成功不代表有写权限。当前账号写权限和远程推送均未验证，PR尚未创建。

维护提交身份已按用户授权设置Iceswing <755875603@qq.com>。这是Git作者信息，不等于已登录GitHub账号。其他组员应设置自己的作者身份，不应照抄冒用。

## 已完成、可供审阅的内容

- 完整历史bundle能恢复a40b3eb、V4/V5前置与稳定版提交。
- 冻结算法和评分代码不改变；新增便携入口、隔离环境/data准备、正式文档。
- accepted/v6包含派生计划、独立证书、小型统计/身份记录，无原始TLE、de421、venv、窗口缓存或密钥。
- docs/V6_PR_TITLE.txt、docs/V6_PR_BODY.md为本地PR草稿；没有调用远程创建接口。
- engineering/release_git.json记录稳定提交和最终fetch快照，provenance/remote_state.json记录读取状态。

## 仅在用户明确批准后执行

以下是可复制的Windows PowerShell命令。设备登录和push需要在有实际账户凭据的用户会话中执行，本轮未实测登录/推送。不要向聊天粘贴令牌，也不要把PAT写进命令历史或Git远程URL。

```powershell
Set-Location 'D:\Codex\2026-10-23\files-pasted-by-the-user-10000\work\v6_stable_project'
git status --short
git remote -v
git credential-manager github login --device
if ($LASTEXITCODE -ne 0) { throw 'GitHub login failed' }
git -c http.sslBackend=openssl fetch team
if ($LASTEXITCODE -ne 0) { throw 'fetch failed' }
git merge-base --is-ancestor team/main HEAD
if ($LASTEXITCODE -ne 0) { throw 'remote main changed; review and merge it in this independent clone before push' }
git log --oneline team/main..HEAD
git diff --stat team/main...HEAD
git -c http.sslBackend=openssl push --dry-run team codex/v6-deep-optimization
if ($LASTEXITCODE -ne 0) { throw 'dry run failed; preserve local branch, do not force push' }
git -c http.sslBackend=openssl push -u team codex/v6-deep-optimization
if ($LASTEXITCODE -ne 0) { throw 'push failed; do not claim success or use --force' }
git -c http.sslBackend=openssl ls-remote team refs/heads/codex/v6-deep-optimization
```

正常push会拒绝覆盖一个并非当前祖先的远程同名分支。如果提示non-fast-forward，先fetch、核对远程同名分支的作者和修改，停止推送并保留两份历史；不得force、reset队友提交。main的保护策略、账户角色和PR审核规则本轮未获登录权限，均待维护者核实。

推送成功且远程SHA与本地HEAD一致后，打开https://github.com/Eli-Mao/baidumoufa/compare/main...codex%2Fv6-deep-optimization?expand=1 ，选择base main，粘贴本地PR标题和正文。此链接是未来创建入口，不是已创建的PR。

本机未安装gh。若队员另有gh，可在确认push成功后使用以下**未实测**替代命令：

```powershell
gh pr create --draft --base main --head codex/v6-deep-optimization --title 'V6稳定版：真实10000目标验收成果与团队复现交付' --body-file docs/V6_PR_BODY.md
```
