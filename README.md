# 七七爱睡懒觉

iOS 越狱插件源(Sileo / Zebra 兼容),基于 GitHub Pages 托管。

![源图标](CydiaIcon.png)

## 源地址

```
https://peipei7-1.github.io/repo/
```

在 Sileo 中:**Sources** → **+** → 输入上面的地址 → Add Source。

- GitHub 仓库:`peipei7-1/repo`(public,main 分支,Pages 从根目录发布)
- 本地克隆目录:`/Users/77mac/WorkBuddy/2026-11-24-13-11-58/repo`
- gh 已登录:`peipei7-1`

## 目录结构

```
repo/
├── debs/            # 放 .deb 插件包(交付用短名:包名_版本.deb)
├── changelogs/      # <包名>.md 更新记录 → Sileo「更新记录」tab
├── descriptions/    # <包名>.md 详情文案 → gen_depictions.py 转成 JSON
├── depictions/      # <包名>.json Sileo 详情页(自动生成)
├── icons/           # <包名>.png 插件图标(可选)
├── tools/
│   └── push_via_api.py   # 443 不通时的备用推送脚本
├── gen_packages.py       # 生成 Packages / Packages.gz / Packages.bz2 / Release
├── gen_depictions.py     # 生成 depictions/*.json
├── .github/workflows/gen.yml  # 推 deb 后自动重建索引
├── CydiaIcon.png         # 源图标
└── index.html            # 源首页
```

## 发布新插件(标准流程)

设包名为 `com.77mac.demo`,版本 `1.0`。

### 1. 把 deb 放进 debs/

Theos `make package` 直出 `com.77mac.demo_1.0_iphoneos-arm64.deb`,交付/上源时**手动改成短名**:

```bash
cp /路径/com.77mac.demo_1.0_iphoneos-arm64.deb debs/com.77mac.demo_1.0.deb
```

> deb 文件名无强制规范——dpkg/Sileo 读包内 control 的 Package/Version,不读文件名。短名让 iOS「文件」App 能完整显示。

### 2. 写更新记录(可选但建议)

`changelogs/com.77mac.demo.md`,**新版本写在最上面**:

```markdown
### 1.0 · 2026-11-24

**一句话概括这一版。**

- **改了什么** — 用户能感知的行为
- **修了什么** — "原来是 X,现在改成 Y"
```

### 3. 写详情文案(可选但建议)

`descriptions/com.77mac.demo.md`,用 `##` 标题、`- **功能** — 说明`,段间用独占一行的 `---`。**不要用表格**(Sileo 渲染会散架)。

### 4. 放插件图标(可选)

`icons/com.77mac.demo.png` — 脚本会自动在 Packages 里加 `Icon:` 字段。

### 5. 本地生成 + 提交推送

```bash
python3 gen_depictions.py     # 生成 depictions/*.json
python3 gen_packages.py       # 生成 Packages / Packages.gz / Packages.bz2 / Release
git add -A
git commit -m "发布 demo 1.0"
git push
```

本地先跑脚本是为了 diff 干净、先看效果;即使不跑,CI 也会跑一遍。

### 6. 等 CI 重建索引(约 1 分钟)

```bash
gh run list --repo peipei7-1/repo --workflow gen.yml --limit 1
```

CI 会多一个 `repo-bot` 的 `chore: regenerate package indexes` 提交,正常现象。

### 7. 验证源已更新

```bash
curl -s https://peipei7-1.github.io/repo/Packages | grep -B2 -A2 "com.77mac.demo"
```

看到新版本号即成功。

## 如果 git push 卡住(github.com:443 不通)

本机常态直连是通的;若某天 443 超时,改用 Git Data API 重放(会照常触发 CI):

```bash
REMOTE=$(gh api repos/peipei7-1/repo/git/refs/heads/main --jq '.object.sha')
python3 tools/push_via_api.py "$REMOTE" "$(git rev-parse HEAD^)" "$(git rev-parse HEAD)" "$(git log -1 --format=%B)"
```

## 说明

- 未签名源,Sileo/Zebra 可直接添加;需签名时再补 `Release.gpg`
- 支持架构:`iphoneos-arm64`(rootless)、`iphoneos-arm`(rootful)、`all`
- 校验和(SHA256/MD5)自动生成,无需手填
- 旧版本 deb 可留在 `debs/`,脚本会全部索引,Sileo 默认装最新版
