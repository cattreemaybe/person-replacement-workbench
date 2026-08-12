# 换影：本地人物替换工作台

一个在本机浏览器运行的人物替换工具：上传参考人物和场景图，在场景中框住要替换的人物，使用 MobileSAM 在本机识别人物轮廓，再通过兼容 OpenAI 图片编辑接口的服务生成结果。最终导出时，人物轮廓外的像素会由本地程序恢复为原图。

> 使用前请阅读[负责任使用说明](RESPONSIBLE_USE.md)。只处理你有权使用的图片，不要将生成结果用于冒充、欺诈或伪造事实证据。

## 功能

- 浏览器内上传、框选、遮罩预览和结果下载。
- MobileSAM 本地人物轮廓识别。
- 演示模式无需 API，也不会上传图片。
- 模型模式支持兼容 OpenAI `/images/edits` 的服务。
- 原图不会覆盖，结果另存到 `outputs/`。

## 环境要求

- Python 3.10 或更高版本；项目当前在 Python 3.12 上验证。
- 首次安装依赖和下载模型时需要网络。
- MobileSAM 模型约 39 MB；PyTorch 等依赖需要额外磁盘空间。

## 安装

```bash
git clone https://github.com/cattreemaybe/person-replacement-workbench.git
cd person-replacement-workbench
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python download_model.py
cp .env.example .env
```

编辑 `.env`：

```dotenv
OPENAI_COMPAT_BASE_URL=https://api.openai.com/v1
OPENAI_COMPAT_API_KEY=你的令牌
OPENAI_COMPAT_MODEL=gpt-image-2
```

如果只使用演示模式，可以不填写令牌。请根据你的服务商文档确认地址、模型名、计费和数据保留规则。

## 启动

macOS 可以双击 `start.command`，也可以运行：

```bash
.venv/bin/python server.py
```

浏览器通常会自动打开 <http://127.0.0.1:8765>。程序只监听本机地址，不要将端口直接暴露到公网。

## 使用

1. 上传想放进场景的参考人物。
2. 上传场景图。
3. 在场景中完整框住要替换的人物。
4. 检查 MobileSAM 生成的红色人物轮廓，必要时调整“轮廓扩缩”。
5. 选择模型模式或演示模式，然后开始替换。
6. 下载 PNG；结果也会保存到 `outputs/`。

## 隐私与费用

- 演示模式完全在本机运行。
- 模型模式会把场景局部、参考人物、遮罩和补充提示发送给你配置的服务商，并可能产生费用。
- `.env` 已被 Git 排除，后端不会把令牌返回给网页。
- 服务商必须返回 Base64 图片数据；为保护本机网络，程序不会下载服务商返回的任意图片 URL。

## 当前边界

- 矩形只用于指定人物，真正送入模型和最终合成的是人物轮廓遮罩。
- 头发、透明衣物、反射、阴影和复杂遮挡仍可能需要多次生成。
- 人物参考图与场景人物视角差异过大时，模型会推测不可见细节。
- 本项目是单用户本地工具，不具备公网多用户服务所需的认证、隔离和流量防护。

## 测试

```bash
.venv/bin/python -m unittest -v
```

测试只使用程序生成的合成图片，不调用付费接口。`live_smoke_test.py` 会调用真实服务并产生费用，请仅在明确需要时运行。

## 开源与贡献

本项目按 [Apache License 2.0](LICENSE) 发布，版权所有者为 `cattreemaybe`。第三方组件见[第三方声明](THIRD_PARTY_NOTICES.md)。

欢迎阅读[贡献指南](CONTRIBUTING.md)后提交 Issue 或 Pull Request。安全问题请按照[安全政策](SECURITY.md)私下报告；社区交流受[行为准则](CODE_OF_CONDUCT.md)约束。
