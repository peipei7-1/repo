# 七七爱睡懒觉

![源图标](CydiaIcon.png)

iOS 越狱插件源(Sileo / Zebra 兼容),基于 GitHub Pages 托管。

## 源地址

```
https://peipei7-1.github.io/repo/
```

在 Sileo 中:**Sources** → **+** → 输入上面的地址 → Add Source。

## 工作原理

- `debs/` 存放编译好的 `.deb` 插件包
- 每次往 `debs/` 推送 `.deb`,GitHub Actions(`.github/workflows/gen.yml`)会自动运行 `gen_packages.py`
- 脚本解析每个 deb 的 control 信息,生成 `Packages`、`Packages.gz`、`Release` 索引
- GitHub Pages 对外提供这些文件,Sileo 即可识别并安装

## 发布新插件

1. 把 `.deb` 文件放进 `debs/`(建议短名,如 `com.example.tweak_1.0.deb`)
2. `git add debs/xxx.deb && git commit -m "add xxx" && git push`
3. CI 自动重建索引,等几十秒后 Sileo 刷新源即可看到

## 本地手动重建索引

环境只需 Python 3(纯标准库,无需 dpkg-deb):

```bash
python3 gen_packages.py
```

生成产物:
- `Packages` — 明文索引
- `Packages.gz` — 压缩索引(Sileo 下载这个)
- `Release` — 仓库元数据 + 校验和

## 说明

- 当前为**未签名**源,Sileo/Zebra 可直接添加;若需签名可后续补充 `Release.gpg`
- 支持架构:`iphoneos-arm64`(rootless)、`iphoneos-arm`(rootful)、`all`
- 索引中的 SHA256/MD5 会自动计算,无需手工填写
