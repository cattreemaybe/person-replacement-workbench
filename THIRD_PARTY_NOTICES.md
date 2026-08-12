# 第三方软件与模型声明

本项目通过 `requirements.txt` 使用多个第三方 Python 包。每个包仍受其各自许可证约束；安装和再分发前请核对对应版本的许可证。

## MobileSAM

- 项目：<https://github.com/ChaoningZhang/MobileSAM>
- 用途：根据用户矩形框在本机细化人物轮廓。
- 许可证：Apache License 2.0。
- 模型权重：不随本仓库分发，由 `download_model.py` 从其官方仓库下载并进行 SHA-256 校验。

如果将本项目打包或重新分发，请同时履行 MobileSAM 及其上游组件要求的版权和归属义务。
